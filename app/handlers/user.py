from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, FSInputFile, CallbackQuery

from app import promo_manager, runtime
from app.ai import analyze_receipt, ReceiptAnalysisError, ReceiptParseError
from app.excel import append_receipt, ensure_workbook
from app.keyboards import contact_request_keyboard, user_main_kb, profile_kb, back_kb, admin_main_kb
from app.keyboards.user import confirm_receipt_kb
from app.rate_limiter import check_rate_limit, remaining
from app.states import ReceiptState, RegistrationState, ProfileState


log = logging.getLogger(__name__)

router = Router()


def _fmt_date(date_str: str | None) -> str:
    """Converts YYYY-MM-DD to DD.MM.YYYY for display."""
    if not date_str:
        return "—"
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return date_str


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


async def _animate_processing(msg: Message, stop_event: asyncio.Event) -> None:
    """Циклічно оновлює повідомлення під час обробки чека."""
    frames = [
        "📷 <b>Аналізую фото чека...</b>\n<i>Це займе кілька секунд</i>",
        "🔍 <b>Розпізнаю текст...</b>\n<i>Читаю дані з чека</i>",
        "🧮 <b>Перевіряю суму та дату...</b>\n<i>Порівнюю з умовами акції</i>",
        "✨ <b>Майже готово...</b>\n<i>Завершую обробку</i>",
    ]
    idx = 0
    while not stop_event.is_set():
        try:
            await msg.edit_text(frames[idx % len(frames)], parse_mode="HTML")
        except Exception:
            break
        idx += 1
        await asyncio.sleep(2.5)


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
        "<i>Переконайтесь, що:</i>\n"
        "• <b>На фото лише чек, без сторонніх предметів</b>\n"
        "• <b>Чек займає весь екран та знаходиться у фокусі</b>\n"
        "• Чітко видно назву магазину, дату, суму та фіскальний номер",
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
    total_count, total_amount = await db.get_user_stats(user.id)

    if not receipts:
        await _send_photo_message(
            message,
            "📭 <b>У вас поки немає зареєстрованих чеків.</b>\n\n" 
            "Час це виправити! Тисніть «Зареєструвати чек» 👇",
            back_kb() 
        )
        await callback.answer()
        return

    msg_lines = [
        "🧾 <b>МОЇ ЧЕКИ</b>\n",
        f"📊 Всього: <b>{total_count}</b> чек(ів) | Сума: <b>{total_amount:.2f} грн</b>\n",
    ]
    for i, r in enumerate(receipts, 1):
        amount_str = f"{r.amount:.2f}" if r.amount else "—"
        date_str = _fmt_date(r.date)
        shop_name = r.shop if r.shop else "Невідомо"
        check_code = r.check_code if r.check_code else f"#{r.id}"

        msg_lines.append(
            f"┌─── Чек {i} ───────────\n"
            f"│ 🏪 {shop_name}\n"
            f"│ 💰 {amount_str} грн  📅 {date_str}\n"
            f"│ 🆔 <code>{check_code}</code>\n"
            f"└──────────────────────"
        )

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
        await _send_photo_message(message, "❌ Спочатку зареєструйтесь за допомогою /start.", back_kb())
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

    # Rate limiting
    if not check_rate_limit(message.from_user.id):
        left = remaining(message.from_user.id)
        await _send_photo_message(
            message,
            "⏱ <b>Забагато спроб.</b>\n\n"
            "Ви перевищили ліміт реєстрацій за сьогодні.\n"
            "Спробуйте завтра або зверніться до підтримки.",
            back_kb()
        )
        return

    waiting_msg = await message.answer(
        "📷 <b>Аналізую фото чека...</b>\n<i>Це займе кілька секунд</i>",
        parse_mode="HTML",
    )

    # Анімація під час обробки
    stop_event = asyncio.Event()
    anim_task = asyncio.create_task(_animate_processing(waiting_msg, stop_event))

    photo = message.photo[-1]
    buffer = BytesIO()
    await message.bot.download(photo, destination=buffer)
    image_bytes = buffer.getvalue()

    rules = await promo_manager.rules_for_ai(db)
    result = None
    exc = None
    try:
        result = await analyze_receipt(image_bytes, rules)
    except Exception as e:
        exc = e
    finally:
        stop_event.set()
        anim_task.cancel()
        try:
            await waiting_msg.delete()
        except Exception:
            pass

    if exc is not None:
        if isinstance(exc, ReceiptAnalysisError):
            log.warning("Receipt analysis error: %s", exc)
            err_text = str(exc)
            if "розмите" in err_text.lower():
                user_msg = (
                    "📷 <b>Фото занадто розмите.</b>\n\n"
                    "Будь ласка, зробіть нову фотографію:\n"
                    "• Тримайте телефон рівно над чеком\n"
                    "• Переконайтесь, що текст у фокусі\n"
                    "• Уникайте руху під час зйомки"
                )
            else:
                user_msg = (
                    "😔 <b>Не вдалося розпізнати чек.</b>\n\n"
                    "Переконайтесь, що:\n"
                    "• Фото чітке, чек видно повністю\n"
                    "• Немає засвітів і тіней\n"
                    "• Дата покупки відповідає умовам акції\n\n"
                    "Спробуйте надіслати краще фото. 📸"
                )
        elif isinstance(exc, ReceiptParseError):
            log.error("Receipt parse error", exc_info=exc)
            user_msg = (
                "😔 <b>Не вдалося розпізнати чек.</b>\n\n"
                "Переконайтесь, що:\n"
                "• Фото чітке, чек видно повністю\n"
                "• Немає засвітів і тіней\n"
                "• Дата покупки відповідає умовам акції\n\n"
                "Спробуйте надіслати краще фото. 📸"
            )
        else:
            log.error("Unexpected processing error: %s: %s", type(exc).__name__, exc, exc_info=exc)
            user_msg = "⚠️ <b>Сталася невідома помилка.</b>\nСпробуйте, будь ласка, ще раз."
        await _send_photo_message(message, user_msg, back_kb())
        return

    log.info(
        "Parsed receipt: shop=%s amount=%s date=%s code=%s errors=%s",
        result.shop, result.amount, result.date, result.check_code, result.errors,
    )

    # Перевірка чи магазин співпадає з активними магазинами акції
    active_shops = rules.get("allowed_shops", [])
    shop_matches = False
    
    if result.shop and active_shops:
        shop_upper = result.shop.upper()
        # Перевірка точного співпадіння або fuzzy match
        for allowed_shop in active_shops:
            if shop_upper == allowed_shop.upper():
                shop_matches = True
                break
            # Fuzzy matching (допускаємо 1 символ різниці)
            if len(shop_upper) > 2 and len(allowed_shop) > 2:
                # Проста перевірка на близькість
                diff_count = sum(1 for a, b in zip(shop_upper, allowed_shop.upper()) if a != b)
                if diff_count <= 1 and abs(len(shop_upper) - len(allowed_shop)) <= 1:
                    shop_matches = True
                    break
    
    # Якщо магазин не співпадає але чек валідний в інших аспектах - пропонуємо вибір
    if not shop_matches and active_shops and not result.is_valid:
        # Перевіряємо чи єдина помилка - це магазин або адреса
        shop_related_errors = [err for err in result.errors if any(word in err.lower() for word in ["магазин", "участь", "адреса"])]
        other_errors = [err for err in result.errors if err not in shop_related_errors]
        
        if shop_related_errors and not other_errors:
            # Тільки проблема з магазином - пропонуємо вибір
            log.info("Shop mismatch, offering selection. Detected: %s, Active: %s", result.shop, active_shops)
            
            # Хеш для дубль-перевірки
            raw_hash = hashlib.sha256(
                result.raw_text.lower().replace(" ", "").encode()
            ).hexdigest() if result.raw_text else None
            
            # Перевірка дублікатів перед вибором магазину
            if (result.check_code and await db.is_duplicate_check_code(result.check_code, result.amount)) or \
               (raw_hash and await db.is_duplicate_raw_hash(raw_hash)):
                log.warning("Duplicate receipt detected: code=%s hash=%s", result.check_code, raw_hash)
                await _send_photo_message(
                    message,
                    "🔁 <b>Цей чек вже зареєстровано.</b>\n\n"
                    "Кожен чек можна надіслати лише один раз.\n"
                    "Надішліть інший чек, щоб продовжити.",
                    back_kb()
                )
                return
            
            # Зберігаємо дані чека і переходимо до вибору магазину
            await state.set_state(ReceiptState.waiting_for_shop_selection)
            await state.update_data(
                pending_receipt={
                    "shop": result.shop,  # Розпізнаний магазин (для інформації)
                    "amount": result.amount,
                    "date": result.date,
                    "time": result.time,
                    "check_code": result.check_code,
                    "address": result.address,
                    "raw_text": result.raw_text,
                    "raw_hash": raw_hash,
                    "file_id": photo.file_id,
                }
            )
            
            detected_shop_info = f"\n\n<i>Розпізнано: {result.shop}</i>" if result.shop else ""
            
            from app.keyboards import shop_selection_kb
            await _send_photo_message(
                message,
                f"🏪 <b>Оберіть магазин з чека</b>\n\n"
                f"ШІ розпізнав назву магазину, але вона не співпадає з учасниками акції.{detected_shop_info}\n\n"
                f"Будь ласка, оберіть правильний магазин зі списку:",
                shop_selection_kb(active_shops)
            )
            return
    
    # Перевірка чи проблема тільки з датою або часом
    if not result.is_valid:
        date_related_errors = [err for err in result.errors if any(word in err.lower() for word in ["дата", "час", "період", "меж", "діапазон", "формат", "не вдалося"])]
        other_errors = [err for err in result.errors if err not in date_related_errors]
        
        if date_related_errors and not other_errors:
            # Тільки проблема з датою/часом - пропонуємо ввести вручну
            log.info("Date/Time mismatch, requesting manual input. Detected: date=%s, time=%s", result.date, result.time)
            
            # Хеш для дубль-перевірки
            raw_hash = hashlib.sha256(
                result.raw_text.lower().replace(" ", "").encode()
            ).hexdigest() if result.raw_text else None
            
            # Перевірка дублікатів перед вводом дати
            if (result.check_code and await db.is_duplicate_check_code(result.check_code, result.amount)) or \
               (raw_hash and await db.is_duplicate_raw_hash(raw_hash)):
                log.warning("Duplicate receipt detected: code=%s hash=%s", result.check_code, raw_hash)
                await _send_photo_message(
                    message,
                    "🔁 <b>Цей чек вже зареєстровано.</b>\n\n"
                    "Кожен чек можна надіслати лише один раз.\n"
                    "Надішліть інший чек, щоб продовжити.",
                    back_kb()
                )
                return
            
            # Зберігаємо дані чека і переходимо до вводу дати
            await state.set_state(ReceiptState.waiting_for_date_input)
            await state.update_data(
                pending_receipt={
                    "shop": result.shop,
                    "amount": result.amount,
                    "date": result.date,  # Розпізнана дата (для інформації)
                    "time": result.time,
                    "check_code": result.check_code,
                    "address": result.address,
                    "raw_text": result.raw_text,
                    "raw_hash": raw_hash,
                    "file_id": photo.file_id,
                }
            )
            
            detected_date_info = f"\n\n<i>Розпізнано: {_fmt_date(result.date)}</i>" if result.date else ""
            
            # Отримуємо період акції
            start_date = rules.get("start_date")
            end_date = rules.get("end_date")
            period_info = ""
            if start_date and end_date:
                period_info = f"\n📅 Період акції: <b>{_fmt_date(start_date)} - {_fmt_date(end_date)}</b>"
            
            from app.keyboards import date_input_kb
            await _send_photo_message(
                message,
                f"📅 <b>Введіть дату з чека</b>\n\n"
                f"ШІ розпізнав дату, але вона не входить в період акції.{detected_date_info}{period_info}\n\n"
                f"Будь ласка, введіть правильну дату у форматі <b>ДД.ММ.РРРР</b>\n"
                f"Наприклад: <code>15.01.2026</code>",
                date_input_kb()
            )
            return
    
    if not result.is_valid:
        reason = result.errors[0] if result.errors else "Чек не пройшов перевірку"
        log.warning("Receipt invalid: %s", reason)
        await _send_photo_message(
            message,
            f"❌ <b>Чек не прийнято</b>\n\n"
            f"<b>Причина:</b> {reason}\n\n"
            "Перевірте умови акції та спробуйте ще раз. 🔄",
            back_kb()
        )
        return

    # Хеш тексту для дубль-перевірки
    raw_hash = hashlib.sha256(
        result.raw_text.lower().replace(" ", "").encode()
    ).hexdigest() if result.raw_text else None

    # Дублікат по коду або по тексту
    if (result.check_code and await db.is_duplicate_check_code(result.check_code, result.amount)) or \
       (raw_hash and await db.is_duplicate_raw_hash(raw_hash)):
        log.warning("Duplicate receipt detected: code=%s hash=%s", result.check_code, raw_hash)
        await _send_photo_message(
            message,
            "🔁 <b>Цей чек вже зареєстровано.</b>\n\n"
            "Кожен чек можна надіслати лише один раз.\n"
            "Надішліть інший чек, щоб продовжити.",
            back_kb()
        )
        return

    # Зберігаємо в стані і просимо підтвердити
    await state.set_state(ReceiptState.waiting_for_confirm)
    await state.update_data(
        pending_receipt={
            "shop": result.shop,
            "amount": result.amount,
            "date": result.date,
            "time": result.time,
            "check_code": result.check_code,
            "address": result.address,
            "raw_text": result.raw_text,
            "raw_hash": raw_hash,
            "file_id": photo.file_id,
        }
    )

    amount_str = f"{result.amount:.2f}" if result.amount else "—"
    date_str = _fmt_date(result.date)
    shop_str = result.shop or "—"

    await _send_photo_message(
        message,
        "🔍 <b>Перевірте дані чека</b>\n\n"
        f"🏪 <b>{shop_str}</b>\n"
        f"💰 {amount_str} грн\n"
        f"📅 {date_str}\n\n"
        "Все правильно?",
        confirm_receipt_kb()
    )


