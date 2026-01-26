from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton


def user_main_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📝 Зареєструвати чек", callback_data="register_receipt")],
        [InlineKeyboardButton(text="🧾 Мої чеки", callback_data="my_receipts")],
        [InlineKeyboardButton(text="👤 Мій профіль", callback_data="profile")],
        [InlineKeyboardButton(text="📜 Правила акції", callback_data="rules")],
        [InlineKeyboardButton(text="🆘 Підтримка", callback_data="support")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="🔐 Адмін панель", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


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