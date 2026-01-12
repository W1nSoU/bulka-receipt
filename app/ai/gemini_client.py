from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

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
    """Base error for receipt analysis via Gemini."""


class ReceiptParseError(ReceiptAnalysisError):
    """Raised when Gemini returns a response that cannot be parsed."""


def _get_model() -> genai.GenerativeModel:
    settings = Settings.load()
    if not settings.gemini_api_key:
        raise ReceiptAnalysisError("GEMINI_API_KEY is not set")
    genai.configure(api_key=settings.gemini_api_key)
    model_name = getattr(settings, "gemini_model", "gemini-1.5-flash") or "gemini-1.5-flash"
    return genai.GenerativeModel(model_name)


def _build_prompt(rules: Dict[str, Any]) -> str:
    rules_text = (
        "Ти витягуєш дані з фото фіскального чеку. Відповідай ТІЛЬКИ сімома рядками + блок RAW_TEXT. "
        "Усі рядки ПОВИННІ бути присутніми, навіть якщо значення UNKNOWN. Формат строго такий:\n"
        "SHOP: <назва магазину або UNKNOWN>\n"
        "ADDRESS: <адреса магазину (місто, вулиця) або UNKNOWN>\n"
        "AMOUNT: <сума з крапкою або UNKNOWN>\n"
        "DATE: <дата YYYY-MM-DD якщо можливо, інакше як прочитано, або UNKNOWN>\n"
        "TIME: <час HH:MM 24h якщо можливо, інакше як прочитано, або UNKNOWN>\n"
        "CHECK_CODE: <код/номер чеку або UNKNOWN>\n"
        "RAW_TEXT:\n"
        "<повний розпізнаний текст чеку, може бути у кілька рядків>\n"
        "Обов'язково виведи ВСІ сім ключів у такому порядку. Якщо суму бачиш з комою, перетвори на крапку. "
        "Не додавай текст поза цим блоком. Не використовуй JSON. "
        "Правила акції (тільки як підказка, у відповідь не включати):"
    )
    example = (
        "Приклад відповіді (формат):\n"
        "SHOP: SILPO\n"
        "ADDRESS: м. Київ, вул. Хрещатик 22\n"
        "AMOUNT: 217.65\n"
        "DATE: 2019-07-30\n"
        "TIME: 12:48\n"
        "CHECK_CODE: 3000278353\n"
        "RAW_TEXT:\n"
        "повний текст чеку тут"
    )
    return f"{rules_text}\n{rules}\n\n{example}"


def _build_prompt_compact(rules: Dict[str, Any]) -> str:
    return (
        "Extract receipt data. MUST return exactly these lines, always include them (UNKNOWN if unreadable):\n"
        "SHOP: ...\n"
        "ADDRESS: ...\n"
        "AMOUNT: ...\n"
        "DATE: ...\n"
        "TIME: ...\n"
        "CHECK_CODE: ...\n"
        "RAW_TEXT:\n"
        "<text>\n"
        "No JSON, no extra text. Use dot for decimals. Prefer YYYY-MM-DD and HH:MM. "
        f"Rules (for context only): {rules}"
    )


def _parse_gemini_text(text: str) -> ReceiptResult:
    lines = (text or "").splitlines()
    cleaned = [ln.strip() for ln in lines if ln.strip()]
    required_keys = ["SHOP:", "ADDRESS:", "AMOUNT:", "DATE:", "TIME:", "CHECK_CODE:"]
    values: Dict[str, str] = {}
    raw_text_parts: List[str] = []
    raw_started = False

    for line in cleaned:
        upper = line.upper()
        if raw_started:
            raw_text_parts.append(line)
            continue
        if upper.startswith("RAW_TEXT:"):
            raw_started = True
            raw_text_parts.append(line.partition("RAW_TEXT:")[2].strip())
            continue
        matched = False
        for key in required_keys:
            if upper.startswith(key):
                values[key[:-1].lower()] = line.partition(":")[2].strip()
                matched = True
                break
        if not matched and not raw_started:
            continue

    missing = [k[:-1].lower() for k in required_keys if k[:-1].lower() not in values]
    if missing:
        logger.warning("Missing fields in Gemini response: %s. Raw: %s", missing, text)
    if not raw_started:
        logger.warning("RAW_TEXT missing in Gemini response. Raw: %s", text)
        raw_started = True
        raw_text_parts.append("")

    def _to_value(key: str) -> Optional[str]:
        val = values.get(key, "UNKNOWN")
        if val is None:
            return None
        return None if val.upper() == "UNKNOWN" or val == "" else val

    shop = _to_value("shop")
    address = _to_value("address")
    amount_str = _to_value("amount")
    amount_val: Optional[float] = None
    if amount_str:
        try:
            amount_val = float(amount_str.replace(",", "."))
        except Exception:
            amount_val = None

    date_val = _to_value("date")
    time_val = _to_value("time")
    check_code_val = _to_value("check_code")
    raw_text = "\n".join(raw_text_parts).strip()

    return ReceiptResult(
        shop=shop,
        amount=amount_val,
        date=date_val,
        time=time_val,
        check_code=check_code_val,
        address=address,
        is_valid=False,
        errors=[],
        raw_text=raw_text,
    )


def _parse_date(value: str) -> Optional[datetime.date]:
    formats = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except Exception:
            continue
    return None


def _parse_time(value: str) -> Optional[datetime.time]:
    formats = ["%H:%M", "%H.%M"]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).time()
        except Exception:
            continue
    return None