@router.callback_query(ReceiptState.waiting_for_confirm, F.data == "receipt:confirm")
async def confirm_receipt(callback: CallbackQuery, state: FSMContext) -> None:
    db, settings = await _get_db_bot_settings(callback.message)
    user = await db.fetch_user(callback.from_user.id)
    is_admin = callback.from_user.id in settings.admin_ids

    data = await state.get_data()
    pending = data.get("pending_receipt")
    if not pending or not user:
        await state.clear()
        await callback.answer("Сесія застаріла, спробуйте ще раз.", show_alert=True)
        return

    receipt = await db.insert_check(
        user_id=user.id,
        shop=pending.get("shop"),
        amount=pending.get("amount"),
        date=pending.get("date"),
        time=pending.get("time"),
        check_code=pending.get("check_code"),
        file_id=pending["file_id"],
        raw_text=pending.get("raw_text", ""),
        raw_text_hash=pending.get("raw_hash"),
    )

    ensure_workbook(settings.excel_path)
    append_receipt(settings.excel_path, receipt, user, callback.from_user.username)
    log.info("Receipt saved: id=%s user_id=%s shop=%s amount=%s", receipt.id, user.id, pending.get("shop"), pending.get("amount"))

    await state.clear()
    amount_str = f"{pending['amount']:.2f}" if pending.get("amount") else "—"
    date_str = _fmt_date(pending.get("date"))
    shop_str = pending.get("shop") or "—"

    await _send_photo_message(
        callback.message,
        "🎉 <b>Чек успішно зареєстровано!</b>\n\n"
        f"🏪 <b>{shop_str}</b>\n"
        f"💰 {amount_str} грн\n"
        f"📅 {date_str}\n\n"
        f"🎟 Ваш номер у розіграші: <b>#{receipt.id}</b>\n\n"
        "Бажаємо удачі! 🍀",
        user_main_kb(is_admin=is_admin)
    )
    await callback.answer()


