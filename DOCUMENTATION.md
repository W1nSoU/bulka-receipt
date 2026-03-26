# 📚 Документація Bulka Receipt Bot

> Telegram-бот для реєстрації чеків та управління рекламними акціями

---

## 📖 Зміст

- [Вступ](#-вступ)
- [Встановлення та налаштування](#️-встановлення-та-налаштування)
- [Конфігурація](#-конфігурація)
- [Архітектура проєкту](#️-архітектура-проєкту)
- [База даних](#️-база-даних)
- [Користувацький інтерфейс](#-користувацький-інтерфейс)
- [Адміністративна панель](#-адміністративна-панель)
- [AI та обробка зображень](#-ai-та-обробка-зображень)
- [Система акцій](#-система-акцій)
- [API та інтеграції](#-api-та-інтеграції)
- [Безпека та обмеження](#️-безпека-та-обмеження)
- [Розробка та тестування](#-розробка-та-тестування)
- [Troubleshooting](#-troubleshooting)
- [Довідник](#-довідник)

---

## 🎯 Вступ

### Про проєкт

**Bulka Receipt Bot** — це сучасний Telegram-бот, розроблений для автоматизації процесу реєстрації касових чеків у рамках рекламних акцій. Бот використовує штучний інтелект для розпізнавання та валідації чеків, забезпечуючи швидку та точну обробку даних.

### Призначення

Основна мета бота — спростити проведення промо-кампаній для роздрібних мереж, де користувачі надсилають фотографії чеків для участі в розіграшах призів. Бот автоматизує:

- ✅ Реєстрацію учасників акції
- ✅ Розпізнавання даних з фотографій чеків
- ✅ Валідацію чеків відповідно до правил акції
- ✅ Збір статистики та аналітики
- ✅ Вибір переможців
- ✅ Експорт даних для звітності

### Ключові можливості

#### Для користувачів:
- 📸 **Швидка реєстрація чеків** — просто надішліть фото чека
- 🤖 **AI-розпізнавання** — автоматичне виділення магазину, суми, дати, часу
- 🧾 **Історія чеків** — перегляд усіх надісланих чеків
- 👤 **Управління профілем** — редагування персональних даних
- 📜 **Правила акції** — актуальна інформація про умови участі
- 🔔 **Миттєвий фідбек** — швидке підтвердження або відхилення чека

#### Для адміністраторів:
- ▶️ **Управління акціями** — запуск, налаштування, зупинка кампаній
- 📊 **Детальна статистика** — загальна, по магазинах, по періодах
- 🏬 **Управління магазинами** — додавання, видалення, активація
- 🎯 **Вибір переможців** — випадковий вибір з валідних чеків
- 📥 **Експорт даних** — автоматичне створення Excel-звітів
- 🔍 **Пошук чеків** — швидкий пошук за фіскальним кодом
- ⚙️ **Гнучкі налаштування** — дати, суми, час, магазини, канали

### Для кого цей бот?

**Bulka Receipt Bot** ідеально підходить для:

- 🏪 **Роздрібних мереж** — для проведення промо-акцій
- 📢 **Маркетингових агентств** — для управління кампаніями клієнтів
- 🎁 **Організаторів розіграшів** — для чесного вибору переможців
- 📊 **Аналітиків** — для збору даних про покупки

### Технологічні переваги

- ⚡ **Швидкість** — обробка чека за 2-5 секунд
- 🧠 **Інтелект** — використання LLaMA Vision моделей через Groq API
- 🔄 **Надійність** — ротація API ключів, fallback механізми
- 🛡️ **Безпека** — захист від дублікатів, rate limiting
- 📈 **Масштабованість** — підтримка множинних адміністраторів та API ключів
- 🇺🇦 **Локалізація** — повна підтримка української мови

---

## ⚙️ Встановлення та налаштування

### Системні вимоги

- **Python**: версія 3.9 або вище
- **Операційна система**: Linux, macOS або Windows
- **Пам'ять**: мінімум 512 MB RAM
- **Дисковий простір**: мінімум 100 MB

### Крок 1: Клонування репозиторію

```bash
git clone https://github.com/your-repo/bulka-receipt.git
cd bulka-receipt
```

### Крок 2: Створення віртуального середовища

```bash
python3 -m venv venv
```

Активація віртуального середовища:

**Linux/macOS:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

### Крок 3: Встановлення залежностей

```bash
pip install -r requirements.txt
```

**Список залежностей:**
- `aiogram==3.13.1` — фреймворк для Telegram ботів
- `aiosqlite==0.20.0` — асинхронна робота з SQLite
- `groq==1.0.0` — клієнт для Groq AI API
- `openpyxl==3.1.5` — робота з Excel файлами
- `python-dotenv==1.0.1` — завантаження змінних середовища
- `Pillow>=10.0.0` — обробка зображень
- `numpy>=1.26.0` — числові обчислення

### Крок 4: Створення Telegram бота

1. Відкрийте [@BotFather](https://t.me/BotFather) у Telegram
2. Надішліть команду `/newbot`
3. Введіть назву бота (наприклад, "Bulka Receipt Bot")
4. Введіть username бота (наприклад, "bulka_receipt_bot")
5. Збережіть отриманий **токен** бота

### Крок 5: Отримання Groq API ключів

1. Зареєструйтесь на [console.groq.com](https://console.groq.com)
2. Перейдіть до розділу API Keys
3. Створіть новий API ключ
4. Збережіть ключ у безпечному місці

**Рекомендація:** Створіть 2-3 ключі для ротації та уникнення rate limits.

### Крок 6: Налаштування змінних середовища

Створіть файл `.env` у кореневій директорії проєкту:

```bash
cp .env.example .env
```

Відредагуйте файл `.env`:

```env
# Токен Telegram бота (отриманий від BotFather)
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# ID адміністраторів (через кому, без пробілів)
# Дізнатись свій ID можна через @userinfobot
ADMIN_IDS=123456789,987654321

# Шлях до бази даних
DB_PATH=data/bot.db

# Шлях до Excel файлу
EXCEL_PATH=data/checks.xlsx

# Groq API ключі (можна вказати кілька через кому)
GROQ_API_KEYS=gsk_xxxxxxxxxxxxxxxxxxxxx,gsk_yyyyyyyyyyyyyyyyyyy

# Модель Groq (необов'язково, є значення за замовчуванням)
GROQ_MODEL=meta-llama/llama-4-maverick-17b-128e-instruct

# Резервна модель (необов'язково)
GROQ_FALLBACK_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

### Крок 7: Підготовка фото

Додайте файл `photo/sakura.jpg` у директорію `photo/`. Це зображення буде відображатись у всіх повідомленнях бота.

```bash
mkdir -p photo
# Помістіть файл sakura.jpg у директорію photo/
```

### Крок 8: Перший запуск

Запустіть бота:

```bash
python bot.py
```

При успішному запуску ви побачите:

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🧾  BULKA RECEIPT — Бот для реєстрації чеків      🧾       ║
║                    Promo System v1.0                         ║
╚══════════════════════════════════════════════════════════════╝

     🚀 Запуск бота...
     
     ⚙️ Завантаження налаштувань...
     📦 Ініціалізація бази даних...
       ✅ База даних підключена
       ✅ Налаштування акції перевірено
     
     🔌 Роутери та обробники підключено
     
────────────────────────────────────────────────────────────
   🤖 Бот готовий до роботи!
────────────────────────────────────────────────────────────
```

### Крок 9: Перевірка роботи

1. Знайдіть свого бота у Telegram за username
2. Надішліть команду `/start`
3. Пройдіть реєстрацію
4. Перевірте доступність адміністративного меню (якщо ваш ID у ADMIN_IDS)

### Можливі проблеми при встановленні

**Проблема:** `ModuleNotFoundError: No module named 'aiogram'`
**Рішення:** Перевірте, що віртуальне середовище активовано, та виконайте `pip install -r requirements.txt`

**Проблема:** `RuntimeError: BOT_TOKEN is not set`
**Рішення:** Перевірте, що файл `.env` створено та містить правильний токен

**Проблема:** `RuntimeError: GROQ_API_KEYS not set in .env`
**Рішення:** Додайте хоча б один Groq API ключ у файл `.env`

---

## 🔧 Конфігурація

### Змінні середовища

Всі налаштування бота зберігаються у файлі `.env`. Нижче детальний опис кожної змінної:

| Змінна | Обов'язкова | Опис | Приклад |
|--------|-------------|------|---------|
| `BOT_TOKEN` | ✅ Так | Токен Telegram бота від @BotFather | `1234567890:ABC...` |
| `ADMIN_IDS` | ✅ Так | ID адміністраторів (через кому) | `123456789,987654321` |
| `DB_PATH` | ❌ Ні | Шлях до бази даних | `data/bot.db` (за замовчуванням) |
| `EXCEL_PATH` | ❌ Ні | Шлях до Excel файлу | `data/checks.xlsx` (за замовчуванням) |
| `GROQ_API_KEYS` | ✅ Так | Groq API ключі (через кому) | `gsk_xxx,gsk_yyy` |
| `GROQ_MODEL` | ❌ Ні | Основна AI модель | `meta-llama/llama-4-maverick-17b-128e-instruct` |
| `GROQ_FALLBACK_MODEL` | ❌ Ні | Резервна AI модель | `meta-llama/llama-4-scout-17b-16e-instruct` |

### Налаштування бази даних

База даних автоматично створюється при першому запуску бота. Файл зберігається за шляхом, вказаним у `DB_PATH`.

**Структура:**
- Автоматичне створення таблиць
- Автоматичне створення індексів
- Foreign key constraints увімкнено
- Асинхронний доступ через aiosqlite

**Резервне копіювання:**
```bash
# Створити резервну копію
cp data/bot.db data/bot.db.backup

# Відновити з резервної копії
cp data/bot.db.backup data/bot.db
```

### Налаштування AI моделей

Бот підтримує різні LLaMA моделі через Groq API:

**Рекомендовані моделі:**
- `meta-llama/llama-4-maverick-17b-128e-instruct` — основна модель (швидка, точна)
- `meta-llama/llama-4-scout-17b-16e-instruct` — резервна модель
- `llama-3.2-90b-vision-preview` — більш потужна модель

**Ротація ключів:**
Якщо вказано кілька API ключів, бот автоматично перемикається між ними при досягненні rate limit або помилках.

### Налаштування адміністраторів

Адміністратори мають повний доступ до всіх функцій бота.

**Як дізнатись свій Telegram ID:**
1. Відкрийте [@userinfobot](https://t.me/userinfobot)
2. Надішліть будь-яке повідомлення
3. Скопіюйте значення `Id`

**Додавання нового адміністратора:**
1. Дізнайтесь ID користувача
2. Додайте ID до `.env` у змінну `ADMIN_IDS` (через кому)
3. Перезапустіть бота

```env
ADMIN_IDS=123456789,987654321,111222333
```

---

## 🏗️ Архітектура проєкту

### Структура директорій

```
bulka-receipt/
├── bot.py                      # Точка входу, ініціалізація бота
├── requirements.txt            # Залежності Python
├── .env                        # Конфігурація (не у git)
├── .env.example                # Шаблон конфігурації
├── README.md                   # Базовий опис проєкту
├── DOCUMENTATION.md            # Ця документація
├── clear_users.py              # Скрипт очищення БД
├── test_groq.py                # Тест Groq AI
├── test_models_comparison.py   # Порівняння моделей
│
├── data/                       # Дані бота (створюється автоматично)
│   ├── bot.db                  # SQLite база даних
│   └── checks.xlsx             # Excel експорт чеків
│
├── photo/                      # Зображення для повідомлень
│   └── sakura.jpg              # Фонове фото для всіх повідомлень
│
└── app/                        # Основний код бота
    ├── __init__.py
    ├── __main__.py             # Альтернативна точка входу
    ├── config.py               # Управління налаштуваннями
    ├── runtime.py              # Глобальний стан (DB, Settings)
    ├── states.py               # FSM стани для діалогів
    ├── rate_limiter.py         # Обмеження запитів
    ├── promo_manager.py        # Управління акціями
    ├── shops_manager.py        # Управління магазинами
    │
    ├── db/                     # Шар бази даних
    │   ├── __init__.py
    │   └── database.py         # SQLite CRUD операції
    │
    ├── ai/                     # AI обробка
    │   ├── __init__.py
    │   └── groq_client.py      # Groq Vision API
    │
    ├── handlers/               # Обробники команд
    │   ├── __init__.py
    │   ├── user.py             # Користувацькі команди
    │   └── admin.py            # Адміністративні команди
    │
    ├── keyboards/              # Telegram клавіатури
    │   ├── __init__.py
    │   ├── user.py             # Користувацькі кнопки
    │   └── admin.py            # Адміністративні кнопки
    │
    └── excel/                  # Excel експорт
        ├── __init__.py
        └── writer.py           # Створення XLSX файлів
```

### Основні модулі

#### `bot.py` — Точка входу
```python
Функції:
- Завантаження налаштувань з .env
- Ініціалізація бази даних
- Налаштування роутерів та фільтрів
- Запуск polling
- Graceful shutdown
```

#### `app/config.py` — Конфігурація
```python
Клас Settings:
- bot_token: str              # Токен бота
- admin_ids: List[int]        # Список ID адміністраторів
- db_path: Path               # Шлях до БД
- excel_path: Path            # Шлях до Excel
- groq_api_keys: List[str]    # Groq API ключі
- groq_model: str             # Основна модель
- groq_fallback_model: str    # Резервна модель
```

#### `app/runtime.py` — Глобальний стан
```python
Функції:
- setup(db, settings) — Ініціалізація
- get_db() — Отримати екземпляр БД
- get_settings() — Отримати налаштування
```

#### `app/db/database.py` — База даних
```python
Клас Database:
- init() — Створення таблиць
- add_user(), get_user() — Управління користувачами
- add_check(), get_checks() — Управління чеками
- add_shop(), list_shops() — Управління магазинами
- set_setting(), get_setting() — Налаштування акцій
```

#### `app/ai/groq_client.py` — AI обробка
```python
Функції:
- analyze_receipt() — Аналіз чека
- preprocess_image() — Попередня обробка
- check_blur() — Перевірка розмитості

Клас CircularKeyRotator:
- Ротація API ключів
- Автоматичний fallback
```

#### `app/handlers/user.py` — Користувацькі обробники
```python
Обробники:
- /start — Початок роботи
- Реєстрація користувача
- Надсилання чеків
- Перегляд чеків
- Управління профілем
```

#### `app/handlers/admin.py` — Адміністративні обробники
```python
Обробники:
- /admin — Головне меню
- Запуск/зупинка акції
- Управління магазинами
- Статистика
- Вибір переможців
- Експорт даних
```

### Потік даних

```
┌─────────────┐
│ Користувач  │
│ надсилає    │
│ фото чека   │
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│ Rate Limit Check │  ← 20 чеків/день
└────────┬─────────┘
         │
         ▼
┌─────────────────────┐
│ Image Preprocessing │  ← Blur detection, enhancement
└──────────┬──────────┘
           │
           ▼
┌───────────────────────┐
│ Groq Vision AI (OCR)  │  ← Розпізнавання тексту
└──────────┬────────────┘
           │
           ▼
┌────────────────────────┐
│ JSON Parsing + Regex   │  ← Витяг даних
└──────────┬─────────────┘
           │
           ▼
┌─────────────────────────┐
│ Validation (Rules)      │  ← Перевірка відповідності
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Duplicate Check         │  ← Перевірка дублікатів
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ User Confirmation       │  ← Підтвердження користувачем
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Save to SQLite          │  ← Збереження у БД
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Export to Excel         │  ← Додавання в XLSX
└─────────────────────────┘
```

### Технологічний стек

| Компонент | Технологія | Версія |
|-----------|------------|--------|
| **Мова** | Python | 3.9+ |
| **Bot Framework** | Aiogram | 3.13.1 |
| **База даних** | SQLite | (через aiosqlite 0.20.0) |
| **AI/Vision** | Groq API | 1.0.0 |
| **Обробка зображень** | Pillow | 10.0.0+ |
| **Числові операції** | NumPy | 1.26.0+ |
| **Excel** | openpyxl | 3.1.5 |
| **Env Variables** | python-dotenv | 1.0.1 |
| **Async Runtime** | asyncio | (вбудований) |

**AI моделі:**
- LLaMA 4 Maverick 17B (основна)
- LLaMA 4 Scout 17B (fallback)
- LLaMA 3.2 90B Vision (опціонально)

---

## 🗄️ База даних

### Схема бази даних

Бот використовує SQLite для зберігання даних. База даних автоматично створюється при першому запуску.

### Діаграма зв'язків

```
┌─────────────────┐
│     users       │
├─────────────────┤
│ id (PK)         │◄──┐
│ telegram_id     │   │
│ phone           │   │
│ full_name       │   │
│ created_at      │   │
└─────────────────┘   │
                      │
                      │ FK
┌─────────────────┐   │
│     checks      │   │
├─────────────────┤   │
│ id (PK)         │   │
│ user_id         │───┘
│ shop            │
│ amount          │
│ date            │
│ time            │
│ check_code      │
│ file_id         │
│ raw_text        │
│ raw_text_hash   │
│ created_at      │
└─────────────────┘

┌──────────────────┐
│ promo_settings   │
├──────────────────┤
│ key (PK)         │
│ value (JSON)     │
└──────────────────┘

┌─────────────────┐
│     shops       │
├─────────────────┤
│ id (PK)         │◄──┐
│ name (UNIQUE)   │   │
│ address         │   │
│ created_at      │   │
└─────────────────┘   │
                      │ FK
┌─────────────────┐   │
│ shop_samples    │   │
├─────────────────┤   │
│ id (PK)         │   │
│ shop_id         │───┘
│ file_id         │
│ created_at      │
└─────────────────┘
```

### Таблиця: `users`

Зберігає зареєстрованих користувачів бота.

| Поле | Тип | Опис | Обмеження |
|------|-----|------|-----------|
| `id` | INTEGER | Внутрішній ID | PRIMARY KEY, AUTOINCREMENT |
| `telegram_id` | INTEGER | Telegram user ID | UNIQUE, NOT NULL |
| `phone` | TEXT | Номер телефону | NOT NULL |
| `full_name` | TEXT | ПІБ користувача | NOT NULL |
| `created_at` | TEXT | Дата реєстрації | NOT NULL, ISO format |

**Приклад:**
```sql
id: 1
telegram_id: 123456789
phone: +380991234567
full_name: Іванов Іван Іванович
created_at: 2025-01-15T10:30:00
```

### Таблиця: `checks`

Зберігає всі надіслані чеки з розпізнаними даними.

| Поле | Тип | Опис | Обмеження |
|------|-----|------|-----------|
| `id` | INTEGER | ID чека | PRIMARY KEY, AUTOINCREMENT |
| `user_id` | INTEGER | Посилання на користувача | FK → users(id), NOT NULL |
| `shop` | TEXT | Назва магазину | NULL (якщо не розпізнано) |
| `amount` | REAL | Сума покупки | NULL (якщо не розпізнано) |
| `date` | TEXT | Дата покупки (YYYY-MM-DD) | NULL (якщо не розпізнано) |
| `time` | TEXT | Час покупки (HH:MM) | NULL (якщо не розпізнано) |
| `check_code` | TEXT | Фіскальний номер | NULL (якщо не розпізнано) |
| `file_id` | TEXT | Telegram file ID фото | NOT NULL |
| `raw_text` | TEXT | Повний OCR текст | NULL |
| `raw_text_hash` | TEXT | SHA256 хеш тексту | NULL |
| `created_at` | TEXT | Дата надсилання | NOT NULL, ISO format |

**Індекси:**
- `idx_checks_check_code` — для швидкого пошуку за фіскальним номером
- `idx_checks_raw_text_hash` — для виявлення дублікатів

**Приклад:**
```sql
id: 1
user_id: 1
shop: BULKA
amount: 125.50
date: 2025-01-15
time: 14:30
check_code: ФН12345678
file_id: AgACAgIAAxkBAAI...
raw_text: "БУЛКА\nКиїв...\nРазом: 125.50"
raw_text_hash: a1b2c3d4e5f6...
created_at: 2025-01-15T14:35:00
```

### Таблиця: `promo_settings`

Зберігає налаштування поточної акції у форматі ключ-значення.

| Поле | Тип | Опис | Обмеження |
|------|-----|------|-----------|
| `key` | TEXT | Назва налаштування | PRIMARY KEY |
| `value` | TEXT | Значення (JSON) | NULL |

**Ключі:**
- `promo_active` — `"true"` або `"false"`
- `start_date` — `"YYYY-MM-DD"`
- `end_date` — `"YYYY-MM-DD"`
- `min_amount` — `"500.0"` (число як текст)
- `active_shops` — `["BULKA", "SILPO"]` (JSON список)
- `allowed_time_from` — `"10:00"`
- `allowed_time_to` — `"20:00"`
- `telegram_channel` — `"@mychannel"` (опціонально)

**Приклад:**
```sql
key: promo_active
value: true

key: min_amount
value: 500.0

key: active_shops
value: ["BULKA", "SILPO", "ATB"]
```

### Таблиця: `shops`

Зберігає список усіх магазинів.

| Поле | Тип | Опис | Обмеження |
|------|-----|------|-----------|
| `id` | INTEGER | ID магазину | PRIMARY KEY, AUTOINCREMENT |
| `name` | TEXT | Назва магазину | UNIQUE, NOT NULL |
| `address` | TEXT | Адреса магазину | NULL |
| `created_at` | TEXT | Дата додавання | NOT NULL, ISO format |

**Приклад:**
```sql
id: 1
name: BULKA
address: м. Київ, вул. Хрещатик, 1
created_at: 2025-01-10T12:00:00
```

### Таблиця: `shop_samples`

Зберігає зразкові фото чеків для кожного магазину (використовується адміністраторами для довідки).

| Поле | Тип | Опис | Обмеження |
|------|-----|------|-----------|
| `id` | INTEGER | ID зразка | PRIMARY KEY, AUTOINCREMENT |
| `shop_id` | INTEGER | Посилання на магазин | FK → shops(id), NOT NULL, ON DELETE CASCADE |
| `file_id` | TEXT | Telegram file ID фото | NOT NULL |
| `created_at` | TEXT | Дата додавання | NOT NULL, ISO format |

**Приклад:**
```sql
id: 1
shop_id: 1
file_id: AgACAgIAAxkBAAI...
created_at: 2025-01-10T12:05:00
```

### Зв'язки між таблицями

```
users (1) ──< (N) checks
  ↑ Один користувач може мати багато чеків

shops (1) ──< (N) shop_samples
  ↑ Один магазин може мати багато зразкових фото
```

### Оптимізація

**Індекси:**
- `checks.check_code` — швидкий пошук за фіскальним кодом
- `checks.raw_text_hash` — швидка перевірка дублікатів
- `users.telegram_id` — UNIQUE constraint автоматично створює індекс

**Foreign Key Constraints:**
```sql
PRAGMA foreign_keys = ON;
```
Забезпечує цілісність даних (не можна видалити користувача, який має чеки).

---

## 💻 Розробка та тестування

### Запуск в режимі розробки

```bash
# Активувати віртуальне середовище
source venv/bin/activate

# Запустити бота
python bot.py

# Або через модуль
python -m app
```

### Тестові скрипти

#### `test_groq.py` — Тестування Groq AI

Перевіряє роботу Groq Vision API на тестовому зображенні:

```bash
python test_groq.py
```

**Що тестується:**
- Підключення до Groq API
- Розпізнавання тексту з чека
- Витяг даних (магазин, сума, дата, час, код)
- Валідація відповідно до правил

**Приклад виводу:**
```
🔍 Testing Groq OCR...

✅ RESULT:
  Shop: BULKA
  Address: Київ, вул. Хрещатик, 1
  Amount: 125.50
  Date: 2025-01-15
  Time: 14:30
  Check code: ФН12345678
  Valid: True
  Errors: []

📄 Raw text:
БУЛКА
Київ, вул. Хрещатик, 1
...
```

#### `test_models_comparison.py` — Порівняння моделей

Порівнює різні LLaMA моделі за точністю та швидкістю.

#### `clear_users.py` — Очищення бази даних

**УВАГА:** Видаляє всіх користувачів та їхні чеки!

```bash
python clear_users.py
```

Використовується при підготовці до нової акції.

### Логування

Бот використовує стандартний модуль `logging` Python.

**Рівні логування:**
- `INFO` — загальна інформація (запуск, реєстрації, чеки)
- `WARNING` — попередження (rate limit, некоректні дані)
- `ERROR` — помилки (AI failures, DB errors)
- `DEBUG` — детальна діагностика (app модуль)

**Налаштування логів:**
```python
# У bot.py
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Приглушити шумні бібліотеки
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("app").setLevel(logging.DEBUG)
```

**Приклад логів:**
```
10:30:15 [INFO] __main__: 🚀 Запуск бота...
10:30:16 [INFO] app.db.database: База даних підключена
10:30:17 [INFO] __main__: 🤖 Бот готовий до роботи!
14:25:30 [INFO] app.handlers.user: Користувач 123456789 надіслав чек
14:25:33 [INFO] app.ai.groq_client: Groq Vision: магазин=BULKA, сума=125.50
14:25:33 [INFO] app.handlers.user: Чек схвалено, збережено ID=1
```

### Структура FSM (Finite State Machine)

Бот використовує FSM для багатокрокових діалогів:

**Користувацькі стани:**
```python
RegistrationState:
  - waiting_for_contact    # Очікування номера телефону
  - waiting_for_full_name  # Очікування ПІБ

ReceiptState:
  - waiting_for_photo      # Очікування фото чека
  - waiting_for_confirm    # Очікування підтвердження

ProfileState:
  - waiting_for_new_name   # Редагування імені
```

**Адміністративні стани:**
```python
AdminStartCampaignStates:
  - start_date → end_date → start_time → end_time → shops → min_amount

AdminAddShopState:
  - waiting_for_name → waiting_for_address → waiting_for_samples

AdminSetDatesState:
  - waiting_for_start → waiting_for_end

AdminSetMinAmountState:
  - waiting_for_amount

AdminSetTimeRangeState:
  - waiting_for_start → waiting_for_end

AdminSearchState:
  - waiting_for_query

AdminStatsByPeriodStates:
  - start_date → end_date

AdminWinnerState:
  - waiting_for_count

AdminSetChannelState:
  - waiting_for_channel
```

### Налагодження

**Проблема:** Чеки не розпізнаються коректно
```bash
# Перевірити Groq API
python test_groq.py

# Збільшити логування
# У bot.py: logging.getLogger("app.ai").setLevel(logging.DEBUG)
```

**Проблема:** Rate limit від Groq
```bash
# Додати більше API ключів у .env
GROQ_API_KEYS=key1,key2,key3,key4
```

**Проблема:** База даних заблокована
```bash
# Закрити всі інші з'єднання
# Перезапустити бота
```

---

## 🔧 Troubleshooting

### Типові помилки та рішення

#### Помилки встановлення

**Помилка:** `ModuleNotFoundError: No module named 'aiogram'`

**Причина:** Залежності не встановлені або віртуальне середовище не активовано

**Рішення:**
```bash
source venv/bin/activate  # або venv\Scripts\activate на Windows
pip install -r requirements.txt
```

---

**Помилка:** `RuntimeError: BOT_TOKEN is not set`

**Причина:** Відсутній або некоректний файл `.env`

**Рішення:**
1. Переконайтесь, що файл `.env` існує у кореневій директорії
2. Перевірте, що `BOT_TOKEN` вказано правильно
3. Перезапустіть бота

---

**Помилка:** `RuntimeError: GROQ_API_KEYS not set in .env`

**Причина:** Відсутні Groq API ключі

**Рішення:**
1. Зареєструйтесь на [console.groq.com](https://console.groq.com)
2. Створіть API ключ
3. Додайте у `.env`: `GROQ_API_KEYS=gsk_your_key_here`

---

#### Помилки Groq AI

**Помилка:** `RateLimitError: Rate limit exceeded`

**Причина:** Перевищено ліміт запитів до Groq API

**Рішення:**
1. Додайте більше API ключів (бот автоматично ротує їх)
```env
GROQ_API_KEYS=key1,key2,key3
```
2. Зачекайте кілька хвилин перед наступною спробою

---

**Помилка:** `APIConnectionError: Connection failed`

**Причина:** Проблеми з інтернет-з'єднанням або Groq API недоступний

**Рішення:**
1. Перевірте інтернет-з'єднання
2. Перевірте статус Groq API на [status.groq.com](https://status.groq.com)
3. Бот автоматично перемкнеться на інший ключ

---

**Помилка:** `BadRequestError: Invalid image`

**Причина:** Зображення занадто розмите або некоректного формату

**Рішення:**
- Попросіть користувача надіслати чіткіше фото
- Бот автоматично відхиляє розмиті зображення (blur score < 500)

---

**Помилка:** `ReceiptParseError: Failed to parse receipt`

**Причина:** AI не зміг розпізнати структуру чека

**Рішення:**
- Перевірте, чи чек з підтримуваного магазину
- Попросіть користувача надіслати краще фото
- Бот спробує fallback механізми (regex, text-only retry)

---

#### Помилки бази даних

**Помилка:** `sqlite3.OperationalError: database is locked`

**Причина:** База даних вже використовується іншим процесом

**Рішення:**
1. Закрийте інші екземпляри бота
2. Видаліть файл `data/bot.db-wal` якщо існує
3. Перезапустіть бота

---

**Помилка:** `FOREIGN KEY constraint failed`

**Причина:** Спроба видалити користувача, який має чеки

**Рішення:**
- Використовуйте `clear_users.py` для повного очищення
- Або видаліть спочатку чеки, потім користувача

---

#### Помилки Telegram API

**Помилка:** `TelegramBadRequest: Message is not modified`

**Причина:** Спроба оновити повідомлення тим самим текстом

**Рішення:**
- Ігноруйте (бот обробляє це автоматично)

---

**Помилка:** `TelegramForbiddenError: Bot was blocked by the user`

**Причина:** Користувач заблокував бота

**Рішення:**
- Бот автоматично обробляє це
- Попросіть користувача розблокувати бота

---

**Помилка:** `ChatNotFound: Chat not found`

**Причина:** Спроба надіслати повідомлення у неіснуючий чат

**Рішення:**
- Перевірте ADMIN_IDS у `.env`
- Переконайтесь, що користувач спочатку написав боту

---

### Проблеми з функціональністю

**Проблема:** Чеки завжди відхиляються

**Діагностика:**
1. Перевірте, чи акція активна:
```bash
# Адмін меню → Налаштування → Перевірте статус
```
2. Перевірте параметри акції:
   - Дати (start_date, end_date)
   - Мінімальна сума
   - Активні магазини
   - Часовий діапазон

**Рішення:**
- Налаштуйте параметри акції відповідно
- Або запустіть нову акцію через /admin

---

**Проблема:** Дублікати чеків не виявляються

**Діагностика:**
```bash
# Перевірити наявність хешів у БД
sqlite3 data/bot.db "SELECT COUNT(*) FROM checks WHERE raw_text_hash IS NOT NULL;"
```

**Рішення:**
- Переконайтесь, що AI повертає `raw_text`
- Хеш обчислюється автоматично

---

**Проблема:** Адміністративне меню не відображається

**Діагностика:**
1. Дізнайтесь свій Telegram ID через [@userinfobot](https://t.me/userinfobot)
2. Перевірте `.env`:
```env
ADMIN_IDS=123456789,987654321
```

**Рішення:**
- Додайте свій ID до `ADMIN_IDS`
- Перезапустіть бота
- Надішліть /start заново

---

**Проблема:** Rate limit спрацьовує занадто часто

**Діагностика:**
```python
# У app/rate_limiter.py
_LIMIT = 20          # чеків на вікно
_WINDOW = 86400      # 24 години
```

**Рішення:**
- Збільшіть `_LIMIT` для більшої кількості чеків
- Або зменшіть `_WINDOW` для коротшого періоду
- **Увага:** Це може збільшити витрати на Groq API

---

### Корисні SQL-запити для діагностики

```sql
-- Перевірити кількість користувачів
SELECT COUNT(*) FROM users;

-- Перевірити кількість чеків
SELECT COUNT(*) FROM checks;

-- Топ-10 користувачів за кількістю чеків
SELECT u.full_name, u.phone, COUNT(c.id) as check_count
FROM users u
LEFT JOIN checks c ON u.id = c.user_id
GROUP BY u.id
ORDER BY check_count DESC
LIMIT 10;

-- Чеки без розпізнаного магазину
SELECT COUNT(*) FROM checks WHERE shop IS NULL;

-- Чеки за останні 24 години
SELECT COUNT(*) FROM checks 
WHERE created_at > datetime('now', '-1 day');

-- Налаштування акції
SELECT * FROM promo_settings;

-- Список магазинів
SELECT * FROM shops;
```

---

## 📚 Довідник

### Команди бота

#### Користувацькі команди

| Команда | Опис | Доступ |
|---------|------|--------|
| `/start` | Початок роботи, реєстрація | Всі |

**Кнопки головного меню:**
- 📸 **Зареєструвати чек** — Надіслати фото чека
- 🧾 **Мої чеки** — Переглянути історію чеків
- 👤 **Профіль** — Переглянути/редагувати дані
- 📜 **Правила акції** — Умови участі
- 🆘 **Підтримка** — Контактна інформація

#### Адміністративні команди

| Команда | Опис | Доступ |
|---------|------|--------|
| `/admin` | Адміністративне меню | Тільки ADMIN_IDS |

**Кнопки адміністративного меню:**
- ▶️ **Запустити акцію** — Налаштувати та запустити нову кампанію
- ⏹ **Зупинити акцію** — Закрити поточну акцію
- ⚙️ **Налаштування** — Змінити параметри акції
- 🏬 **Магазини** — Управління магазинами
- 📊 **Статистика** — Перегляд аналітики
- 🎯 **Переможці** — Вибір переможців
- 🔍 **Пошук чека** — Знайти чек за кодом

### FSM стани

#### Користувацькі стани

```python
class RegistrationState(StatesGroup):
    waiting_for_contact   # Очікування поділитися контактом
    waiting_for_full_name # Очікування введення ПІБ

class ReceiptState(StatesGroup):
    waiting_for_photo     # Очікування фото чека
    waiting_for_confirm   # Очікування підтвердження даних

class ProfileState(StatesGroup):
    waiting_for_new_name  # Очікування нового імені
```

#### Адміністративні стани

```python
class AdminStartCampaignStates(StatesGroup):
    start_date   # Дата початку акції
    end_date     # Дата закінчення
    start_time   # Час початку (години)
    end_time     # Час закінчення
    shops        # Вибір магазинів
    min_amount   # Мінімальна сума

class AdminAddShopState(StatesGroup):
    waiting_for_name     # Назва магазину
    waiting_for_address  # Адреса
    waiting_for_samples  # Зразкові фото

class AdminSetDatesState(StatesGroup):
    waiting_for_start    # Дата початку
    waiting_for_end      # Дата закінчення

class AdminSetMinAmountState(StatesGroup):
    waiting_for_amount   # Мінімальна сума

class AdminSetTimeRangeState(StatesGroup):
    waiting_for_start    # Час початку
    waiting_for_end      # Час закінчення

class AdminSearchState(StatesGroup):
    waiting_for_query    # Пошуковий запит

class AdminStatsByPeriodStates(StatesGroup):
    start_date           # Дата початку періоду
    end_date             # Дата закінчення періоду

class AdminWinnerState(StatesGroup):
    waiting_for_count    # Кількість переможців

class AdminSetChannelState(StatesGroup):
    waiting_for_channel  # Username каналу
```

### Константи та налаштування

#### Rate Limiting (`app/rate_limiter.py`)
```python
_LIMIT = 20          # Максимум чеків на вікно
_WINDOW = 86400      # Вікно: 24 години (секунди)
```

#### Прomo Rules Cache (`app/promo_manager.py`)
```python
_RULES_CACHE_TTL = 30.0  # Час життя кешу: 30 секунд
```

#### Image Processing (`app/ai/groq_client.py`)
```python
BLUR_THRESHOLD = 500.0          # Поріг розмитості (Laplacian)
MAX_IMAGE_DIMENSION = 2048      # Максимальний розмір зображення
JPEG_QUALITY = 92               # Якість JPEG (0-100)
SHARPEN_FACTOR = 1.5            # Коефіцієнт підвищення різкості
AUTO_CONTRAST_CUTOFF = 2        # Відсікання для auto-contrast
```

#### AI Models
```python
DEFAULT_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
MAX_TOKENS = 512                # Для vision request
TEXT_RETRY_MAX_TOKENS = 256     # Для text-only retry
```

### Глосарій термінів

| Термін | Опис |
|--------|------|
| **Акція (Campaign)** | Рекламна кампанія з конкретними правилами та періодом |
| **Чек (Receipt/Check)** | Касовий чек, надісланий користувачем |
| **Фіскальний номер (Check Code)** | Унікальний код чека (ФН, ФП, ФЧ) |
| **OCR** | Optical Character Recognition — розпізнавання тексту з зображень |
| **FSM** | Finite State Machine — скінченний автомат для багатокрокових діалогів |
| **Rate Limit** | Обмеження кількості запитів на період часу |
| **Groq API** | API для доступу до LLaMA моделей штучного інтелекту |
| **Blur Detection** | Виявлення розмитості зображення |
| **Fallback** | Запасний варіант при збої основного методу |
| **Telegram ID** | Унікальний числовий ідентифікатор користувача Telegram |
| **Levenshtein Distance** | Відстань редагування між рядками (для fuzzy matching) |

---

## 🎓 Заключення

**Bulka Receipt Bot** — це потужний та гнучкий інструмент для автоматизації промо-акцій з чеками. Завдяки інтеграції з Groq Vision AI, бот забезпечує швидку та точну обробку чеків, а адміністративна панель дозволяє повністю контролювати акції.

### Підтримка

Якщо у вас виникли питання або проблеми:
1. Перевірте розділ [Troubleshooting](#-troubleshooting)
2. Переглянте логи бота
3. Звернутьсяло до репозиторію проєкту

### Ліцензія

[Вкажіть ліцензію вашого проєкту]

### Автори

[Вкажіть авторів проєкту]

---

**Дякуємо за використання Bulka Receipt Bot! 🧾**
