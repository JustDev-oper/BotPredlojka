"""Mass messaging services:
- Broadcast to all bot users
- Broadcast to selected channels
"""

import asyncio
import logging
from typing import Any

from aiogram import Bot
from aiogram.types import Message

from db.database import db

logger = logging.getLogger(__name__)


def payload_from_message(message: Message) -> dict[str, Any] | None:
    if message.photo:
        return {
            "type": "photo",
            "file_id": message.photo[-1].file_id,
            "caption": message.html_caption or message.caption,
        }
    if message.video:
        return {
            "type": "video",
            "file_id": message.video.file_id,
            "caption": message.html_caption or message.caption,
        }
    if message.document:
        return {
            "type": "document",
            "file_id": message.document.file_id,
            "caption": message.html_caption or message.caption,
        }
    if message.text:
        return {"type": "text", "text": message.html_text}
    return None


async def send_payload_to_user(
    bot: Bot, user_id: int, payload: dict[str, Any], *, disable_web_page_preview: bool = False,
) -> bool:
    try:
        if payload["type"] == "text":
            await bot.send_message(
                user_id, payload["text"], parse_mode="HTML",
                disable_web_page_preview=disable_web_page_preview,
            )
        elif payload["type"] == "photo":
            await bot.send_photo(user_id, payload["file_id"], caption=payload.get("caption"), parse_mode="HTML")
        elif payload["type"] == "video":
            await bot.send_video(user_id, payload["file_id"], caption=payload.get("caption"), parse_mode="HTML")
        elif payload["type"] == "document":
            await bot.send_document(user_id, payload["file_id"], caption=payload.get("caption"), parse_mode="HTML")
        else:
            return False
        return True
    except Exception:
        logger.warning("Не удалось доставить сообщение пользователю %s", user_id)
        return False


async def run_broadcast(bot: Bot, payload: dict[str, Any], *, disable_web_page_preview: bool = False) -> tuple[int, int]:
    """Возвращает (успешно, ошибок)."""
    recipients = db.get_broadcast_recipients()
    ok, fail = 0, 0
    for user_id in recipients:
        if await send_payload_to_user(bot, user_id, payload, disable_web_page_preview=disable_web_page_preview):
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.05)
    return ok, fail


async def send_preview(bot: Bot, admin_id: int, payload: dict[str, Any]) -> None:
    await send_payload_to_user(bot, admin_id, payload)


async def run_broadcast_background(bot: Bot, admin_id: int, payload: dict[str, Any], *, disable_web_page_preview: bool = False) -> None:
    ok, fail = await run_broadcast(bot, payload, disable_web_page_preview=disable_web_page_preview)
    from keyboards.admin import admin_panel_keyboard
    from utils.helpers import is_owner
    await bot.send_message(
        admin_id,
        f"📢 <b>Рассылка завершена</b>\n\n"
        f"✅ Доставлено: <b>{ok}</b>\n"
        f"❌ Не доставлено: <b>{fail}</b>",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(is_owner=is_owner(admin_id)),
    )


async def send_payload_to_channel(
    bot: Bot, channel_id: int, payload: dict[str, Any], *, silent: bool = True
) -> list[int] | None:
    """Отправка поста в канал без водянки, без предпросмотра ссылок, без инлайн-кнопок."""
    channel = db.get_channel_by_id(channel_id)
    if not channel or not channel["is_active"]:
        return None

    # Определяем target: для приватных каналов используем channel_tg_id, для публичных — @username
    target = channel["channel_tg_id"] if channel["channel_tg_id"] else f"@{channel['channel_username']}"
    try:
        if payload["type"] == "text":
            msg = await bot.send_message(
                target, payload["text"], parse_mode="HTML",
                disable_web_page_preview=True,
                disable_notification=silent,
            )
            return [msg.message_id]
        elif payload["type"] == "photo":
            msg = await bot.send_photo(
                target, payload["file_id"], caption=payload.get("caption"),
                parse_mode="HTML",
                disable_notification=silent,
            )
            return [msg.message_id]
        elif payload["type"] == "video":
            msg = await bot.send_video(
                target, payload["file_id"], caption=payload.get("caption"),
                parse_mode="HTML",
                disable_notification=silent,
            )
            return [msg.message_id]
        elif payload["type"] == "document":
            msg = await bot.send_document(
                target, payload["file_id"], caption=payload.get("caption"),
                parse_mode="HTML",
                disable_notification=silent,
            )
            return [msg.message_id]
        return None
    except Exception:
        logger.exception("Ошибка отправки в канал %s", target)
        return None


async def run_channel_broadcast(
    bot: Bot, admin_id: int, payload: dict[str, Any], channel_ids: list[int],
    auto_delete_hours: int = 0,
) -> None:
    """Рассылка по каналам: silent, без водянки, без предпросмотра."""
    from keyboards.admin import admin_panel_keyboard
    from utils.helpers import is_owner

    results = []
    all_message_ids = []

    for ch_id in channel_ids:
        msg_ids = await send_payload_to_channel(bot, ch_id, payload, silent=True)
        if msg_ids:
            results.append((ch_id, True, msg_ids))
            all_message_ids.extend(msg_ids)
        else:
            results.append((ch_id, False, []))
        await asyncio.sleep(0.1)

    ok = sum(1 for _, s, _ in results if s)
    fail = sum(1 for _, s, _ in results if not s)

    if auto_delete_hours > 0 and all_message_ids:
        from datetime import datetime, timedelta, timezone
        delete_at = (datetime.now(timezone.utc) + timedelta(hours=auto_delete_hours)).isoformat()
        # Сохраняем по одному посту на канал
        for ch_id, success, msg_ids in results:
            if success and msg_ids:
                db.add_auto_delete(0, ch_id, delete_at, msg_ids)

    await bot.send_message(
        admin_id,
        f"📢 <b>Рассылка по каналам завершена</b>\n\n"
        f"✅ Успешно: <b>{ok}</b>\n"
        f"❌ Ошибок: <b>{fail}</b>",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(is_owner=is_owner(admin_id)),
    )
