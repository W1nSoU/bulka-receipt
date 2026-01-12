from __future__ import annotations

import logging
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import promo_manager, runtime
from app.ai import analyze_receipt, ReceiptAnalysisError, ReceiptParseError
from app.excel import append_receipt, ensure_workbook
from app.keyboards import contact_request_keyboard, user_main_kb
from app.states import ReceiptState, RegistrationState


log = logging.getLogger(__name__)

router = Router()


async def _get_db_bot_settings(message: Message) -> tuple:
    # Using shared runtime context because aiogram Bot does not allow item assignment
    return runtime.get_db(), runtime.get_settings()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    # Захист від повторного /start коли вже в процесі реєстрації
    current_state = await state.get_state()
    if current_state and current_state.startswith("RegistrationState"):
        await message.answer("⏳ Ви вже в процесі реєстрації. Завершіть поточний крок.")
        return

    db, _ = await _get_db_bot_settings(message)
    user = await db.fetch_user(message.from_user.id)
    if user:
        await state.clear()
        full_name_parts = user.full_name.split() if user.full_name else []
        first_name = full_name_parts[1] if len(full_name_parts) > 1 else (full_name_parts[0] if full_name_parts else "друже")
        await message.answer(
            f"👋 <b>З поверненням, {first_name}!</b>\n\n"
            "Готові зареєструвати новий чек? Натисніть кнопку нижче 👇",
            parse_mode="HTML",
            reply_markup=user_main_kb(),
        )
        return
    await state.set_state(RegistrationState.waiting_for_contact)
    await message.answer(
        "👋 <b>Вітаємо в боті для реєстрації чеків!</b>\n\n"
        "Реєструйте чеки, щоб вигравати призи 🎁\n\n"
        "Для початку, будь ласка, надайте ваш контакт, натиснувши кнопку нижче 👇\n"
        "<i>Натискаючи кнопку, ви погоджуєтесь на обробку персональних даних.</i>",
        parse_mode="HTML",
        reply_markup=contact_request_keyboard(),
    )


@router.message(RegistrationState.waiting_for_contact, F.contact)
async def process_contact(message: Message, state: FSMContext) -> None:
    contact = message.contact
    await state.update_data(phone=contact.phone_number)
    await state.set_state(RegistrationState.waiting_for_full_name)
    await message.answer(
        "✅ <b>Дякуємо!</b>\n\n"
        "Тепер введіть ваше ПІБ (Прізвище Ім'я По батькові).",
        parse_mode="HTML",
        reply_markup=None,
    )


@router.message(RegistrationState.waiting_for_contact)
async def contact_required(message: Message) -> None:
    await message.answer(
        "☝️ Для продовження, будь ласка, натисніть кнопку <b>«Поділитись контактом»</b>.",
        parse_mode="HTML",
    )


@router.message(RegistrationState.waiting_for_full_name, F.text)
async def process_full_name(message: Message, state: FSMContext) -> None:
    db, _ = await _get_db_bot_settings(message)
    data = await state.get_data()
    phone = data.get("phone")
    full_name = message.text.strip()
    if not phone:
        await state.clear()
        await message.answer(
            "❌ Сталася помилка. Спробуйте ще раз — /start",
            parse_mode="HTML",
        )
        return
    await db.create_user(message.from_user.id, phone, full_name)
    await state.clear()
    full_name_parts = full_name.split() if full_name else []
    first_name = full_name_parts[1] if len(full_name_parts) > 1 else (full_name_parts[0] if full_name_parts else "")
    await message.answer(
        f"🎉 <b>Реєстрацію завершено, {first_name}!</b>\n\n"
        "Тепер ви можете надсилати фото чеків для участі в акції. Хай щастить! 🧾✨",
        parse_mode="HTML",
        reply_markup=user_main_kb(),
    )


@router.message(RegistrationState.waiting_for_full_name)
async def name_required(message: Message) -> None:
    await message.answer(
        "✍️ Будь ласка, введіть ваше ПІБ текстом.",
        parse_mode="HTML",
    )


@router.message(F.text == "Зареєструвати чек")
async def start_receipt_flow(message: Message, state: FSMContext) -> None:
    db, _ = await _get_db_bot_settings(message)
    user = await db.fetch_user(message.from_user.id)
    if not user:
        await message.answer(
            "👋 Спочатку зареєструйтесь — /start",
            parse_mode="HTML",
            reply_markup=user_main_kb(),
        )
        return
    if not await promo_manager.is_promo_active(db):
        await message.answer(
            "Зараз немає актуальних акцій. \n"
            "Слідкуйте за оновленнями — нові акції вже скоро! 🔔",
            parse_mode="HTML",
            reply_markup=user_main_kb(),
        )
        return
    
    # Перевірка підписки на Telegram канал
    channel = await promo_manager.get_telegram_channel(db)
    if channel:
        try:
            member = await message.bot.get_chat_member(chat_id=channel, user_id=message.from_user.id)
            if member.status not in ["member", "administrator", "creator"]:
                await message.answer(
                    f"📢 <b>Для участі потрібна підписка!</b>\n\n"
                    f"Підпишіться на канал {channel} та спробуйте знову.",
                    parse_mode="HTML",
                    reply_markup=user_main_kb(),
                )
                return
        except Exception as e:
            log.warning("Failed to check channel subscription: %s", e)
            # Якщо не вдалося перевірити - пропускаємо (бот може не бути адміном каналу)
    
    await state.set_state(ReceiptState.waiting_for_photo)
    await message.answer(
        "📸 <b>Надішліть фото вашого чека.</b>\n\n"
        "Переконайтесь, що:\n"
        "• Чек видно повністю та він гарно освітлений\n"
        "• Фото чітке, не розмите та без засвітів\n"
        "• На чеку немає сильних потертостей чи стертої фарби\n"
        "• Добре видно дату, суму та магазин\n\n"
        "<i>Інакше система не зможе зісканувати ваш чек.</i>\n\n"
        "Чекаю на ваше фото! 👇",
        parse_mode="HTML",
    )


