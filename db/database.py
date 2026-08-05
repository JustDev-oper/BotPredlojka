"""SQLite database layer for the Telegram bot.

Provides a single Database class with CRUD operations for users, posts,
spam tracking, channels, watermarks, auto-delete, requests, and statistics.
All public methods are thread-safe (uses connection-level locking).
"""

import asyncio
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import config

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "bot.db")))


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class Database:
    """Database with connection-level locking for async safety."""

    def __init__(self) -> None:
        self.connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.cursor = self.connection.cursor()
        # Asyncio-compatible lock to serialise all DB operations
        self._lock = asyncio.Lock()
        self._init_tables()

    async def _execute(self, func, *args):
        """Run a DB operation under the lock — serialises all calls."""
        async with self._lock:
            return func(*args)

    @contextmanager
    def _transaction(self):
        try:
            yield self.cursor
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _init_tables(self) -> None:
        # This runs only once on init (sync), not under async lock.
        # Сначала удаляем старые таблицы, которые больше не нужны
        self.cursor.executescript("""
            DROP TABLE IF EXISTS message_stats;
            DROP TABLE IF EXISTS spam_log;
            DROP TABLE IF EXISTS admin_requests;
        """)
        self.connection.commit()

        # Создаём таблицы по одной, чтобы избежать ошибок при конфликте схем
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                banned INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                muted_until TEXT,
                spam_level INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS post_topic_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                admin_tg_id INTEGER NOT NULL,
                topic_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reply_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_message_id INTEGER NOT NULL,
                user_tg_id INTEGER NOT NULL,
                admin_tg_id INTEGER,
                direction TEXT NOT NULL,
                post_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS fake_stats (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_username TEXT UNIQUE NOT NULL,
                channel_title TEXT,
                channel_tg_id INTEGER,
                is_active INTEGER DEFAULT 1,
                require_subscription INTEGER DEFAULT 0,
                added_by INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS admin_channel_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_tg_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                topic_id INTEGER NOT NULL,
                UNIQUE(admin_tg_id, channel_id)
            );

            CREATE TABLE IF NOT EXISTS watermarks (
                channel_id INTEGER PRIMARY KEY,
                text TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS auto_delete_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                delete_at TEXT NOT NULL,
                message_ids TEXT,
                is_cancelled INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS channel_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_tg_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_tg_id, channel_id)
            );

            CREATE TABLE IF NOT EXISTS user_post_count (
                user_tg_id INTEGER PRIMARY KEY,
                post_count INTEGER DEFAULT 0,
                last_post_at TEXT
            );
        """)
        self.connection.commit()

        # Миграция: проверяем и создаём таблицу posts заново если схема устарела
        self._migrate_posts_table()
        self._migrate_channels_table()

        # Индексы (создаём после миграции)
        self.cursor.executescript("""
            CREATE INDEX IF NOT EXISTS idx_posts_channel_status ON posts(channel_id, status);
            CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_tg_id);
            CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
            CREATE INDEX IF NOT EXISTS idx_users_tg_id ON users(tg_id);
            CREATE INDEX IF NOT EXISTS idx_auto_delete_del ON auto_delete_posts(delete_at);
            CREATE INDEX IF NOT EXISTS idx_channel_requests_user ON channel_requests(user_tg_id);
            CREATE INDEX IF NOT EXISTS idx_channel_requests_ch ON channel_requests(channel_id);
        """)
        self.connection.commit()
        self._ensure_owner()

    def _table_has_column(self, table: str, column: str) -> bool:
        """Check if a column exists in a table."""
        try:
            known_tables = {
                "users", "posts", "channels", "auto_delete_posts",
                "watermarks", "post_topic_messages", "reply_map",
                "fake_stats", "admin_channel_topics", "channel_requests",
                "user_post_count",
            }
            if table not in known_tables:
                logger.warning("Unknown table in _table_has_column: %s", table)
                return False
            # PRAGMA doesn't accept parameters — table name is validated above
            self.cursor.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in self.cursor.fetchall()]
            return column in columns
        except sqlite3.OperationalError:
            return False

    def _table_exists(self, table: str) -> bool:
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        return self.cursor.fetchone() is not None

    def _migrate_posts_table(self) -> None:
        """Если таблица posts существует, но не содержит нужных колонок — пересоздаём."""
        if not self._table_exists("posts"):
            self.cursor.execute("""
                CREATE TABLE posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_tg_id INTEGER NOT NULL,
                    content_type TEXT NOT NULL,
                    file_id TEXT,
                    file_ids TEXT,
                    caption TEXT,
                    text_content TEXT,
                    status TEXT DEFAULT 'pending',
                    channel_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.connection.commit()
            return

        # Проверяем наличие обязательных колонок
        required = {"user_tg_id", "content_type", "file_id", "file_ids", "caption", "text_content", "status", "channel_id"}
        existing = set()
        self.cursor.execute("PRAGMA table_info(posts)")
        for row in self.cursor.fetchall():
            existing.add(row[1])

        if not required.issubset(existing):
            # Схема не совпадает — пересоздаём таблицу
            self.cursor.execute("DROP TABLE posts")
            self.cursor.execute("""
                CREATE TABLE posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_tg_id INTEGER NOT NULL,
                    content_type TEXT NOT NULL,
                    file_id TEXT,
                    file_ids TEXT,
                    caption TEXT,
                    text_content TEXT,
                    status TEXT DEFAULT 'pending',
                    channel_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.connection.commit()

    def _migrate_channels_table(self) -> None:
        """Добавляет require_subscription если отсутствует."""
        if self._table_exists("channels") and not self._table_has_column("channels", "require_subscription"):
            self.cursor.execute("ALTER TABLE channels ADD COLUMN require_subscription INTEGER DEFAULT 0")
            self.connection.commit()

    def _ensure_owner(self) -> None:
        if not config.OWNER_ID:
            return
        user = self.get_user_by_telegram_id(config.OWNER_ID)
        if not user:
            self.create_user(config.OWNER_ID, None, "Владелец", is_admin=True)
        else:
            self.set_admin(config.OWNER_ID, True)

    def is_owner(self, tg_id: int) -> bool:
        return tg_id == config.OWNER_ID

    # ── Users ─────────────────────────────────────────────────

    def get_user_by_telegram_id(self, tg_id: int) -> sqlite3.Row | None:
        self.cursor.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        return self.cursor.fetchone()

    @lru_cache(maxsize=256)
    def _is_admin_cached(self, tg_id: int) -> bool:
        """Cached admin check — invalidated on admin changes."""
        if self.is_owner(tg_id):
            return True
        user = self.get_user_by_telegram_id(tg_id)
        return bool(user and user["is_admin"])

    def create_user(
        self,
        tg_id: int,
        username: str | None,
        full_name: str | None,
        *,
        banned: bool = False,
        is_admin: bool = False,
    ) -> None:
        with self._transaction() as cur:
            cur.execute(
                """INSERT OR IGNORE INTO users (tg_id, username, full_name, banned, is_admin)
                   VALUES (?, ?, ?, ?, ?)""",
                (tg_id, username, full_name, int(banned), int(is_admin)),
            )

    def upsert_user(self, tg_id: int, username: str | None, full_name: str | None) -> sqlite3.Row:
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO users (tg_id, username, full_name)
                   VALUES (?, ?, ?)
                   ON CONFLICT(tg_id) DO UPDATE SET
                     username = excluded.username,
                     full_name = excluded.full_name""",
                (tg_id, username, full_name),
            )
        return self.get_user_by_telegram_id(tg_id)

    def set_banned(self, tg_id: int, banned: bool) -> None:
        with self._transaction() as cur:
            cur.execute("UPDATE users SET banned = ? WHERE tg_id = ?", (int(banned), tg_id))

    def set_admin(self, tg_id: int, is_admin: bool) -> None:
        with self._transaction() as cur:
            cur.execute("UPDATE users SET is_admin = ? WHERE tg_id = ?", (int(is_admin), tg_id))
        self.invalidate_admin_cache()

    def set_muted_until(self, tg_id: int, until: datetime | None) -> None:
        with self._transaction() as cur:
            cur.execute(
                "UPDATE users SET muted_until = ? WHERE tg_id = ?",
                (until.isoformat() if until else None, tg_id),
            )

    def is_muted(self, tg_id: int) -> bool:
        user = self.get_user_by_telegram_id(tg_id)
        if not user or not user["muted_until"]:
            return False
        try:
            until = datetime.fromisoformat(user["muted_until"])
        except ValueError:
            return False
        return datetime.now(timezone.utc) < _to_utc(until)

    def get_mute_remaining(self, tg_id: int) -> int | None:
        user = self.get_user_by_telegram_id(tg_id)
        if not user or not user["muted_until"]:
            return None
        try:
            until = datetime.fromisoformat(user["muted_until"])
        except ValueError:
            return None
        delta = _to_utc(until) - datetime.now(timezone.utc)
        return int(delta.total_seconds()) if delta.total_seconds() > 0 else None

    def is_admin(self, tg_id: int) -> bool:
        if self.is_owner(tg_id):
            return True
        return self._is_admin_cached(tg_id)

    def invalidate_admin_cache(self) -> None:
        """Call after set_admin() to clear the LRU cache."""
        self._is_admin_cached.cache_clear()

    def is_moderator(self, tg_id: int) -> bool:
        """Модератор — это админ, но не владелец."""
        if self.is_owner(tg_id):
            return False
        user = self.get_user_by_telegram_id(tg_id)
        return bool(user and user["is_admin"])

    def is_banned(self, tg_id: int) -> bool:
        user = self.get_user_by_telegram_id(tg_id)
        return bool(user and user["banned"])

    def get_all_admins(self) -> list[int]:
        self.cursor.execute("SELECT tg_id FROM users WHERE is_admin = 1")
        ids = {row[0] for row in self.cursor.fetchall()}
        if config.OWNER_ID:
            ids.add(config.OWNER_ID)
        return list(ids)

    def get_all_moderators(self) -> list[sqlite3.Row]:
        """Все админы, кроме владельца."""
        self.cursor.execute("SELECT * FROM users WHERE is_admin = 1 AND tg_id != ?", (config.OWNER_ID,))
        return self.cursor.fetchall()

    def get_banned_users(self) -> list[sqlite3.Row]:
        self.cursor.execute("SELECT * FROM users WHERE banned = 1 ORDER BY id DESC")
        return self.cursor.fetchall()

    def get_all_users(self) -> list[sqlite3.Row]:
        self.cursor.execute("SELECT * FROM users ORDER BY id DESC")
        return self.cursor.fetchall()

    def find_user_by_username(self, username: str) -> sqlite3.Row | None:
        self.cursor.execute(
            "SELECT * FROM users WHERE LOWER(username) = ?",
            (username.lstrip("@").lower(),),
        )
        return self.cursor.fetchone()

    # ── Posts ─────────────────────────────────────────────────

    def create_post(
        self,
        user_tg_id: int,
        content_type: str,
        *,
        file_id: str | None = None,
        file_ids: str | None = None,
        caption: str | None = None,
        text_content: str | None = None,
    ) -> int:
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO posts
                   (user_tg_id, content_type, file_id, file_ids, caption, text_content)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_tg_id, content_type, file_id, file_ids, caption, text_content),
            )
            return cur.lastrowid

    def set_post_channel(self, post_id: int, channel_id: int) -> None:
        with self._transaction() as cur:
            cur.execute("UPDATE posts SET channel_id = ? WHERE id = ?", (channel_id, post_id))

    def get_post(self, post_id: int) -> sqlite3.Row | None:
        self.cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        return self.cursor.fetchone()

    def set_post_status(self, post_id: int, status: str) -> None:
        with self._transaction() as cur:
            cur.execute("UPDATE posts SET status = ? WHERE id = ?", (status, post_id))

    def try_set_post_status(self, post_id: int, new_status: str, *, expected_status: str = "pending") -> bool:
        with self._transaction() as cur:
            cur.execute(
                "UPDATE posts SET status = ? WHERE id = ? AND status = ?",
                (new_status, post_id, expected_status),
            )
            return cur.rowcount > 0

    def count_posts_by_channel(self, channel_id: int, status: str = "pending") -> int:
        self.cursor.execute(
            "SELECT COUNT(*) FROM posts WHERE channel_id = ? AND status = ?",
            (channel_id, status),
        )
        return self.cursor.fetchone()[0]

    def get_posts_by_channel(
        self, channel_id: int, offset: int, limit: int, status: str = "pending"
    ) -> list[sqlite3.Row]:
        self.cursor.execute(
            """SELECT * FROM posts WHERE channel_id = ? AND status = ?
               ORDER BY id DESC LIMIT ? OFFSET ?""",
            (channel_id, status, limit, offset),
        )
        return self.cursor.fetchall()

    # ── Reply Map ─────────────────────────────────────────────

    def add_reply_map(
        self,
        bot_message_id: int,
        user_tg_id: int,
        direction: str,
        *,
        admin_tg_id: int | None = None,
        post_id: int | None = None,
    ) -> None:
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO reply_map
                   (bot_message_id, user_tg_id, admin_tg_id, direction, post_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (bot_message_id, user_tg_id, admin_tg_id, direction, post_id),
            )

    def get_reply_map(self, bot_message_id: int) -> sqlite3.Row | None:
        self.cursor.execute("SELECT * FROM reply_map WHERE bot_message_id = ?", (bot_message_id,))
        return self.cursor.fetchone()

    # ── Statistics ────────────────────────────────────────────

    def get_statistics(self) -> dict[str, Any]:
        self.cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM users) AS all_users,
                (SELECT COUNT(*) FROM posts) AS all_posts,
                (SELECT COUNT(*) FROM posts WHERE status = 'published') AS published,
                (SELECT COUNT(*) FROM posts WHERE status = 'rejected') AS rejected,
                (SELECT COUNT(*) FROM posts WHERE status = 'pending') AS pending,
                (SELECT COUNT(*) FROM channels WHERE is_active = 1) AS channels_count,
                (SELECT COUNT(*) FROM users WHERE banned = 1) AS banned,
                (SELECT COUNT(*) FROM users WHERE is_admin = 1) AS admins
        """)
        row = self.cursor.fetchone()
        stats = dict(row)
        if config.OWNER_ID:
            stats["admins"] = max(stats["admins"], 1)
        return stats

    # ── Fake Stats ────────────────────────────────────────────

    def get_fake_stats(self) -> dict[str, int]:
        self.cursor.execute("SELECT key, value FROM fake_stats")
        return {row[0]: row[1] for row in self.cursor.fetchall()}

    def set_fake_stat(self, key: str, value: int) -> None:
        with self._transaction() as cur:
            cur.execute(
                "INSERT INTO fake_stats (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def clear_all_fake_stats(self) -> None:
        with self._transaction() as cur:
            cur.execute("DELETE FROM fake_stats")

    # ── Broadcast ─────────────────────────────────────────────

    def get_broadcast_recipients(self) -> list[int]:
        self.cursor.execute("SELECT tg_id FROM users WHERE banned = 0")
        return [row[0] for row in self.cursor.fetchall()]

    # ── Channels ──────────────────────────────────────────────

    def add_channel(
        self,
        channel_username: str,
        channel_title: str | None,
        channel_tg_id: int | None,
        added_by: int,
    ) -> int:
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO channels (channel_username, channel_title, channel_tg_id, added_by)
                   VALUES (?, ?, ?, ?)""",
                (channel_username, channel_title, channel_tg_id, added_by),
            )
            return cur.lastrowid

    def rename_channel(self, channel_id: int, new_title: str) -> None:
        with self._transaction() as cur:
            cur.execute("UPDATE channels SET channel_title = ? WHERE id = ?", (new_title, channel_id))

    def get_channel_by_username(self, username: str) -> sqlite3.Row | None:
        self.cursor.execute("SELECT * FROM channels WHERE channel_username = ?", (username,))
        return self.cursor.fetchone()

    def get_channel_by_id(self, channel_id: int) -> sqlite3.Row | None:
        self.cursor.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
        return self.cursor.fetchone()

    def get_channel_by_tg_id(self, channel_tg_id: int) -> sqlite3.Row | None:
        self.cursor.execute("SELECT * FROM channels WHERE channel_tg_id = ?", (channel_tg_id,))
        return self.cursor.fetchone()

    def get_active_channels(self) -> list[sqlite3.Row]:
        self.cursor.execute("SELECT * FROM channels WHERE is_active = 1 ORDER BY id")
        return self.cursor.fetchall()

    def get_channels_with_stats(self) -> list[dict]:
        self.cursor.execute("""
            SELECT c.*,
                   COUNT(CASE WHEN p.status = 'pending' THEN 1 END) AS post_count,
                   (SELECT COUNT(*) FROM channel_requests cr WHERE cr.channel_id = c.id AND cr.status = 'pending') AS request_count
            FROM channels c
            LEFT JOIN posts p ON p.channel_id = c.id
            WHERE c.is_active = 1
            GROUP BY c.id
            ORDER BY c.id
        """)
        return [dict(row) for row in self.cursor.fetchall()]

    def deactivate_channel(self, channel_id: int) -> None:
        with self._transaction() as cur:
            cur.execute("UPDATE channels SET is_active = 0 WHERE id = ?", (channel_id,))

    def toggle_require_subscription(self, channel_id: int) -> bool:
        with self._transaction() as cur:
            cur.execute("SELECT require_subscription FROM channels WHERE id = ?", (channel_id,))
            row = cur.fetchone()
            if not row:
                return False
            new_val = 0 if row["require_subscription"] else 1
            cur.execute("UPDATE channels SET require_subscription = ? WHERE id = ?", (new_val, channel_id))
            return bool(new_val)

    def delete_channel(self, channel_id: int) -> bool:
        """Полное удаление канала и связанных данных из БД."""
        with self._transaction() as cur:
            # Удаляем связанные данные в правильном порядке (FK-зависимости)
            cur.execute("DELETE FROM channel_requests WHERE channel_id = ?", (channel_id,))
            cur.execute("DELETE FROM auto_delete_posts WHERE channel_id = ?", (channel_id,))
            cur.execute("DELETE FROM watermarks WHERE channel_id = ?", (channel_id,))
            cur.execute("DELETE FROM posts WHERE channel_id = ?", (channel_id,))
            # Удаляем сам канал
            cur.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
            return cur.rowcount > 0

    def get_channel_with_stats(self, channel_id: int) -> dict | None:
        """Получает канал со статистикой."""
        cur = self.cursor.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
        channel = cur.fetchone()
        if not channel:
            return None
        # Количество постов
        self.cursor.execute(
            "SELECT COUNT(*) as cnt FROM posts WHERE channel_id = ?",
            (channel_id,),
        )
        pending = self.cursor.fetchone()["cnt"]
        return {
            "id": channel["id"],
            "channel_username": channel["channel_username"],
            "channel_title": channel["channel_title"],
            "channel_tg_id": channel["channel_tg_id"],
            "is_active": channel["is_active"],
            "require_subscription": channel["require_subscription"],
            "pending_posts": pending,
        }

    # ── Watermarks ────────────────────────────────────────────

    def set_watermark(self, channel_id: int, text: str) -> None:
        with self._transaction() as cur:
            cur.execute(
                "INSERT INTO watermarks (channel_id, text) VALUES (?, ?) "
                "ON CONFLICT(channel_id) DO UPDATE SET text = excluded.text",
                (channel_id, text),
            )

    def get_watermark(self, channel_id: int) -> str | None:
        self.cursor.execute("SELECT text FROM watermarks WHERE channel_id = ?", (channel_id,))
        row = self.cursor.fetchone()
        return row[0] if row else None

    def delete_watermark(self, channel_id: int) -> None:
        with self._transaction() as cur:
            cur.execute("DELETE FROM watermarks WHERE channel_id = ?", (channel_id,))

    # ── Auto-delete ───────────────────────────────────────────

    def add_auto_delete(self, post_id: int, channel_id: int, delete_at: str, message_ids: list[int]) -> int:
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO auto_delete_posts (post_id, channel_id, delete_at, message_ids)
                   VALUES (?, ?, ?, ?)""",
                (post_id, channel_id, delete_at, json.dumps(message_ids)),
            )
            return cur.lastrowid

    def get_auto_delete_posts(self) -> list[sqlite3.Row]:
        self.cursor.execute(
            "SELECT * FROM auto_delete_posts WHERE is_cancelled = 0 ORDER BY delete_at"
        )
        return self.cursor.fetchall()

    def get_pending_auto_deletes(self) -> list[sqlite3.Row]:
        self.cursor.execute(
            "SELECT * FROM auto_delete_posts WHERE is_cancelled = 0 AND datetime(delete_at) <= datetime('now')"
        )
        return self.cursor.fetchall()

    def cancel_auto_delete(self, ad_id: int) -> None:
        with self._transaction() as cur:
            cur.execute("UPDATE auto_delete_posts SET is_cancelled = 1 WHERE id = ?", (ad_id,))

    def get_auto_delete(self, ad_id: int) -> sqlite3.Row | None:
        self.cursor.execute("SELECT * FROM auto_delete_posts WHERE id = ?", (ad_id,))
        return self.cursor.fetchone()

    def update_auto_delete_time(self, ad_id: int, new_delete_at: str) -> None:
        with self._transaction() as cur:
            cur.execute("UPDATE auto_delete_posts SET delete_at = ? WHERE id = ?", (new_delete_at, ad_id))

    # ── Channel Requests (Заявки) ─────────────────────────────

    def add_channel_request(self, user_tg_id: int, channel_id: int) -> None:
        with self._transaction() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO channel_requests (user_tg_id, channel_id) VALUES (?, ?)",
                (user_tg_id, channel_id),
            )

    def has_pending_request(self, user_tg_id: int, channel_id: int) -> bool:
        self.cursor.execute(
            "SELECT status FROM channel_requests WHERE user_tg_id = ? AND channel_id = ?",
            (user_tg_id, channel_id),
        )
        row = self.cursor.fetchone()
        return bool(row and row["status"] == "pending")

    def has_channel_request(self, user_tg_id: int, channel_id: int) -> bool:
        """Подавал ли пользователь заявку в канал (любой статус)."""
        self.cursor.execute(
            "SELECT 1 FROM channel_requests WHERE user_tg_id = ? AND channel_id = ?",
            (user_tg_id, channel_id),
        )
        return self.cursor.fetchone() is not None

    def get_pending_requests_for_channel(self, channel_id: int) -> list[sqlite3.Row]:
        self.cursor.execute(
            "SELECT cr.*, u.username, u.full_name FROM channel_requests cr "
            "JOIN users u ON u.tg_id = cr.user_tg_id "
            "WHERE cr.channel_id = ? AND cr.status = 'pending' ORDER BY cr.created_at",
            (channel_id,),
        )
        return self.cursor.fetchall()

    def accept_request(self, user_tg_id: int, channel_id: int) -> None:
        with self._transaction() as cur:
            cur.execute(
                "UPDATE channel_requests SET status = 'accepted' WHERE user_tg_id = ? AND channel_id = ?",
                (user_tg_id, channel_id),
            )

    def accept_all_requests(self, channel_id: int) -> int:
        with self._transaction() as cur:
            cur.execute(
                "UPDATE channel_requests SET status = 'accepted' WHERE channel_id = ? AND status = 'pending'",
                (channel_id,),
            )
            return cur.rowcount

    # ── User Post Count (Антиспам) ────────────────────────────

    def increment_user_post_count(self, user_tg_id: int) -> int:
        with self._transaction() as cur:
            cur.execute(
                "INSERT INTO user_post_count (user_tg_id, post_count, last_post_at) VALUES (?, 1, datetime('now')) "
                "ON CONFLICT(user_tg_id) DO UPDATE SET "
                "post_count = CASE "
                "  WHEN datetime(last_post_at) < datetime('now', '-1 hours') THEN 1 "
                "  ELSE post_count + 1 "
                "END, "
                "last_post_at = datetime('now')",
                (user_tg_id,),
            )
            cur.execute("SELECT post_count, last_post_at FROM user_post_count WHERE user_tg_id = ?", (user_tg_id,))
            row = cur.fetchone()
            return row["post_count"] if row else 1

    def reset_user_post_count(self, user_tg_id: int) -> None:
        with self._transaction() as cur:
            cur.execute("DELETE FROM user_post_count WHERE user_tg_id = ?", (user_tg_id,))

    # ── Admin Channel Topics ──────────────────────────────────

    def save_admin_topic(self, admin_tg_id: int, channel_id: int, topic_id: int) -> None:
        with self._transaction() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO admin_channel_topics
                   (admin_tg_id, channel_id, topic_id)
                   VALUES (?, ?, ?)""",
                (admin_tg_id, channel_id, topic_id),
            )

    def get_admin_topic(self, admin_tg_id: int, channel_id: int) -> sqlite3.Row | None:
        self.cursor.execute(
            "SELECT * FROM admin_channel_topics WHERE admin_tg_id = ? AND channel_id = ?",
            (admin_tg_id, channel_id),
        )
        return self.cursor.fetchone()

    def get_topics_for_channel(self, channel_id: int) -> list[sqlite3.Row]:
        self.cursor.execute(
            "SELECT * FROM admin_channel_topics WHERE channel_id = ?",
            (channel_id,),
        )
        return self.cursor.fetchall()

    def get_topics_for_admin(self, admin_tg_id: int) -> list[sqlite3.Row]:
        self.cursor.execute(
            "SELECT * FROM admin_channel_topics WHERE admin_tg_id = ?",
            (admin_tg_id,),
        )
        return self.cursor.fetchall()

    def delete_admin_topic(self, admin_tg_id: int, channel_id: int) -> None:
        with self._transaction() as cur:
            cur.execute(
                "DELETE FROM admin_channel_topics WHERE admin_tg_id = ? AND channel_id = ?",
                (admin_tg_id, channel_id),
            )

    def delete_all_topics_for_channel(self, channel_id: int) -> None:
        with self._transaction() as cur:
            cur.execute(
                "DELETE FROM admin_channel_topics WHERE channel_id = ?",
                (channel_id,),
            )

    # ── Post Topic Messages ───────────────────────────────────

    def save_post_topic_message(self, post_id: int, admin_tg_id: int, topic_id: int, message_id: int) -> None:
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO post_topic_messages
                   (post_id, admin_tg_id, topic_id, message_id)
                   VALUES (?, ?, ?, ?)""",
                (post_id, admin_tg_id, topic_id, message_id),
            )

    def get_post_topic_messages(self, post_id: int) -> list[sqlite3.Row]:
        self.cursor.execute(
            "SELECT * FROM post_topic_messages WHERE post_id = ?",
            (post_id,),
        )
        return self.cursor.fetchall()


db = Database()
