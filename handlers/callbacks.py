import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from config import config
from db.database import db
from keyboards.inline import channel_select_keyboard_for_moderation, moderation_keyboard, post_status_keyboard
from services.posts import publish_post_to_channel
from utils.helpers import notify_user_banned

logger = logging.getLogger(__name__)

router = Router(name="callbacks")

_STATUS_ALERT = {
    "published": "Уже опубликовано другим админом.",
    "rejected": "Уже отклонено другим админом.",
}


async def _update_all_topic_messages(bot: Bot, post_id: int, status: str) -> None:
    topic_msgs = db.get_post_topic_messages(post_id)
    kb = post_status_keyboard(status)
    for msg in topic_msgs:
        try:
            await bot.edit_message_reply_markup(
                chat_id=msg["admin_tg_id"],
                message_id=msg["message_id"],
                reply_markup=kb,
            )
        except Exception:
            logger.warning("Не удалось обновить markup для post=%s topic admin=%s", post_id, msg["admin_tg_id"])


def _parse_callback_id(data: str, index: int = 1) -> int | None:
    try:
        return int(data.split(":")[index])
    except (ValueError, IndexError):
        return None


def _admin_only(callback: CallbackQuery) -> bool:
    return db.is_admin(callback.from_user.id)


async def _already_handled_alert(callback: CallbackQuery, post_id: int) -> bool:
    post = db.get_post(post_id)
    if not post or post["status"] == "pending":
        return False

    await callback.answer(
        _STATUS_ALERT.get(post["status"], "Уже обработано."),
        show_alert=True,
    )
    return True


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("pub:"))
async def publish_post(callback: CallbackQuery, bot: Bot) -> None:
    if not _admin_only(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    post_id = _parse_callback_id(callback.data)
    if post_id is None:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    post = db.get_post(post_id)
    if not post:
        await callback.answer("Пост не найден", show_alert=True)
        return

    if await _already_handled_alert(callback, post_id):
        return

    if not post["channel_id"]:
        await callback.answer("Канал не выбран. Нажмите «ВЫБРАТЬ КАНАЛЫ».", show_alert=True)
        return

    if not db.try_set_post_status(post_id, "published"):
        await _already_handled_alert(callback, post_id)
        return

    ok = await publish_post_to_channel(bot, post_id)
    if not ok:
        db.set_post_status(post_id, "pending")
        await callback.answer(
            "Ошибка публикации. Проверьте настройки канала и права бота.",
            show_alert=True,
        )
        return

    await _update_all_topic_messages(bot, post_id, "published")
    await callback.answer()
    try:
        await bot.send_message(
            post["user_tg_id"],
            "Ваш пост опубликован в канале!",
        )
    except Exception:
        logger.warning("Не удалось уведомить пользователя %s о публикации", post["user_tg_id"])


@router.callback_query(F.data.startswith("rej:"))
async def reject_post(callback: CallbackQuery, bot: Bot) -> None:
    if not _admin_only(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    post_id = _parse_callback_id(callback.data)
    if post_id is None:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    post = db.get_post(post_id)
    if not post:
        await callback.answer("Пост не найден", show_alert=True)
        return

    if await _already_handled_alert(callback, post_id):
        return

    if not db.try_set_post_status(post_id, "rejected"):
        await _already_handled_alert(callback, post_id)
        return

    await _update_all_topic_messages(bot, post_id, "rejected")
    await callback.answer()
    try:
        await bot.send_message(
            post["user_tg_id"],
            "Ваш пост не был опубликован.",
        )
    except Exception:
        logger.warning("Не удалось уведомить пользователя %s об отклонении", post["user_tg_id"])


@router.callback_query(F.data.startswith("change_ch:"))
async def change_channel_start(callback: CallbackQuery) -> None:
    if not _admin_only(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    post_id = _parse_callback_id(callback.data)
    if post_id is None:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    post = db.get_post(post_id)
    if not post or post["status"] != "pending":
        await _already_handled_alert(callback, post_id)
        return

    channels = db.get_active_channels()
    if not channels:
        await callback.answer("Нет доступных каналов", show_alert=True)
        return

    await callback.message.edit_text(
        "📩 <b>Выберите канал для публикации:</b>",
        parse_mode="HTML",
        reply_markup=channel_select_keyboard_for_moderation(channels, post_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mod_ch:"))
async def change_channel_select(callback: CallbackQuery, bot: Bot) -> None:
    if not _admin_only(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")
    try:
        channel_id = int(parts[1])
        post_id = int(parts[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    post = db.get_post(post_id)
    if not post or post["status"] != "pending":
        await _already_handled_alert(callback, post_id)
        return

    channel = db.get_channel_by_id(channel_id)
    if not channel or not channel["is_active"]:
        await callback.answer("Канал недоступен", show_alert=True)
        return

    db.set_post_channel(post_id, channel_id)
    user = db.get_user_by_telegram_id(post["user_tg_id"])
    user_tg_id = user["tg_id"] if user else 0

    title = channel["channel_title"] or f"@{channel['channel_username']}"
    await callback.message.edit_text(
        f"✅ Канал изменён на <b>{title}</b>.\n\nНажмите «Опубликовать», чтобы отправить пост.",
        parse_mode="HTML",
        reply_markup=moderation_keyboard(post_id, user_tg_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("block:"))
async def block_user(callback: CallbackQuery, bot: Bot) -> None:
    if not _admin_only(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_tg_id = _parse_callback_id(callback.data, 1)
    post_id = _parse_callback_id(callback.data, 2)

    if user_tg_id is None:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    if user_tg_id == config.OWNER_ID:
        await callback.answer("Нельзя заблокировать владельца", show_alert=True)
        return

    db.set_banned(user_tg_id, True)
    await notify_user_banned(bot, user_tg_id)

    # Отклоняем пост пользователя
    if post_id:
        post = db.get_post(post_id)
        if post and post["status"] == "pending":
            db.set_post_status(post_id, "rejected")
            await _update_all_topic_messages(bot, post_id, "rejected")

    await callback.answer("Пользователь заблокирован")


@router.callback_query(F.data.startswith("unblock:"))
async def unblock_user(callback: CallbackQuery) -> None:
    if not _admin_only(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_tg_id = _parse_callback_id(callback.data)
    if user_tg_id is None:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    db.set_banned(user_tg_id, False)
    db.reset_user_post_count(user_tg_id)
    await callback.answer("Разблокирован")


async def create_topics_for_admin(bot: Bot, admin_tg_id: int) -> int:
    """Создаёт топики для каналов в чате нового админа."""
    channels = db.get_active_channels()
    created = 0
    for ch in channels:
        existing = db.get_admin_topic(admin_tg_id, ch["id"])
        if existing:
            continue
        try:
            topic = await bot.create_forum_topic(
                chat_id=admin_tg_id,
                name=f"📢 {ch['channel_title'] or ch['channel_username']}",
            )
            db.save_admin_topic(admin_tg_id, ch["id"], topic.message_thread_id)
            created += 1
        except Exception:
            logger.warning("Не удалось создать топик для админа %s", admin_tg_id)
    return created
