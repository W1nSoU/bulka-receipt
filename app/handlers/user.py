from __future__ import annotations

import logging
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, FSInputFile, CallbackQuery

from app import promo_manager, runtime
from app.ai import analyze_receipt, ReceiptAnalysisError, ReceiptParseError
from app.excel import append_receipt, ensure_workbook
from app.keyboards import contact_request_keyboard, user_main_kb, profile_kb, back_kb, admin_main_kb
from app.states import ReceiptState, RegistrationState, ProfileState


log = logging.getLogger(__name__)

router = Router()


async def _get_db_bot_settings(message: Message | CallbackQuery) -> tuple:
    return runtime.get_db(), runtime.get_settings()


async def _send_photo_message(message: Message, text: str, reply_markup=None):
    photo = FSInputFile("photo/sakura.jpg")
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer_photo(
        photo=photo,
        caption=text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state and current_state.startswith("RegistrationState"):
        await message.answer("⏳ Ви вже в процесі реєстрації. Завершіть поточний крок.")
        return

    db, settings = await _get_db_bot_settings(message)
    user = await db.fetch_user(message.from_user.id)
    
    if user:
        await state.clear()
        full_name_parts = user.full_name.split() if user.full_name else []
        first_name = full_name_parts[1] if len(full_name_parts) > 1 else (full_name_parts[0] if full_name_parts else "друже")
        
        is_admin = message.from_user.id in settings.admin_ids
        
        photo = FSInputFile("photo/sakura.jpg")
        await message.answer_photo(
            photo=photo,
            caption=f"👋 <b>З поверненням, {first_name}!</b>\n\n" 
                    "Готові зареєструвати новий чек? Натисніть кнопку нижче 👇",
            parse_mode="HTML",
            reply_markup=user_main_kb(is_admin=is_admin),
        )
        return

    await state.set_state(RegistrationState.waiting_for_contact)
    photo = FSInputFile("photo/sakura.jpg")
    sent_message = await message.answer_photo(
        photo=photo,
        caption="👋 <b>Вітаємо в боті для реєстрації чеків!</b>\n\n" 
                "Реєструйте чеки, щоб вигравати призи 🎁\n\n" 
                "Для початку, будь ласка, надайте ваш контакт, натиснувши кнопку нижче 👇\n" 
                "<i>Натискаючи кнопку, ви погоджуєтесь на обробку персональних даних.</i>",
        parse_mode="HTML",
        reply_markup=contact_request_keyboard(),
    )
    await state.update_data(last_bot_msg_id=sent_message.message_id)


@router.message(RegistrationState.waiting_for_contact, F.contact)
async def process_contact(message: Message, state: FSMContext) -> None:
    contact = message.contact
    data = await state.get_data()
    last_msg_id = data.get("last_bot_msg_id")

    if last_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_msg_id)
        except Exception:
            pass

    await state.update_data(phone=contact.phone_number)
    await state.set_state(RegistrationState.waiting_for_full_name)
    
    photo = FSInputFile("photo/sakura.jpg")
    sent_message = await message.answer_photo(
        photo=photo,
        caption="✅ <b>Дякуємо!</b>\n\n" 
                "Тепер введіть ваше ПІБ (Прізвище Ім'я По батькові).",
        parse_mode="HTML",
        reply_markup=None,
    )
    await state.update_data(last_bot_msg_id=sent_message.message_id)


@router.message(RegistrationState.waiting_for_contact)
async def contact_required(message: Message) -> None:
    await message.answer(
        "☝️ Для продовження, будь ласка, натисніть кнопку <b>«Поділитись контактом»</b>.",
        parse_mode="HTML",
    )


@router.message(RegistrationState.waiting_for_full_name, F.text)
async def process_full_name(message: Message, state: FSMContext) -> None:
    db, settings = await _get_db_bot_settings(message)
    data = await state.get_data()
    phone = data.get("phone")
    last_msg_id = data.get("last_bot_msg_id")
    full_name = message.text.strip()
    
    if not phone:
        await state.clear()
        await message.answer(
            "❌ Сталася помилка. Спробуйте ще раз — /start",
            parse_mode="HTML",
        )
        return

    if last_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_msg_id)
        except Exception:
            pass
            
    try:
        await message.delete()
    except Exception:
        pass

    await db.create_user(message.from_user.id, phone, full_name)
    await state.clear()
    
    full_name_parts = full_name.split() if full_name else []
    first_name = full_name_parts[1] if len(full_name_parts) > 1 else (full_name_parts[0] if full_name_parts else "")
    
    is_admin = message.from_user.id in settings.admin_ids
    photo = FSInputFile("photo/sakura.jpg")
    
    await message.answer_photo(
        photo=photo,
        caption=f"🎉 <b>Реєстрацію завершено, {first_name}!</b>\n\n" 
                "Тепер ви можете надсилати фото чеків для участі в акції. Хай щастить! 🧾✨",
        parse_mode="HTML",
        reply_markup=user_main_kb(is_admin=is_admin),
    )


