import asyncio
from pathlib import Path

from app.ai.groq_client import analyze_receipt
from app.config import Settings


async def main() -> None:
    settings = Settings.load()
    if not settings.groq_api_keys:
        raise RuntimeError("GROQ_API_KEYS is not set")

    img_path = Path("test_receipts/receipt1.jpg")
    if not img_path.exists():
        print(f"❌ Test image not found: {img_path}")
        print("Please add a receipt image to test_receipts/receipt1.jpg")
        return
        
    image_bytes = img_path.read_bytes()

    rules = {
        "campaign_active": True,
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "min_amount": 10.0,
        "allowed_shops": ["BULKA", "БУЛКА", "ATB", "АТБ", "SILPO", "СІЛЬПО"],
        "allowed_time_range": {"start": "00:00", "end": "23:59"},
    }

    print("🔍 Testing Groq OCR...")
    result = await analyze_receipt(image_bytes, rules)
    
    print("\n✅ RESULT:")
    print(f"  Shop: {result.shop}")
    print(f"  Address: {result.address}")
    print(f"  Amount: {result.amount}")
    print(f"  Date: {result.date}")
    print(f"  Time: {result.time}")
    print(f"  Check code: {result.check_code}")
    print(f"  Valid: {result.is_valid}")
    print(f"  Errors: {result.errors}")
    print(f"\n📄 Raw text:\n{result.raw_text}")


if __name__ == "__main__":
    asyncio.run(main())
    
