from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import database as db


class BanCheckMiddleware(BaseMiddleware):
    """Полностью блокирует забаненных пользователей (кроме отображения самого факта бана)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            banned = await db.is_banned(user.id)
            if banned:
                if isinstance(event, CallbackQuery):
                    await event.answer("Вы заблокированы.", show_alert=True)
                    return
                if isinstance(event, Message):
                    # разрешаем только /start, чтобы бот вежливо сообщил о бане (см. handlers/user.py)
                    if not (event.text and event.text.startswith("/start")):
                        return
        return await handler(event, data)