@router.callback_query(ReceiptState.waiting_for_confirm, F.data == "receipt:retry")
async def retry_receipt_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ReceiptState.waiting_for_photo)
    await _send_photo_message(
        callback.message,
        "📸 <b>Надішліть нове фото чека</b>\n\n"
        "<i>Переконайтесь, що текст чітко видно</i>",
        back_kb()
    )
    await callback.answer()


@router.callback_query(ReceiptState.waiting_for_shop_selection, F.data.startswith("select_shop:"))
async def handle_shop_selection(callback: CallbackQuery, state: FSMContext) -> None:
    """Обробка вибору магазину користувачем"""
    db, settings = await _get_db_bot_settings(callback.message)
    user = await db.fetch_user(callback.from_user.id)
    
    # Витягуємо назву обраного магазину з callback_data
    selected_shop = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    pending = data.get("pending_receipt")
    
    if not pending or not user:
        await state.clear()
        await callback.answer("Сесія застаріла, спробуйте ще раз.", show_alert=True)
        return
    
    # Оновлюємо магазин на обраний користувачем
    pending["shop"] = selected_shop
    
    log.info(
        "User %s manually selected shop: %s (was: %s)",
        user.telegram_id, selected_shop, pending.get("shop")
    )
    
    # Перевірка чи дата в межах акції
    from datetime import datetime
    rules = await promo_manager.rules_for_ai(db)
    start_date_str = rules.get("start_date")
    end_date_str = rules.get("end_date")
    date_valid = True
    
    if pending.get("date") and start_date_str and end_date_str:
        try:
            receipt_date = datetime.strptime(pending["date"], "%Y-%m-%d").date()
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            
            if not (start_date <= receipt_date <= end_date):
                date_valid = False
        except ValueError:
            date_valid = False
    
    # Якщо дата невалідна - запитуємо її вручну
    if not date_valid:
        log.info("Date still invalid after shop selection, requesting manual input")
        await state.set_state(ReceiptState.waiting_for_date_input)
        await state.update_data(pending_receipt=pending)
        
        detected_date_info = f"\n\n<i>Розпізнано: {_fmt_date(pending.get('date'))}</i>" if pending.get('date') else ""
        period_info = ""
        if start_date_str and end_date_str:
            period_info = f"\n📅 Період акції: <b>{_fmt_date(start_date_str)} - {_fmt_date(end_date_str)}</b>"
        
        from app.keyboards import date_input_kb
        await _send_photo_message(
            callback.message,
            f"📅 <b>Введіть дату з чека</b>\n\n"
            f"Магазин обрано, але дата не входить в період акції.{detected_date_info}{period_info}\n\n"
            f"Будь ласка, введіть правильну дату у форматі <b>ДД.ММ.РРРР</b>\n"
            f"Наприклад: <code>15.01.2026</code>",
            date_input_kb()
        )
        await callback.answer("✅ Магазин обрано, введіть дату")
        return
    
    # Переходимо до підтвердження
    await state.set_state(ReceiptState.waiting_for_confirm)
    await state.update_data(pending_receipt=pending)
    
    amount_str = f"{pending['amount']:.2f}" if pending.get('amount') else "—"
    date_str = _fmt_date(pending.get('date'))
    
    await _send_photo_message(
        callback.message,
        "🔍 <b>Перевірте дані чека</b>\n\n"
        f"🏪 <b>{selected_shop}</b>\n"
        f"💰 {amount_str} грн\n"
        f"📅 {date_str}\n\n"
        "Все правильно?",
        confirm_receipt_kb()
    )
    await callback.answer(f"✅ Обрано: {selected_shop}")


