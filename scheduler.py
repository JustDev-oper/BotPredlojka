import asyncio
import json
import logging

from aiogram import Bot

import database as db
from config import OWNER_ID
from utils import send_content

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


async def scheduled_broadcast_loop(bot: Bot, interval: int = 15) -> None:
    """Периодически проверяет запланированные рассылки и отправляет их всем пользователям
    ровно в назначенное время, без ручного вмешательства."""
    while True:
        try:
            due = await db.due_broadcasts()
            for item in due:
                # Помечаем как отправленную сразу, чтобы не разослать дважды, если что-то пойдёт не так.
                await db.mark_broadcast_sent(item["sched_id"])

                content_type = item["content_type"]
                content_data = json.loads(item["content_data"])
                user_ids = await db.all_user_ids()

                sent, failed = 0, 0
                for uid in user_ids:
                    try:
                        await send_content(bot, uid, content_type, content_data)
                        sent += 1
                    except Exception:
                        failed += 1
                    await asyncio.sleep(0.05)

                if item["created_by"]:
                    try:
                        await bot.send_message(
                            item["created_by"],
                            f"⏰ Запланированная рассылка №{item['sched_id']} выполнена.\n"
                            f"Отправлено: {sent}\nНе доставлено: {failed}",
                        )
                    except Exception:
                        pass
        except Exception as e:
            log.exception("Ошибка в цикле запланированных рассылок: %s", e)

        await asyncio.sleep(interval)
