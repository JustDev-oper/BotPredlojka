from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import database as db


class OwnerControlsMiddleware(BaseMiddleware):
    """Restrict router controls to the owner; optionally expose selected callbacks to staff."""

    def __init__(self, allowed_callback_prefixes: tuple[str, ...] = ()):
        self.allowed_callback_prefixes = allowed_callback_prefixes

    async def __call__(self, handler, event: TelegramObject, data: Dict[str, Any]):
        user = data.get("event_from_user")
        if user is None or await db.is_owner(user.id):
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            callback_data = event.data or ""
            if any(callback_data.startswith(prefix) for prefix in self.allowed_callback_prefixes):
                return await handler(event, data)
            await event.answer("Недостаточно прав", show_alert=True)
            return
        if isinstance(event, Message) and event.text and event.text.startswith("/admin"):
            return await handler(event, data)
        return


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
            await db.upsert_user(user.id, user.username, user.first_name)
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