@router.message(ReceiptState.waiting_for_date_input, F.text)
async def handle_date_input(message: Message, state: FSMContext) -> None:
    """Обробка введення дати користувачем"""
    from datetime import datetime
    
    db, settings = await _get_db_bot_settings(message)
    user = await db.fetch_user(message.from_user.id)
    
    data = await state.get_data()
    pending = data.get("pending_receipt")
    
    if not pending or not user:
        await state.clear()
        await _send_photo_message(message, "Сесія застаріла, спробуйте ще раз.", back_kb())
        return
    
    date_text = message.text.strip()
    
    # Спроба парсити дату у форматі ДД.ММ.РРРР
    parsed_date = None
    try:
        parsed_date = datetime.strptime(date_text, "%d.%m.%Y")
    except ValueError:
        # Спроба альтернативних форматів
        for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]:
            try:
                parsed_date = datetime.strptime(date_text, fmt)
                break
            except ValueError:
                continue
    
    if not parsed_date:
        await _send_photo_message(
            message,
            "❌ <b>Неправильний формат дати</b>\n\n"
            "Будь ласка, введіть дату у форматі <b>ДД.ММ.РРРР</b>\n"
            "Наприклад: <code>15.01.2026</code>",
            back_kb()
        )
        return
    
    # Перевірка чи дата в межах акції
    rules = await promo_manager.rules_for_ai(db)
    start_date_str = rules.get("start_date")
    end_date_str = rules.get("end_date")
    
    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        
        if not (start_date <= parsed_date.date() <= end_date):
            await _send_photo_message(
                message,
                f"❌ <b>Дата поза межами акції</b>\n\n"
                f"📅 Період акції: <b>{_fmt_date(start_date_str)} - {_fmt_date(end_date_str)}</b>\n\n"
                f"Введена дата: <b>{parsed_date.strftime('%d.%m.%Y')}</b>\n\n"
                f"Будь ласка, введіть дату яка входить в період акції:",
                back_kb()
            )
            return
    
    # Оновлюємо дату на введену користувачем
    pending["date"] = parsed_date.strftime("%Y-%m-%d")
    
    log.info(
        "User %s manually entered date: %s (was: %s)",
        user.telegram_id, pending["date"], data.get("pending_receipt", {}).get("date")
    )
    
    # Переходимо до підтвердження
    await state.set_state(ReceiptState.waiting_for_confirm)
    await state.update_data(pending_receipt=pending)
    
    amount_str = f"{pending['amount']:.2f}" if pending.get('amount') else "—"
    date_str = _fmt_date(pending.get('date'))
    shop_str = pending.get('shop') or "—"
    
    await _send_photo_message(
        message,
        "🔍 <b>Перевірте дані чека</b>\n\n"
        f"🏪 <b>{shop_str}</b>\n"
        f"💰 {amount_str} грн\n"
        f"📅 {date_str}\n\n"
        "Все правильно?",
        confirm_receipt_kb()
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