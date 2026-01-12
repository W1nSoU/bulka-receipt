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


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
# Silence noisy libraries; keep our own logs at INFO
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
log = logging.getLogger(__name__)


async def main() -> None:
    settings = Settings.load()
    db = Database(settings.db_path)
    await db.init()
    await promo_manager.ensure_defaults(db)

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    runtime.setup(db, settings)

    dp = Dispatcher()
    admin_router.message.filter(AdminFilter(settings.admin_ids))
    admin_router.callback_query.filter(AdminCallbackFilter(settings.admin_ids))

    dp.include_router(admin_router)
    dp.include_router(user_router)

    log.info("Bot started")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
