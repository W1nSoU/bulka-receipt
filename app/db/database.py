from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

import aiosqlite


@dataclass
class User:
    id: int
    telegram_id: int
    phone: str
    full_name: str
    created_at: str


@dataclass
class Receipt:
    id: int
    user_id: int
    shop: Optional[str]
    amount: Optional[float]
    date: Optional[str]
    time: Optional[str]
    check_code: Optional[str]
    file_id: str
    raw_text: str
    created_at: str


class Database:
    EXCLUDED_SHOP_FOR_STATS = 'ТОВ "Епіцентр К" Гіпермаркет "Епіцентр К"'

    def __init__(self, path: Path):
        self.path = path

    async def _fetchone(self, query: str, params: tuple[Any, ...] = (), row_factory=None):
        async with aiosqlite.connect(self.path) as db:
            if row_factory:
                db.row_factory = row_factory
            cursor = await db.execute(query, params)
            return await cursor.fetchone()

    async def _fetchall(self, query: str, params: tuple[Any, ...] = (), row_factory=None):
        async with aiosqlite.connect(self.path) as db:
            if row_factory:
                db.row_factory = row_factory
            cursor = await db.execute(query, params)
            return await cursor.fetchall()

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    phone TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    min_amount REAL DEFAULT 0.0,
                    shops TEXT,
                    is_current INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    archived_at TEXT
                );

                CREATE TABLE IF NOT EXISTS checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    shop TEXT,
                    amount REAL,
                    date TEXT,
                    time TEXT,
                    check_code TEXT,
                    file_id TEXT NOT NULL,
                    raw_text TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_checks_check_code ON checks(check_code);

                CREATE TABLE IF NOT EXISTS promo_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS shops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    address TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS shop_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shop_id INTEGER NOT NULL,
                    file_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(shop_id) REFERENCES shops(id) ON DELETE CASCADE
                );
                """
            )
            # Міграція: додаємо raw_text_hash якщо колонки ще немає
            try:
                await db.execute("ALTER TABLE checks ADD COLUMN raw_text_hash TEXT")
            except Exception:
                pass  # колонка вже існує
            
            # Міграція: додаємо campaign_id якщо колонки ще немає
            try:
                await db.execute("ALTER TABLE checks ADD COLUMN campaign_id INTEGER")
            except Exception:
                pass  # колонка вже існує
            
            # Індекс на raw_text_hash — після міграції, щоб колонка точно існувала
            try:
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_checks_raw_text_hash ON checks(raw_text_hash)"
                )
            except Exception:
                pass
            
            # Індекс на campaign_id — після міграції
            try:
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_checks_campaign_id ON checks(campaign_id)"
                )
            except Exception:
                pass
            
            await db.commit()

    async def fetch_user(self, telegram_id: int) -> Optional[User]:
        row = await self._fetchone(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,),
            row_factory=aiosqlite.Row,
        )
        if not row:
            return None
        return User(
            id=row["id"],
            telegram_id=row["telegram_id"],
            phone=row["phone"],
            full_name=row["full_name"],
            created_at=row["created_at"],
        )

    async def create_user(self, telegram_id: int, phone: str, full_name: str) -> User:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "INSERT INTO users (telegram_id, phone, full_name, created_at) VALUES (?, ?, ?, ?)",
                (telegram_id, phone, full_name, now),
            )
            await db.commit()
            user_id = cursor.lastrowid
        return User(
            id=int(user_id),
            telegram_id=telegram_id,
            phone=phone,
            full_name=full_name,
            created_at=now,
        )

    async def update_user_name(self, telegram_id: int, new_name: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET full_name = ? WHERE telegram_id = ?",
                (new_name, telegram_id),
            )
            await db.commit()

    async def get_user_receipts(self, user_id: int, limit: int = 5) -> List[Receipt]:
        rows = await self._fetchall(
            """
            SELECT * FROM checks 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
            """,
            (user_id, limit),
            row_factory=aiosqlite.Row,
        )
        return [
            Receipt(
                id=row["id"],
                user_id=row["user_id"],
                shop=row["shop"],
                amount=row["amount"],
                date=row["date"],
                time=row["time"],
                check_code=row["check_code"],
                file_id=row["file_id"],
                raw_text=row["raw_text"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def insert_check(
        self,
        user_id: int,
        shop: Optional[str],
        amount: Optional[float],
        date: Optional[str],
        time: Optional[str],
        check_code: Optional[str],
        file_id: str,
        raw_text: str,
        raw_text_hash: Optional[str] = None,
    ) -> Receipt:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                INSERT INTO checks (user_id, shop, amount, date, time, check_code, file_id, raw_text, raw_text_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, shop, amount, date, time, check_code, file_id, raw_text, raw_text_hash, now),
            )
            await db.commit()
            check_id = cursor.lastrowid
        return Receipt(
            id=int(check_id),
            user_id=user_id,
            shop=shop,
            amount=amount,
            date=date,
            time=time,
            check_code=check_code,
            file_id=file_id,
            raw_text=raw_text,
            created_at=now,
        )

    async def is_duplicate_check_code(self, check_code: Optional[str], amount: Optional[float] = None) -> bool:
        if not check_code:
            return False
        
        if amount is not None:
            # Якщо є сума, перевіряємо комбінацію код + сума
            row = await self._fetchone(
                "SELECT id FROM checks WHERE check_code = ? AND amount = ? LIMIT 1", 
                (check_code, amount)
            )
        else:
            # Fallback на стару логіку
            row = await self._fetchone(
                "SELECT id FROM checks WHERE check_code = ? LIMIT 1", (check_code,)
            )
        return row is not None

    async def is_duplicate_raw_hash(self, raw_text_hash: Optional[str]) -> bool:
        if not raw_text_hash:
            return False
        row = await self._fetchone(
            "SELECT id FROM checks WHERE raw_text_hash = ? LIMIT 1", (raw_text_hash,)
        )
        return row is not None

    async def get_user_stats(self, user_id: int) -> tuple[int, float]:
        """Повертає (кількість чеків, загальна сума) для юзера."""
        row = await self._fetchone(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0.0) FROM checks WHERE user_id = ?",
            (user_id,),
        )
        return (int(row[0]), float(row[1])) if row else (0, 0.0)

    async def set_setting(self, key: str, value: Any) -> None:
        stored = json.dumps(value) if not isinstance(value, str) else value
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO promo_settings(key, value) VALUES(?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, stored),
            )
            await db.commit()

    async def get_setting(self, key: str, default: Any | None = None) -> Any:
        row = await self._fetchone(
            "SELECT value FROM promo_settings WHERE key = ?", (key,)
        )
        if not row:
            return default
        raw_value = row[0]
        try:
            return json.loads(raw_value)
        except (TypeError, json.JSONDecodeError):
            return raw_value

    async def get_settings_map(self) -> dict[str, Any]:
        rows = await self._fetchall(
            "SELECT key, value FROM promo_settings", row_factory=aiosqlite.Row
        )
        result: dict[str, Any] = {}
        for row in rows:
            raw = row["value"]
            try:
                result[row["key"]] = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                result[row["key"]] = raw
        return result

    async def add_shop(self, name: str) -> int:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "INSERT INTO shops(name, created_at) VALUES(?, ?)", (name, now)
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def delete_shop(self, shop_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM shops WHERE id = ?", (shop_id,))
            await db.execute("DELETE FROM shop_samples WHERE shop_id = ?", (shop_id,))
            await db.commit()

    async def list_shops(self) -> List[tuple[int, str]]:
        rows = await self._fetchall("SELECT id, name FROM shops ORDER BY name")
        return [(int(r[0]), str(r[1])) for r in rows]

    async def get_shop_address(self, shop_name: str) -> Optional[str]:
        row = await self._fetchone(
            "SELECT address FROM shops WHERE UPPER(name) = UPPER(?) LIMIT 1",
            (shop_name,),
        )
        return row[0] if row and row[0] else None

    async def set_shop_address(self, shop_id: int, address: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE shops SET address = ? WHERE id = ?",
                (address, shop_id),
            )
            await db.commit()

    async def update_shop_name(self, shop_id: int, new_name: str) -> str:
        """Оновлює назву магазину та повертає стару назву"""
        # Спочатку отримуємо стару назву
        row = await self._fetchone("SELECT name FROM shops WHERE id = ?", (shop_id,))
        old_name = row[0] if row else None
        
        if old_name:
            async with aiosqlite.connect(self.path) as db:
                await db.execute(
                    "UPDATE shops SET name = ? WHERE id = ?",
                    (new_name, shop_id),
                )
                await db.commit()
        
        return old_name

    async def list_shops_with_addresses(self) -> List[tuple[int, str, Optional[str]]]:
        rows = await self._fetchall("SELECT id, name, address FROM shops ORDER BY name")
        return [(int(r[0]), str(r[1]), r[2]) for r in rows]

    async def add_shop_sample(self, shop_id: int, file_id: str) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO shop_samples(shop_id, file_id, created_at) VALUES(?, ?, ?)",
                (shop_id, file_id, now),
            )
            await db.commit()

    async def clear_checks(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM checks")
            await db.commit()

    async def clear_users(self) -> None:
        # delete checks first due to FK constraint, then users
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM checks")
            await db.execute("DELETE FROM users")
            await db.commit()

    async def get_shop_samples(self, shop_id: int) -> List[str]:
        rows = await self._fetchall(
            "SELECT file_id FROM shop_samples WHERE shop_id = ?", (shop_id,)
        )
        return [r[0] for r in rows]

    async def count_checks(self) -> int:
        row = await self._fetchone("SELECT COUNT(*) FROM checks")
        return int(row[0]) if row else 0

    async def count_valid_checks(self) -> int:
        # currently every saved check is valid by workflow
        return await self.count_checks()

    async def stats_by_shop(self) -> List[tuple[str, int, float]]:
        rows = await self._fetchall(
            """
            SELECT COALESCE(shop, 'Невідомо') as shop, COUNT(*) as cnt, SUM(amount) as total
            FROM checks
            WHERE UPPER(TRIM(COALESCE(shop, ''))) != UPPER(TRIM(?))
            GROUP BY shop
            ORDER BY cnt DESC
            """,
            (self.EXCLUDED_SHOP_FOR_STATS,),
        )
        result: List[tuple[str, int, float]] = []
        for row in rows:
            total = float(row[2]) if row[2] is not None else 0.0
            result.append((str(row[0]), int(row[1]), total))
        return result

    async def stats_overview(self) -> tuple[int, int, float]:
        row = await self._fetchone(
            "SELECT COUNT(*) as cnt, COUNT(DISTINCT user_id) as users, SUM(amount) as total FROM checks"
        )
        if not row:
            return 0, 0, 0.0
        total_amount = float(row[2]) if row[2] is not None else 0.0
        return int(row[0]), int(row[1]), total_amount

    async def stats_by_period(self, start_date: str, end_date: str) -> tuple[int, int, float]:
        row = await self._fetchone(
            """
            SELECT COUNT(*) as cnt, COUNT(DISTINCT user_id) as users, SUM(amount) as total
            FROM checks
            WHERE date >= ? AND date <= ?
            """,
            (start_date, end_date),
        )
        if not row:
            return 0, 0, 0.0
        total_amount = float(row[2]) if row[2] is not None else 0.0
        return int(row[0]), int(row[1]), total_amount

    async def random_receipt(self) -> Optional[Receipt]:
        row = await self._fetchone(
            """
            SELECT * FROM checks
            ORDER BY RANDOM()
            LIMIT 1
            """,
            row_factory=aiosqlite.Row,
        )
        if not row:
            return None
        return Receipt(
            id=row["id"],
            user_id=row["user_id"],
            shop=row["shop"],
            amount=row["amount"],
            date=row["date"],
            time=row["time"],
            check_code=row["check_code"],
            file_id=row["file_id"],
            raw_text=row["raw_text"],
            created_at=row["created_at"],
        )

    async def random_receipts(self, count: int) -> List[Receipt]:
        rows = await self._fetchall(
            """
            SELECT * FROM checks
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (count,),
            row_factory=aiosqlite.Row,
        )
        return [
            Receipt(
                id=row["id"],
                user_id=row["user_id"],
                shop=row["shop"],
                amount=row["amount"],
                date=row["date"],
                time=row["time"],
                check_code=row["check_code"],
                file_id=row["file_id"],
                raw_text=row["raw_text"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def random_user_with_stats(self) -> Optional[tuple[User, int, float]]:
        row = await self._fetchone(
            """
            SELECT user_id, COUNT(*) as cnt, SUM(amount) as total
            FROM checks
            GROUP BY user_id
            ORDER BY RANDOM()
            LIMIT 1
            """
        )
        if not row:
            return None
        user = await self.find_user(int(row[0]))
        total_amount = float(row[2]) if row[2] is not None else 0.0
        return user, int(row[1]), total_amount

    async def latest_checks(self, limit: int = 10) -> List[Receipt]:
        rows = await self._fetchall(
            "SELECT * FROM checks ORDER BY created_at DESC LIMIT ?",
            (limit,),
            row_factory=aiosqlite.Row,
        )
        results: List[Receipt] = []
        for row in rows:
            results.append(
                Receipt(
                    id=row["id"],
                    user_id=row["user_id"],
                    shop=row["shop"],
                    amount=row["amount"],
                    date=row["date"],
                    time=row["time"],
                    check_code=row["check_code"],
                    file_id=row["file_id"],
                    raw_text=row["raw_text"],
                    created_at=row["created_at"],
                )
            )
        return results

    async def find_receipt_by_code(self, code: str) -> Optional[Receipt]:
        row = await self._fetchone(
            "SELECT * FROM checks WHERE check_code = ? LIMIT 1",
            (code,),
            row_factory=aiosqlite.Row,
        )
        if not row:
            return None
        return Receipt(
            id=row["id"],
            user_id=row["user_id"],
            shop=row["shop"],
            amount=row["amount"],
            date=row["date"],
            time=row["time"],
            check_code=row["check_code"],
            file_id=row["file_id"],
            raw_text=row["raw_text"],
            created_at=row["created_at"],
        )

    async def find_receipt_by_id(self, receipt_id: int) -> Optional[Receipt]:
        row = await self._fetchone(
            "SELECT * FROM checks WHERE id = ? LIMIT 1",
            (receipt_id,),
            row_factory=aiosqlite.Row,
        )
        if not row:
            return None
        return Receipt(
            id=row["id"],
            user_id=row["user_id"],
            shop=row["shop"],
            amount=row["amount"],
            date=row["date"],
            time=row["time"],
            check_code=row["check_code"],
            file_id=row["file_id"],
            raw_text=row["raw_text"],
            created_at=row["created_at"],
        )

    async def find_user(self, user_id: int) -> Optional[User]:
        row = await self._fetchone(
            "SELECT * FROM users WHERE id = ? LIMIT 1",
            (user_id,),
            row_factory=aiosqlite.Row,
        )
        if not row:
            return None
        return User(
            id=row["id"],
            telegram_id=row["telegram_id"],
            phone=row["phone"],
            full_name=row["full_name"],
            created_at=row["created_at"],
        )

    async def all_valid_receipts(self) -> List[Receipt]:
        rows = await self._fetchall("SELECT * FROM checks", row_factory=aiosqlite.Row)
        return [
            Receipt(
                id=row["id"],
                user_id=row["user_id"],
                shop=row["shop"],
                amount=row["amount"],
                date=row["date"],
                time=row["time"],
                check_code=row["check_code"],
                file_id=row["file_id"],
                raw_text=row["raw_text"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def search_receipt(self, query: str) -> Optional[Receipt]:
        # search by check_code or id
        row = await self._fetchone(
            "SELECT * FROM checks WHERE check_code = ? OR id = ? LIMIT 1",
            (query, query),
            row_factory=aiosqlite.Row,
        )
        if row:
            return Receipt(
                id=row["id"],
                user_id=row["user_id"],
                shop=row["shop"],
                amount=row["amount"],
                date=row["date"],
                time=row["time"],
                check_code=row["check_code"],
                file_id=row["file_id"],
                raw_text=row["raw_text"],
                created_at=row["created_at"],
            )
        # search by user full_name/phone
        row = await self._fetchone(
            """
            SELECT c.* FROM checks c
            JOIN users u ON u.id = c.user_id
            WHERE u.phone = ? OR u.full_name LIKE ?
            ORDER BY c.created_at DESC
            LIMIT 1
            """,
            (query, f"%{query}%"),
            row_factory=aiosqlite.Row,
        )
        if not row:
            return None
        return Receipt(
            id=row["id"],
            user_id=row["user_id"],
            shop=row["shop"],
            amount=row["amount"],
            date=row["date"],
            time=row["time"],
            check_code=row["check_code"],
            file_id=row["file_id"],
            raw_text=row["raw_text"],
            created_at=row["created_at"],
        )

    # Campaign management
    async def create_campaign(
        self, name: str, start_date: str, end_date: str, min_amount: float, shops: List[str]
    ) -> int:
        """Створює нову акцію"""
        import json
        now = datetime.utcnow().isoformat()
        shops_json = json.dumps(shops)
        
        async with aiosqlite.connect(self.path) as db:
            # Знімаємо прапорець is_current з усіх акцій
            await db.execute("UPDATE campaigns SET is_current = 0")
            
            # Створюємо нову
            cursor = await db.execute(
                """INSERT INTO campaigns 
                (name, start_date, end_date, min_amount, shops, is_current, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (name, start_date, end_date, min_amount, shops_json, now),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def get_current_campaign(self) -> Optional[tuple]:
        """Повертає поточну акцію (id, name, start_date, end_date, min_amount, shops)"""
        import json
        row = await self._fetchone(
            "SELECT id, name, start_date, end_date, min_amount, shops FROM campaigns WHERE is_current = 1 LIMIT 1"
        )
        if not row:
            return None
        shops = json.loads(row[5]) if row[5] else []
        return (row[0], row[1], row[2], row[3], row[4], shops)

    async def archive_current_campaign(self) -> None:
        """Архівує поточну акцію"""
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE campaigns SET is_current = 0, archived_at = ? WHERE is_current = 1",
                (now,),
            )
            await db.commit()

    async def assign_checks_to_campaign(self, campaign_id: int) -> int:
        """Прив'язує всі чеки без campaign_id до вказаної акції. Повертає кількість оновлених."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "UPDATE checks SET campaign_id = ? WHERE campaign_id IS NULL",
                (campaign_id,),
            )
            await db.commit()
            return cursor.rowcount or 0

    async def get_campaigns_history(self) -> List[tuple]:
        """Повертає список всіх акцій (id, name, start_date, end_date, checks_count, is_current)"""
        rows = await self._fetchall(
            """
            SELECT 
                c.id, c.name, c.start_date, c.end_date,
                COUNT(ch.id) as checks_count,
                c.is_current
            FROM campaigns c
            LEFT JOIN checks ch ON ch.campaign_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
            """,
            row_factory=aiosqlite.Row,
        )
        return [(row["id"], row["name"], row["start_date"], row["end_date"], row["checks_count"], row["is_current"]) for row in rows]