@router.message(ReceiptState.waiting_for_photo, F.photo)
async def handle_receipt_photo(message: Message, state: FSMContext) -> None:
    db, settings = await _get_db_bot_settings(message)
    user = await db.fetch_user(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer(
            "❌ Спочатку зареєструйтесь за допомогою /start.",
            reply_markup=user_main_kb(),
        )
        return
    if not await promo_manager.is_promo_active(db):
        await state.clear()
        await message.answer(
            "🚫 Акція завершена. Нові чеки не приймаються.\n"
            "Слідкуйте за оновленнями — нові акції вже скоро! 🎉",
            reply_markup=user_main_kb(),
        )
        return

    # Повідомлення про очікування
    waiting_msg = await message.answer(
        "⏳ <b>Опрацьовую ваш чек...</b>\n"
        "Зачекайте, це займе кілька секунд.",
        parse_mode="HTML",
    )

    photo = message.photo[-1]
    buffer = BytesIO()
    await message.bot.download(photo, destination=buffer)
    image_bytes = buffer.getvalue()

    rules = await promo_manager.rules_for_gemini(db)
    try:
        result = await analyze_receipt(image_bytes, rules)
    except (ReceiptAnalysisError, ReceiptParseError):
        log.exception("Gemini processing failed")
        await waiting_msg.delete()
        await message.answer(
            "😔 <b>Не вдалося розпізнати чек.</b>\n\n"
            "Будь ласка, переконайтесь, що:\n"
            "• Фото чітке, а чек видно повністю та без засвітів\n"
            "• Чек гарно освітлений і текст не стертий\n"
            "• Дата покупки відповідає умовам акції\n\n"
            "Спробуйте надіслати краще фото. 📸",
            parse_mode="HTML",
            reply_markup=user_main_kb(),
        )
        return
    except Exception:
        log.exception("Gemini processing failed")
        await waiting_msg.delete()
        await message.answer(
            "⚠️ <b>Сталася невідома помилка.</b>\n"
            "Спробуйте, будь ласка, ще раз.",
            parse_mode="HTML",
            reply_markup=user_main_kb(),
        )
        return

    # Видаляємо повідомлення про очікування
    try:
        await waiting_msg.delete()
    except Exception:
        pass

    log.info(
        "Gemini parsed receipt: shop=%s amount=%s date=%s time=%s code=%s errors=%s",
        result.shop,
        result.amount,
        result.date,
        result.time,
        result.check_code,
        result.errors,
    )

    if not result.is_valid:
        reason = result.errors[0] if result.errors else "Чек не пройшов перевірку"
        log.warning("Receipt invalid: %s", reason)
        await message.answer(
            f"❌ <b>Чек не пройшов перевірку.</b>\n\n"
            f"Причина: {reason}.\n\n"
            "Будь ласка, перевірте умови акції та спробуйте ще раз. 🔄",
            parse_mode="HTML",
            reply_markup=user_main_kb(),
        )
        return

    if result.check_code and await db.is_duplicate_check_code(result.check_code):
        log.warning("Duplicate check_code detected: %s", result.check_code)
        await message.answer(
            "🧾 <b>Цей чек вже є в системі.</b>\n\n"
            "Пам'ятайте, кожен чек унікальний і реєструється лише раз.\n"
            "Надішліть інший, щоб продовжити.",
            parse_mode="HTML",
            reply_markup=user_main_kb(),
        )
        return

    receipt = await db.insert_check(
        user_id=user.id,
        shop=result.shop,
        amount=result.amount,
        date=result.date,
        time=result.time,
        check_code=result.check_code,
        file_id=photo.file_id,
        raw_text=result.raw_text,
    )

    ensure_workbook(settings.excel_path)
    append_receipt(settings.excel_path, receipt, user, message.from_user.username)

    log.info("Receipt saved: id=%s user_id=%s shop=%s amount=%s", receipt.id, user.id, result.shop, result.amount)

    await state.clear()
    amount_str = f"{result.amount:.2f}" if result.amount else "0.00"
    await message.answer(
        "✅ <b>Чудово! Ваш чек зареєстровано.</b>\n\n"
        f"<b>Магазин:</b> {result.shop or '—'}\n"
        f"<b>Сума:</b> {amount_str} грн\n"
        f"<b>Дата:</b> {result.date or '—'}\n\n"
        f"Ваш номер для розіграшу: <b>#{receipt.id}</b>\n\n"
        "Бажаємо успіху! 🍀",
        parse_mode="HTML",
        reply_markup=user_main_kb(),
    )


@router.message(ReceiptState.waiting_for_photo)
async def require_photo(message: Message) -> None:
    await message.answer(
        "Будь ласка, надішліть <b>фотографію</b>, а не текст. 📷",
        parse_mode="HTML",
    )


@router.message()
async def fallback_handler(message: Message, state: FSMContext) -> None:
    """Обробник для невідомих повідомлень поза FSM станами."""
    current = await state.get_state()
    if current is None:
        db, _ = await _get_db_bot_settings(message)
        user = await db.fetch_user(message.from_user.id)
        if user:
            await message.answer(
                "Не розумію вас. 🤔\nЩоб додати новий чек, натисніть кнопку нижче.",
                reply_markup=user_main_kb(),
            )
        else:
            await message.answer("Вітаю! Щоб почати, введіть команду /start")
