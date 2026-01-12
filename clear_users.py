from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.db import Database


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


async def main() -> None:
    settings = Settings.load()
    db = Database(settings.db_path)
    await db.init()
    await db.clear_users()
    log.info("Users and related checks have been cleared for testing.")


if __name__ == "__main__":
    asyncio.run(main())
