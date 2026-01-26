from __future__ import annotations
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(
        self,
        bot_token: str,
        admin_ids: List[int],
        db_path: Path,
        excel_path: Path,
        groq_api_keys: List[str],
        groq_model: str,
    ):
        self.bot_token = bot_token
        self.admin_ids = admin_ids
        self.db_path = db_path
        self.excel_path = excel_path
        self.groq_api_keys = groq_api_keys
        self.groq_model = groq_model

    @classmethod
    def load(cls) -> Settings:
        token = os.getenv("BOT_TOKEN")
        if not token:
            raise RuntimeError("BOT_TOKEN is not set")

        admin_ids_str = os.getenv("ADMIN_IDS", "")
        admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]

        db_path = Path(os.getenv("DB_PATH", "data/bot.db"))
        excel_path = Path(os.getenv("EXCEL_PATH", "data/checks.xlsx"))

        # Groq API keys (підтримка множинних ключів)
        groq_keys_str = os.getenv("GROQ_API_KEYS", "")
        groq_api_keys = [k.strip() for k in groq_keys_str.split(",") if k.strip()]
        
        if not groq_api_keys:
            raise RuntimeError("GROQ_API_KEYS not set in .env")

        # ✅ ВИПРАВЛЕНО: правильна назва моделі за замовчуванням
        groq_model = os.getenv(
            "GROQ_MODEL", 
            "meta-llama/llama-4-maverick-17b-128e-instruct"
        )

        return cls(
            bot_token=token,
            admin_ids=admin_ids,
            db_path=db_path,
            excel_path=excel_path,
            groq_api_keys=groq_api_keys,
            groq_model=groq_model,
        )
    
    @property
    def groq_fallback_model(self) -> str:
        """Резервна модель якщо основна не працює"""
        return os.getenv(
            "GROQ_FALLBACK_MODEL", 
            "meta-llama/llama-4-scout-17b-16e-instruct"
        )