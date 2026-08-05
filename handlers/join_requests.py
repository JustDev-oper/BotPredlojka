"""Обработка заявок на вступление в приватные каналы (ChatJoinRequest).

Бот должен быть администратором канала, чтобы получать эти события.
Заявка НЕ одобряется автоматически — она уходит админу канала.
Пользователь, подавший заявку, получает доступ к отправке постов.
"""

import logging

from aiogram import Router
from aiogram.types import ChatJoinRequest

from db.database import db

logger = logging.getLogger(__name__)

router = Router(name="join_requests")


@router.chat_join_request()
async def on_chat_join_request(request: ChatJoinRequest) -> None:
    """Пользователь подал заявку на вступление в приватный канал."""
    user = request.from_user
    chat = request.chat

    logger.info(
        "Заявка на вступление: user=%s (%s) -> chat=%s (%s)",
        user.id, user.username, chat.id, chat.title,
    )

    # Записываем пользователя в базу
    db.upsert_user(user.id, user.username, user.full_name)

    # Ищем канал в нашей БД по tg_id чата
    channel = db.get_channel_by_tg_id(chat.id)
    if channel:
        # Регистрируем заявку в боте — это разблокирует доступ к отправке постов
        db.add_channel_request(user.id, channel["id"])
        logger.info(
            "Заявка зарегистрирована: user=%s -> channel=%s (%s)",
            user.id, channel["id"], chat.title,
        )

    # Заявка НЕ одобряется автоматически — её рассматривает админ канала вручную.
    # Пользователь уже может отправлять посты в боте.
