"""
Moderation handlers for the bot.
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import get_db, close_db
from database.models import Post, User, Channel
from services.moderation import ModerationService

moderation_router = Router()


@moderation_router.callback_query(F.data.startswith("approve_post_"))
async def handle_approve_post(query: CallbackQuery):
    """Approve and publish post."""
    await query.answer()

    post_id = int(query.data.split("_")[2])
    db = get_db()

    try:
        post = db.query(Post).filter(Post.id == post_id).first()

        if not post:
            await query.message.edit_text("❌ Пост не найден.")
            return

        # Approve post
        success = await ModerationService.approve_post(post, db, query.bot)

        if success:
            await query.message.edit_text(
                "✅ Пост опубликован в канал!"
            )

            # Notify user
            user = post.user
            if user:
                try:
                    await query.bot.send_message(
                        chat_id=user.user_id,
                        text="✅ Ваш пост опубликован!"
                    )
                except Exception:
                    pass
        else:
            await query.message.edit_text(
                "❌ Ошибка при публикации поста."
            )

    finally:
        close_db(db)


@moderation_router.callback_query(F.data.startswith("reject_post_"))
async def handle_reject_post(query: CallbackQuery):
    """Reject post."""
    await query.answer()

    post_id = int(query.data.split("_")[2])
    db = get_db()

    try:
        post = db.query(Post).filter(Post.id == post_id).first()

        if not post:
            await query.message.edit_text("❌ Пост не найден.")
            return

        # Reject post
        await ModerationService.reject_post(post, "Отклонено модератором", db)

        await query.message.edit_text(
            "❌ Пост отклонён."
        )

        # Notify user
        user = post.user
        if user:
            try:
                await query.bot.send_message(
                    chat_id=user.user_id,
                    text="❌ Ваш пост отклонён."
                )
            except Exception:
                pass

    finally:
        close_db(db)


@moderation_router.callback_query(F.data.startswith("ban_user_"))
async def handle_ban_user(query: CallbackQuery):
    """Ban user."""
    await query.answer()

    post_id = int(query.data.split("_")[2])
    db = get_db()

    try:
        post = db.query(Post).filter(Post.id == post_id).first()

        if not post or not post.user:
            await query.message.edit_text("❌ Пост не найден.")
            return

        success = await ModerationService.ban_user(
            post.user.user_id,
            "За нарушение правил",
            query.from_user.id,
            db
        )

        if success:
            await query.message.edit_text(
                f"🚫 Пользователь заблокирован."
            )
        else:
            await query.message.edit_text(
                "⚠️ Пользователь уже заблокирован."
            )

    finally:
        close_db(db)


@moderation_router.callback_query(F.data.startswith("select_channels_"))
async def handle_select_channels(query: CallbackQuery, state: FSMContext):
    """Select channels for publishing."""
    await query.answer()

    post_id = int(query.data.split("_")[3])

    # Store post for channel selection
    await state.update_data(post_for_channel_select=post_id)

    db = get_db()

    try:
        channels = db.query(Channel).filter(Channel.is_archived == False).all()

        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard_buttons = []
        for channel in channels:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=channel.name,
                    callback_data=f"publish_to_channel_{post_id}_{channel.id}"
                )
            ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await query.message.edit_text(
            "📢 Выберите канал для публикации:",
            reply_markup=keyboard
        )

    finally:
        close_db(db)
