from __future__ import annotations

from app.config import Settings
from app.db import Database

_db: Database | None = None
_settings: Settings | None = None


def setup(database: Database, settings: Settings) -> None:
    global _db, _settings
    _db = database
    _settings = settings


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database is not initialized")
    return _db


def get_settings() -> Settings:
    if _settings is None:
        raise RuntimeError("Settings are not initialized")
    return _settings
