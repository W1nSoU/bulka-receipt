#!/bin/bash

# Скрипт автоматичного оновлення бота на сервері

set -e

echo "🔄 Оновлення Bulka Receipt Bot..."
echo ""

# 1. Перевірка git змін
echo "📥 Завантаження змін з GitHub..."
git pull

# 2. Перевірка/створення venv
if [ ! -d "venv" ]; then
    echo "📦 Створення віртуального оточення..."
    python3 -m venv venv
fi

# 3. Активація venv та встановлення залежностей
echo "📦 Встановлення залежностей..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 4. Перевірка бази даних
if [ -f "data/bot.db" ]; then
    echo "💾 База даних знайдена: $(du -h data/bot.db | cut -f1)"
else
    echo "⚠️  База даних не знайдена, буде створена нова"
fi

# 5. Перезапуск сервісу (якщо є)
if systemctl is-active --quiet bulka-receipt 2>/dev/null; then
    echo "🔄 Перезапуск systemd сервісу..."
    sudo systemctl restart bulka-receipt
    sleep 2
    if systemctl is-active --quiet bulka-receipt; then
        echo "✅ Сервіс успішно перезапущено"
    else
        echo "❌ Помилка запуску сервісу!"
        echo "Перевірте логи: sudo journalctl -u bulka-receipt -n 50"
        exit 1
    fi
else
    echo "ℹ️  Systemd сервіс не знайдено"
    echo "Для запуску вручну: source venv/bin/activate && python bot.py"
fi

echo ""
echo "✅ Оновлення завершено!"
echo ""
echo "Нові функції:"
echo "  • 📦 Продовжити акцію (архівація + нова акція)"
echo "  • ✏️ Редагування назви магазину"
echo "  • 🔄 Автосинхронізація магазинів з акцією"
echo "  • 📜 Історія акцій"
echo "  • 🐛 Виправлено баг з валідацією дати"
