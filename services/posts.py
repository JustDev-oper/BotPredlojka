"""Channel publishing service.

Publishes approved posts to the configured Telegram channel.
Always silent. Adds watermark if configured.
"""

from __future__ import annotations

import json
import logging

from aiogram import Bot
from aiogram.types import InputMediaPhoto, InputMediaVideo

from db.database import db

logger = logging.getLogger(__name__)


def _append_watermark(text: str | None, channel_id: int) -> str:
    """Добавляет водянку под постом без отступов."""
    watermark = db.get_watermark(channel_id)
    if watermark:
        return (text or "") + watermark
    return text or ""


async def publish_post_to_channel(bot: Bot, post_id: int) -> bool:
    post = db.get_post(post_id)
    if not post:
        return False

    channel_id_db = post["channel_id"]
    if not channel_id_db:
        return False

    channel = db.get_channel_by_id(channel_id_db)
    if not channel or not channel["is_active"]:
        return False

    target = f"@{channel['channel_username']}"
    silent = True  # всегда silent mode

    try:
        text_content = post["text_content"] or post["caption"]
        text_with_watermark = _append_watermark(text_content, channel_id_db)

        if post["content_type"] in ("photo_group", "video_group") and post["file_ids"]:
            file_ids = json.loads(post["file_ids"])
            caption = _append_watermark(post["caption"], channel_id_db)

            media = []
            for i, fid in enumerate(file_ids):
                cap = caption if i == 0 else None
                if post["content_type"] == "video_group":
                    media.append(InputMediaVideo(media=fid, caption=cap, parse_mode="HTML" if cap else None))
                else:
                    media.append(InputMediaPhoto(media=fid, caption=cap, parse_mode="HTML" if cap else None))

            await bot.send_media_group(target, media, disable_notification=silent)
        elif post["content_type"] == "photo" and post["file_id"]:
            await bot.send_photo(
                target, post["file_id"],
                caption=_append_watermark(post["caption"], channel_id_db),
                parse_mode="HTML",
                disable_notification=silent,
            )
        elif post["content_type"] == "video" and post["file_id"]:
            await bot.send_video(
                target, post["file_id"],
                caption=_append_watermark(post["caption"], channel_id_db),
                parse_mode="HTML",
                disable_notification=silent,
            )
        else:
            await bot.send_message(
                target,
                text_with_watermark,
                parse_mode="HTML",
                disable_web_page_preview=True,
                disable_notification=silent,
            )
        return True
    except Exception:
        logger.exception("Ошибка публикации поста %s в канал %s", post_id, target)
        return False


async def publish_post_to_channel_raw(
    bot: Bot,
    channel_id: int,
    content_type: str,
    file_id: str | None = None,
    file_ids: str | None = None,
    caption: str | None = None,
    text_content: str | None = None,
    *,
    silent: bool = True,
    disable_web_page_preview: bool = True,
) -> list[int] | None:
    """Публикация поста в канал без водянки."""
    channel = db.get_channel_by_id(channel_id)
    if not channel or not channel["is_active"]:
        return None

    target = f"@{channel['channel_username']}"
    message_ids = []

    try:
        if content_type in ("photo_group", "video_group") and file_ids:
            fids = json.loads(file_ids)
            media = []
            for i, fid in enumerate(fids):
                cap = caption if i == 0 else None
                if content_type == "video_group":
                    media.append(InputMediaVideo(media=fid, caption=cap, parse_mode="HTML" if cap else None))
                else:
                    media.append(InputMediaPhoto(media=fid, caption=cap, parse_mode="HTML" if cap else None))
            sent = await bot.send_media_group(target, media, disable_notification=silent)
            message_ids = [m.message_id for m in sent]
        elif content_type == "photo" and file_id:
            msg = await bot.send_photo(
                target, file_id, caption=caption, parse_mode="HTML",
                disable_notification=silent,
            )
            message_ids = [msg.message_id]
        elif content_type == "video" and file_id:
            msg = await bot.send_video(
                target, file_id, caption=caption, parse_mode="HTML",
                disable_notification=silent,
            )
            message_ids = [msg.message_id]
        else:
            msg = await bot.send_message(
                target, text_content or caption or "",
                parse_mode="HTML",
                disable_web_page_preview=disable_web_page_preview,
                disable_notification=silent,
            )
            message_ids = [msg.message_id]
        return message_ids
    except Exception:
        logger.exception("Ошибка публикации в канал %s", target)
        return None
