import json
import random
import time
from typing import Optional

import aiosqlite

from config import DB_PATH, OWNER_ID

_SCHEMA = """
          CREATE TABLE IF NOT EXISTS users
          (
              user_id
              INTEGER
              PRIMARY
              KEY,
              username
              TEXT,
              first_name
              TEXT,
              is_banned
              INTEGER
              NOT
              NULL
              DEFAULT
              0,
              is_muted
              INTEGER
              NOT
              NULL
              DEFAULT
              0,
              joined_at
              INTEGER
              NOT
              NULL
          );

          CREATE TABLE IF NOT EXISTS admins
          (
              user_id
              INTEGER
              PRIMARY
              KEY,
              is_owner
              INTEGER
              NOT
              NULL
              DEFAULT
              0,
              added_at
              INTEGER
              NOT
              NULL
          );

          CREATE TABLE IF NOT EXISTS channels
          (
              channel_id
              INTEGER
              PRIMARY
              KEY
              AUTOINCREMENT,
              chat_id
              INTEGER
              NOT
              NULL,
              title
              TEXT
              NOT
              NULL,
              invite_link
              TEXT,
              archived
              INTEGER
              NOT
              NULL
              DEFAULT
              0,
              water_text
              TEXT
          );

          CREATE TABLE IF NOT EXISTS applications
          (
              app_id
              INTEGER
              PRIMARY
              KEY
              AUTOINCREMENT,
              user_id
              INTEGER
              NOT
              NULL,
              channel_id
              INTEGER
              NOT
              NULL,
              status
              TEXT
              NOT
              NULL
              DEFAULT
              'pending', -- pending / accepted
              created_at
              INTEGER
              NOT
              NULL,
              UNIQUE
          (
              user_id,
              channel_id
          )
              );

          CREATE TABLE IF NOT EXISTS posts
          (
              post_id
              INTEGER
              PRIMARY
              KEY
              AUTOINCREMENT,
              user_id
              INTEGER
              NOT
              NULL,
              channel_id
              INTEGER
              NOT
              NULL,
              content_type
              TEXT
              NOT
              NULL,      -- text / photo / video / document
              content_data
              TEXT
              NOT
              NULL,      -- JSON: {text, caption, file_id, entities}
              status
              TEXT
              NOT
              NULL
              DEFAULT
              'pending', -- pending/published/rejected
              created_at
              INTEGER
              NOT
              NULL,
              admin_chat_id
              INTEGER,
              admin_message_id
              INTEGER,
              published_chat_id
              INTEGER,
              published_message_id
              INTEGER
          );

          CREATE TABLE IF NOT EXISTS ad_posts
          (
              ad_id
              INTEGER
              PRIMARY
              KEY
              AUTOINCREMENT,
              user_id
              INTEGER
              NOT
              NULL,
              content_type
              TEXT
              NOT
              NULL,
              content_data
              TEXT
              NOT
              NULL,
              is_active
              INTEGER
              NOT
              NULL
              DEFAULT
              1,
              is_main
              INTEGER
              NOT
              NULL
              DEFAULT
              0,
              created_at
              INTEGER
              NOT
              NULL
          );

          CREATE TABLE IF NOT EXISTS ad_settings
          (
              key
              TEXT
              PRIMARY
              KEY,
              value
              TEXT
              NOT
              NULL
          );

          CREATE TABLE IF NOT EXISTS post_spam
          (
              user_id
              INTEGER
              NOT
              NULL,
              sent_at
              INTEGER
              NOT
              NULL
          );

          CREATE TABLE IF NOT EXISTS scheduled_deletions
          (
              sched_id
              INTEGER
              PRIMARY
              KEY
              AUTOINCREMENT,
              channel_id
              INTEGER
              NOT
              NULL,
              chat_id
              INTEGER
              NOT
              NULL,
              message_id
              INTEGER
              NOT
              NULL,
              delete_at
              INTEGER, -- NULL => не удалять
              deleted
              INTEGER
              NOT
              NULL
              DEFAULT
              0,
              created_at
              INTEGER
              NOT
              NULL
          );

          CREATE TABLE IF NOT EXISTS scheduled_broadcasts
          (
              sched_id
              INTEGER
              PRIMARY
              KEY
              AUTOINCREMENT,
              content_type
              TEXT
              NOT
              NULL,
              content_data
              TEXT
              NOT
              NULL, -- JSON: {text, caption, file_id, ...}
              send_at
              INTEGER
              NOT
              NULL,
              sent
              INTEGER
              NOT
              NULL
              DEFAULT
              0,
              created_by
              INTEGER,
              created_at
              INTEGER
              NOT
              NULL
          );

          CREATE TABLE IF NOT EXISTS ad_user_state (
              user_id      INTEGER PRIMARY KEY,
              last_ad_id   INTEGER,
              sent_at      INTEGER NOT NULL DEFAULT 0
          );
          """


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id, is_owner, added_at) VALUES (?, 1, ?)",
            (OWNER_ID, int(time.time())),
        )
        await db.commit()

    # На случай, если каналы уже были задублированы раньше (до этой правки) —
    # схлопываем дубликаты по chat_id и только потом ставим уникальный индекс,
    # чтобы его создание не падало на старых данных.
    await _dedupe_channels()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_chat_id ON channels(chat_id)"
        )
        await db.commit()


