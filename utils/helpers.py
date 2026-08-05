import logging
from datetime import datetime

from aiogram import Bot
from aiogram.types import User

from config import config
from db.database import db

logger = logging.getLogger(__name__)


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_admin_post_text_from_db(post, user_row, channel_row) -> str:
    """Формат поста для админа:
    [Пост пользователя — без изменений]
    ——————————————————
    Канал: Название канала
    Ник: Имя
    Юзернейм: @username
    ID: 123456789
    """
    content = post["text_content"] or post["caption"]
    body = (content or "").strip() or "—"

    channel_title = channel_row["channel_title"] or f"@{channel_row['channel_username']}"
    full_name = user_row["full_name"] or "—"
    username = f"@{user_row['username']}" if user_row["username"] else "нет username"
    tg_id = user_row["tg_id"]

    return (
        f"{body}\n"
        f"——————————————————\n"
        f"Канал: {escape_html(channel_title)}\n"
        f"Ник: {escape_html(full_name)}\n"
        f"Юзернейм: {escape_html(username)}\n"
        f"ID: <code>{tg_id}</code>"
    )


BAN_USER_MESSAGE = (
    "Вы заблокированы в боте и больше не можете отправлять посты."
)


async def notify_user_banned(bot: Bot, tg_id: int) -> None:
    try:
        await bot.send_message(tg_id, BAN_USER_MESSAGE)
    except Exception:
        logger.warning("Не удалось уведомить пользователя %s о бане", tg_id)


def format_mute_time(seconds: int) -> str:
    if seconds >= 3600:
        return f"{seconds // 3600} ч. {(seconds % 3600) // 60} мин."
    if seconds >= 60:
        return f"{seconds // 60} мин."
    return f"{seconds} сек."


def format_statistics(stats: dict) -> str:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    return (
        f"📊 <b>Статистика бота</b>\n"
        f"<i>Обновлено: {now}</i>\n\n"
        f"👥 Пользователей: <b>{stats['all_users']}</b>\n"
        f"📨 Постов: <b>{stats['all_posts']}</b>\n"
        f"📢 Каналов: <b>{stats['channels_count']}</b>\n\n"
        f"⏳ На модерации: <b>{stats['pending']}</b>\n"
        f"✅ Опубликовано: <b>{stats['published']}</b>\n"
        f"❌ Отклонено: <b>{stats['rejected']}</b>\n\n"
        f"🚫 В бане: <b>{stats['banned']}</b>\n"
        f"👮 Админов: <b>{stats['admins']}</b>"
    )


async def get_admin_ids() -> list[int]:
    return db.get_all_admins()


def is_owner(tg_id: int) -> bool:
    return tg_id == config.OWNER_ID
