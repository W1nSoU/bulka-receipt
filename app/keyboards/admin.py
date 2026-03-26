from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="▶️ Запустити акцію", callback_data="admin:campaign_start")
    kb.button(text="⏹ Зупинити акцію", callback_data="admin:campaign_stop")
    kb.button(text="📦 Продовжити акцію", callback_data="admin:campaign_continue")
    kb.button(text="⚙️ Налаштування", callback_data="admin:settings")
    kb.button(text="🏬 Магазини", callback_data="admin:shops")
    kb.button(text="📊 Статистика", callback_data="admin:stats")
    kb.button(text="🎯 Переможці", callback_data="admin:winner")
    kb.button(text="📜 Історія акцій", callback_data="admin:campaign_history")
    kb.button(text="⬅️ На головну", callback_data="back_to_main")
    kb.adjust(2, 1, 2, 2, 2, 1)
    return kb.as_markup()


def admin_settings_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Період акції", callback_data="admin:settings:period")
    kb.button(text="💰 Мінімальна сума", callback_data="admin:settings:min_amount")
    kb.button(text="⏰ Години роботи", callback_data="admin:settings:time")
    kb.button(text="📢 Канал підписки", callback_data="admin:settings:channel")
    kb.button(text="🔍 Знайти чек", callback_data="admin:settings:search")
    kb.button(text="⬅️ Головне меню", callback_data="admin:main")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def admin_shops_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати", callback_data="admin:shops:add")
    kb.button(text="✏️ Редагувати", callback_data="admin:shops:edit")
    kb.button(text="🗑 Видалити", callback_data="admin:shops:delete")
    kb.button(text="🔄 Увімкнути/Вимкнути", callback_data="admin:shops:toggle")
    kb.button(text="📋 Переглянути список", callback_data="admin:shops:list")
    kb.button(text="⬅️ Головне меню", callback_data="admin:main")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


def shops_toggle_kb(shops: list[tuple[int, str, bool]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for shop_id, name, active in shops:
        flag = "🟢" if active else "🔴"
        kb.button(text=f"{flag} {name}", callback_data=f"admin:shops:toggle_item:{shop_id}")
    kb.button(text="⬅️ Назад", callback_data="admin:shops")
    kb.adjust(1)
    return kb.as_markup()


def shops_delete_kb(shops: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for shop_id, name in shops:
        kb.button(text=f"🗑 {name}", callback_data=f"admin:shops:delete_item:{shop_id}")
    kb.button(text="⬅️ Назад", callback_data="admin:shops")
    kb.adjust(1)
    return kb.as_markup()


def shops_edit_kb(shops: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for shop_id, name in shops:
        kb.button(text=f"✏️ {name}", callback_data=f"admin:shops:edit_item:{shop_id}")
    kb.button(text="⬅️ Назад", callback_data="admin:shops")
    kb.adjust(1)
    return kb.as_markup()


def admin_stats_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📈 Загальна", callback_data="admin:stats:overview")
    kb.button(text="🏬 За магазинами", callback_data="admin:stats:by_shop")
    kb.button(text="📆 За період", callback_data="admin:stats:by_period")
    kb.button(text="🧾 Останні чеки", callback_data="admin:stats:last_checks")
    kb.button(text="⬅️ Головне меню", callback_data="admin:main")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def admin_winner_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎟 Обрати переможців", callback_data="admin:winner:by_receipt")
    kb.button(text="⬅️ Головне меню", callback_data="admin:main")
    kb.adjust(1)
    return kb.as_markup()


def cancel_kb(callback_data: str = "admin:main") -> InlineKeyboardMarkup:
    """Клавіатура з однією кнопкою Скасувати для станів введення."""
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Скасувати", callback_data=callback_data)
    return kb.as_markup()


def back_cancel_kb(back_cb: str, cancel_cb: str = "admin:main") -> InlineKeyboardMarkup:
    """Клавіатура з кнопками Назад і Скасувати."""
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=back_cb)
    kb.button(text="❌ Скасувати", callback_data=cancel_cb)
    kb.adjust(2)
    return kb.as_markup()
