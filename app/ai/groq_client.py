from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Tuple

from groq import AsyncGroq
from groq import (
    RateLimitError,
    APIError,
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
)
from PIL import Image, ImageEnhance, ImageOps
import numpy as np

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

    async def close(self) -> None:
        for client in self.clients.values():
            try:
                await client.close()
            except Exception:
                pass
    
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


def _detect_mime_type(image_bytes: bytes) -> str:
    """Визначає MIME тип зображення за сигнатурою байтів."""
    if image_bytes[:2] == b'\xff\xd8':
        return "image/jpeg"
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if image_bytes[:4] in (b'RIFF', b'WEBP') or image_bytes[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"  # fallback


def _check_blur(image_bytes: bytes, threshold: float = 500.0) -> Tuple[bool, float]:
    """
    Визначає чи зображення розмите (variance of image gradient).
    Використовує різниці сусідніх пікселів як апроксимацію Лапласіана.

    Returns:
        (is_blurry, score) — score < threshold вважається розмитим.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")  # grayscale
        # Обмежуємо до 512px для швидкості
        img.thumbnail((512, 512), Image.LANCZOS)
        arr = np.array(img, dtype=np.float32)
        # Variance of horizontal + vertical gradients (апроксимація Лапласіана)
        dx = np.diff(arr, axis=1)
        dy = np.diff(arr, axis=0)
        score = float(np.var(dx) + np.var(dy))
        is_blurry = score < threshold
        return is_blurry, score
    except Exception as e:
        logger.warning(f"Blur check failed: {e}")
        return False, 9999.0  # не блокуємо при помилці


def _preprocess_image(image_bytes: bytes) -> Tuple[bytes, str]:
    """
    Препроцесинг зображення для кращого OCR:
    - Конвертує в grayscale (кращий контраст тексту)
    - Авто-контраст
    - Підсилює різкість
    - Обмежує максимальний розмір (2048px по довшій стороні)
    - Повертає JPEG bytes та MIME тип
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))

        # Обмежуємо розмір до 2048px по довшій стороні (зберігає пропорції)
        max_side = 2048
        if max(img.size) > max_side:
            img = img.copy()
            img.thumbnail((max_side, max_side), Image.LANCZOS)

        # Grayscale — для чеків (чорний текст на білому) дає кращий OCR
        img = img.convert("L")

        # Авто-контраст — вирівнює засвіти/тіні без кліпінгу
        img = ImageOps.autocontrast(img, cutoff=2)

        # Підсилення різкості (+50%)
        img = ImageEnhance.Sharpness(img).enhance(1.5)

        # Конвертуємо назад в RGB (модель очікує RGB)
        img = img.convert("RGB")

        # Зберігаємо в JPEG
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92, optimize=True)
        return buf.getvalue(), "image/jpeg"

    except Exception as e:
        logger.warning(f"Image preprocessing failed, using original: {e}")
        return image_bytes, _detect_mime_type(image_bytes)


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
    
    return f"""Ти — система розпізнавання УКРАЇНСЬКИХ фіскальних чеків (РРО/ПРРО/ФО-П). Витягни ВСІ поля.

ВАЖЛИВО: Текст на чеках — ВИКЛЮЧНО УКРАЇНСЬКОЮ мовою.
Унікальні літери: Є, І, Ї, Ґ (не плутай з Э, И, Ы, Г).

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

ІНСТРУКЦІЇ ДЛЯ КОЖНОГО ПОЛЯ:

shop — назва мережі/магазину. Перевір верхній рядок чека.
  Типові: СІЛЬПО, SILPO, АТБ, ATB, НОВУС, NOVUS, БУЛКА, BULKA, ФОРА, FORA, АШАН, AUCHAN, METRO, ВЕЛМАРТ.
  Якщо є скорочена і повна назва — бери коротку (наприклад "БУЛКА", а не "ТОВ ПЕКАРНЯ БУЛКА").

address — місто та вулиця. Зазвичай під назвою магазину.

amount — ПІДСУМКОВА сума до сплати (не проміжні). Шукай: "СУМА", "ДО СПЛАТИ", "РАЗОМ", "ЗАГАЛЬНА СУМА", "TOTAL".
  Використовуй КРАПКУ як роздільник (217.65). Ігноруй копійки-суфікси — якщо "21765" без роздільника, це 217.65.

date — дата покупки. Конвертуй у YYYY-MM-DD.
  Формати на чеках: DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD.

time — час покупки. 24-годинний формат HH:MM.

check_code — фіскальний ідентифікатор. Шукай:
  ФН, ФП, ФЧ, ФІСКАЛЬНИЙ НОМЕР, CHECK #, НОМЕР ЧЕКА, ЧЕК №, КВИТАНЦІЯ №.
  На ПРРО-чеках: "Фіскальний номер документа", QR або штрих-код внизу (числовий рядок).
  Якщо кілька номерів — бери той, що позначений "ФН" або "Фіскальний номер".

raw_text — скопіюй ВЕСЬ видимий текст з чека рядок за рядком, зберігаючи українські літери.

ТИПОВІ ПОМИЛКИ (уникай):
- Не плутай суму ПДВ з підсумковою сумою.
- Не плутай номер картки/телефону з кодом чека.
- Якщо поле нечитабельне або відсутнє → null (не вигадуй).

Відповідай ТІЛЬКИ JSON, без пояснень."""


