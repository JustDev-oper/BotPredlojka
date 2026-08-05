from aiogram import Router
from aiogram.types import ChatJoinRequest

import database as db

router = Router(name="join_request")


@router.chat_join_request()
async def on_join_request(event: ChatJoinRequest) -> None:
    """
    Срабатывает, когда пользователь отправляет заявку на вступление в приватный канал
    (кнопка «Подать заявку» в самом Telegram, invite-ссылка с подтверждением и т.п.).

    Как только заявка зафиксирована — пользователь сразу может отправлять посты в этот
    канал через бота, не дожидаясь, пока администратор канала её одобрит.
    """
    channel = await db.get_channel_by_chat_id(event.chat.id)
    if not channel:
        return  # заявка пришла не по каналу, зарегистрированному в боте

    await db.upsert_user(event.from_user.id, event.from_user.username, event.from_user.first_name)
    await db.create_application(event.from_user.id, channel["channel_id"])
