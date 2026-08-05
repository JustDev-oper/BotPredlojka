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
    """Check if user is subscribed to the channel.

    Only MEMBER status counts as subscribed.
    LEFT/KICKED/RESTRICTED/ADMINISTRATOR/CREATOR are not subscribers.
    """
    try:
        member = await bot.get_chat_member(channel_tg_id, user_id)
        is_sub = member.status == ChatMemberStatus.MEMBER
        logger.debug("Subscription: user=%s channel=%s status=%s -> %s",
                     user_id, channel_tg_id, member.status, is_sub)
        return is_sub
    except Exception as e:
        logger.warning("Subscription check failed: user=%s channel=%s error=%s", user_id, channel_tg_id, e)
        return False


async def check_bot_permissions(bot: Bot, channel_tg_id: int) -> tuple[bool, str]:
    """Check if bot has getChatMember permission in the channel.

    Returns (ok, message).
    """
    try:
        bot_member = await bot.get_chat_member(channel_tg_id, bot.id)
        if bot_member.status not in BOT_ADMIN_STATUSES:
            return False, "Бот не является администратором канала"
        return True, "OK"
    except Exception as e:
        return False, f"Не удалось проверить права бота: {e}"


async def verify_bot_in_channel(
    bot: Bot, channel_input: str
) -> tuple[bool, str, str | None, int | None]:
    """Check bot has admin rights in the channel.

    Accepts either @username (public) or numeric ID like -1001234567890 (private).
    Returns (ok, message, title, channel_tg_id).
    """
    raw = channel_input.strip()

    # Определяем тип: числовой ID или @username
    if raw.lstrip("-").isdigit():
        # Числовой ID (приватный канал)
        chat_id = int(raw)
        try:
            chat = await bot.get_chat(chat_id)
        except Exception:
            return False, "Канал не найден. Проверьте ID или добавьте бота в канал.", None, None
    else:
        # @username (публичный канал)
        username = raw.lstrip("@")
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
    channel_input: str,
    channel_title: str | None,
    channel_tg_id: int | None,
    added_by: int,
) -> int | None:
    """Add channel to DB if not already present. Returns channel id or None.

    channel_input: @username (public) or numeric ID string (private).
    """
    raw = channel_input.strip()
    # Для приватных каналов храним ID как строку, для публичных — username
    identifier = raw.lstrip("@").lower() if not raw.lstrip("-").isdigit() else raw
    existing = db.get_channel_by_username(identifier)
    if existing:
        return None
    return db.add_channel(identifier, channel_title, channel_tg_id, added_by)
