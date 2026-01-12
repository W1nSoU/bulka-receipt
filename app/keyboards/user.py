from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def user_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Зареєструвати чек")]],
        resize_keyboard=True,
    )


def contact_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Поділитись контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
