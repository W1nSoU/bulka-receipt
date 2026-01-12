import asyncio
import json
from pathlib import Path

from app.ai.gemini_client import analyze_receipt
from app.config import Settings


async def main() -> None:
    settings = Settings.load()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    img_path = Path("test_receipts/receipt1.jpg")
    image_bytes = img_path.read_bytes()

    rules = {
        "campaign_active": True,
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "min_amount": 10.0,
        "allowed_shops": ["BULKA", "ATB", "SILPO"],
        "allowed_time_range": {"start": "00:00", "end": "23:59"},
    }

    result = await analyze_receipt(image_bytes, rules)
    print("RESULT:")
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