def _regex_extract_amount(text: str) -> Optional[float]:
    """Витягує підсумкову суму з тексту чека regex-патернами."""
    # Спочатку шукаємо "до сплати" / "разом" / "сума" — вони найнадійніші
    priority_patterns = [
        r"(?:до\s+сплати|сума\s+до\s+сплати|загальна\s+сума|разом\s+до\s+сплати)\s*[:\s]\s*(\d[\d\s]*[.,]\d{2})",
        r"(?:разом|всього|total|підсумок)\s*[:\s]\s*(\d[\d\s]*[.,]\d{2})",
        r"(?:сума|sum)\s*[:\s]\s*(\d[\d\s]*[.,]\d{2})",
    ]
    fallback_patterns = [
        r"(\d{1,6}[.,]\d{2})\s*(?:грн|UAH|₴)",
    ]
    for pat in priority_patterns + fallback_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(" ", "").replace(",", ".")
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _regex_extract_date(text: str) -> Optional[str]:
    """Витягує дату покупки з тексту чека."""
    patterns = [
        r"\b(\d{2})[./](\d{2})[./](\d{4})\b",   # DD.MM.YYYY або DD/MM/YYYY
        r"\b(\d{4})-(\d{2})-(\d{2})\b",           # YYYY-MM-DD
        r"\b(\d{2})[./](\d{2})[./](\d{2})\b",     # DD.MM.YY
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            g = m.groups()
            if len(g[2]) == 4 and g[2].startswith(("19", "20")):
                # DD.MM.YYYY
                return f"{g[2]}-{g[1].zfill(2)}-{g[0].zfill(2)}"
            elif len(g[0]) == 4:
                # YYYY-MM-DD
                return f"{g[0]}-{g[1]}-{g[2]}"
            else:
                # DD.MM.YY → 20YY
                return f"20{g[2]}-{g[1].zfill(2)}-{g[0].zfill(2)}"
    return None


def _regex_extract_time(text: str) -> Optional[str]:
    """Витягує час покупки з тексту чека."""
    m = re.search(r"\b(\d{2}):(\d{2})(?::\d{2})?\b", text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return f"{h:02d}:{mn:02d}"
    return None


def _regex_extract_check_code(text: str) -> Optional[str]:
    """Витягує фіскальний код чека з тексту."""
    patterns = [
        r"(?:фіскальний\s+номер\s+документа|фіскальний\s+номер|фн|фп|фч)\s*[:\s#№]\s*(\d{6,20})",
        r"(?:check\s*#|номер\s+чека|чек\s*№|квитанція\s*№)\s*[:\s]?\s*(\d{4,20})",
        r"(?:фн|фп)\s+(\d{6,20})",
        r"\bqr\b.*?(\d{10,20})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _apply_regex_fallback(result: ReceiptResult) -> ReceiptResult:
    """
    Якщо AI не зміг витягти критичні поля — пробуємо regex по raw_text.
    Не перезаписує поля, які вже є.
    """
    if not result.raw_text:
        return result

    changed = []

    if result.amount is None:
        val = _regex_extract_amount(result.raw_text)
        if val is not None:
            result.amount = val
            changed.append(f"amount={val}")

    if result.date is None:
        val = _regex_extract_date(result.raw_text)
        if val is not None:
            result.date = val
            changed.append(f"date={val}")

    if result.time is None:
        val = _regex_extract_time(result.raw_text)
        if val is not None:
            result.time = val
            changed.append(f"time={val}")

    if result.check_code is None:
        val = _regex_extract_check_code(result.raw_text)
        if val is not None:
            result.check_code = val
            changed.append(f"check_code={val}")

    if changed:
        logger.info(f"🔍 Regex fallback recovered: {', '.join(changed)}")

    return result


async def _retry_missing_fields(
    raw_text: str,
    result: ReceiptResult,
    rotator: "CircularKeyRotator",
    model: str,
) -> ReceiptResult:
    """
    Якщо після regex-fallback критичні поля ще null —
    робимо короткий text-only запит до AI з raw_text.
    """
    missing = []
    if result.amount is None:
        missing.append("amount (сума до сплати, число з крапкою)")
    if result.date is None:
        missing.append('date (дата у форматі "YYYY-MM-DD")')

    if not missing or not raw_text:
        return result

    fields_str = ", ".join(f'"{f.split()[0]}"' for f in missing)
    prompt = (
        f"З тексту чека нижче витягни ТІЛЬКИ ці поля: {', '.join(missing)}.\n"
        f"Відповідай ТІЛЬКИ JSON: {{{', '.join(f'{f.split()[0]}: ...' for f in missing)}}}\n\n"
        f"ТЕКСТ ЧЕКА:\n{raw_text[:1500]}"
    )

    async def make_text_request(client: AsyncGroq):
        return await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_completion_tokens=256,
            stream=False,
        )

    try:
        response = await rotator.call_with_circular_retry(make_text_request)
        content = response.choices[0].message.content or ""
        content = content.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(content)

        if result.amount is None and data.get("amount") is not None:
            result.amount = float(data["amount"])
            logger.info(f"🔁 AI retry recovered amount={result.amount}")
        if result.date is None and data.get("date"):
            result.date = str(data["date"])
            logger.info(f"🔁 AI retry recovered date={result.date}")
    except Exception as e:
        logger.debug(f"AI retry for missing fields failed: {e}")

    return result


async def analyze_receipt(image_bytes: bytes, rules: Dict[str, Any]) -> ReceiptResult:
    """
    Аналізує чек через Groq Vision API з круговою ротацією ключів.

    Args:
        image_bytes: Зображення чеку в форматі bytes
        rules: Правила поточної акції для валідації

    Returns:
        ReceiptResult з розпізнаними даними

    Raises:
        ReceiptAnalysisError: Якщо зображення розмите або всі API ключі не спрацювали
        ReceiptParseError: Якщо не вдалося розпарсити відповідь
    """
    rotator = await _get_rotator()
    settings = Settings.load()

    logger.info(f"📸 Starting receipt analysis (image size: {len(image_bytes)} bytes)")

    # Перевірка на розмитість — перед обробкою, щоб не витрачати API квоту
    is_blurry, blur_score = _check_blur(image_bytes)
    logger.info(f"🔍 Blur score: {blur_score:.1f} (blurry={is_blurry})")
    if is_blurry:
        raise ReceiptAnalysisError(
            "Фото занадто розмите. Будь ласка, зробіть чіткіший знімок чека."
        )
    
    # Препроцесинг: покращення якості та нормалізація формату
    processed_bytes, mime_type = _preprocess_image(image_bytes)
    logger.info(f"🖼️ Preprocessed: {len(processed_bytes)} bytes, MIME: {mime_type}")
    
    # Конвертуємо зображення в base64
    image_base64 = base64.b64encode(processed_bytes).decode('utf-8')
    
    # Промпт
    prompt = _build_prompt(rules)
    
    # Функція для виклику Groq API
    async def make_groq_request(client: AsyncGroq, model: Optional[str] = None):
        response = await client.chat.completions.create(
            model=model or settings.groq_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.0,
            max_completion_tokens=2048,
            top_p=1,
            stream=False,
            stop=None,
        )
        return response
    
    # Виклик з круговою ротацією основної моделі
    response = None
    try:
        response = await rotator.call_with_circular_retry(make_groq_request)
    except ReceiptAnalysisError:
        # Основна модель не спрацювала — пробуємо fallback модель
        fallback_model = settings.groq_fallback_model
        if fallback_model and fallback_model != settings.groq_model:
            logger.warning(
                f"⚠️ Primary model failed. Retrying with fallback: {fallback_model}"
            )
            try:
                async def make_fallback_request(client: AsyncGroq):
                    return await make_groq_request(client, model=fallback_model)
                response = await rotator.call_with_circular_retry(make_fallback_request)
            except ReceiptAnalysisError:
                raise
        else:
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

    # Regex fallback — відновлюємо поля, які AI не зміг витягти
    result = _apply_regex_fallback(result)

    # Smart AI retry — якщо критичні поля ще null, робимо text-only запит
    if result.amount is None or result.date is None:
        result = await _retry_missing_fields(
            result.raw_text, result, rotator, settings.groq_model
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
                # Спробуємо різні формати дати, які може повернути AI або regex
                receipt_date = None
                for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"]:
                    try:
                        receipt_date = datetime.strptime(result.date, fmt).date()
                        break
                    except ValueError:
                        continue
                
                if not receipt_date:
                    raise ValueError(f"Unknown date format: {result.date}")

                start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
                
                if receipt_date < start_dt or receipt_date > end_dt:
                    errors.append("Дата покупки не входить у період акції.")
                
                # Нормалізуємо дату до YYYY-MM-DD для бази даних
                result.date = receipt_date.strftime("%Y-%m-%d")
                
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