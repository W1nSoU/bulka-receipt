from __future__ import annotations

import aiosqlite
import logging
import random
from datetime import datetime
from typing import List

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import promo_manager, runtime, shops_manager
from app.config import Settings
from app.db import Database
from app.excel import ensure_workbook
from app.keyboards import (
    admin_main_kb,
    admin_settings_kb,
    admin_shops_kb,
    admin_stats_kb,
    admin_winner_kb,
    shops_delete_kb,
    shops_toggle_kb,
    stats_shop_exclude_kb,
    stats_shop_exclude_confirm_kb,
    cancel_kb,
    back_cancel_kb,
)
from app.states import (
    AdminAddShopState,
    AdminContinueCampaignState,
    AdminEditShopState,
    AdminSearchState,
    AdminSetChannelState,
    AdminSetDatesState,
    AdminSetMinAmountState,
    AdminSetTimeRangeState,
    AdminStartCampaignStates,
    AdminStatsByPeriodStates,
    AdminWinnerState,
)


log = logging.getLogger(__name__)


class AdminFilter(BaseFilter):
    def __init__(self, admin_ids: List[int]):
        self.admin_ids = admin_ids

    async def __call__(self, message: Message) -> bool:  # type: ignore[override]
        return message.from_user and message.from_user.id in self.admin_ids


class AdminCallbackFilter(BaseFilter):
    def __init__(self, admin_ids: List[int]):
        self.admin_ids = admin_ids

    async def __call__(self, callback: CallbackQuery) -> bool:  # type: ignore[override]
        return callback.from_user and callback.from_user.id in self.admin_ids


router = Router()
TELEGRAM_CAPTION_MAX_LEN = 1024
TELEGRAM_MESSAGE_MAX_LEN = 4096
SHOPS_EXCLUDE_PAGE_SIZE = 10


async def _context() -> tuple[Database, Settings]:
    return runtime.get_db(), runtime.get_settings()


def _split_message_chunks(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(line) > max_len:
            if current:
                chunks.append(current.rstrip("\n"))
                current = ""
            for i in range(0, len(line), max_len):
                chunks.append(line[i : i + max_len].rstrip("\n"))
            continue
        if current and len(current) + len(line) > max_len:
            chunks.append(current.rstrip("\n"))
            current = line
            continue
        current += line

    if current:
        chunks.append(current.rstrip("\n"))

    return chunks or [text[:max_len]]


async def _send_admin_text_message(
    message: Message,
    text: str,
    reply_markup=None,
    state: FSMContext = None,
):
    chunks = _split_message_chunks(text, TELEGRAM_MESSAGE_MAX_LEN)
    sent = await message.answer(chunks[0], reply_markup=reply_markup)
    for chunk in chunks[1:]:
        await message.answer(chunk)
    if state:
        await state.update_data(bot_msg_id=sent.message_id)
    return sent


async def _send_admin_photo_message(message: Message, text: str, reply_markup=None, state: FSMContext = None, edit: bool = False):
    """
    Sends or edits a photo message with sakura.jpg.
    - If edit=True (Buttons): Tries to edit the message caption.
    - If edit=False (Text Input): Deletes user message, DELETES previous bot message, and sends NEW bot message.
    """
    photo_path = "photo/sakura.jpg"
    photo = FSInputFile(photo_path)
    
    # 1. Handle Text Input (User sent a message) -> Delete & Send New
    if state and not edit:
        # Delete user's text input
        try:
            await message.delete()
        except Exception:
            pass
            
        data = await state.get_data()
        prev_bot_msg_id = data.get("bot_msg_id")
        
        # Delete previous bot message
        if prev_bot_msg_id:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=prev_bot_msg_id)
            except Exception:
                pass
        
        # Send NEW message
        if len(text) > TELEGRAM_CAPTION_MAX_LEN:
            return await _send_admin_text_message(message, text, reply_markup=reply_markup, state=state)
        sent = await message.answer_photo(photo, caption=text, reply_markup=reply_markup)
        await state.update_data(bot_msg_id=sent.message_id)
        return sent

    # 2. Handle Callback (Button click) -> Edit existing
    if edit:
        if len(text) > TELEGRAM_CAPTION_MAX_LEN:
            try:
                await message.delete()
            except Exception:
                pass
            return await _send_admin_text_message(message, text, reply_markup=reply_markup, state=state)
        try:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
            # Ensure bot_msg_id is up to date in state
            if state:
                await state.update_data(bot_msg_id=message.message_id)
            return message
        except Exception:
            # Edit failed (e.g. message too old), fall back to delete & send
            pass

    # 3. Fallback (Start command, or edit failed) -> Delete previous (if known or context) & Send New
    
    # If we tried to edit and failed, try to delete that message first to avoid duplicates
    if edit:
        try:
            await message.delete()
        except Exception:
            pass
    
    if len(text) > TELEGRAM_CAPTION_MAX_LEN:
        return await _send_admin_text_message(message, text, reply_markup=reply_markup, state=state)
    sent = await message.answer_photo(photo, caption=text, reply_markup=reply_markup)
    if state:
        await state.update_data(bot_msg_id=sent.message_id)
    return sent


async def _show_admin_main(message: Message, state: FSMContext = None) -> None:
    db, _ = await _context()
    is_active = await promo_manager.is_promo_active(db)
    status = "🟢 Акція активна" if is_active else "🔴 Акція неактивна"
    await _send_admin_photo_message(
        message,
        f"Панель адміністратора.\n{status}\n\nОберіть дію:",
        reply_markup=admin_main_kb(),
        edit=True,
        state=state
    )


async def _show_settings_menu(message: Message, state: FSMContext = None) -> None:
    await _send_admin_photo_message(message, "⚙️ <b>Налаштування акції</b>\n\nОберіть параметр:", reply_markup=admin_settings_kb(), edit=True, state=state)


async def _show_shops_menu(message: Message, state: FSMContext = None) -> None:
    await _send_admin_photo_message(message, "🏬 <b>Магазини-партнери</b>\n\nОберіть дію:", reply_markup=admin_shops_kb(), edit=True, state=state)


async def _show_shops_selection(message: Message, state: FSMContext, edit: bool = False) -> None:
    db, _ = await _context()
    shops = await db.list_shops()
    data = await state.get_data()
    selected = data.get("selected_shops", [])
    await _send_admin_photo_message(
        message,
        "Оберіть магазини для акції (🟢 - обрано, 🔴 - не обрано):",
        reply_markup=_shops_wizard_kb(shops, selected).as_markup(),
        edit=edit,
        state=state
    )


async def _do_campaign_start(db: Database, settings: Settings) -> None:
    await db.clear_checks()
    await promo_manager.set_promo_active(db, True)
    path = settings.excel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    ensure_workbook(path)