@router.message(RegistrationState.waiting_for_full_name)
async def name_required(message: Message) -> None:
    await message.answer(
        "✍️ Будь ласка, введіть ваше ПІБ текстом.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_to_main")
async def back_to_main_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    db, settings = await _get_db_bot_settings(callback.message)
    user = await db.fetch_user(callback.from_user.id)
    is_admin = callback.from_user.id in settings.admin_ids
    
    full_name_parts = user.full_name.split() if user and user.full_name else []
    first_name = full_name_parts[1] if len(full_name_parts) > 1 else (full_name_parts[0] if full_name_parts else "друже")

    await _send_photo_message(
        callback.message,
        f"👋 <b>З поверненням, {first_name}!</b>\n\n" 
        "Готові зареєструвати новий чек? Натисніть кнопку нижче 👇",
        user_main_kb(is_admin=is_admin)
    )
    await callback.answer()


@router.callback_query(F.data == "register_receipt")
async def start_receipt_flow(callback: CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    db, settings = await _get_db_bot_settings(message)
    user = await db.fetch_user(callback.from_user.id)
    is_admin = callback.from_user.id in settings.admin_ids

    if not user:
        await _send_photo_message(
            message,
            "👋 Спочатку зареєструйтесь — /start",
            back_kb() 
        )
        await callback.answer()
        return

    if not await promo_manager.is_promo_active(db):
        await _send_photo_message(
            message,
            "Зараз немає актуальних акцій. \n" 
            "Слідкуйте за оновленнями — нові акції вже скоро! 🔔",
            back_kb() 
        )
        await callback.answer()
        return
    
    channel = await promo_manager.get_telegram_channel(db)
    if channel:
        try:
            member = await message.bot.get_chat_member(chat_id=channel, user_id=callback.from_user.id)
            if member.status not in ["member", "administrator", "creator"]:
                await _send_photo_message(
                    message,
                    f"📢 <b>Для участі потрібна підписка!</b>\n\n" 
                    f"Підпишіться на канал {channel} та спробуйте знову.",
                    back_kb() 
                )
                await callback.answer()
                return
        except Exception as e:
            log.warning("Failed to check channel subscription: %s", e)
    
    await state.set_state(ReceiptState.waiting_for_photo)
    await _send_photo_message(
        message,
        "📸 <b>РЕЄСТРАЦІЯ ЧЕКА</b>\n\n"
        "Для участі в розіграші надішліть чітке фото фіскального чека.\n\n"
        "👇 <b>Натисніть на значок скріпки 📎 та оберіть фото</b>\n\n"
        "<i>Переконайтесь, що на фото чітко видно:</i>\n"
        "• Назву магазину\n"
        "• Дату та час\n"
        "• Суму покупки\n"
        "• Фіскальний номер",
        back_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "my_receipts")
async def my_receipts(callback: CallbackQuery) -> None:
    message = callback.message
    db, settings = await _get_db_bot_settings(message)
    user = await db.fetch_user(callback.from_user.id)
    is_admin = callback.from_user.id in settings.admin_ids
    
    if not user:
        await _send_photo_message(message, "Спочатку зареєструйтесь — /start", back_kb())
        await callback.answer()
        return

    if not await promo_manager.is_promo_active(db):
        await _send_photo_message(
            message,
            "🔴 <b>Наразі акція не активна</b>\n\n"
            "📊 Статистика за поточний період відсутня.\n"
            "🔔 Слідкуйте за анонсами!\n\n"
            "📂 <b>Останні 5 завантажень:</b>\n"
            "• Список порожній",
            back_kb()
        )
        await callback.answer()
        return

    receipts = await db.get_user_receipts(user.id, limit=3)
    
    if not receipts:
        await _send_photo_message(
            message,
            "📭 <b>У вас поки немає зареєстрованих чеків.</b>\n\n" 
            "Час це виправити! Тисніть «Зареєструвати чек» 👇",
            back_kb() 
        )
        await callback.answer()
        return

    msg_lines = ["🧾 <b>ВАШІ ОСТАННІ ЧЕКИ</b>\n\nТут відображаються 3 останні завантажені вами чеки:\n"]
    for i, r in enumerate(receipts, 1):
        amount_str = f"{r.amount:.2f}" if r.amount else "0.00"
        date_str = r.date if r.date else "—"
        shop_name = r.shop if r.shop else "Невідомо"
        check_code = r.check_code if r.check_code else f"#{r.id}"
        
        msg_lines.append(f"{i}️⃣ <b>Магазин «{shop_name}»</b>")
        msg_lines.append(f"   📅 {date_str} | 💰 {amount_str} грн")
        msg_lines.append(f"   🆔 {check_code}\n")
    
    await _send_photo_message(
        message,
        "\n".join(msg_lines),
        back_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "profile")
async def my_profile(callback: CallbackQuery) -> None:
    message = callback.message
    db, settings = await _get_db_bot_settings(message)
    user = await db.fetch_user(callback.from_user.id)
    is_admin = callback.from_user.id in settings.admin_ids

    if not user:
        await _send_photo_message(message, "Спочатку зареєструйтесь — /start", back_kb())
        await callback.answer()
        return
        
    created_at_date = user.created_at.split('T')[0] if user.created_at else "—"
    
    await _send_photo_message(
        message,
        "👤 <b>МІЙ ПРОФІЛЬ</b>\n\n"
        f"👤 <b>Імʼя:</b> {user.full_name}\n"
        f"📞 <b>Номер телефону:</b> {user.phone}\n"
        f"📅 <b>В боті з:</b> {created_at_date}",
        profile_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "change_name")
async def change_name_start(callback: CallbackQuery, state: FSMContext) -> None:
    await _send_photo_message(
        callback.message,
        "✍️ <b>Введіть ваше нове ПІБ:</b>",
        back_kb()
    )
    await state.set_state(ProfileState.waiting_for_new_name)
    await callback.answer()


@router.message(ProfileState.waiting_for_new_name, F.text)
async def process_new_name(message: Message, state: FSMContext) -> None:
    db, settings = await _get_db_bot_settings(message)
    new_name = message.text.strip()
    
    # Try to delete user's message
    try:
        await message.delete()
    except Exception:
        pass
        
    if not new_name:
        await _send_photo_message(message, "Будь ласка, введіть коректне ім'я.", back_kb())
        return

    await db.update_user_name(message.from_user.id, new_name)
    await state.clear()
    
    user = await db.fetch_user(message.from_user.id)
    created_at_date = user.created_at.split('T')[0] if user and user.created_at else "—"
    
    await _send_photo_message(
        message,
        "✅ <b>Ім'я успішно змінено!</b>\n\n"
        "👤 <b>МІЙ ПРОФІЛЬ</b>\n\n"
        f"👤 <b>Імʼя:</b> {new_name}\n"
        f"📞 <b>Номер телефону:</b> {user.phone if user else '—'}\n"
        f"📅 <b>В боті з:</b> {created_at_date}",
        profile_kb()
    )


@router.callback_query(F.data == "rules")
async def rules_handler(callback: CallbackQuery) -> None:
    db, _ = await _get_db_bot_settings(callback.message)
    is_active = await promo_manager.is_promo_active(db)
    
    if is_active:
        promo_info = "Акція активна! Поспішайте зареєструвати свій чек та виграти призи. 🎁"
    else:
        promo_info = "Зараз акції не проводяться. Ми повідомимо вам, коли розпочнеться нова акція."

    text = (
        "📜 <b>ПРАВИЛА ТА УМОВИ АКЦІЇ</b>\n\n"
        f"<b>Поточна акція:</b> {promo_info}\n\n"
        "<b>МАГАЗИНИ-УЧАСНИКИ:</b>\n"
        "• Всі магазини мережі\n\n"
        "<b>ЯК ВЗЯТИ УЧАСТЬ:</b>\n"
        "1. Зробіть покупку в магазині-партнері.\n"
        "2. Переконайтесь, що сума чеку відповідає умовам акції.\n"
        "3. Сфотографуйте чек та надішліть його в цей бот за допомогою кнопки «Зареєструвати чек».\n"
        "4. Очікуйте на результати розіграшу!\n\n"
        "📸 <b>ВИМОГИ ДО ФОТО:</b>\n"
        "• Чек має бути чітким та повністю в кадрі.\n"
        "• Без засвітів, тіней та сильних згинів.\n"
        "• Текст (дата, сума, назва магазину) має бути розбірливим.\n\n"
        "⚠️ <b>ВАЖЛИВО:</b>\n"
        "• Один чек можна зареєструвати лише один раз\n"
        "• Зберігайте оригінал чека до завершення розіграшу."
    )
    
    await _send_photo_message(callback.message, text, back_kb())
    await callback.answer()


@router.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery) -> None:
    await _send_photo_message(
        callback.message,
        "🆘 <b>Підтримка</b>\n\n" 
        "Якщо у вас виникли питання або проблеми, зверніться до нашого адміністратора: @support_user",
        back_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: CallbackQuery) -> None:
    db, settings = await _get_db_bot_settings(callback.message)
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("⛔️ Доступ заборонено", show_alert=True)
        return
    
    is_active = await promo_manager.is_promo_active(db)
    status = "🟢 Акція активна" if is_active else "🔴 Акція неактивна"
    
    await _send_photo_message(
        callback.message,
        f"Панель адміністратора.\n{status}\n\nОберіть дію:",
        admin_main_kb()
    )
    await callback.answer()


