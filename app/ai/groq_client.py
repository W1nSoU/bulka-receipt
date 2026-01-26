from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from groq import AsyncGroq
from groq import (
    RateLimitError,
    APIError,
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
)

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class ReceiptResult:
    shop: Optional[str]
    amount: Optional[float]
    date: Optional[str]
    time: Optional[str]
    check_code: Optional[str]
    address: Optional[str]
    is_valid: bool
    errors: List[str]
    raw_text: str


class ReceiptAnalysisError(Exception):
    """Base error for receipt analysis via Groq."""


class ReceiptParseError(ReceiptAnalysisError):
    """Raised when Groq returns a response that cannot be parsed."""


class CircularKeyRotator:
    """
    Кругова ротація API ключів з автоматичним fallback.
    Якщо один ключ не працює - пробує наступний, і так по колу.
    """
    
    def __init__(self, api_keys: List[str]):
        if not api_keys:
            raise ValueError("No Groq API keys provided")
        
        self.api_keys = api_keys
        self.current_index = 0
        self.clients = {key: AsyncGroq(api_key=key) for key in api_keys}
        
        logger.info(f"🔑 Initialized Groq with {len(api_keys)} API key(s)")
    
    def get_current_client(self) -> tuple[AsyncGroq, str]:
        """Отримує поточний клієнт і ключ"""
        current_key = self.api_keys[self.current_index]
        return self.clients[current_key], current_key
    
    def rotate_to_next(self) -> str:
        """
        Переключається на наступний ключ (по колу).
        Повертає новий ключ.
        """
        old_index = self.current_index
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        
        old_key = self.api_keys[old_index]
        new_key = self.api_keys[self.current_index]
        
        logger.info(
            f"🔄 Rotated from key #{old_index + 1} ({old_key[:12]}...) "
            f"to key #{self.current_index + 1} ({new_key[:12]}...)"
        )
        
        return new_key
    
    async def call_with_circular_retry(
        self, 
        func, 
        max_attempts: Optional[int] = None
    ):
        """
        Викликає функцію з автоматичною круговою ротацією.
        
        Args:
            func: Async функція, яка приймає AsyncGroq клієнт
            max_attempts: Максимум спроб (за замовчуванням = кількість ключів)
        
        Raises:
            ReceiptAnalysisError: Якщо всі ключі не спрацювали
        """
        if max_attempts is None:
            max_attempts = len(self.api_keys)
        
        errors = []
        start_index = self.current_index
        
        for attempt in range(max_attempts):
            client, current_key = self.get_current_client()
            key_num = self.current_index + 1
            
            try:
                logger.info(f"🔍 Attempt {attempt + 1}/{max_attempts} with key #{key_num}")
                result = await func(client)
                
                logger.info(f"✅ Success with key #{key_num}")
                return result
                
            except RateLimitError as e:
                msg = f"Key #{key_num}: Rate limit exceeded"
                logger.warning(f"⚠️ {msg}")
                errors.append(msg)
                
                # Якщо є інші ключі - переключаємось
                if len(self.api_keys) > 1:
                    self.rotate_to_next()
                    await asyncio.sleep(0.5)
                else:
                    # Тільки один ключ - чекаємо довше
                    wait_time = min(30, 2 ** attempt)
                    logger.warning(f"⏳ Single key, waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
            
            except (APIConnectionError, APITimeoutError) as e:
                msg = f"Key #{key_num}: Connection/Timeout error - {str(e)[:100]}"
                logger.warning(f"⚠️ {msg}")
                errors.append(msg)
                
                # Переключаємось на наступний ключ
                if len(self.api_keys) > 1:
                    self.rotate_to_next()
                await asyncio.sleep(1)
            
            except BadRequestError as e:
                # Помилка в запиті - не retry
                msg = f"Key #{key_num}: Bad request - {str(e)[:200]}"
                logger.error(f"❌ {msg}")
                raise ReceiptAnalysisError(
                    "Помилка обробки зображення. Переконайтесь, що фото чека коректне."
                ) from e
            
            except APIError as e:
                msg = f"Key #{key_num}: API error - {str(e)[:100]}"
                logger.error(f"❌ {msg}")
                errors.append(msg)
                
                # Якщо це не остання спроба - пробуємо інший ключ
                if attempt < max_attempts - 1 and len(self.api_keys) > 1:
                    self.rotate_to_next()
                    await asyncio.sleep(1)
            
            except Exception as e:
                msg = f"Key #{key_num}: Unexpected error - {str(e)[:100]}"
                logger.exception(f"💥 {msg}")
                errors.append(msg)
                
                if attempt < max_attempts - 1 and len(self.api_keys) > 1:
                    self.rotate_to_next()
                    await asyncio.sleep(1)
            
            # Якщо зробили повний круг і повернулись до початкового ключа
            if self.current_index == start_index and attempt > 0:
                logger.warning(f"🔁 Completed full rotation, tried all {len(self.api_keys)} key(s)")
        
        # Всі спроби провалились
        error_summary = "\n".join(f"  - {e}" for e in errors[-3:])  # Останні 3 помилки
        raise ReceiptAnalysisError(
            f"Не вдалося обробити чек після {max_attempts} спроб.\n"
            f"Спробуйте пізніше або надішліть краще фото."
        )


# Глобальний ротатор (створюється один раз)
_rotator: Optional[CircularKeyRotator] = None
_rotator_lock = asyncio.Lock()


async def _get_rotator() -> CircularKeyRotator:
    """Отримує або створює глобальний ротатор (thread-safe)"""
    global _rotator
    
    if _rotator is None:
        async with _rotator_lock:
            if _rotator is None:  # Double-check
                settings = Settings.load()
                if not settings.groq_api_keys:
                    raise ReceiptAnalysisError("GROQ_API_KEYS not configured in .env")
                _rotator = CircularKeyRotator(settings.groq_api_keys)
    
    return _rotator


def _build_prompt(rules: Dict[str, Any]) -> str:
    """Створює оптимізований промпт для Groq Vision"""
    
    allowed_shops = rules.get("allowed_shops", [])
    min_amount = rules.get("min_amount", 0)
    start_date = rules.get("start_date", "")
    end_date = rules.get("end_date", "")
    
    shops_str = ", ".join(allowed_shops[:5]) if allowed_shops else "будь-який"
    
    return f"""Ти система розпізнавання УКРАЇНСЬКИХ чеків. Витягни ВСІ поля з чека.

ВАЖЛИВО: Весь текст на чеках — ВИКЛЮЧНО УКРАЇНСЬКОЮ мовою. 
Українська абетка має унікальні літери: Є, І, Ї, Ґ (не плутай з російськими Э, И, Ы, Г).

УКРАЇНСЬКА ОРФОГРАФІЯ:
- "Є" на початку слів: Єрмак, Євген, Євгенія, Єлизавета, Європа (НЕ "Ермак")
- "і" замість російської "и": Наталія, Марія, Ірина, Віталій, Олексій
- "ї" де потрібно: Олександрівна, Київ, їжа
- Прізвища: Єрмак, Шевченко, Коваленко, Бондаренко

ФОРМАТ ВІДПОВІДІ (тільки JSON, без markdown):
{{
  "shop": "точна назва магазину або null",
  "address": "адреса магазину (місто, вулиця) або null",
  "amount": 123.45 або null,
  "date": "YYYY-MM-DD або null",
  "time": "HH:MM або null",
  "check_code": "фіскальний номер/код чека або null",
  "raw_text": "весь видимий текст з чека"
}}

ПРАВИЛА АКЦІЇ (контекст):
- Дозволені магазини: {shops_str}
- Мінімальна сума: {min_amount} грн
- Період: {start_date} — {end_date}

ІНСТРУКЦІЇ:
- Сума: використовуй КРАПКУ як роздільник (217.65)
- Дата: конвертуй у формат YYYY-MM-DD
- Час: 24-годинний формат HH:MM
- Магазин: точна назва УКРАЇНСЬКОЮ (Є не Е, І не И)
- Код чека: шукай ФН/ФП/ФІСКАЛЬНИЙ/CHECK #/НОМЕР ЧЕКА
- Raw text: копіюй ВЕСЬ текст українською
- Якщо поле нечитабельне → null

ТИПОВІ МАГАЗИНИ:
СІЛЬПО, SILPO, АТБ, ATB, НОВУС, NOVUS, БУЛКА, BULKA, ФОРА, FORA, АШАН, AUCHAN

Відповідай ТІЛЬКИ JSON, без пояснень."""


async def analyze_receipt(image_bytes: bytes, rules: Dict[str, Any]) -> ReceiptResult:
    """
    Аналізує чек через Groq Vision API з круговою ротацією ключів.
    
    Args:
        image_bytes: Зображення чеку в форматі bytes
        rules: Правила поточної акції для валідації
        
    Returns:
        ReceiptResult з розпізнаними даними
        
    Raises:
        ReceiptAnalysisError: Якщо всі API ключі не спрацювали
        ReceiptParseError: Якщо не вдалося розпарсити відповідь
    """
    rotator = await _get_rotator()
    settings = Settings.load()
    
    logger.info(f"📸 Starting receipt analysis (image size: {len(image_bytes)} bytes)")
    
    # Конвертуємо зображення в base64
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    
    # Промпт
    prompt = _build_prompt(rules)
    
    # Функція для виклику Groq API
    async def make_groq_request(client: AsyncGroq):
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.0,
            max_completion_tokens=2048,  # ✅ Правильний параметр
            top_p=1,
            stream=False,
            stop=None,
        )
        return response
    
    # Виклик з круговою ротацією
    try:
        response = await rotator.call_with_circular_retry(make_groq_request)
    except ReceiptAnalysisError:
        raise
    except Exception as e:
        logger.exception("Unexpected error in Groq API call")
        raise ReceiptAnalysisError(
            "Не вдалося обробити чек через технічну помилку. Спробуйте пізніше."
        ) from e
    
    # Парсимо відповідь
    content = response.choices[0].message.content
    
    if not content:
        raise ReceiptParseError("Groq повернув порожню відповідь")
    
    logger.debug(f"📝 Groq response: {content[:200]}...")
    
    # Очищаємо від можливого markdown
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    
    # Парсимо JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON. Raw content: {content[:500]}")
        raise ReceiptParseError(
            "Не вдалося розпізнати структуру чека. "
            "Переконайтесь, що фото чітке і чек видно повністю."
        ) from e
    
    # Створюємо результат
    result = ReceiptResult(
        shop=data.get("shop"),
        amount=float(data["amount"]) if data.get("amount") is not None else None,
        date=data.get("date"),
        time=data.get("time"),
        check_code=data.get("check_code"),
        address=data.get("address"),
        is_valid=False,
        errors=[],
        raw_text=data.get("raw_text", "")
    )
    
    # Валідація проти правил акції
    result = _validate_against_rules(result, rules)
    
    logger.info(
        f"✅ Parsed: shop={result.shop}, amount={result.amount}, "
        f"date={result.date}, valid={result.is_valid}, errors={len(result.errors)}"
    )
    
    return result