@router.message(Command("admin"))
async def admin_entry(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _send_admin_photo_message(message, "Панель адміністратора. Оберіть дію:", reply_markup=admin_main_kb(), state=state)


@router.callback_query(F.data == "admin:main")
async def admin_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    # Pass state to ensure bot_msg_id is updated
    await _show_admin_main(callback.message, state)
    await callback.answer()


# --- Start campaign wizard ---

async def _start_campaign_wizard(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminStartCampaignStates.start_date)
    await _send_admin_photo_message(
        message,
        "Введіть дату початку акції у форматі дд.мм.рррр",
        reply_markup=cancel_kb("admin:start:cancel"),
        edit=True,
        state=state
    )


@router.callback_query(F.data == "admin:start:cancel")
async def admin_start_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _show_admin_main(callback.message, state)


def _parse_date(text: str) -> str | None:
    try:
        dt = datetime.strptime(text.strip(), "%d.%m.%Y").date()
        return dt.isoformat()
    except ValueError:
        return None


def _parse_time(text: str) -> str | None:
    try:
        t = datetime.strptime(text.strip(), "%H:%M").time()
        return t.strftime("%H:%M")
    except ValueError:
        return None


def _minutes(time_str: str) -> int:
    t = datetime.strptime(time_str, "%H:%M").time()
    return t.hour * 60 + t.minute


def _shops_wizard_kb(shops: list[tuple[int, str]], selected: list[int]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    selected_set = set(selected or [])
    for shop_id, name in shops:
        flag = "🟢" if shop_id in selected_set else "🔴"
        kb.button(text=f"{name} {flag}", callback_data=f"admin:start:shop:{shop_id}")
    kb.button(text="⬅️ Назад", callback_data="admin:start:back:end_time")
    kb.button(text="❌ Скасувати", callback_data="admin:start:cancel")
    kb.button(text="✅ Далі", callback_data="admin:start:shops_next")
    kb.adjust(1)
    return kb


@router.callback_query(F.data == "admin:settings")
async def admin_settings(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show_settings_menu(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "admin:shops")
async def admin_shops(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show_shops_menu(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "admin:campaign_start")
async def admin_campaign_start(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    if await promo_manager.is_promo_active(db):
        await _send_admin_photo_message(
            callback.message,
            "Зараз вже активна акція. Спочатку зупиніть поточну акцію, щоб запустити нову.",
            reply_markup=admin_main_kb(),
            edit=True,
            state=state
        )
        await callback.answer()
        return
    await callback.answer()
    await _start_campaign_wizard(callback.message, state)


@router.callback_query(F.data == "admin:campaign_stop")
async def admin_campaign_stop(callback: CallbackQuery, state: FSMContext) -> None:
    db, settings = await _context()
    await promo_manager.set_promo_active(db, False)
    await _send_admin_photo_message(callback.message, "Акцію зупинено. Формуємо файл...", reply_markup=admin_main_kb(), edit=True, state=state)
    if settings.excel_path.exists():
        doc = FSInputFile(settings.excel_path)
        failed: list[int] = []
        for admin_id in settings.admin_ids:
            try:
                await callback.message.bot.send_document(admin_id, doc)
            except TelegramForbiddenError:
                log.warning("Cannot send document to admin_id=%s: forbidden (no chat)", admin_id)
                failed.append(admin_id)
            except TelegramBadRequest:
                log.warning("Failed to send document to admin_id=%s", admin_id)
                failed.append(admin_id)
        if failed:
            await _send_admin_photo_message(
                callback.message,
                "Файл надіслано, але деяким адміністраторам не доставлено (chat not found).",
                reply_markup=admin_main_kb(),
                edit=True,
                state=state
            )
        else:
            await _send_admin_photo_message(
                callback.message,
                "Акцію зупинено. Файл надіслано адміністраторам.",
                reply_markup=admin_main_kb(),
                edit=True,
                state=state
            )
    else:
        await _send_admin_photo_message(callback.message, "Файл відсутній.", reply_markup=admin_main_kb(), edit=True, state=state)
    await callback.answer()


@router.callback_query(F.data == "admin:campaign_continue")
async def admin_campaign_continue(callback: CallbackQuery, state: FSMContext) -> None:
    """Продовжити акцію - архівувати поточну та створити нову"""
    db, _ = await _context()
    
    # Перевіряємо чи активна акція
    is_active = await promo_manager.is_promo_active(db)
    
    # Підраховуємо чеки без campaign_id
    uncategorized_count = await db._fetchone("SELECT COUNT(*) FROM checks WHERE campaign_id IS NULL")
    checks_count = uncategorized_count[0] if uncategorized_count else 0
    
    # Отримуємо поточні налаштування
    current_settings = await db.get_settings_map()
    start_date = current_settings.get("start_date", "")
    end_date = current_settings.get("end_date", "")
    min_amount = current_settings.get("min_amount", 0)
    active_shops = current_settings.get("active_shops", [])
    
    from app.states import AdminContinueCampaignState
    await state.set_state(AdminContinueCampaignState.waiting_for_name)
    await state.update_data(
        old_start=start_date,
        old_end=end_date,
        old_min_amount=min_amount,
        old_shops=active_shops,
        checks_count=checks_count
    )
    
    from app.keyboards import cancel_kb
    await _send_admin_photo_message(
        callback.message,
        f"📦 <b>Продовження акції</b>\n\n"
        f"{'🟢 Акція активна' if is_active else '🔴 Акція зупинена'}\n"
        f"📊 Чеків без категорії: <b>{checks_count}</b>\n\n"
        f"Поточні налаштування:\n"
        f"📅 Період: {start_date} – {end_date}\n"
        f"💰 Мін. сума: {min_amount} грн\n"
        f"🏬 Магазини: {', '.join(active_shops) if active_shops else 'немає'}\n\n"
        f"Введіть назву нової акції\n"
        f"<i>(наприклад: \"Акція Лютий 2026\")</i>:",
        reply_markup=cancel_kb("admin:main"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.message(AdminContinueCampaignState.waiting_for_name, F.text)
async def admin_campaign_continue_name(message: Message, state: FSMContext) -> None:
    from app.states import AdminContinueCampaignState
    
    campaign_name = message.text.strip()
    data = await state.get_data()
    
    await state.update_data(campaign_name=campaign_name)
    await state.set_state(AdminContinueCampaignState.waiting_for_confirmation)
    
    from app.keyboards import back_cancel_kb
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Так, продовжити", callback_data="admin:campaign_continue:confirm")
    kb.button(text="❌ Скасувати", callback_data="admin:main")
    kb.adjust(1)
    
    await _send_admin_photo_message(
        message,
        f"📦 <b>Підтвердження продовження акції</b>\n\n"
        f"Буде виконано:\n"
        f"1️⃣ Поточні чеки ({data['checks_count']}) будуть прив'язані до поточної акції\n"
        f"2️⃣ Поточна акція буде заархівована\n"
        f"3️⃣ Створена нова акція: <b>{campaign_name}</b>\n"
        f"4️⃣ Налаштування скопійовані з поточної:\n"
        f"   📅 {data['old_start']} – {data['old_end']}\n"
        f"   💰 {data['old_min_amount']} грн\n"
        f"   🏬 {', '.join(data['old_shops']) if data['old_shops'] else 'немає'}\n\n"
        f"<b>Після створення ви зможете змінити ці налаштування в меню</b>\n\n"
        f"Продовжити?",
        reply_markup=kb.as_markup(),
        state=state
    )


@router.callback_query(F.data == "admin:campaign_continue:confirm")
async def admin_campaign_continue_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    data = await state.get_data()
    
    try:
        # 1. Створюємо нову кампанію з поточними налаштуваннями
        campaign_id = await db.create_campaign(
            name=data['campaign_name'],
            start_date=data['old_start'],
            end_date=data['old_end'],
            min_amount=float(data['old_min_amount']),
            shops=data['old_shops']
        )
        
        # 2. Прив'язуємо всі чеки без campaign_id до попередньої акції
        if data['checks_count'] > 0:
            # Створюємо архівну акцію для старих чеків
            old_campaign_id = await db.create_campaign(
                name=f"Архівна акція до {data['campaign_name']}",
                start_date=data['old_start'],
                end_date=data['old_end'],
                min_amount=float(data['old_min_amount']),
                shops=data['old_shops']
            )
            await db.assign_checks_to_campaign(old_campaign_id)
            await db.archive_current_campaign()  # Архівуємо стару
            
            # Робимо нову поточною
            async with aiosqlite.connect(db.path) as conn:
                await conn.execute("UPDATE campaigns SET is_current = 1 WHERE id = ?", (campaign_id,))
                await conn.commit()
        
        # 3. Скидаємо кеш
        promo_manager.invalidate_rules_cache()
        
        await _send_admin_photo_message(
            callback.message,
            f"✅ <b>Акцію продовжено!</b>\n\n"
            f"📦 Створено нову акцію: <b>{data['campaign_name']}</b>\n"
            f"📊 Старих чеків збережено: {data['checks_count']}\n\n"
            f"Налаштування скопійовані. Ви можете змінити їх в меню ⚙️ Налаштування.",
            reply_markup=admin_main_kb(),
            edit=True,
            state=state
        )
        await state.clear()
        
    except Exception as e:
        log.error("Error continuing campaign: %s", e)
        await _send_admin_photo_message(
            callback.message,
            f"❌ Помилка при продовженні акції: {str(e)}",
            reply_markup=admin_main_kb(),
            edit=True,
            state=state
        )
        await state.clear()
    
    await callback.answer()


@router.callback_query(F.data == "admin:campaign_history")
async def admin_campaign_history(callback: CallbackQuery, state: FSMContext) -> None:
    """Показує історію акцій"""
    db, _ = await _context()
    
    campaigns = await db.get_campaigns_history()
    
    if not campaigns:
        await _send_admin_photo_message(
            callback.message,
            "📜 <b>Історія акцій</b>\n\nАкцій ще немає.",
            reply_markup=admin_main_kb(),
            edit=True,
            state=state
        )
    else:
        lines = ["📜 <b>Історія акцій</b>\n"]
        for campaign_id, name, start_date, end_date, checks_count, is_current in campaigns:
            status = "🟢 ПОТОЧНА" if is_current else "📦 Архівна"
            lines.append(
                f"\n{status}\n"
                f"<b>{name}</b>\n"
                f"📅 {start_date} – {end_date}\n"
                f"📊 Чеків: {checks_count}"
            )
        
        await _send_admin_photo_message(
            callback.message,
            "\n".join(lines),
            reply_markup=admin_main_kb(),
            edit=True,
            state=state
        )
    
    await callback.answer()


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery, state: FSMContext) -> None:
    await _send_admin_photo_message(
        callback.message,
        "Статистика. Оберіть, що саме ви хочете переглянути:",
        reply_markup=admin_stats_kb(),
        edit=True,
        state=state
    )
    await callback.answer()


@router.callback_query(F.data == "admin:winner")
async def admin_winner(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _send_admin_photo_message(
        callback.message,
        "🎯 <b>Вибір переможців</b>\n\n" "Натисніть кнопку, щоб обрати переможців серед зареєстрованих чеків.",
        reply_markup=admin_winner_kb(),
        edit=True,
        state=state
    )
    await callback.answer()


@router.callback_query(F.data == "admin:winner:by_receipt")
async def admin_winner_by_receipt(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    total_participants = await db.count_unique_participants()
    if total_participants == 0:
        await _send_admin_photo_message(
            callback.message,
            "❌ <b>Немає жодного учасника з чеком</b>\n\nДочекайтесь, поки учасники зареєструють чеки.",
            reply_markup=admin_winner_kb(),
            edit=True,
            state=state
        )
        await callback.answer()
        return
    await state.set_state(AdminWinnerState.waiting_for_count)
    await _send_admin_photo_message(
        callback.message,
        (
            "🎟 <b>Вибір переможців</b>\n\n"
            f"Унікальних учасників з чеками: <b>{total_participants}</b>\n\n"
            f"Введіть кількість переможців (від 1 до {total_participants}):"
        ),
        edit=True,
        state=state
    )
    await callback.answer()


def _winner_confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🟢 Так, завершити", callback_data="admin:winner:finish_yes")
    kb.button(text="🔴 Ні, продовжити", callback_data="admin:winner:finish_no")
    kb.adjust(2)
    return kb.as_markup()


def _winner_reselect_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обрати знову", callback_data="admin:winner:by_receipt")
    kb.button(text="⬅️ Назад", callback_data="admin:winner")
    kb.adjust(1)
    return kb.as_markup()

def _winner_done_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Повернутися в панель", callback_data="admin:main")
    kb.adjust(1)
    return kb.as_markup()


@router.message(AdminWinnerState.waiting_for_count, F.text)
async def admin_winner_count(message: Message, state: FSMContext) -> None:
    db, _ = await _context()
    try:
        count = int(message.text.strip())
    except ValueError:
        await _send_admin_photo_message(message, "❌ Введіть число.", state=state)
        return
    
    total_participants = await db.count_unique_participants()
    if count < 1 or count > total_participants:
        await _send_admin_photo_message(message, f"❌ Введіть число від 1 до {total_participants}.", state=state)
        return
    
    # Вибираємо випадкових переможців без повторення людей
    winner_pairs = await db.random_winners_by_unique_users(count)
    if len(winner_pairs) != count:
        await state.clear()
        await _send_admin_photo_message(message, "❌ Не вдалося обрати переможців.", reply_markup=admin_winner_kb(), state=state)
        return
    
    winners_data = []
    for place, (receipt, user) in enumerate(winner_pairs, 1):
        winners_data.append({
            "place": place,
            "receipt_id": receipt.id,
            "full_name": user.full_name if user else "Невідомо",
            "phone": user.phone if user else "",
            "telegram_id": user.telegram_id if user else None,
            "check_code": receipt.check_code or str(receipt.id),
            "amount": receipt.amount or 0,
        })
    
    await state.update_data(winners=winners_data)
    
    # Формуємо список переможців
    lines = ["🏆 <b>ПЕРЕМОЖЦІ РОЗІГРАШУ</b>\n"]
    for w in winners_data:
        lines.append(f"{w['place']}. {w['full_name']}")
        lines.append(f"   📞 {w['phone']}")
        lines.append(f"   🎫 Чек: #{w['check_code']}")
        lines.append(f"   💰 {w['amount']:.2f} грн\n")
    
    lines.append("\n<b>Завершити акцію?</b>")
    
    await _send_admin_photo_message(
        message,
        "\n".join(lines),
        reply_markup=_winner_confirm_kb(),
        state=state
    )


@router.callback_query(F.data == "admin:winner:finish_no")
async def admin_winner_finish_no(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    winners = data.get("winners", [])
    
    # Показуємо список з кнопками перевибору
    lines = ["🏆 <b>ПЕРЕМОЖЦІ РОЗІГРАШУ</b>\n"]
    for w in winners:
        lines.append(f"{w['place']}. {w['full_name']}, {w['phone']}, #{w['check_code']}, {w['amount']:.2f} грн")
    
    await state.clear()
    await _send_admin_photo_message(
        callback.message,
        "\n".join(lines),
        reply_markup=_winner_reselect_kb(),
        edit=True,
        state=state
    )
    await callback.answer()


@router.callback_query(F.data == "admin:winner:finish_yes")
async def admin_winner_finish_yes(callback: CallbackQuery, state: FSMContext) -> None:
    db, settings = await _context()
    data = await state.get_data()
    winners = data.get("winners", [])

    if not winners:
        await state.clear()
        await _send_admin_photo_message(
            callback.message,
            "❌ Немає сформованого списку переможців. Оберіть переможців ще раз.",
            reply_markup=admin_winner_kb(),
            edit=True,
            state=state,
        )
        await callback.answer()
        return
    
    # Формуємо повідомлення про переможців
    lines = ["🏆 <b>ПЕРЕМОЖЦІ РОЗІГРАШУ</b>\n"]
    for w in winners:
        lines.append(f"{w['place']}. {w['full_name']}, {w['phone']}, #{w['check_code']}, {w['amount']:.2f} грн")
    
    winners_text = "\n".join(lines)

    notified = 0
    for w in winners:
        telegram_id = w.get("telegram_id")
        if telegram_id is None:
            continue
        try:
            await callback.message.bot.send_message(
                int(telegram_id),
                (
                    "🎉 Вітаємо!\n\n"
                    f"Ви посіли <b>{w['place']}</b> місце у розіграші.\n"
                    f"Ваш чек: <b>#{w['check_code']}</b>."
                ),
            )
            notified += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            log.warning("Failed to notify winner telegram_id=%s place=%s", telegram_id, w.get("place"))
    
    # Спочатку відправляємо файл звіту
    await promo_manager.set_promo_active(db, False)
    
    if settings.excel_path.exists():
        doc = FSInputFile(settings.excel_path)
        failed: list[int] = []
        for admin_id in settings.admin_ids:
            try:
                await callback.message.bot.send_document(admin_id, doc)
            except (TelegramForbiddenError, TelegramBadRequest):
                log.warning("Failed to send document to admin_id=%s", admin_id)
                failed.append(admin_id)
    
    await state.clear()
    
    await _send_admin_photo_message(
        callback.message,
        (
            "✅ <b>Акцію завершено!</b>\n\n"
            f"{winners_text}\n\n"
            f"👤 Повідомлено переможців: {notified}/{len(winners)}\n"
            "📄 Файл звіту надіслано адміністраторам."
        ),
        reply_markup=_winner_done_kb(),
        edit=True,
        state=state
    )
    await callback.answer()


@router.callback_query(F.data == "admin:settings:period")
async def admin_settings_period(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminSetDatesState.waiting_for_start)
    await _send_admin_photo_message(
        callback.message,
        "📅 Введіть дату початку у форматі <b>ДД.ММ.РРРР</b>",
        reply_markup=cancel_kb("admin:settings"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.callback_query(F.data == "admin:settings:min_amount")
async def admin_settings_min(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminSetMinAmountState.waiting_for_amount)
    await _send_admin_photo_message(
        callback.message,
        "💰 Введіть мінімальну суму покупки (наприклад: 500)",
        reply_markup=cancel_kb("admin:settings"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.callback_query(F.data == "admin:settings:time")
async def admin_settings_time(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminSetTimeRangeState.waiting_for_start)
    await _send_admin_photo_message(
        callback.message,
        "⏰ Вкажіть час початку у форматі <b>ГГ:ХХ</b>",
        reply_markup=cancel_kb("admin:settings"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.callback_query(F.data == "admin:settings:search")
async def admin_settings_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminSearchState.waiting_for_query)
    await _send_admin_photo_message(
        callback.message,
        "🔍 Введіть телефон, ПІБ або код чеку",
        reply_markup=cancel_kb("admin:settings"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.callback_query(F.data == "admin:settings:channel")
async def admin_settings_channel(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    current = await promo_manager.get_telegram_channel(db)
    current_text = current if current else "не встановлено"
    await state.set_state(AdminSetChannelState.waiting_for_channel)
    await _send_admin_photo_message(
        callback.message,
        f"📢 <b>Канал для підписки</b>\n\n" f"Поточне значення: <code>{current_text}</code>\n\n" "Введіть @username каналу (наприклад: @my_channel)\n" "або напишіть <b>Вимкнути</b> щоб відключити.\n\n" "⚠️ Бот повинен бути адміністратором каналу!",
        reply_markup=cancel_kb("admin:settings"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.message(AdminSetChannelState.waiting_for_channel, F.text)
async def set_channel(message: Message, state: FSMContext) -> None:
    db, _ = await _context()
    text = message.text.strip()
    
    if text.lower() in ["вимкнути", "off", "disable", "-"]:
        await promo_manager.set_telegram_channel(db, None)
        await _send_admin_photo_message(
            message,
            "✅ Перевірку підписки на канал вимкнено.",
            reply_markup=admin_settings_kb(),
            state=state
        )
        await state.clear()
        return
    
    # Валідація формату каналу
    if not text.startswith("@"):
        text = "@" + text
    
    await promo_manager.set_telegram_channel(db, text)
    await _send_admin_photo_message(
        message,
        f"✅ Канал <code>{text}</code> встановлено.\n\n" "Тепер користувачі мають бути підписані на канал для реєстрації чеків.",
        reply_markup=admin_settings_kb(),
        state=state
    )
    await state.clear()


@router.callback_query(F.data == "admin:stats:overview")
async def admin_stats_overview(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    total, users_cnt, total_amount = await db.stats_overview()
    text = (
        "Загальна статистика акції:\n"
        f"• Всього зареєстрованих чеків: {total}\n"
        f"• Унікальних учасників: {users_cnt}\n"
        f"• Загальна сума покупок: {total_amount:.2f} грн"
    )
    await _send_admin_photo_message(callback.message, text, reply_markup=admin_stats_kb(), edit=True, state=state)
    await callback.answer()


def _parse_exclude_callback_payload(data: str, expected_prefix: str) -> tuple[int, int] | None:
    parts = data.split(":")
    if len(parts) != 6 or ":".join(parts[:4]) != expected_prefix:
        return None
    try:
        return int(parts[4]), int(parts[5])
    except ValueError:
        return None


async def _show_stats_exclude_shop_page(
    message: Message,
    state: FSMContext,
    page: int = 0,
    edit: bool = True,
    notice: str | None = None,
) -> None:
    db, _ = await _context()
    rows = await db.stats_by_shop()
    if not rows:
        await _send_admin_photo_message(
            message,
            "Немає магазинів для виключення з участі.",
            reply_markup=admin_stats_kb(),
            edit=edit,
            state=state,
        )
        await state.update_data(stats_exclude_rows=[])
        return

    serialized_rows = [
        {"shop": shop, "cnt": cnt, "total": total_sum}
        for shop, cnt, total_sum in rows
    ]
    await state.update_data(stats_exclude_rows=serialized_rows)

    total_pages = (len(serialized_rows) + SHOPS_EXCLUDE_PAGE_SIZE - 1) // SHOPS_EXCLUDE_PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    start = page * SHOPS_EXCLUDE_PAGE_SIZE
    page_items = []
    for idx, item in enumerate(serialized_rows[start : start + SHOPS_EXCLUDE_PAGE_SIZE], start=start):
        page_items.append((idx, str(item["shop"]), int(item["cnt"]), float(item["total"])))

    header = "Оберіть магазин, чеки якого потрібно видалити з участі:"
    if notice:
        header = f"{notice}\n\n{header}"
    text = (
        f"{header}\n\n"
        f"Сторінка {page + 1}/{total_pages}\n"
        "Показано до 10 магазинів на сторінку."
    )
    await _send_admin_photo_message(
        message,
        text,
        reply_markup=stats_shop_exclude_kb(page_items, page, total_pages),
        edit=edit,
        state=state,
    )


@router.callback_query(F.data == "admin:stats:exclude")
async def admin_stats_exclude(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_stats_exclude_shop_page(callback.message, state, page=0, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:stats:exclude:page:"))
async def admin_stats_exclude_page(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer("Некоректна сторінка", show_alert=False)
        return
    try:
        page = int(parts[4])
    except ValueError:
        await callback.answer("Некоректна сторінка", show_alert=False)
        return
    await _show_stats_exclude_shop_page(callback.message, state, page=page, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:stats:exclude:pick:"))
async def admin_stats_exclude_pick(callback: CallbackQuery, state: FSMContext) -> None:
    payload = _parse_exclude_callback_payload(callback.data, "admin:stats:exclude:pick")
    if payload is None:
        await callback.answer("Некоректні дані", show_alert=False)
        return
    shop_idx, page = payload
    data = await state.get_data()
    rows = data.get("stats_exclude_rows") or []
    if not (0 <= shop_idx < len(rows)):
        await _show_stats_exclude_shop_page(callback.message, state, page=0, edit=True)
        await callback.answer("Список оновлено, оберіть магазин ще раз", show_alert=False)
        return

    row = rows[shop_idx]
    shop_name = str(row["shop"])
    checks_count = int(row["cnt"])
    total_sum = float(row["total"])
    text = (
        f"Ви дійсно хочете видалити з участі всі чеки магазину:\n"
        f"«{shop_name}»?\n\n"
        f"Буде видалено чеків: {checks_count}\n"
        f"Сума цих чеків: {total_sum:.2f} грн"
    )
    await _send_admin_photo_message(
        callback.message,
        text,
        reply_markup=stats_shop_exclude_confirm_kb(shop_idx, page),
        edit=True,
        state=state,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:stats:exclude:confirm:"))
async def admin_stats_exclude_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    payload = _parse_exclude_callback_payload(callback.data, "admin:stats:exclude:confirm")
    if payload is None:
        await callback.answer("Некоректні дані", show_alert=False)
        return
    shop_idx, page = payload

    data = await state.get_data()
    rows = data.get("stats_exclude_rows") or []
    if not (0 <= shop_idx < len(rows)):
        await _show_stats_exclude_shop_page(callback.message, state, page=0, edit=True)
        await callback.answer("Список оновлено, оберіть магазин ще раз", show_alert=False)
        return

    shop_name = str(rows[shop_idx]["shop"])
    db, _ = await _context()
    deleted_count, recipients = await db.delete_checks_by_shop(shop_name)

    notify_text = (
        f'Ваші чеки з магазину "{shop_name}" відкликані, '
        "оскільки вони не підлягають умовам акції."
    )
    notified = 0
    for telegram_id in recipients:
        try:
            await callback.message.bot.send_message(telegram_id, notify_text)
            notified += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            log.warning("Failed to notify user telegram_id=%s for excluded shop=%s", telegram_id, shop_name)

    notice = (
        f"✅ З магазину «{shop_name}» видалено {deleted_count} чек(ів).\n"
        f"Повідомлено користувачів: {notified}/{len(recipients)}."
    )
    await _show_stats_exclude_shop_page(callback.message, state, page=page, edit=True, notice=notice)
    await callback.answer("Готово")


@router.callback_query(F.data == "admin:stats:by_shop")
async def admin_stats_by_shop(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    rows = await db.stats_by_shop()
    if not rows:
        text = "Немає зареєстрованих чеків."
    else:
        lines = ["Статистика за магазинами:"]
        total_checks = 0
        total_amount = 0.0
        for shop, cnt, total_sum in rows:
            lines.append(f"• {shop} — {cnt} чеків, сума {total_sum:.2f} грн")
            total_checks += cnt
            total_amount += total_sum
        lines.append("")
        lines.append(f"Всього магазинів: {len(rows)}")
        lines.append(f"Всього чеків (без виключеного магазину): {total_checks}")
        lines.append(f"Загальна сума (без виключеного магазину): {total_amount:.2f} грн")
        text = "\n".join(lines)
    await _send_admin_photo_message(callback.message, text, reply_markup=admin_stats_kb(), edit=True, state=state)
    await callback.answer()


@router.callback_query(F.data == "admin:stats:last_checks")
async def admin_stats_last_checks(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    latest = await db.latest_checks()
    if not latest:
        text = "Немає зареєстрованих чеків."
    else:
        lines = ["Останні 10 чеків:"]
        for rec in latest:
            lines.append(
                f"#{rec.id} — {rec.shop or 'Невідомо'}, {rec.amount or 0} грн, {rec.date or ''}"
            )
        text = "\n".join(lines)
    await _send_admin_photo_message(callback.message, text, reply_markup=admin_stats_kb(), edit=True, state=state)
    await callback.answer()


@router.callback_query(F.data == "admin:shops:add")
async def admin_shops_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminAddShopState.waiting_for_name)
    await _send_admin_photo_message(
        callback.message,
        "🏬 Введіть назву магазину",
        reply_markup=cancel_kb("admin:shops"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.callback_query(F.data == "admin:shops:delete")
async def admin_shops_delete(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    shops = await db.list_shops()
    if not shops:
        await _send_admin_photo_message(callback.message, "Список магазинів порожній", reply_markup=admin_shops_kb(), edit=True, state=state)
    else:
        await _send_admin_photo_message(
            callback.message,
            "Оберіть магазин для видалення:",
            reply_markup=shops_delete_kb(shops),
            edit=True,
            state=state
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:shops:delete_item:"))
async def admin_shops_delete_item(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    shop_id_str = callback.data.split(":")[-1]
    try:
        shop_id = int(shop_id_str)
    except ValueError:
        await callback.answer("Помилка id", show_alert=False)
        return
    await shops_manager.delete_shop(db, shop_id)
    await _send_admin_photo_message(callback.message, "Магазин видалено", reply_markup=admin_shops_kb(), edit=True, state=state)
    await callback.answer("Готово")


@router.callback_query(F.data == "admin:shops:edit")
async def admin_shops_edit(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    shops = await db.list_shops()
    if not shops:
        await _send_admin_photo_message(callback.message, "Список магазинів порожній", reply_markup=admin_shops_kb(), edit=True, state=state)
    else:
        from app.keyboards import shops_edit_kb
        await _send_admin_photo_message(
            callback.message,
            "Оберіть магазин для редагування:",
            reply_markup=shops_edit_kb(shops),
            edit=True,
            state=state
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:shops:edit_item:"))
async def admin_shops_edit_item(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    shop_id_str = callback.data.split(":")[-1]
    try:
        shop_id = int(shop_id_str)
    except ValueError:
        await callback.answer("Помилка id", show_alert=False)
        return
    
    # Знаходимо магазин
    shops = await db.list_shops()
    shop_name = None
    for sid, name in shops:
        if sid == int(shop_id):
            shop_name = name
            break
    
    if not shop_name:
        await callback.answer("Магазин не знайдено", show_alert=True)
        return
    
    # Зберігаємо shop_id в стан і просимо ввести нову назву
    from app.states import AdminEditShopState
    await state.set_state(AdminEditShopState.waiting_for_new_name)
    await state.update_data(edit_shop_id=shop_id, old_shop_name=shop_name)
    
    from app.keyboards import cancel_kb
    await _send_admin_photo_message(
        callback.message,
        f"📝 Поточна назва: <b>{shop_name}</b>\n\n"
        f"Введіть нову назву магазину:",
        reply_markup=cancel_kb("admin:shops"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.message(AdminEditShopState.waiting_for_new_name, F.text)
async def admin_shops_edit_name(message: Message, state: FSMContext) -> None:
    from app.states import AdminEditShopState
    db, _ = await _context()
    
    new_name = message.text.strip()
    data = await state.get_data()
    shop_id = data.get("edit_shop_id")
    old_name = data.get("old_shop_name")
    
    if not shop_id or not old_name:
        await _send_admin_photo_message(message, "❌ Сталася помилка", reply_markup=admin_shops_kb(), state=state)
        await state.clear()
        return
    
    # Перевіряємо чи не існує вже магазин з такою назвою
    existing = [name.lower() for sid, name in await db.list_shops() if sid != shop_id]
    if new_name.lower() in existing:
        await _send_admin_photo_message(
            message,
            "❌ Магазин з такою назвою вже існує.\n"
            "Введіть іншу назву:",
            reply_markup=cancel_kb("admin:shops"),
            state=state
        )
        return
    
    # Оновлюємо назву (це також оновить active_shops якщо магазин був активним)
    await shops_manager.update_shop_name(db, shop_id, new_name)
    
    await _send_admin_photo_message(
        message,
        f"✅ Назву магазину змінено:\n"
        f"<b>{old_name}</b> → <b>{new_name}</b>\n\n"
        f"{'🎯 Оновлено в активній акції' if await promo_manager.is_promo_active(db) else ''}",
        reply_markup=admin_shops_kb(),
        state=state
    )
    await state.clear()


@router.callback_query(F.data == "admin:shops:toggle")
async def admin_shops_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    shops = await shops_manager.list_shops_with_flags(db)
    if not shops:
        await _send_admin_photo_message(callback.message, "Немає магазинів для перемикання", reply_markup=admin_shops_kb(), edit=True, state=state)
    else:
        await _send_admin_photo_message(
            callback.message,
            "Перемикайте участь магазинів:",
            reply_markup=shops_toggle_kb(shops),
            edit=True,
            state=state
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:shops:toggle_item:"))
async def admin_shops_toggle_item(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    shop_id_str = callback.data.split("admin:shops:toggle_item:")[-1]
    try:
        shop_id = int(shop_id_str)
    except ValueError:
        await callback.answer("Помилка id", show_alert=False)
        return
    shops = await db.list_shops()
    id_to_name = {sid: name for sid, name in shops}
    shop_name = id_to_name.get(shop_id)
    if not shop_name:
        await callback.answer("Магазин не знайдено", show_alert=False)
        return
    new_state = await shops_manager.toggle_shop_for_campaign(db, shop_name)
    shops_with_flags = await shops_manager.list_shops_with_flags(db)
    
    await _send_admin_photo_message(
        callback.message,
        "Перемикайте участь магазинів:",
        reply_markup=shops_toggle_kb(shops_with_flags),
        edit=True,
        state=state
    )
    await callback.answer("Активовано" if new_state else "Вимкнено")


@router.callback_query(F.data == "admin:shops:list")
async def admin_shops_list(callback: CallbackQuery, state: FSMContext) -> None:
    db, _ = await _context()
    shops = await shops_manager.list_shops_with_flags(db)
    if not shops:
        await _send_admin_photo_message(callback.message, "Список магазинів порожній", reply_markup=admin_shops_kb(), edit=True, state=state)
    else:
        lines = [f"{name} — {'активний 🟢' if active else 'неактивний 🔴'}" for _, name, active in shops]
        await _send_admin_photo_message(callback.message, "\n".join(lines), reply_markup=admin_shops_kb(), edit=True, state=state)
    await callback.answer()


# --- Start campaign wizard steps ---


@router.message(AdminStartCampaignStates.start_date, F.text)
async def wizard_start_date(message: Message, state: FSMContext) -> None:
    iso = _parse_date(message.text)
    if not iso:
        await _send_admin_photo_message(
            message,
            "Невірний формат дати. Введіть дату початку акції у форматі дд.мм.рррр",
            reply_markup=cancel_kb("admin:start:cancel"),
            state=state
        )
        return
    await state.update_data(start_date=iso)
    await state.set_state(AdminStartCampaignStates.end_date)
    await _send_admin_photo_message(
        message,
        "Введіть дату закінчення акції у форматі дд.мм.рррр",
        reply_markup=back_cancel_kb("admin:start:back:start", "admin:start:cancel"),
        state=state
    )


@router.callback_query(F.data == "admin:start:back:start")
async def wizard_back_to_start_date(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStartCampaignStates.start_date)
    await _send_admin_photo_message(
        callback.message,
        "Введіть дату початку акції у форматі дд.мм.рррр",
        reply_markup=cancel_kb("admin:start:cancel"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.message(AdminStartCampaignStates.end_date, F.text)
async def wizard_end_date(message: Message, state: FSMContext) -> None:
    iso = _parse_date(message.text)
    if not iso:
        await _send_admin_photo_message(
            message,
            "Невірний формат дати. Введіть дату закінчення у форматі дд.мм.рррр",
            reply_markup=back_cancel_kb("admin:start:back:start", "admin:start:cancel"),
            state=state
        )
        return
    data = await state.get_data()
    start_date = data.get("start_date")
    if start_date and iso < start_date:
        await _send_admin_photo_message(
            message,
            "Дата завершення не може бути раніше дати початку. Введіть коректну дату.",
            reply_markup=back_cancel_kb("admin:start:back:start", "admin:start:cancel"),
            state=state
        )
        return
    await state.update_data(end_date=iso)
    await state.set_state(AdminStartCampaignStates.start_time)
    await _send_admin_photo_message(
        message,
        "Введіть час початку акції у форматі год:хв (наприклад, 10:00)",
        reply_markup=back_cancel_kb("admin:start:back:end_date", "admin:start:cancel"),
        state=state
    )


@router.callback_query(F.data == "admin:start:back:end_date")
async def wizard_back_to_end_date(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStartCampaignStates.end_date)
    await _send_admin_photo_message(
        callback.message,
        "Введіть дату закінчення акції у форматі дд.мм.рррр",
        reply_markup=back_cancel_kb("admin:start:back:start", "admin:start:cancel"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.message(AdminStartCampaignStates.start_time, F.text)
async def wizard_start_time(message: Message, state: FSMContext) -> None:
    time_val = _parse_time(message.text)
    if not time_val:
        await _send_admin_photo_message(
            message,
            "Невірний формат часу. Використовуйте год:хв (наприклад, 10:00)",
            reply_markup=back_cancel_kb("admin:start:back:end_date", "admin:start:cancel"),
            state=state
        )
        return
    await state.update_data(start_time=time_val)
    await state.set_state(AdminStartCampaignStates.end_time)
    await _send_admin_photo_message(
        message,
        "Введіть час закінчення акції у форматі год:хв (наприклад, 21:00)",
        reply_markup=back_cancel_kb("admin:start:back:start_time", "admin:start:cancel"),
        state=state
    )


@router.callback_query(F.data == "admin:start:back:start_time")
async def wizard_back_to_start_time(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStartCampaignStates.start_time)
    await _send_admin_photo_message(
        callback.message,
        "Введіть час початку акції у форматі год:хв (наприклад, 10:00)",
        reply_markup=back_cancel_kb("admin:start:back:end_date", "admin:start:cancel"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.message(AdminStartCampaignStates.end_time, F.text)
async def wizard_end_time(message: Message, state: FSMContext) -> None:
    time_val = _parse_time(message.text)
    data = await state.get_data()
    if not time_val:
        await _send_admin_photo_message(
            message,
            "Невірний формат часу. Використовуйте год:хв (наприклад, 21:00)",
            reply_markup=back_cancel_kb("admin:start:back:start_time", "admin:start:cancel"),
            state=state
        )
        return
    start_time = data.get("start_time")
    if start_time and _minutes(time_val) < _minutes(start_time):
        await _send_admin_photo_message(
            message,
            "Час завершення не може бути раніше часу початку.",
            reply_markup=back_cancel_kb("admin:start:back:start_time", "admin:start:cancel"),
            state=state
        )
        return
    await state.update_data(end_time=time_val)
    await state.set_state(AdminStartCampaignStates.shops)
    await _show_shops_selection(message, state)


@router.callback_query(F.data.startswith("admin:start:shop:"))
async def wizard_toggle_shop(callback: CallbackQuery, state: FSMContext) -> None:
    shop_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    selected = data.get("selected_shops", [])
    if shop_id in selected:
        selected.remove(shop_id)
    else:
        selected.append(shop_id)
    await state.update_data(selected_shops=selected)
    db, _ = await _context()
    shops = await db.list_shops()
    await _send_admin_photo_message(
        callback.message,
        "Оберіть магазини для акції (🟢 - обрано, 🔴 - не обрано):",
        reply_markup=_shops_wizard_kb(shops, selected).as_markup(),
        edit=True,
        state=state
    )
    await callback.answer()


@router.callback_query(F.data == "admin:start:shops_next")
async def wizard_shops_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = data.get("selected_shops", [])
    if not selected:
        await callback.answer("Оберіть хоча б один магазин", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStartCampaignStates.min_amount)
    await _send_admin_photo_message(
        callback.message,
        "💰 Введіть мінімальну суму чеку для участі в акції (наприклад: 500):",
        reply_markup=back_cancel_kb("admin:start:back:shops", "admin:start:cancel"),
        edit=True,
        state=state
    )


@router.message(AdminStartCampaignStates.min_amount, F.text)
async def wizard_min_amount(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    try:
        amount = int(text)
        if amount < 0:
            raise ValueError()
    except ValueError:
        await _send_admin_photo_message(
            message,
            "❌ Введіть коректну суму (ціле число >= 0)",
            reply_markup=back_cancel_kb("admin:start:back:shops", "admin:start:cancel"),
            state=state
        )
        return
    await state.update_data(min_amount=amount)
    await _show_wizard_summary(message, state)


async def _show_wizard_summary(message: Message, state: FSMContext, edit: bool = False) -> None:
    db, _ = await _context()
    data = await state.get_data()
    selected = data.get("selected_shops", [])
    shops = await db.list_shops()
    shop_names = [name for sid, name in shops if sid in selected]
    
    summary = (
        f"📋 <b>Підтвердіть запуск акції:</b>\n\n"
        f"📅 Дати: {data.get('start_date')} — {data.get('end_date')}\n"
        f"🕐 Час: {data.get('start_time')} — {data.get('end_time')}\n"
        f"🏬 Магазини: {', '.join(shop_names)}\n"
        f"💰 Мін. сума: {data.get('min_amount')} грн"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Запустити акцію", callback_data="admin:start:confirm")
    kb.button(text="⬅️ Назад", callback_data="admin:start:back:min_amount")
    kb.button(text="❌ Скасувати", callback_data="admin:start:cancel")
    kb.adjust(1)
    
    await _send_admin_photo_message(
        message,
        summary,
        reply_markup=kb.as_markup(),
        edit=edit,
        state=state
    )


@router.callback_query(F.data == "admin:start:back:shops")
async def wizard_back_to_shops(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStartCampaignStates.shops)
    await _show_shops_selection(callback.message, state, edit=True)
    await callback.answer()


@router.callback_query(F.data == "admin:start:back:min_amount")
async def wizard_back_to_min_amount(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStartCampaignStates.min_amount)
    await _send_admin_photo_message(
        callback.message,
        "💰 Введіть мінімальну суму чеку для участі в акції (наприклад: 500):",
        reply_markup=back_cancel_kb("admin:start:back:shops", "admin:start:cancel"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.callback_query(F.data == "admin:start:confirm")
async def wizard_confirm_start(callback: CallbackQuery, state: FSMContext) -> None:
    db, settings = await _context()
    data = await state.get_data()
    
    # Зберігаємо дати та час
    await db.set_setting("start_date", data.get("start_date"))
    await db.set_setting("end_date", data.get("end_date"))
    await db.set_setting("allowed_time_from", data.get("start_time"))
    await db.set_setting("allowed_time_to", data.get("end_time"))
    
    # Зберігаємо мінімальну суму
    await db.set_setting("min_amount", data.get("min_amount"))
    
    # Оновлюємо магазини для акції
    selected = data.get("selected_shops", [])
    shops = await db.list_shops()
    active_shop_names = [name for sid, name in shops if sid in selected]
    await db.set_setting("active_shops", active_shop_names)
    
    # Запускаємо акцію
    await _do_campaign_start(db, settings)
    await state.clear()
    
    await _send_admin_photo_message(
        callback.message,
        "✅ Акцію успішно запущено!",
        reply_markup=admin_main_kb(),
        edit=True,
        state=state
    )
    await callback.answer("Акцію запущено!")


@router.callback_query(F.data == "admin:start:back:end_time")
async def wizard_back_to_end_time(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStartCampaignStates.end_time)
    await _send_admin_photo_message(
        callback.message,
        "Введіть час закінчення акції у форматі год:хв (наприклад, 21:00)",
        reply_markup=back_cancel_kb("admin:start:back:start_time", "admin:start:cancel"),
        edit=True,
        state=state
    )
    await callback.answer()


@router.message(AdminSetDatesState.waiting_for_end, F.text)
async def set_dates_end(message: Message, state: FSMContext) -> None:
    db, _ = await _context()
    data = await state.get_data()
    start_date = data.get("start_date")
    text = message.text.strip()
    parsed = None
    for fmt in ["%d.%m.%Y", "%Y-%m-%d"]:
        try:
            parsed = datetime.strptime(text, fmt).date()
            break
        except ValueError:
            continue
    if not parsed:
        await _send_admin_photo_message(
            message,
            "❌ Невірний формат дати. Використовуйте <b>ДД.ММ.РРРР</b>",
            reply_markup=cancel_kb("admin:settings"),
            state=state
        )
        return
    await promo_manager.set_date_range(db, start_date, parsed.isoformat())
    await _send_admin_photo_message(message, "✅ Дати акції оновлено", reply_markup=admin_settings_kb(), state=state)
    await state.clear()


@router.message(AdminSetMinAmountState.waiting_for_amount, F.text)
async def set_min_amount(message: Message, state: FSMContext) -> None:
    db, _ = await _context()
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await _send_admin_photo_message(message, "❌ Введіть число", reply_markup=cancel_kb("admin:settings"), state=state)
        return
    await promo_manager.set_min_amount(db, amount)
    await _send_admin_photo_message(message, "✅ Мінімальну суму оновлено", reply_markup=admin_settings_kb(), state=state)
    await state.clear()


@router.message(AdminSetTimeRangeState.waiting_for_start, F.text)
async def set_time_start(message: Message, state: FSMContext) -> None:
    try:
        datetime.strptime(message.text.strip(), "%H:%M")
    except ValueError:
        await _send_admin_photo_message(
            message,
            "❌ Вкажіть час у форматі <b>ГГ:ХХ</b>",
            reply_markup=cancel_kb("admin:settings"),
            state=state
        )
        return
    await state.update_data(time_start=message.text.strip())
    await state.set_state(AdminSetTimeRangeState.waiting_for_end)
    await _send_admin_photo_message(
        message,
        "⏰ Вкажіть час завершення у форматі <b>ГГ:ХХ</b>",
        reply_markup=cancel_kb("admin:settings"),
        state=state
    )


@router.message(AdminSetTimeRangeState.waiting_for_end, F.text)
async def set_time_end(message: Message, state: FSMContext) -> None:
    db, _ = await _context()
    data = await state.get_data()
    start_time = data.get("time_start")
    end_time = message.text.strip()
    try:
        datetime.strptime(end_time, "%H:%M")
    except ValueError:
        await _send_admin_photo_message(
            message,
            "❌ Вкажіть час у форматі <b>ГГ:ХХ</b>",
            reply_markup=cancel_kb("admin:settings"),
            state=state
        )
        return
    await promo_manager.set_time_range(db, start_time, end_time)
    await _send_admin_photo_message(message, "✅ Часовий діапазон оновлено", reply_markup=admin_settings_kb(), state=state)
    await state.clear()


@router.message(AdminAddShopState.waiting_for_name, F.text)
async def add_shop_name(message: Message, state: FSMContext) -> None:
    db, _ = await _context()
    shop_name = message.text.strip()

    existing = [name.lower() for _, name in await db.list_shops()]
    if shop_name.lower() in existing:
        await _send_admin_photo_message(
            message,
            "❌ Такий магазин вже існує.\n" "Введіть іншу назву.",
            reply_markup=cancel_kb("admin:shops"),
            state=state
        )
        return

    shop_id = await shops_manager.add_shop(db, shop_name)
    await state.update_data(shop_id=shop_id, shop_name=shop_name)
    await state.set_state(AdminAddShopState.waiting_for_address)
    await _send_admin_photo_message(
        message,
        f"✅ Магазин <b>{shop_name}</b> створено!\n\n" "📍 Введіть адресу магазину:\n" "<i>наприклад: м. Київ, вул. Хрещатик 22</i>\n\n" "Або напишіть <b>Пропустити</b>",
        reply_markup=cancel_kb("admin:shops"),
        state=state
    )


@router.message(AdminAddShopState.waiting_for_address, F.text)
async def add_shop_address(message: Message, state: FSMContext) -> None:
    db, _ = await _context()
    data = await state.get_data()
    shop_id = data.get("shop_id")
    
    if not shop_id:
        await _send_admin_photo_message(message, "❌ Сталася помилка, повторіть додавання магазину", reply_markup=admin_shops_kb(), state=state)
        await state.clear()
        return
    
    address_text = message.text.strip()
    if address_text.lower() != "пропустити":
        await db.set_shop_address(int(shop_id), address_text)
        await _send_admin_photo_message(
            message,
            f"✅ Адресу збережено: <b>{address_text}</b>\n\n" "📸 Надішліть 1–5 фото прикладів чеків\nабо напишіть <b>Готово</b>",
            reply_markup=cancel_kb("admin:shops"),
            state=state
        )
    else:
        await _send_admin_photo_message(
            message,
            "📸 Надішліть 1–5 фото прикладів чеків\nабо напишіть <b>Готово</b>",
            reply_markup=cancel_kb("admin:shops"),
            state=state
        )
    
    await state.set_state(AdminAddShopState.waiting_for_samples)


@router.message(AdminAddShopState.waiting_for_samples, F.photo)
async def add_shop_sample(message: Message, state: FSMContext) -> None:
    db, _ = await _context()
    data = await state.get_data()
    shop_id = data.get("shop_id")
    if not shop_id:
        await _send_admin_photo_message(message, "❌ Сталася помилка, повторіть додавання магазину", reply_markup=admin_shops_kb(), state=state)
        await state.clear()
        return
    file_id = message.photo[-1].file_id
    await shops_manager.add_sample(db, int(shop_id), file_id)
    await _send_admin_photo_message(
        message,
        "✅ Фото збережено!\n" "Надішліть ще або напишіть <b>Готово</b>",
        reply_markup=cancel_kb("admin:shops"),
        state=state
    )


@router.message(AdminAddShopState.waiting_for_samples, F.text.regexp("(?i)^готово$"))
async def add_shop_done(message: Message, state: FSMContext) -> None:
    db, _ = await _context()
    data = await state.get_data()
    shop_name = data.get("shop_name", "Магазин")
    
    # Автоматично додаємо новий магазин до активних якщо акція запущена
    is_active = await promo_manager.is_promo_active(db)
    if is_active:
        # Додаємо магазин до active_shops
        await shops_manager.toggle_shop_for_campaign(db, shop_name)
        promo_manager.invalidate_rules_cache()
        
        await _send_admin_photo_message(
            message,
            f"✅ <b>{shop_name}</b> успішно додано!\n\n"
            f"🎯 Магазин автоматично додано до активної акції.",
            reply_markup=admin_shops_kb(),
            state=state
        )
    else:
        await _send_admin_photo_message(
            message,
            f"✅ <b>{shop_name}</b> успішно додано!",
            reply_markup=admin_shops_kb(),
            state=state
        )
    
    await state.clear()


@router.message(AdminSearchState.waiting_for_query, F.text)
async def search_receipt(message: Message, state: FSMContext) -> None:
    db, _ = await _context()
    query = message.text.strip()
    receipt = await db.search_receipt(query)
    if not receipt:
        await _send_admin_photo_message(message, "❌ Нічого не знайдено", reply_markup=admin_settings_kb(), state=state)
        await state.clear()
        return
    user = await db.find_user(receipt.user_id)
    
    await _send_admin_photo_message(
        message,
        f"🧾 <b>Чек #{receipt.id}</b>\n\n" f"👤 {user.full_name if user else '—'}\n" f"📞 {user.phone if user else '—'}\n" f"🏬 {receipt.shop or '—'}\n" f"💰 {receipt.amount or 0} грн\n" f"📅 {receipt.date or '—'} {receipt.time or ''}\n" f"🔢 Код: {receipt.check_code or '—'}",
        reply_markup=admin_settings_kb(),
        state=state
    )
    await state.clear()
    try:
        await message.answer_photo(receipt.file_id)
    except Exception:
        log.warning("Failed to send photo for receipt %s", receipt.id)
