import json

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import Message

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


async def send_content(bot: Bot, chat_id: int, content_type: str, data: dict, **kwargs):
    if content_type == "text":
        return await bot.send_message(chat_id, data.get("text", ""), parse_mode="HTML", **kwargs)
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


def load_content(post_row) -> dict:
    return json.loads(post_row["content_data"])
