from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from app.db import Database


DEFAULT_RULES = {
    "campaign_active": False,
    "start_date": None,
    "end_date": None,
    "min_amount": 0.0,
    "allowed_shops": [],
    "allowed_time_range": None,
    "telegram_channel": None,
}


async def is_promo_active(db: Database) -> bool:
    raw = await db.get_setting("promo_active", "false")
    return str(raw).lower() == "true"


async def set_promo_active(db: Database, active: bool) -> None:
    await db.set_setting("promo_active", "true" if active else "false")


async def set_date_range(db: Database, start: str, end: str) -> None:
    await db.set_setting("start_date", start)
    await db.set_setting("end_date", end)


async def set_min_amount(db: Database, amount: float) -> None:
    await db.set_setting("min_amount", float(amount))


async def set_time_range(db: Database, start: Optional[str], end: Optional[str]) -> None:
    await db.set_setting("allowed_time_from", start)
    await db.set_setting("allowed_time_to", end)


async def set_active_shops(db: Database, shops: List[str]) -> None:
    await db.set_setting("active_shops", shops)


async def set_telegram_channel(db: Database, channel: Optional[str]) -> None:
    await db.set_setting("telegram_channel", channel)


async def get_telegram_channel(db: Database) -> Optional[str]:
    return await db.get_setting("telegram_channel", None)


async def toggle_shop(db: Database, shop_name: str) -> bool:
    current = await db.get_setting("active_shops", []) or []
    if shop_name in current:
        current = [s for s in current if s != shop_name]
        await db.set_setting("active_shops", current)
        return False
    current.append(shop_name)
    await db.set_setting("active_shops", current)
    return True


async def rules_for_gemini(db: Database) -> Dict[str, Any]:
    settings = DEFAULT_RULES | {}
    settings.update(await db.get_settings_map())

    start_date = settings.get("start_date")
    end_date = settings.get("end_date")
    min_amount = settings.get("min_amount", 0)
    active_shops = settings.get("active_shops", []) or []
    allowed_time_from = settings.get("allowed_time_from")
    allowed_time_to = settings.get("allowed_time_to")

    # Отримуємо адреси магазинів
    shop_addresses: Dict[str, str] = {}
    shops_with_addr = await db.list_shops_with_addresses()
    for _, name, address in shops_with_addr:
        if address and name.upper() in [s.upper() for s in active_shops]:
            shop_addresses[name.upper()] = address

    return {
        "campaign_active": str(settings.get("promo_active", "false")).lower() == "true",
        "start_date": start_date,
        "end_date": end_date,
        "min_amount": float(min_amount) if min_amount else 0.0,
        "allowed_shops": active_shops,
        "shop_addresses": shop_addresses,
        "allowed_time_range":
            {
                "start": allowed_time_from,
                "end": allowed_time_to,
            }
            if allowed_time_from and allowed_time_to
            else None,
    }


async def ensure_defaults(db: Database) -> None:
    # ensure required keys exist
    await db.set_setting("promo_active", await db.get_setting("promo_active", "false"))
    today = date.today().isoformat()
    await db.set_setting("start_date", await db.get_setting("start_date", today))
    await db.set_setting("end_date", await db.get_setting("end_date", today))
    await db.set_setting("min_amount", await db.get_setting("min_amount", 0.0))
    await db.set_setting("active_shops", await db.get_setting("active_shops", []))
