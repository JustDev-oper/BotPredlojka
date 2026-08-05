"""Channel management service.

Verifies bot permissions in Telegram channels and provides helpers
for adding channels to the database.
"""

import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus

from db.database import db

logger = logging.getLogger(__name__)

BOT_ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


async def is_user_subscribed(bot: Bot, user_id: int, channel_tg_id: int) -> bool:
    """Check if user is subscribed to the channel."""
    try:
        member = await bot.get_chat_member(channel_tg_id, user_id)
        status = member.status
        logger.debug("Subscription check: user=%s channel=%s status=%s", user_id, channel_tg_id, status)
        return status not in (
            ChatMemberStatus.LEFT,
            ChatMemberStatus.KICKED,
        )
    except Exception as e:
        logger.warning("Subscription check failed: user=%s channel=%s error=%s", user_id, channel_tg_id, e)
        return False


async def verify_bot_in_channel(
    bot: Bot, channel_username: str
) -> tuple[bool, str, str | None, int | None]:
    """Check bot has admin rights in the channel.

    Returns (ok, message, title, channel_tg_id).
    """
    username = channel_username.lstrip("@")

    try:
        chat = await bot.get_chat(f"@{username}")
    except Exception:
        return False, "Канал не найден. Проверьте @username.", None, None

    try:
        member = await bot.get_chat_member(chat.id, bot.id)
    except Exception:
        return (
            False,
            "Не удалось проверить права бота. Убедитесь, что бот добавлен в канал.",
            None,
            None,
        )

    if member.status not in BOT_ADMIN_STATUSES:
        return (
            False,
            "Бот не является администратором канала.\n"
            "Добавьте бота в канал и дайте ему права администратора.",
            None,
            None,
        )

    return True, "OK", chat.title, chat.id


def add_channel_to_db(
    channel_username: str,
    channel_title: str | None,
    channel_tg_id: int | None,
    added_by: int,
) -> int | None:
    """Add channel to DB if not already present. Returns channel id or None."""
    username = channel_username.lstrip("@").lower()
    existing = db.get_channel_by_username(username)
    if existing:
        return None
    return db.add_channel(username, channel_title, channel_tg_id, added_by)
