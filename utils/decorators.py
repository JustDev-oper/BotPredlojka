"""
Decorators for access control and common operations.
"""

from functools import wraps
from typing import Callable

from config import OWNER_ID
from database.db import get_db, close_db
from database.models import User, Ban


def owner_only(func: Callable) -> Callable:
    """Decorator to restrict function to owner only."""

    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id

        if user_id != OWNER_ID:
            await update.message.reply_text(
                "❌ У вас нет доступа к этой команде."
            )
            return

        return await func(update, context, *args, **kwargs)

    return wrapper


def admin_only(func: Callable) -> Callable:
    """Decorator to restrict function to admins only."""

    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        db = get_db()

        try:
            user = db.query(User).filter(User.user_id == user_id).first()

            if not user or not user.is_admin:
                await update.message.reply_text(
                    "❌ У вас нет доступа к этой команде."
                )
                return

            return await func(update, context, *args, **kwargs)
        finally:
            close_db(db)

    return wrapper


def not_banned(func: Callable) -> Callable:
    """Decorator to check if user is banned."""

    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        db = get_db()

        try:
            ban = db.query(Ban).filter(Ban.user_id == user_id).first()

            if ban:
                await update.message.reply_text(
                    "❌ Вы заблокированы и не можете использовать бота."
                )
                return

            return await func(update, context, *args, **kwargs)
        finally:
            close_db(db)

    return wrapper


def with_db(func: Callable) -> Callable:
    """Decorator to automatically manage database session."""

    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        db = get_db()
        try:
            return await func(update, context, db, *args, **kwargs)
        finally:
            close_db(db)

    return wrapper