async def _dedupe_channels() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT chat_id, COUNT(*) AS cnt FROM channels GROUP BY chat_id HAVING cnt > 1"
        )
        dupes = await cur.fetchall()

        for row in dupes:
            chat_id = row["chat_id"]
            cur = await db.execute(
                "SELECT * FROM channels WHERE chat_id=? ORDER BY channel_id ASC", (chat_id,)
            )
            rows = await cur.fetchall()
            canonical = rows[0]
            extra_ids = [r["channel_id"] for r in rows[1:]]

            # Предпочитаем непустые title/invite_link/water_text из дублей, если у канонической записи их нет
            title = canonical["title"]
            invite_link = canonical["invite_link"]
            water_text = canonical["water_text"]
            archived = canonical["archived"]
            for r in rows[1:]:
                if not invite_link and r["invite_link"]:
                    invite_link = r["invite_link"]
                if not water_text and r["water_text"]:
                    water_text = r["water_text"]
                if not r["archived"]:
                    archived = 0

            await db.execute(
                "UPDATE channels SET title=?, invite_link=?, water_text=?, archived=? WHERE channel_id=?",
                (title, invite_link, water_text, archived, canonical["channel_id"]),
            )

            if extra_ids:
                placeholders = ",".join("?" * len(extra_ids))
                # applications имеет UNIQUE(user_id, channel_id) — используем OR IGNORE,
                # чтобы не упасть, если у пользователя уже есть заявка на канонический канал
                await db.execute(
                    f"UPDATE OR IGNORE applications SET channel_id=? WHERE channel_id IN ({placeholders})",
                    (canonical["channel_id"], *extra_ids),
                )
                # то, что не смогли перенести из-за конфликта уникальности, просто удаляем
                await db.execute(
                    f"DELETE FROM applications WHERE channel_id IN ({placeholders})",
                    extra_ids,
                )
                await db.execute(
                    f"UPDATE posts SET channel_id=? WHERE channel_id IN ({placeholders})",
                    (canonical["channel_id"], *extra_ids),
                )
                await db.execute(
                    f"UPDATE scheduled_deletions SET channel_id=? WHERE channel_id IN ({placeholders})",
                    (canonical["channel_id"], *extra_ids),
                )
                await db.execute(
                    f"DELETE FROM channels WHERE channel_id IN ({placeholders})", extra_ids
                )

        await db.commit()


def _now() -> int:
    return int(time.time())


# --- users -------------------------------------------------------------------

