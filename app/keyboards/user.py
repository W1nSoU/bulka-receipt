from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton


def user_main_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        # Головна дія — на весь рядок
        [InlineKeyboardButton(text="📸 Зареєструвати чек", callback_data="register_receipt")],
        # Другорядні дії — парами
        [
            InlineKeyboardButton(text="🧾 Мої чеки", callback_data="my_receipts"),
            InlineKeyboardButton(text="👤 Профіль", callback_data="profile"),
        ],
        [
            InlineKeyboardButton(text="📜 Правила", callback_data="rules"),
            InlineKeyboardButton(text="🆘 Підтримка", callback_data="support"),
        ],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="🔐 Адмін панель", callback_data="admin_panel")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def contact_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поділитись контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Змінити імʼя", callback_data="change_name")],
            [InlineKeyboardButton(text="⬅️ На головну", callback_data="back_to_main")]
        ]
    )

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ На головну", callback_data="back_to_main")]
        ]
    )


def confirm_receipt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Зберегти", callback_data="receipt:confirm"),
                InlineKeyboardButton(text="🔄 Нове фото", callback_data="receipt:retry"),
            ],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="back_to_main")],
        ]
    )


def shop_selection_kb(active_shops: list[str]) -> InlineKeyboardMarkup:
    """
    Створює клавіатуру для вибору магазину зі списку активних магазинів.
    
    Args:
        active_shops: Список назв активних магазинів
    
    Returns:
        InlineKeyboardMarkup з кнопками для кожного магазину
    """
    buttons = []
    
    # Додаємо кнопку для кожного магазину
    for shop in active_shops:
        buttons.append([
            InlineKeyboardButton(
                text=f"✅ {shop}", 
                callback_data=f"select_shop:{shop}"
            )
        ])
    
    # Кнопка "Скасувати"
    buttons.append([
        InlineKeyboardButton(text="❌ Скасувати", callback_data="back_to_main")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def date_input_kb() -> InlineKeyboardMarkup:
    """
    Створює клавіатуру для запиту вводу дати.
    
    Returns:
        InlineKeyboardMarkup з кнопкою скасування
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="back_to_main")]
        ]
    )