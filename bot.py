from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.config import Settings
from app.db import Database
from app.handlers import AdminCallbackFilter, AdminFilter, admin_router, user_router
from app import promo_manager
from app import runtime


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Silence noisy libraries; keep our own logs at INFO
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("app").setLevel(logging.DEBUG)
log = logging.getLogger(__name__)


def print_banner():
    """Виводить красивий банер при старті."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🧾  BULKA RECEIPT — Бот для реєстрації чеків      🧾       ║
║                    Promo System v1.0                         ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_status(emoji: str, message: str, indent: int = 5):
    """Виводить статусне повідомлення з відступом."""
    print(" " * indent + f"{emoji} {message}")


async def main() -> None:
    print_banner()
    print_status("🚀", "Запуск бота...")
    print()

    print_status("⚙️", "Завантаження налаштувань...")
    settings = Settings.load()
    
    print_status("📦", "Ініціалізація бази даних...")
    db = Database(settings.db_path)
    await db.init()
    print_status("✅", "База даних підключена", indent=7)
    
    await promo_manager.ensure_defaults(db)
    print_status("✅", "Налаштування акції перевірено", indent=7)
    print()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    runtime.setup(db, settings)

    dp = Dispatcher()
    admin_router.message.filter(AdminFilter(settings.admin_ids))
    admin_router.callback_query.filter(AdminCallbackFilter(settings.admin_ids))

    dp.include_router(admin_router)
    dp.include_router(user_router)
    print_status("🔌", "Роутери та обробники підключено")

    print()
    print("─" * 60)
    print_status("🤖", "Бот готовий до роботи!", indent=3)
    print("─" * 60)
    print()

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
    finally:
        from app.ai.groq_client import _rotator
        if _rotator is not None:
            await _rotator.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())