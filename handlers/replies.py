import logging

from aiogram import Bot, F, Router
from aiogram.types import Message

from db.database import db
from utils.helpers import escape_html

logger = logging.getLogger(__name__)

router = Router(name="replies")

MODERATOR_REPLY_HEADER = "📩 На ваш пост ответил модератор:"
USER_REPLY_HEADER = "Сообщение от пользователя"


@router.message(F.reply_to_message)
async def handle_reply(message: Message, bot: Bot) -> None:
    if not message.text and not message.caption:
        return

    text = message.text or message.caption
    replied = message.reply_to_message

    if db.is_admin(message.from_user.id):
        await _admin_reply(message, bot, replied, text)
    else:
        await _user_reply(message, bot, replied, text)


async def _admin_reply(
        message: Message,
        bot: Bot,
        replied: Message,
        text: str,
) -> None:
    link = db.get_reply_map(replied.message_id)
    if not link:
        return

    user_tg_id = link["user_tg_id"]
    post_id = link["post_id"]

    try:
        sent = await bot.send_message(
            user_tg_id,
            f"{MODERATOR_REPLY_HEADER}\n\n{text}",
            parse_mode="HTML",
        )
        db.add_reply_map(
            sent.message_id,
            user_tg_id,
            "admin_to_user",
            admin_tg_id=message.from_user.id,
            post_id=post_id,
        )
    except Exception:
        logger.warning("Не удалось отправить ответ модератора пользователю %s", user_tg_id)
        try:
            await message.answer(
                "Не удалось отправить (возможно, пользователь заблокировал бота)."
            )
        except Exception:
            logger.warning("Не удалось отправить сообщение пользователю %s при попытке ответить", user_tg_id)



async def _user_reply(
        message: Message,
        bot: Bot,
        replied: Message,
        text: str,
) -> None:
    if db.is_banned(message.from_user.id):
        await message.answer("Вы заблокированы.")
        return

    link = db.get_reply_map(replied.message_id)
    if not link or link["direction"] != "admin_to_user":
        return

    user = message.from_user
    uname = f"@{escape_html(user.username)}" if user.username else "нет username"
    admin_text = (
        f"{USER_REPLY_HEADER}\n\n"
        f"{escape_html(text)}\n\n"
        f"— {escape_html(user.full_name)} ({uname}, ID: <code>{user.id}</code>)"
    )

    # Отправляем ответ конкретному модератору, который писал
    target_id = link["admin_tg_id"]
    if target_id is None:
        admins = db.get_all_admins()
        target_id = admins[0] if admins else None
    if target_id is None:
        return

    try:
        await bot.send_message(target_id, admin_text, parse_mode="HTML")
    except Exception:
        logger.warning("Не удалось переслать ответ пользователя модератору %s", target_id)
        await message.answer("Ошибка при отправке ответа модератору.")
    else:
        await message.answer("Ваш ответ отправлен модератору.")