def _normalize_shop_name(name: str) -> str:
    """Нормалізація назви магазину для порівняння"""
    result = name.strip().upper()
    
    # Заміна схожих кирилічних на латинські
    replacements = {
        "І": "I", "Ї": "I", "А": "A", "В": "B", "Е": "E", "К": "K",
        "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T",
        "У": "Y", "Х": "X", "Є": "E",
    }
    for cyr, lat in replacements.items():
        result = result.replace(cyr, lat)
    
    return result


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Обчислює відстань Левенштейна між двома рядками"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def _shop_matches(shop_norm: str, allowed: str, max_distance: int = 1) -> bool:
    """Перевіряє чи співпадає магазин з допуском на помилки"""
    # Точне співпадіння
    if shop_norm == allowed:
        return True
    # Часткове входження
    if shop_norm in allowed or allowed in shop_norm:
        return True
    # Fuzzy matching з допуском в max_distance символів
    if _levenshtein_distance(shop_norm, allowed) <= max_distance:
        return True
    return False


def _validate_against_rules(result: ReceiptResult, rules: Dict[str, Any]) -> ReceiptResult:
    """Валідація розпізнаного чеку проти правил акції"""
    errors: List[str] = []
    
    # 1. Перевірка суми
    min_amount = rules.get("min_amount")
    if min_amount is not None:
        if result.amount is None:
            errors.append("Не вдалося прочитати суму покупки.")
        elif result.amount < float(min_amount):
            errors.append("Сума покупки менша за мінімально дозволену.")
    
    # 2. Перевірка магазину
    allowed_shops = [_normalize_shop_name(str(s)) for s in rules.get("allowed_shops", []) if s]
    if allowed_shops:
        if not result.shop:
            errors.append("Не вдалося визначити магазин.")
        else:
            shop_norm = _normalize_shop_name(result.shop)
            # Перевірка з допуском в 1 символ
            match = any(
                _shop_matches(shop_norm, allowed, max_distance=1)
                for allowed in allowed_shops
            )
            if not match:
                errors.append("Магазин не бере участі в акції.")
    
    # 3. Перевірка адреси магазину (якщо вказана в правилах)
    shop_addresses = rules.get("shop_addresses", {})
    if result.shop and shop_addresses:
        shop_norm = _normalize_shop_name(result.shop)
        expected_address = shop_addresses.get(shop_norm)
        
        if expected_address:
            if not result.address:
                errors.append("Не вдалося визначити адресу магазину.")
            else:
                # Нормалізуємо адреси для порівняння
                receipt_addr = result.address.upper().replace(",", " ").replace(".", " ")
                expected_addr = expected_address.upper().replace(",", " ").replace(".", " ")
                
                # Перевірка ключових частин адреси
                expected_parts = [p.strip() for p in expected_addr.split() if len(p.strip()) > 2]
                match_count = sum(1 for part in expected_parts if part in receipt_addr)
                
                if expected_parts and match_count < len(expected_parts) / 2:
                    errors.append(f"Адреса магазину не співпадає. Очікується: {expected_address}")
    
    # 4. Перевірка дати
    start_date = rules.get("start_date")
    end_date = rules.get("end_date")
    
    if start_date and end_date:
        if not result.date:
            errors.append("Не вдалося визначити дату покупки.")
        else:
            try:
                receipt_date = datetime.strptime(result.date, "%Y-%m-%d").date()
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
                
                if receipt_date < start_dt or receipt_date > end_dt:
                    errors.append("Дата покупки не входить у період акції.")
            except ValueError as e:
                logger.warning(f"Date validation error: {e}")
                errors.append("Невірний формат дати на чеку.")
    
    # 5. Перевірка часу (якщо вказаний діапазон)
    allowed_time = rules.get("allowed_time_range")
    if allowed_time and isinstance(allowed_time, dict):
        start_time_str = allowed_time.get("start")
        end_time_str = allowed_time.get("end")
        
        if start_time_str and end_time_str:
            if not result.time:
                errors.append("Не вдалося визначити час покупки.")
            else:
                try:
                    receipt_time = datetime.strptime(result.time, "%H:%M").time()
                    start_time = datetime.strptime(start_time_str, "%H:%M").time()
                    end_time = datetime.strptime(end_time_str, "%H:%M").time()
                    
                    if receipt_time < start_time or receipt_time > end_time:
                        errors.append("Час покупки не входить до дозволеного діапазону.")
                except ValueError as e:
                    logger.warning(f"Time validation error: {e}")
                    # Не додаємо помилку, бо час не критичний
    
    result.is_valid = len(errors) == 0
    result.errors = errors
    
    return result