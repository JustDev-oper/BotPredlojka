import logging

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatMemberUpdated

import database as db

router = Router(name="channel_membership")
log = logging.getLogger(__name__)

_NOT_MEMBER_STATUSES = {
    ChatMemberStatus.LEFT,
    ChatMemberStatus.KICKED,
    ChatMemberStatus.RESTRICTED,
}


@router.my_chat_member()
async def on_bot_membership_changed(event: ChatMemberUpdated, bot: Bot) -> None:
    """
    Срабатывает при любом изменении статуса бота в чате/канале.

    Если бота только что сделали администратором канала — автоматически
    добавляем этот канал в список каналов бота-предложки (если его там ещё нет).
    """
    if event.chat.type != ChatType.CHANNEL:
        return

    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    became_admin = (
        new_status == ChatMemberStatus.ADMINISTRATOR
        and old_status != ChatMemberStatus.ADMINISTRATOR
    )
    if not became_admin:
        return

    chat_id = event.chat.id
    title = event.chat.title or str(chat_id)

    invite_link = None
    try:
        chat = await bot.get_chat(chat_id)
        invite_link = chat.invite_link
        if not invite_link:
            invite_link = await bot.export_chat_invite_link(chat_id)
    except Exception:
        pass

    channel_id, created = await db.add_channel(chat_id, title, invite_link)

    if not created:
        # канал уже был в базе (например, добавлен вручную ранее) — дублировать не нужно
        return

    log.info("Канал «%s» (%s) автоматически добавлен: бот получил права администратора.", title, chat_id)

    text = f"✅ Бота добавили администратором в канал «{title}».\nКанал автоматически добавлен в список бота-предложки."
    for admin in await db.list_admins():
        try:
            await bot.send_message(admin["user_id"], text)
        except Exception:
            pass