@router.message(ReceiptState.waiting_for_photo, F.photo)
async def handle_receipt_photo(message: Message, state: FSMContext) -> None:
    db, settings = await _get_db_bot_settings(message)
    user = await db.fetch_user(message.from_user.id)
    is_admin = message.from_user.id in settings.admin_ids
    
    if not user:
        await state.clear()
        await _send_photo_message(
            message,
            "❌ Спочатку зареєструйтесь за допомогою /start.",
            back_kb()
        )
        return
    if not await promo_manager.is_promo_active(db):
        await state.clear()
        await _send_photo_message(
            message,
            "🚫 Акція завершена. Нові чеки не приймаються.\n" 
            "Слідкуйте за оновленнями — нові акції вже скоро! 🎉",
            back_kb()
        )
        return

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
        try:
            await waiting_msg.delete()
        except:
            pass
        await _send_photo_message(
            message,
            "😔 <b>Не вдалося розпізнати чек.</b>\n\n" 
            "Будь ласка, переконайтесь, що:\n" 
            "• Фото чітке, а чек видно повністю та без засвітів\n" 
            "• Чек гарно освітлений і текст не стертий\n" 
            "• Дата покупки відповідає умовам акції\n\n" 
            "Спробуйте надіслати краще фото. 📸",
            back_kb()
        )
        return
    except Exception:
        log.exception("Gemini processing failed")
        try:
            await waiting_msg.delete()
        except:
            pass
        await _send_photo_message(
            message,
            "⚠️ <b>Сталася невідома помилка.</b>\n" 
            "Спробуйте, будь ласка, ще раз.",
            back_kb()
        )
        return

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
        await _send_photo_message(
            message,
            f"❌ <b>Чек не пройшов перевірку.</b>\n\n" 
            f"Причина: {reason}.\n\n" 
            "Будь ласка, перевірте умови акції та спробуйте ще раз. 🔄",
            back_kb()
        )
        return

    if result.check_code and await db.is_duplicate_check_code(result.check_code):
        log.warning("Duplicate check_code detected: %s", result.check_code)
        await _send_photo_message(
            message,
            "🧾 <b>Цей чек вже є в системі.</b>\n\n" 
            "Пам'ятайте, кожен чек унікальний і реєструється лише раз.\n" 
            "Надішліть інший, щоб продовжити.",
            back_kb()
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
    
    await _send_photo_message(
        message,
        "✅ <b>Чудово! Ваш чек зареєстровано.</b>\n\n" 
        f"<b>Магазин:</b> {result.shop or '—'}\n" 
        f"<b>Сума:</b> {amount_str} грн\n" 
        f"<b>Дата:</b> {result.date or '—'}\n\n" 
        f"Ваш номер для розіграшу: <b>#{receipt.id}</b>\n\n" 
        "Бажаємо успіху! 🍀",
        user_main_kb(is_admin=is_admin) 
    )


@router.message(ReceiptState.waiting_for_photo)
async def require_photo(message: Message) -> None:
    await message.answer(
        "Будь ласка, надішліть <b>фотографію</b>, а не текст. 📷",
        parse_mode="HTML",
    )


@router.message()
async def fallback_handler(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        db, settings = await _get_db_bot_settings(message)
        user = await db.fetch_user(message.from_user.id)
        is_admin = message.from_user.id in settings.admin_ids
        if user:
            # Re-send main menu with photo
            await _send_photo_message(
                message,
                "Використовуйте меню нижче 👇",
                user_main_kb(is_admin=is_admin)
            )
        else:
            await message.answer("Вітаю! Щоб почати, введіть команду /start")