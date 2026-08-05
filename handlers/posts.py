import asyncio
import json
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from db.database import db
from keyboards.inline import (
    channel_select_keyboard,
    moderation_keyboard,
    subscription_check_keyboard,
)
from services.channels import is_user_subscribed
from states.admin import UserStates
from utils.antispam import check_antispam
from utils.helpers import build_admin_post_text_from_db

logger = logging.getLogger(__name__)

router = Router(name="posts")

_media_group_buffers: dict[str, list[Message]] = {}
_media_group_timers: dict[str, asyncio.Task] = {}
_MAX_MEDIA_GROUPS = 50


def _cleanup_old_media_groups() -> None:
    if len(_media_group_buffers) > _MAX_MEDIA_GROUPS:
        oldest_keys = list(_media_group_buffers.keys())[:len(_media_group_buffers) - _MAX_MEDIA_GROUPS]
        for key in oldest_keys:
            _media_group_buffers.pop(key, None)
            timer = _media_group_timers.pop(key, None)
            if timer:
                timer.cancel()


def _extract_media_group_data(messages: list[Message]) -> dict | None:
    file_ids = []
    has_photo = False
    has_video = False
    caption = None

    for msg in messages:
        if msg.photo:
            has_photo = True
            file_ids.append(msg.photo[-1].file_id)
            if msg.caption and not caption:
                caption = msg.caption
        elif msg.video:
            has_video = True
            file_ids.append(msg.video.file_id)
            if msg.caption and not caption:
                caption = msg.caption

    if not file_ids:
        return None

    content_type = "video_group" if has_video else "photo_group"
    return {
        "type": "media_group",
        "content_type": content_type,
        "file_ids": json.dumps(file_ids),
        "caption": caption,
        "user_tg_id": messages[0].from_user.id,
    }


def _extract_content_data(message: Message) -> dict | None:
    if message.photo:
        return {
            "type": "photo",
            "content_type": "photo",
            "file_id": message.photo[-1].file_id,
            "caption": message.caption,
            "user_tg_id": message.from_user.id,
        }
    if message.video:
        return {
            "type": "video",
            "content_type": "video",
            "file_id": message.video.file_id,
            "caption": message.caption,
            "user_tg_id": message.from_user.id,
        }
    if message.document:
        return {
            "type": "document",
            "content_type": "document",
            "file_id": message.document.file_id,
            "caption": message.caption,
            "user_tg_id": message.from_user.id,
        }
    if message.text:
        return {
            "type": "text",
            "content_type": "text",
            "text_content": message.text,
            "user_tg_id": message.from_user.id,
        }
    return None


async def _process_media_group(chat_id: int, media_group_id: str, bot: Bot, state: FSMContext) -> None:
    messages = _media_group_buffers.pop(media_group_id, [])
    _media_group_timers.pop(media_group_id, None)

    if not messages:
        return

    first = messages[0]
    if first.reply_to_message:
        return

    if db.is_admin(first.from_user.id):
        return

    db.upsert_user(first.from_user.id, first.from_user.username, first.from_user.full_name)

    if db.is_banned(first.from_user.id):
        await first.answer("Вы заблокированы и не можете отправлять посты.")
        return

    spam = check_antispam(first)
    if not spam.allowed:
        await first.answer(spam.reason)
        return

    content_data = _extract_media_group_data(messages)
    if not content_data:
        return

    current_state = await state.get_state()
    if current_state == UserStates.waiting_post_content.state:
        data = await state.get_data()
        channel_id = data.get("channel_id")
        if channel_id:
            await _create_post_with_channel(first, content_data, channel_id, bot, state)
            return

    await _ask_channel_or_create(first, content_data, state, bot)


async def _ask_channel_or_create(
        message: Message, content_data: dict, state: FSMContext, bot: Bot
) -> None:
    channels = db.get_active_channels()

    if not channels:
        await message.answer("Нет доступных каналов. Попробуйте позже.")
        return

    await state.update_data(pending_content=content_data)
    await state.set_state(UserStates.choosing_channel)
    kb = channel_select_keyboard(channels)
    await message.answer(
        "📢 <b>Выберите канал для публикации:</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def _create_post_with_channel(
        message: Message, content_data: dict, channel_id: int, bot: Bot, state: FSMContext
) -> None:
    await state.clear()

    user_id = content_data["user_tg_id"]
    content_type = content_data["content_type"]

    post_id = db.create_post(
        user_id,
        content_type,
        file_id=content_data.get("file_id"),
        file_ids=content_data.get("file_ids"),
        caption=content_data.get("caption"),
        text_content=content_data.get("text_content"),
    )

    if channel_id:
        db.set_post_channel(post_id, channel_id)

    await _send_post_to_admin_topics(bot, post_id, channel_id, content_data)

    await message.answer(
        "Ваш пост отправлен на модерацию"
    )


