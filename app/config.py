from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from dotenv import load_dotenv


load_dotenv()


def _parse_admin_ids(raw: str | None) -> List[int]:
    if not raw:
        return []
    ids: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


@dataclass
class Settings:
    bot_token: str
    gemini_api_key: str
    gemini_model: str
    admin_ids: List[int]
    db_path: Path
    excel_path: Path
    data_dir: Path

    @classmethod
    def load(cls) -> "Settings":
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
        if not gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS"))
        base_dir = Path(os.getenv("DATA_DIR", "data"))
        base_dir.mkdir(parents=True, exist_ok=True)

        db_path = base_dir / "bot.sqlite3"
        excel_path = base_dir / "promo.xlsx"

        return cls(
            bot_token=bot_token,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            admin_ids=admin_ids,
            db_path=db_path,
            excel_path=excel_path,
            data_dir=base_dir,
        )
