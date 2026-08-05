"""
Decorators for access control and common operations.
"""

from functools import wraps
from typing import Callable

from aiogram.types import Message, CallbackQuery

from config import OWNER_ID
from database.db import get_db, close_db
from database.models import User, Ban


def _get_user_id(event: Message | CallbackQuery) -> int:
    return event.from_user.id


async def _deny_access(event: Message | CallbackQuery, text: str):
    if isinstance(event, Message):
        await event.answer(text)
    else:
        await event.answer(text, show_alert=True)


def owner_only(func: Callable) -> Callable:
    """Decorator to restrict function to owner only."""

    @wraps(func)
    async def wrapper(event: Message | CallbackQuery, *args, **kwargs):
        if _get_user_id(event) != OWNER_ID:
            await _deny_access(event, "❌ У вас нет доступа к этой команде.")
            return
        return await func(event, *args, **kwargs)

    return wrapper


def admin_only(func: Callable) -> Callable:
    """Decorator to restrict function to admins only."""

    @wraps(func)
    async def wrapper(event: Message | CallbackQuery, *args, **kwargs):
        user_id = _get_user_id(event)
        db = get_db()

        try:
            user = db.query(User).filter(User.user_id == user_id).first()

            if not user or not user.is_admin:
                await _deny_access(event, "❌ У вас нет доступа к этой команде.")
                return

            return await func(event, *args, **kwargs)
        finally:
            close_db(db)

    return wrapper


def not_banned(func: Callable) -> Callable:
    """Decorator to check if user is banned."""

    @wraps(func)
    async def wrapper(event: Message | CallbackQuery, *args, **kwargs):
        user_id = _get_user_id(event)
        db = get_db()

        try:
            ban = db.query(Ban).filter(Ban.user_id == user_id).first()

            if ban:
                await _deny_access(
                    event,
                    "❌ Вы заблокированы и не можете использовать бота."
                )
                return

            return await func(event, *args, **kwargs)
        finally:
            close_db(db)

    return wrapper


def with_db(func: Callable) -> Callable:
    """Decorator to automatically manage database session."""

    @wraps(func)
    async def wrapper(event: Message | CallbackQuery, *args, **kwargs):
        db = get_db()
        try:
            return await func(event, db, *args, **kwargs)
        finally:
            close_db(db)

    return wrapper
