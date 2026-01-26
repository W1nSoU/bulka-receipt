import asyncio
from pathlib import Path
from app.ai.groq_client import analyze_receipt
from app.config import Settings
import os

async def test_model(model_name: str, image_bytes: bytes, rules: dict):
    """Тестує конкретну модель"""
    # Тимчасово змінюємо модель
    original = os.getenv("GROQ_MODEL")
    os.environ["GROQ_MODEL"] = model_name
    
    # Очищаємо кеш Settings
    import app.ai.groq_client as groq_module
    groq_module._rotator = None
    
    print(f"\n{'='*60}")
    print(f"📊 Testing: {model_name}")
    print(f"{'='*60}")
    
    try:
        import time
        start = time.time()
        result = await analyze_receipt(image_bytes, rules)
        elapsed = time.time() - start
        
        print(f"⏱️  Time: {elapsed:.2f}s")
        print(f"🏪 Shop: {result.shop}")
        print(f"💰 Amount: {result.amount}")
        print(f"📅 Date: {result.date}")
        print(f"🕐 Time: {result.time}")
        print(f"✅ Valid: {result.is_valid}")
        
        return elapsed, result
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None
    finally:
        os.environ["GROQ_MODEL"] = original

async def main():
    # Завантажуємо тестове зображення
    img_path = Path("test_receipts/receipt1.jpg")
    if not img_path.exists():
        print("❌ Add test image to test_receipts/receipt1.jpg")
        return
    
    image_bytes = img_path.read_bytes()
    
    rules = {
        "min_amount": 10.0,
        "allowed_shops": ["БУЛКА", "ATB", "СІЛЬПО"],
        "start_date": "2024-01-01",
        "end_date": "2026-12-31",
    }
    
    models = [
        "meta-llama/llama-4-maverick-17b-128e-instruct",  # Найточніша
        "meta-llama/llama-4-scout-17b-16e-instruct",      # Найшвидша
    ]
    
    results = {}
    
    for model in models:
        elapsed, result = await test_model(model, image_bytes, rules)
        if result:
            results[model] = {"time": elapsed, "result": result}
        await asyncio.sleep(2)  # Delay між тестами
    
    # Порівняння
    print(f"\n{'='*60}")
    print("📊 COMPARISON")
    print(f"{'='*60}")
    
    for model, data in results.items():
        short_name = model.split("/")[-1]
        print(f"\n{short_name}:")
        print(f"  Time: {data['time']:.2f}s")
        print(f"  Accuracy: {'✅' if data['result'].is_valid else '❌'}")

if __name__ == "__main__":
    asyncio.run(main())