async def upsert_user(user_id: int, username: Optional[str], first_name: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (user_id, username, first_name, joined_at)
               VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO
            UPDATE SET username=excluded.username,
                first_name=excluded.first_name""",
            (user_id, username, first_name, _now()),
        )
        await db.commit()


async def get_user(user_id: int) -> Optional[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return await cur.fetchone()


async def get_user_by_username(username: str) -> Optional[aiosqlite.Row]:
    """Find a known bot user by username, ignoring an optional leading @."""
    username = username.strip().lstrip("@").casefold()
    if not username:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE username IS NOT NULL AND lower(username)=? LIMIT 1",
            (username,),
        )
        return await cur.fetchone()


async def all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users WHERE is_banned=0")
        return [r[0] for r in await cur.fetchall()]


async def set_ban(user_id: int, banned: bool) -> None:
    # The owner must never be blocked, even if a caller forgets to check first.
    if banned and user_id == OWNER_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=? WHERE user_id=?", (int(banned), user_id))
        await db.commit()


async def set_mute(user_id: int, muted: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_muted=? WHERE user_id=?", (int(muted), user_id))
        await db.commit()


async def is_banned(user_id: int) -> bool:
    u = await get_user(user_id)
    return bool(u and u["is_banned"])


async def is_muted(user_id: int) -> bool:
    u = await get_user(user_id)
    return bool(u and u["is_muted"])


async def banned_list() -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE is_banned=1")
        return await cur.fetchall()


# --- admins -------------------------------------------------------------------

async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
        return (await cur.fetchone()) is not None


async def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


async def add_admin(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id, is_owner, added_at) VALUES (?, 0, ?)",
            (user_id, _now()),
        )
        await db.commit()


async def remove_admin(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id=? AND is_owner=0", (user_id,))
        await db.commit()


async def restore_owner() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id, is_owner, added_at) VALUES (?, 1, ?)",
            (OWNER_ID, _now()),
        )
        await db.commit()


async def list_admins() -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM admins ORDER BY is_owner DESC")
        return await cur.fetchall()


# --- channels -----------------------------------------------------------------

async def add_channel(chat_id: int, title: str, invite_link: Optional[str]) -> tuple[int, bool]:
    """
    Добавляет канал, если его ещё нет в базе (по chat_id).
    Если канал уже существует — обновляет title/invite_link (если пришли новые)
    и снимает архивн��ю отметку, но НЕ создаёт дубликат.

    Возвращает (channel_id, created), где created=True, если запись новая.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM channels WHERE chat_id=?", (chat_id,))
        existing = await cur.fetchone()

        if existing:
            new_title = title or existing["title"]
            new_link = invite_link or existing["invite_link"]
            await db.execute(
                "UPDATE channels SET title=?, invite_link=?, archived=0 WHERE channel_id=?",
                (new_title, new_link, existing["channel_id"]),
            )
            await db.commit()
            return existing["channel_id"], False

        cur = await db.execute(
            "INSERT INTO channels (chat_id, title, invite_link) VALUES (?, ?, ?)",
            (chat_id, title, invite_link),
        )
        await db.commit()
        return cur.lastrowid, True


async def rename_channel(channel_id: int, new_title: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE channels SET title=? WHERE channel_id=?", (new_title, channel_id))
        await db.commit()


async def archive_channel(channel_id: int, archived: bool = True) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE channels SET archived=? WHERE channel_id=?", (int(archived), channel_id)
        )
        await db.commit()


async def get_channel(channel_id: int) -> Optional[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM channels WHERE channel_id=?", (channel_id,))
        return await cur.fetchone()


async def list_channels(include_archived: bool = False) -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if include_archived:
            cur = await db.execute("SELECT * FROM channels ORDER BY title")
        else:
            cur = await db.execute("SELECT * FROM channels WHERE archived=0 ORDER BY title")
        return await cur.fetchall()


async def set_water(channel_id: int, text: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE channels SET water_text=? WHERE channel_id=?", (text, channel_id))
        await db.commit()


# --- applications (заявки) ----------------------------------------------------

async def create_application(user_id: int, channel_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO applications (user_id, channel_id, status, created_at)
               VALUES (?, ?, 'pending', ?) ON CONFLICT(user_id, channel_id) DO NOTHING""",
            (user_id, channel_id, _now()),
        )
        await db.commit()


async def has_application(user_id: int, channel_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM applications WHERE user_id=? AND channel_id=?", (user_id, channel_id)
        )
        return (await cur.fetchone()) is not None


async def get_channel_by_chat_id(chat_id: int) -> Optional[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM channels WHERE chat_id=?", (chat_id,))
        return await cur.fetchone()


async def pending_counts_by_channel() -> dict[int, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT channel_id, COUNT(*) FROM applications WHERE status='pending' GROUP BY channel_id"
        )
        return {row[0]: row[1] for row in await cur.fetchall()}


async def accept_applications(channel_ids: list[int]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        q = f"UPDATE applications SET status='accepted' WHERE status='pending' AND channel_id IN ({','.join('?' * len(channel_ids))})"
        await db.execute(q, channel_ids)
        await db.commit()


async def accept_all_applications() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE applications SET status='accepted' WHERE status='pending'")
        await db.commit()


# --- posts / moderation --------------------------------------------------------

async def create_post(user_id: int, channel_id: int, content_type: str, content_data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO posts (user_id, channel_id, content_type, content_data, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, channel_id, content_type, json.dumps(content_data), _now()),
        )
        await db.commit()
        return cur.lastrowid


async def set_post_admin_message(post_id: int, chat_id: int, message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE posts SET admin_chat_id=?, admin_message_id=? WHERE post_id=?",
            (chat_id, message_id, post_id),
        )
        await db.commit()


async def get_post(post_id: int) -> Optional[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM posts WHERE post_id=?", (post_id,))
        return await cur.fetchone()


async def set_post_channel(post_id: int, channel_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE posts SET channel_id=? WHERE post_id=?", (channel_id, post_id))
        await db.commit()


async def mark_post_published(post_id: int, chat_id: int, message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE posts
               SET status='published',
                   published_chat_id=?,
                   published_message_id=?
               WHERE post_id = ?""",
            (chat_id, message_id, post_id),
        )
        await db.commit()


async def mark_post_rejected(post_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE posts SET status='rejected' WHERE post_id=?", (post_id,))
        await db.commit()


async def count_posts() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM posts WHERE status='published'")
        row = await cur.fetchone()
        return row[0]


# --- antispam -------------------------------------------------------------------

async def register_post_sent(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO post_spam (user_id, sent_at) VALUES (?, ?)", (user_id, _now()))
        await db.commit()


async def recent_post_count(user_id: int, window_seconds: int) -> int:
    since = _now() - window_seconds
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM post_spam WHERE user_id=? AND sent_at>=?", (user_id, since)
        )
        row = await cur.fetchone()
        return row[0]


# --- fake stats -------------------------------------------------------------------

async def set_fake_stat(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO fake_stats (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await db.commit()


async def get_fake_stat(key: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM fake_stats WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None


# --- scheduled deletions -------------------------------------------------------

async def add_scheduled_deletion(
        channel_id: int, chat_id: int, message_id: int, delete_at: Optional[int]
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO scheduled_deletions (channel_id, chat_id, message_id, delete_at, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (channel_id, chat_id, message_id, delete_at, _now()),
        )
        await db.commit()
        return cur.lastrowid


async def due_deletions() -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM scheduled_deletions WHERE deleted=0 AND delete_at IS NOT NULL AND delete_at<=?",
            (_now(),),
        )
        return await cur.fetchall()


async def list_scheduled(active_only: bool = True) -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if active_only:
            cur = await db.execute("SELECT * FROM scheduled_deletions WHERE deleted=0")
        else:
            cur = await db.execute("SELECT * FROM scheduled_deletions")
        return await cur.fetchall()


async def mark_deleted(sched_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE scheduled_deletions SET deleted=1 WHERE sched_id=?", (sched_id,))
        await db.commit()


async def cancel_scheduled(sched_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE scheduled_deletions SET delete_at=NULL WHERE sched_id=?", (sched_id,)
        )
        await db.commit()


async def reschedule(sched_id: int, delete_at: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE scheduled_deletions SET delete_at=? WHERE sched_id=?", (delete_at, sched_id)
        )
        await db.commit()


async def get_scheduled(sched_id: int) -> Optional[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM scheduled_deletions WHERE sched_id=?", (sched_id,))
        return await cur.fetchone()


# --- scheduled broadcasts (рассылка в��ем пользователям бота в заданное время) --

async def create_scheduled_broadcast(
        content_type: str, content_data: dict, send_at: int, created_by: Optional[int]
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO scheduled_broadcasts (content_type, content_data, send_at, created_by, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (content_type, json.dumps(content_data), send_at, created_by, _now()),
        )
        await db.commit()
        return cur.lastrowid


async def due_broadcasts() -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM scheduled_broadcasts WHERE sent=0 AND send_at<=?", (_now(),)
        )
        return await cur.fetchall()


async def mark_broadcast_sent(sched_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE scheduled_broadcasts SET sent=1 WHERE sched_id=?", (sched_id,))
        await db.commit()


async def list_pending_broadcasts() -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM scheduled_broadcasts WHERE sent=0 ORDER BY send_at"
        )
        return await cur.fetchall()


async def cancel_scheduled_broadcast(sched_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM scheduled_broadcasts WHERE sched_id=?", (sched_id,))
        await db.commit()


async def set_ad_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO ad_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await db.commit()


async def get_ad_setting(key: str, default: str = "1") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM ad_settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default


async def ads_enabled() -> bool:
    return (await get_ad_setting("ads_enabled", "1")) == "1"


async def set_ads_enabled(enabled: bool) -> bool:
    enabled_value = "1" if enabled else "0"
    await set_ad_setting("ads_enabled", enabled_value)
    return enabled


async def toggle_ads_enabled() -> bool:
    enabled = await ads_enabled()
    await set_ads_enabled(not enabled)
    return not enabled


async def set_ads_mode(mode: str) -> str:
    mode = mode if mode in {"main", "random"} else "main"
    await set_ad_setting("ads_mode", mode)
    return mode


async def get_ads_mode() -> str:
    return await get_ad_setting("ads_mode", "main")


async def list_ad_posts(active_only: bool = False) -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if active_only:
            cur = await db.execute(
                "SELECT * FROM ad_posts WHERE is_active=1 ORDER BY is_main DESC, created_at DESC"
            )
        else:
            cur = await db.execute("SELECT * FROM ad_posts ORDER BY created_at DESC")
        return await cur.fetchall()


async def get_ad_post(ad_id: int) -> Optional[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM ad_posts WHERE ad_id=?", (ad_id,))
        return await cur.fetchone()


async def add_ad_post(user_id: int, content_type: str, content_data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO ad_posts (user_id, content_type, content_data, is_active, is_main, created_at) VALUES (?, ?, ?, 1, 0, ?)",
            (user_id, content_type, json.dumps(content_data), _now()),
        )
        await db.commit()
        return cur.lastrowid


async def update_ad_post(ad_id: int, content_type: str, content_data: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE ad_posts SET content_type=?, content_data=? WHERE ad_id=?",
            (content_type, json.dumps(content_data), ad_id),
        )
        await db.commit()


async def delete_ad_post(ad_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM ad_posts WHERE ad_id=?", (ad_id,))
        await db.commit()


async def set_ad_active(ad_id: int, active: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE ad_posts SET is_active=? WHERE ad_id=?",
            (int(active), ad_id),
        )
        await db.commit()


async def set_ad_main(ad_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE ad_posts SET is_main=0 WHERE is_main=1")
        await db.execute(
            "UPDATE ad_posts SET is_main=1, is_active=1 WHERE ad_id=?",
            (ad_id,),
        )
        await db.commit()
        await set_ads_mode("main")


async def get_last_ad_for_user(user_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT last_ad_id FROM ad_user_state WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        return row[0] if row and row[0] is not None else None


async def set_last_ad_for_user(user_id: int, ad_id: Optional[int]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO ad_user_state (user_id, last_ad_id, sent_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_ad_id=excluded.last_ad_id, sent_at=excluded.sent_at",
            (user_id, ad_id, _now()),
        )
        await db.commit()


async def clear_last_ad_for_user(user_id: int) -> None:
    await set_last_ad_for_user(user_id, None)


async def pick_ad_for_user(user_id: int) -> Optional[aiosqlite.Row]:
    ads = await list_ad_posts(active_only=True)
    if not ads:
        return None

    last_ad_id = await get_last_ad_for_user(user_id)
    candidates = [ad for ad in ads if ad["ad_id"] != last_ad_id]
    if not candidates:
        candidates = ads

    mode = await get_ads_mode()
    if mode == "main":
        for ad in candidates:
            if ad["is_main"]:
                return ad
        return candidates[0]
    if mode == "random":
        return random.choice(candidates)
    return candidates[0]
