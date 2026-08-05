import asyncio
import logging

from aiogram import Bot

import database as db
from config import OWNER_ID

log = logging.getLogger(__name__)


async def autodelete_loop(bot: Bot, interval: int = 30) -> None:
    """Периодически проверяет запланированные удаления и выполняет их."""
    while True:
        try:
            due = await db.due_deletions()
            for item in due:
                try:
                    await bot.delete_message(item["chat_id"], item["message_id"])
                except Exception as e:
                    log.warning("Не удалось удалить сообщение %s: %s", item["sched_id"], e)
                await db.mark_deleted(item["sched_id"])
                try:
                    await bot.send_message(
                        OWNER_ID, f"Пост №{item['sched_id']} успешно удалён по таймеру"
                    )
                except Exception:
                    pass
        except Exception as e:
            log.exception("Ошибка в цикле автоудаления: %s", e)

        await asyncio.sleep(interval)
