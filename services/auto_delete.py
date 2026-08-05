"""Auto-delete service.

Deletes posts from channels by timer.
"""

import asyncio
import json
import logging

from aiogram import Bot

from db.database import db

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60


async def delete_post_messages(bot: Bot, ad) -> bool:
    """Удаляет сообщения поста из канала. Возвращает True при успехе."""
    channel = db.get_channel_by_id(ad["channel_id"])
    if not channel or not channel["channel_tg_id"]:
        return False

    try:
        message_ids = json.loads(ad["message_ids"])
    except (ValueError, TypeError):
        message_ids = []

    if not message_ids:
        return False

    try:
        for msg_id in message_ids:
            try:
                await bot.delete_message(channel["channel_tg_id"], msg_id)
            except Exception:
                logger.warning("Не удалось удалить сообщение %s в канале %s", msg_id, channel["channel_tg_id"])
        return True
    except Exception:
        logger.exception("Ошибка автоудаления поста %s", ad["post_id"])
        return False


async def auto_delete_loop(bot: Bot) -> None:
    """Фоновая задача: проверяет посты на автоудаление каждую минуту."""
    while True:
        try:
            pending = db.get_pending_auto_deletes()
            for ad in pending:
                ok = await delete_post_messages(bot, ad)
                db.cancel_auto_delete(ad["id"])
                if ok:
                    text = f"Пост №{ad['id']} успешно удалён по таймеру"
                    # Сообщаем всем админам
                    for admin_id in db.get_all_admins():
                        try:
                            await bot.send_message(admin_id, text)
                        except Exception:
                            logger.warning("Не удалось уведомить админа %s об автоудалении поста %s", admin_id, ad["id"])
        except Exception:
            logger.exception("Ошибка в цикле автоудаления")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
