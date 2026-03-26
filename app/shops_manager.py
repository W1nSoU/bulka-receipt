from __future__ import annotations

from typing import List, Tuple

from app.db import Database
from app import promo_manager


async def add_shop(db: Database, name: str) -> int:
    return await db.add_shop(name)


async def delete_shop(db: Database, shop_id: int) -> None:
    await db.delete_shop(shop_id)


async def list_shops(db: Database) -> List[tuple[int, str]]:
    return await db.list_shops()


async def list_shops_with_flags(db: Database) -> List[Tuple[int, str, bool]]:
    shops = await db.list_shops()
    active = await db.get_setting("active_shops", []) or []
    active_upper = [s.upper() for s in active]
    result: List[Tuple[int, str, bool]] = []
    for sid, name in shops:
        result.append((sid, name, name.upper() in active_upper))
    return result


async def toggle_shop_for_campaign(db: Database, shop_name: str) -> bool:
    return await promo_manager.toggle_shop(db, shop_name)


async def update_shop_name(db: Database, shop_id: int, new_name: str) -> str:
    """Оновлює назву магазину та повертає стару назву.
    Також оновлює active_shops якщо магазин був активним."""
    old_name = await db.update_shop_name(shop_id, new_name)
    
    if old_name:
        # Якщо магазин був активним - оновлюємо active_shops
        current_active = await db.get_setting("active_shops", []) or []
        if old_name in current_active:
            # Замінюємо стару назву на нову
            updated_active = [new_name if s == old_name else s for s in current_active]
            await db.set_setting("active_shops", updated_active)
            promo_manager.invalidate_rules_cache()
    
    return old_name


async def add_sample(db: Database, shop_id: int, file_id: str) -> None:
    await db.add_shop_sample(shop_id, file_id)
