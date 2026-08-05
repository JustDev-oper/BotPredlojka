"""
User handlers for the bot.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from datetime import datetime, timedelta

from config import UserStates
from database.db import get_db, close_db
from database.models import User, Channel, Post, Subscription, Application, Ban
from services.channel import ChannelService
from services.antispam import AntiSpamService
from services.moderation import ModerationService
from utils.decorators import not_banned, with_db
from utils.helpers import (
    get_or_create_user,
    check_user_banned,
    is_user_muted,
    create_channels_keyboard,
)

user_router = Router()


@user_router.message(Command("start"))
async def start(message: Message, state: FSMContext):
    """Handle /start command."""
    user = message.from_user
    db = get_db()

    try:
        # Create or update user
        await get_or_create_user(user.id, user.username, user.first_name, user.last_name, db)

        # Check if banned
        if await check_user_banned(user.id, db):
            await message.reply_text(
                "❌ Вы заблокированы и не можете использовать бота."
            )
            return

        # Get active channels
        channels = await ChannelService.get_all_active_channels(db)

        if not channels:
            await message.reply_text(
                "😔 На данный момент нет доступных каналов."
            )
            return

        # Create keyboard
        keyboard = create_channels_keyboard(channels, "select_channel")

        await message.reply_text(
            "👋 Добро пожаловать! Выберите канал для публикации поста:",
            reply_markup=keyboard
        )

    finally:
        close_db(db)


@user_router.callback_query(F.data.startswith("select_channel_"))
async def channel_selected(query: CallbackQuery, state: FSMContext):
    """Handle channel selection."""
    await query.answer()

    channel_id = int(query.data.split("_")[2])
    db = get_db()

    try:
        user = db.query(User).filter(User.user_id == query.from_user.id).first()

        # Check if banned
        if user and user.is_banned:
            await query.edit_message_text(
                "❌ Вы заблокированы и не можете использовать бота."
            )
            return

        channel = await ChannelService.get_channel_by_id(channel_id, db)
        if not channel:
            await query.edit_message_text("❌ Канал не найден.")
            return

        # Check subscription
        application = db.query(Application).filter(
            Application.user_id == query.from_user.id,
            Application.channel_id == channel_id
        ).first()

        if application and application.status == "approved":
            # User can post
            await state.update_data(selected_channel_id=channel_id)
            await query.edit_message_text(
                f"✅ Канал выбран: {channel.name}\n\n"
                f"Отправьте пост (текст, фото, видео или документ):"
            )
            await state.set_state(UserStates.WAITING_FOR_POST)
            return

        # Check if user is subscribed
        subscription = db.query(Subscription).filter(
            Subscription.user_id == query.from_user.id,
            Subscription.channel_id == channel_id
        ).first()

        if subscription and subscription.is_subscribed:
            # User can post
            await state.update_data(selected_channel_id=channel_id)
            await query.edit_message_text(
                f"✅ Канал выбран: {channel.name}\n\n"
                f"Отправьте пост (текст, фото, видео или документ):"
            )
            await state.set_state(UserStates.WAITING_FOR_POST)
            return

        # User not subscribed - show subscription request
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Перейти на канал", url=f"https://t.me/{channel.channel_username}")],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data=f"verify_sub_{channel_id}")],
        ])

        await query.edit_message_text(
            f"📢 Канал: {channel.name}\n\n"
            f"Подпишитесь на канал, чтобы опубликовать пост.",
            reply_markup=keyboard
        )

    finally:
        close_db(db)


@user_router.callback_query(F.data.startswith("verify_sub_"))
async def verify_subscription(query: CallbackQuery, state: FSMContext):
    """Verify subscription."""
    await query.answer()

    channel_id = int(query.data.split("_")[2])
    db = get_db()

    try:
        channel = await ChannelService.get_channel_by_id(channel_id, db)
        if not channel:
            await query.edit_message_text("❌ Канал не найден.")
            return

        # Mark as subscribed
        subscription = db.query(Subscription).filter(
            Subscription.user_id == query.from_user.id,
            Subscription.channel_id == channel_id
        ).first()

        if not subscription:
            subscription = Subscription(
                user_id=query.from_user.id,
                channel_id=channel_id,
                is_subscribed=True,
                verified_at=datetime.utcnow()
            )
            db.add(subscription)
        else:
            subscription.is_subscribed = True
            subscription.verified_at = datetime.utcnow()

        db.commit()

        await state.update_data(selected_channel_id=channel_id)
        await query.edit_message_text(
            f"✅ Спасибо за подписку!\n\n"
            f"Отправьте пост (текст, фото, видео или документ):"
        )
        await state.set_state(UserStates.WAITING_FOR_POST)

    finally:
        close_db(db)


@user_router.message(UserStates.WAITING_FOR_POST)
async def receive_post(message: Message, state: FSMContext):
    """Receive post from user."""
    db = get_db()

    try:
        user = db.query(User).filter(User.user_id == message.from_user.id).first()

        # Check if muted
        if await is_user_muted(message.from_user.id, db):
            await message.reply_text(
                "🔕 Вы на муте и не можете отправлять посты."
            )
            await state.clear()
            return

        # Check spam
        is_spam, spam_msg = await AntiSpamService.check_spam(message.from_user.id, db)
        if is_spam:
            await message.reply_text(spam_msg)
            await state.clear()
            return

        data = await state.get_data()
        channel_id = data.get("selected_channel_id")
        if not channel_id:
            await message.reply_text("❌ Ошибка: канал не выбран.")
            await state.clear()
            return

        channel = await ChannelService.get_channel_by_id(channel_id, db)

        # Determine content type
        if message.text:
            content_type = "text"
            media_file_id = None
            text_content = message.text
        elif message.photo:
            content_type = "photo"
            media_file_id = message.photo[-1].file_id
            text_content = message.caption
        elif message.video:
            content_type = "video"
            media_file_id = message.video.file_id
            text_content = message.caption
        elif message.document:
            content_type = "document"
            media_file_id = message.document.file_id
            text_content = message.caption
        else:
            await message.reply_text(
                "❌ Неподдерживаемый тип контента."
            )
            await state.clear()
            return

        # Create post
        post = Post(
            user_id=user.id,
            channel_id=channel.id,
            content_type=content_type,
            text_content=text_content,
            media_file_id=media_file_id,
            status="pending"
        )
        db.add(post)
        db.commit()

        await message.reply_text(
            "✅ Ваш пост отправлен на модерацию.\n\n"
            "Администраторы проверят его и опубликуют в течение времени."
        )

        await state.clear()

    finally:
        close_db(db)