async def _send_post_to_admin_topics(bot: Bot, post_id: int, channel_id: int, content_data: dict) -> None:
    topics = db.get_topics_for_channel(channel_id)
    if not topics:
        return

    user_row = db.get_user_by_telegram_id(content_data["user_tg_id"])
    post = db.get_post(post_id)
    channel_row = db.get_channel_by_id(channel_id)
    if not post or not user_row or not channel_row:
        return

    text = build_admin_post_text_from_db(post, user_row, channel_row)
    kb = moderation_keyboard(post_id, content_data["user_tg_id"])

    for topic in topics:
        try:
            sent_msg = None
            if content_data["content_type"] in ("photo_group", "video_group") and content_data.get("file_ids"):
                file_ids = json.loads(content_data["file_ids"])
                from aiogram.types import InputMediaPhoto, InputMediaVideo
                media = []
                for i, fid in enumerate(file_ids):
                    cap = text if i == 0 else None
                    if content_data["content_type"] == "video_group":
                        media.append(InputMediaVideo(media=fid, caption=cap, parse_mode="HTML" if cap else None))
                    else:
                        media.append(InputMediaPhoto(media=fid, caption=cap, parse_mode="HTML" if cap else None))
                await bot.send_media_group(
                    topic["admin_tg_id"],
                    media,
                    message_thread_id=topic["topic_id"],
                )
                sent_msg = await bot.send_message(
                    topic["admin_tg_id"],
                    "^(пост выше)",
                    reply_markup=kb,
                    message_thread_id=topic["topic_id"],
                )
            elif content_data["content_type"] == "photo" and content_data.get("file_id"):
                sent_msg = await bot.send_photo(
                    topic["admin_tg_id"],
                    content_data["file_id"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                    message_thread_id=topic["topic_id"],
                )
            elif content_data["content_type"] == "video" and content_data.get("file_id"):
                sent_msg = await bot.send_video(
                    topic["admin_tg_id"],
                    content_data["file_id"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                    message_thread_id=topic["topic_id"],
                )
            elif content_data["content_type"] == "document" and content_data.get("file_id"):
                sent_msg = await bot.send_document(
                    topic["admin_tg_id"],
                    content_data["file_id"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                    message_thread_id=topic["topic_id"],
                )
            else:
                sent_msg = await bot.send_message(
                    topic["admin_tg_id"],
                    text,
                    parse_mode="HTML",
                    reply_markup=kb,
                    message_thread_id=topic["topic_id"],
                )

            if sent_msg:
                db.save_post_topic_message(post_id, topic["admin_tg_id"], topic["topic_id"], sent_msg.message_id)
                # Связываем сообщение поста с пользователем, чтобы админ мог ответить реплаем
                db.add_reply_map(
                    sent_msg.message_id,
                    content_data["user_tg_id"],
                    "post",
                    post_id=post_id,
                )
        except Exception:
            logger.warning("Не удалось отправить пост %s в топик %s админа %s", post_id, topic["topic_id"],
                           topic["admin_tg_id"])


async def _check_subscription_or_request(
        callback: CallbackQuery, channel_id: int, bot: Bot
) -> bool:
    """Проверяет подписку. Если не подписан — подаёт заявку и показывает ссылку + кнопку «Проверить ✅».

    Возвращает True, если пользователь может отправлять пост.
    """
    channel = db.get_channel_by_id(channel_id)
    if not channel or not channel["is_active"]:
        await callback.answer("Канал недоступен", show_alert=True)
        return False

    tg_chat_id = channel["channel_tg_id"]
    subscribed = False
    if tg_chat_id:
        subscribed = await is_user_subscribed(bot, callback.from_user.id, tg_chat_id)

    if subscribed:
        return True

    # Пользователь подаёт заявку — после этого он может отправлять посты.
    db.add_channel_request(callback.from_user.id, channel_id)

    channel_link = f"https://t.me/{channel['channel_username']}"
    title = channel["channel_title"] or f"@{channel['channel_username']}"
    await callback.message.answer(
        f"❌ Вы не подписаны на канал <b>{title}</b>.\n\n"
        f"Подпишитесь и нажмите «Проверить ✅».\n"
        f"Ваша заявка зарегистрирована — вы уже можете отправить пост.",
        parse_mode="HTML",
        reply_markup=subscription_check_keyboard(channel_link, channel_id),
    )
    return False


@router.callback_query(F.data.startswith("check_sub:"))
async def check_subscription(callback: CallbackQuery, bot: Bot) -> None:
    if db.is_admin(callback.from_user.id):
        await callback.answer("Это для пользователей", show_alert=True)
        return

    parts = callback.data.split(":")
    try:
        channel_id = int(parts[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    channel = db.get_channel_by_id(channel_id)
    if not channel or not channel["is_active"]:
        await callback.answer("Канал недоступен", show_alert=True)
        return

    tg_chat_id = channel["channel_tg_id"]
    if tg_chat_id:
        subscribed = await is_user_subscribed(bot, callback.from_user.id, tg_chat_id)
        if subscribed:
            await callback.answer("✅ Подписка подтверждена!", show_alert=False)
            await callback.message.edit_text(
                "✅ Подписка подтверждена.\n\n"
                "Отправьте ваш пост (текст, фото, видео или документ):",
                parse_mode="HTML",
            )
            return

    await callback.answer("Вы всё ещё не подписаны на канал", show_alert=True)


@router.callback_query(F.data.startswith("select_ch:"))
async def select_channel_post(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if db.is_admin(callback.from_user.id):
        await callback.answer("Это для пользователей", show_alert=True)
        return

    parts = callback.data.split(":")
    try:
        channel_id = int(parts[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    channel = db.get_channel_by_id(channel_id)
    if not channel or not channel["is_active"]:
        await callback.answer("Канал недоступен", show_alert=True)
        return

    if channel["require_subscription"]:
        can_send = await _check_subscription_or_request(callback, channel_id, bot)
        if not can_send:
            await callback.answer()
            return

    data = await state.get_data()
    content_data = data.get("pending_content")

    if content_data:
        await _create_post_with_channel(callback.message, content_data, channel_id, bot, state)
        await callback.answer()
        return

    await state.clear()
    await state.update_data(channel_id=channel_id)
    await state.set_state(UserStates.waiting_post_content)

    title = channel["channel_title"] or f"@{channel['channel_username']}"
    await callback.message.edit_text(
        f"📢 Канал: <b>{title}</b>\n\n"
        f"Отправьте ваш пост (текст, фото, видео или документ):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(UserStates.choosing_channel)
async def ignored_during_channel_selection(message: Message) -> None:
    await message.answer("Пожалуйста, выберите канал кнопкой ниже.")


@router.message(F.photo | F.video | F.document | (F.text & ~F.text.startswith("/")))
async def handle_user_post(message: Message, bot: Bot, state: FSMContext) -> None:
    if message.reply_to_message:
        return

    if db.is_admin(message.from_user.id):
        return

    current_state = await state.get_state()

    if current_state == UserStates.waiting_post_content.state:
        data = await state.get_data()
        channel_id = data.get("channel_id")
        if channel_id:
            if message.media_group_id:
                mg_id = message.media_group_id
                _cleanup_old_media_groups()
                if mg_id not in _media_group_buffers:
                    _media_group_buffers[mg_id] = []
                _media_group_buffers[mg_id].append(message)

                if mg_id in _media_group_timers:
                    _media_group_timers[mg_id].cancel()

                async def _delayed(mid: str = mg_id, chat: int = message.chat.id) -> None:
                    await asyncio.sleep(1.5)
                    _media_group_timers.pop(mid, None)
                    await _process_media_group(chat, mid, bot, state)

                _media_group_timers[mg_id] = asyncio.create_task(_delayed())
                return

            content_data = _extract_content_data(message)
            if content_data:
                await _create_post_with_channel(message, content_data, channel_id, bot, state)
            return

    if message.media_group_id:
        mg_id = message.media_group_id
        _cleanup_old_media_groups()
        if mg_id not in _media_group_buffers:
            _media_group_buffers[mg_id] = []
        _media_group_buffers[mg_id].append(message)

        if mg_id in _media_group_timers:
            _media_group_timers[mg_id].cancel()

        async def _delayed2(mid: str = mg_id, chat: int = message.chat.id) -> None:
            await asyncio.sleep(1.5)
            _media_group_timers.pop(mid, None)
            await _process_media_group(chat, mid, bot, state)

        _media_group_timers[mg_id] = asyncio.create_task(_delayed2())
        return

    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    if db.is_banned(message.from_user.id):
        await message.answer("Вы заблокированы и не можете отправлять посты.")
        return

    spam = check_antispam(message)
    if not spam.allowed:
        await message.answer(spam.reason)
        return

    if not (message.text or message.photo or message.video or message.document):
        await message.answer("Отправьте текст, фото, видео или документ.")
        return

    if message.text and not message.photo and not message.video and not message.document:
        if len(message.text.strip()) < 2:
            await message.answer("Пост слишком короткий.")
            return

    content_data = _extract_content_data(message)
    if not content_data:
        await message.answer("Отправьте текст, фото, видео или документ.")
        return

    await _ask_channel_or_create(message, content_data, state, bot)