def _normalize_shop_name(name: str) -> str:
    """Нормалізація назви магазину для порівняння."""
    result = name.strip().upper()
    # Кирилиця -> латиниця для типових випадків
    replacements = {
        "І": "I", "Ї": "I", "А": "A", "В": "B", "Е": "E", "К": "K",
        "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T",
        "У": "Y", "Х": "X",
    }
    for cyr, lat in replacements.items():
        result = result.replace(cyr, lat)
    return result


def _validate_against_rules(result: ReceiptResult, rules: Dict[str, Any]) -> ReceiptResult:
    errors: List[str] = []

    # Amount rule
    min_amount = rules.get("min_amount")
    if min_amount is not None:
        if result.amount is None:
            errors.append("Не вдалося прочитати суму покупки.")
        elif result.amount < float(min_amount):
            errors.append("Сума покупки менша за мінімально дозволену.")

    # Shop rule
    allowed_shops = [_normalize_shop_name(str(s)) for s in rules.get("allowed_shops") or [] if s]
    if allowed_shops:
        if not result.shop:
            errors.append("Не вдалося визначити магазин.")
        else:
            shop_norm = _normalize_shop_name(result.shop)
            if shop_norm not in allowed_shops:
                errors.append("Магазин не бере участі в акції.")

    # Address rule - перевірка адреси магазину
    shop_addresses = rules.get("shop_addresses") or {}
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
                # Перевіряємо чи ключові частини адреси співпадають
                expected_parts = [p.strip() for p in expected_addr.split() if len(p.strip()) > 2]
                match_count = sum(1 for part in expected_parts if part in receipt_addr)
                # Якщо менше половини частин співпадає - адреса не та
                if match_count < len(expected_parts) / 2:
                    errors.append(f"Адреса магазину не співпадає. Очікується: {expected_address}")

    # DateTime rule - перевірка повного діапазону (дата + час)
    start_date = rules.get("start_date")
    end_date = rules.get("end_date")
    allowed_time = rules.get("allowed_time_range") or {}
    start_time_str = allowed_time.get("start")
    end_time_str = allowed_time.get("end")

    parsed_date = _parse_date(result.date) if result.date else None
    parsed_time = _parse_time(result.time) if result.time else None

    if start_date and end_date:
        start_dt = _parse_date(start_date)
        end_dt = _parse_date(end_date)

        if not parsed_date:
            errors.append("Не вдалося визначити дату покупки.")
        elif start_dt and end_dt:
            # Якщо є час — перевіряємо повний datetime діапазон
            if start_time_str and end_time_str and parsed_time:
                start_t = _parse_time(start_time_str)
                end_t = _parse_time(end_time_str)
                if start_t and end_t:
                    from datetime import datetime as dt
                    receipt_datetime = dt.combine(parsed_date, parsed_time)
                    start_datetime = dt.combine(start_dt, start_t)
                    end_datetime = dt.combine(end_dt, end_t)

                    if receipt_datetime < start_datetime or receipt_datetime > end_datetime:
                        errors.append("Дата/час покупки не входить у період акції.")
            else:
                # Тільки дата без часу
                if parsed_date < start_dt or parsed_date > end_dt:
                    errors.append("Дата покупки не входить у період акції.")
    elif start_time_str and end_time_str:
        # Якщо вказано тільки час без дат — перевіряємо час (щоденно)
        if not parsed_time:
            errors.append("Не вдалося визначити час покупки.")
        else:
            start_t = _parse_time(start_time_str)
            end_t = _parse_time(end_time_str)
            if start_t and end_t and (parsed_time < start_t or parsed_time > end_t):
                errors.append("Час покупки не входить до дозволеного діапазону.")

    result.errors = errors
    result.is_valid = len(errors) == 0
    return result


async def analyze_receipt(image_bytes: bytes, rules: Dict[str, Any]) -> ReceiptResult:
    model = _get_model()
    prompts = [_build_prompt(rules), _build_prompt_compact(rules)]

    last_exc: Exception | None = None
    result: ReceiptResult | None = None

    for attempt, prompt in enumerate(prompts, start=1):
        try:
            response = await model.generate_content_async(
                [
                    prompt,
                    {"mime_type": "image/jpeg", "data": image_bytes},
                ],
                generation_config={"temperature": 0.0, "max_output_tokens": 2048},
            )
        except ResourceExhausted as e:
            logger.warning("Gemini quota exceeded: %s", e)
            raise ReceiptAnalysisError("Перевищено ліміт запитів до Gemini. Спробуйте пізніше.") from e
        except Exception as e:  # pragma: no cover - external API errors
            logger.exception("Gemini API error on attempt %s: %s", attempt, e)
            last_exc = e
            continue

        text = (getattr(response, "text", None) or "").strip()
        if not text:
            logger.warning("Empty response from Gemini on attempt %s", attempt)
            last_exc = ReceiptParseError("Не вдалося розібрати відповідь Gemini")
            continue

        try:
            parsed = _parse_gemini_text(text)
            result = parsed
            break
        except ReceiptParseError as e:
            logger.warning("Parse failed on attempt %s: %s", attempt, e)
            last_exc = e
            continue

    if result is None:
        if last_exc:
            if isinstance(last_exc, ReceiptParseError):
                raise last_exc
            raise ReceiptAnalysisError("Помилка під час запиту до Gemini") from last_exc
        raise ReceiptAnalysisError("Помилка під час запиту до Gemini")

    result = _validate_against_rules(result, rules)
    return result
