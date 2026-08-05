"""
User handlers for the bot.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from datetime import datetime

from config import UserStates, ADMIN_CHAT_ID
from database.db import get_db, close_db
from database.models import User, Post, Subscription, Application
from services.channel import ChannelService
from services.antispam import AntiSpamService
from services.moderation import ModerationService
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
        await get_or_create_user(user.id, user.username, user.first_name, user.last_name, db)

        if await check_user_banned(user.id, db):
            await message.answer(
                "❌ Вы заблокированы и не можете использовать бота."
            )
            return

        channels = await ChannelService.get_all_active_channels(db)

        if not channels:
            await message.answer(
                "😔 На данный момент нет доступных каналов."
            )
            return

        keyboard = create_channels_keyboard(channels, "select_channel")

        await message.answer(
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

        if not user:
            await query.message.edit_text(
                "❌ Пользователь не найден. Нажмите /start"
            )
            return

        if user.is_banned:
            await query.message.edit_text(
                "❌ Вы заблокированы и не можете использовать бота."
            )
            return

        channel = await ChannelService.get_channel_by_id(channel_id, db)
        if not channel:
            await query.message.edit_text("❌ Канал не найден.")
            return

        application = db.query(Application).filter(
            Application.user_id == user.id,
            Application.channel_id == channel_id
        ).first()

        if application and application.status == "approved":
            await state.update_data(selected_channel_id=channel_id)
            await query.message.edit_text(
                f"✅ Канал выбран: {channel.name}\n\n"
                f"Отправьте пост (текст, фото, видео или документ):"
            )
            await state.set_state(UserStates.WAITING_FOR_POST)
            return

        subscription = db.query(Subscription).filter(
            Subscription.user_id == user.id,
            Subscription.channel_id == channel_id
        ).first()

        if subscription and subscription.is_subscribed:
            await state.update_data(selected_channel_id=channel_id)
            await query.message.edit_text(
                f"✅ Канал выбран: {channel.name}\n\n"
                f"Отправьте пост (текст, фото, видео или документ):"
            )
            await state.set_state(UserStates.WAITING_FOR_POST)
            return

        keyboard_rows = []
        if channel.channel_username:
            keyboard_rows.append([
                InlineKeyboardButton(
                    text="Перейти на канал",
                    url=f"https://t.me/{channel.channel_username.lstrip('@')}"
                )
            ])
        keyboard_rows.append([
            InlineKeyboardButton(
                text="✅ Я подписался",
                callback_data=f"verify_sub_{channel_id}"
            )
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        await query.message.edit_text(
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
        user = db.query(User).filter(User.user_id == query.from_user.id).first()
        if not user:
            await query.message.edit_text("❌ Пользователь не найден. Нажмите /start")
            return

        channel = await ChannelService.get_channel_by_id(channel_id, db)
        if not channel:
            await query.message.edit_text("❌ Канал не найден.")
            return

        subscription = db.query(Subscription).filter(
            Subscription.user_id == user.id,
            Subscription.channel_id == channel_id
        ).first()

        if not subscription:
            subscription = Subscription(
                user_id=user.id,
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
        await query.message.edit_text(
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
        if not user:
            user = await get_or_create_user(
                message.from_user.id,
                message.from_user.username,
                message.from_user.first_name,
                message.from_user.last_name,
                db,
            )

        if await is_user_muted(message.from_user.id, db):
            await message.answer(
                "🔕 Вы на муте и не можете отправлять посты."
            )
            await state.clear()
            return

        is_spam, spam_msg = await AntiSpamService.check_spam(user.id, db)
        if is_spam:
            await message.answer(spam_msg)
            await state.clear()
            return

        data = await state.get_data()
        channel_id = data.get("selected_channel_id")
        if not channel_id:
            await message.answer("❌ Ошибка: канал не выбран.")
            await state.clear()
            return

        channel = await ChannelService.get_channel_by_id(channel_id, db)
        if not channel:
            await message.answer("❌ Канал не найден.")
            await state.clear()
            return

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
            await message.answer(
                "❌ Неподдерживаемый тип контента."
            )
            await state.clear()
            return

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
        db.refresh(post)

        if ADMIN_CHAT_ID:
            await ModerationService.send_post_to_moderation(
                post, user, channel, message.bot, ADMIN_CHAT_ID
            )

        await message.answer(
            "✅ Ваш пост отправлен на модерацию.\n\n"
            "Администраторы проверят его и опубликуют в течение времени."
        )

        await state.clear()

    finally:
        close_db(db)
