import asyncio
import json

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import (
    InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo, LinkPreviewOptions, Message,
)

NOT_MEMBER_STATUSES = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}


async def is_subscribed(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status not in NOT_MEMBER_STATUSES


def extract_content(message: Message) -> tuple[str, dict]:
    """Turn an incoming user message into (content_type, content_data) for storage."""
    if message.photo:
        return "photo", {
            "file_id": message.photo[-1].file_id,
            "caption": message.html_text or "",
        }
    if message.video:
        return "video", {
            "file_id": message.video.file_id,
            "caption": message.html_text or "",
        }
    if message.document:
        return "document", {
            "file_id": message.document.file_id,
            "caption": message.html_text or "",
        }
    if message.animation:
        return "animation", {
            "file_id": message.animation.file_id,
            "caption": message.html_text or "",
        }
    return "text", {"text": message.html_text or message.text or ""}


_ALBUMS: dict = {}


async def collect_album(message: Message, delay: float = 1.2):
    """Собирает все сообщения одного альбома (media_group_id).
    Первому сообщению возвращает отсортированный список всех частей, остальным — None."""
    key = (message.chat.id, message.media_group_id)
    if key in _ALBUMS:
        _ALBUMS[key].append(message)
        return None
    _ALBUMS[key] = [message]
    await asyncio.sleep(delay)
    return sorted(_ALBUMS.pop(key), key=lambda m: m.message_id)


def _album_item(message: Message):
    if message.photo:
        return {"type": "photo", "file_id": message.photo[-1].file_id}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id}
    if message.document:
        return {"type": "document", "file_id": message.document.file_id}
    if message.audio:
        return {"type": "audio", "file_id": message.audio.file_id}
    return None


def extract_album(messages: list[Message]) -> tuple[str, dict]:
    """Альбом -> ("album", {"items": [...], "caption": html}); подпись берётся из той части, где она есть."""
    items = [i for i in (_album_item(m) for m in messages) if i]
    caption = next((m.html_text for m in messages if m.caption and m.html_text), "")
    if len(items) == 1:  # группа из одного медиа — обычный пост
        return extract_content(messages[0])
    return "album", {"items": items, "caption": caption or ""}


_MEDIA_CLASSES = {
    "photo": InputMediaPhoto, "video": InputMediaVideo,
    "document": InputMediaDocument, "audio": InputMediaAudio,
}


async def send_content(bot: Bot, chat_id: int, content_type: str, data: dict, **kwargs):
    if content_type == "text":
        return await bot.send_message(chat_id, data.get("text", ""), parse_mode="HTML", **kwargs)
    if content_type == "album":
        media = [
            _MEDIA_CLASSES[it["type"]](
                media=it["file_id"],
                caption=(data.get("caption") or None) if idx == 0 else None,
                parse_mode="HTML",
            )
            for idx, it in enumerate(data["items"])
        ]
        markup = kwargs.pop("reply_markup", None)
        kwargs.pop("link_preview_options", None)
        kwargs.pop("disable_web_page_preview", None)
        msgs = await bot.send_media_group(chat_id, media, **kwargs)
        if markup:  # у альбома не бывает кнопок — отправляем их отдельным сообщением ниже
            await bot.send_message(chat_id, "⬆️ Управление", reply_markup=markup,
                                   reply_to_message_id=msgs[0].message_id)
        return msgs
    if content_type == "photo":
        return await bot.send_photo(
            chat_id, data["file_id"], caption=data.get("caption") or None, parse_mode="HTML", **kwargs
        )
    if content_type == "video":
        return await bot.send_video(
            chat_id, data["file_id"], caption=data.get("caption") or None, parse_mode="HTML", **kwargs
        )
    if content_type == "document":
        return await bot.send_document(
            chat_id, data["file_id"], caption=data.get("caption") or None, parse_mode="HTML", **kwargs
        )
    if content_type == "animation":
        return await bot.send_animation(
            chat_id, data["file_id"], caption=data.get("caption") or None, parse_mode="HTML", **kwargs
        )
    raise ValueError(f"Unknown content type {content_type}")


async def send_ad_content(bot: Bot, chat_id: int, content_type: str, data: dict, **kwargs):
    ad_kwargs = {
        "link_preview_options": LinkPreviewOptions(is_disabled=True),
        **kwargs,
    }
    if content_type == "text":
        ad_kwargs["disable_web_page_preview"] = True
    return await send_content(bot, chat_id, content_type, data, **ad_kwargs)


def load_content(post_row) -> dict:
    return json.loads(post_row["content_data"])
