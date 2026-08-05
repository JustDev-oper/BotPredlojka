"""
Admin handlers for the bot.
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import UserStates, OWNER_ID
from database.db import get_db, close_db
from database.models import User, Channel, Ban, Post, Application
from services.channel import ChannelService
from services.statistics import StatisticsService
from utils.helpers import create_admin_panel_keyboard

admin_router = Router()


@admin_router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    """Show admin panel."""
    user_id = message.from_user.id
    db = get_db()

    try:
        user = db.query(User).filter(User.user_id == user_id).first()

        if not user or not user.is_admin:
            await message.reply_text("❌ У вас нет доступа к этой команде.")
            return

        keyboard = create_admin_panel_keyboard()

        await message.reply_text(
            "👨‍💼 Админ-панель",
            reply_markup=keyboard
        )
    finally:
        close_db(db)


@admin_router.callback_query(F.data == "admin_real_stats")
async def admin_real_stats(query: CallbackQuery):
    """Show real statistics."""
    await query.answer()

    db = get_db()

    try:
        stats = await StatisticsService.get_real_statistics(db)

        text = f"""
📊 Статистика бота

👥 Пользователей: {stats['users']}
📝 Опубликовано постов: {stats['posts']}
📢 Активных каналов: {stats['channels']}
"""

        await query.edit_message_text(text)

    finally:
        close_db(db)


@admin_router.callback_query(F.data == "admin_fake_stats")
async def admin_fake_stats(query: CallbackQuery):
    """Manage fake statistics."""
    await query.answer()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="fake_stat_users")],
        [InlineKeyboardButton(text="📝 Посты", callback_data="fake_stat_posts")],
        [InlineKeyboardButton(text="📈 Показать итог", callback_data="fake_stat_show")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])

    await query.edit_message_text(
        "📈 Фейк-статистика\n\nВыберите, что хотите настроить:",
        reply_markup=keyboard
    )


@admin_router.callback_query(F.data == "admin_banlist")
async def admin_banlist(query: CallbackQuery):
    """Show ban list."""
    await query.answer()

    db = get_db()

    try:
        bans = db.query(Ban).all()

        if not bans:
            await query.edit_message_text("✅ Бан-лист пуст.")
            return

        text = "🚫 Бан-лист\n\n"
        for ban in bans:
            text += f"ID: {ban.user_id}\nПричина: {ban.reason or 'Не указана'}\n\n"

        await query.edit_message_text(text)

    finally:
        close_db(db)


@admin_router.callback_query(F.data == "admin_users")
async def admin_users(query: CallbackQuery):
    """Manage users."""
    await query.answer()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Найти пользователя", callback_data="admin_find_user")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])

    await query.edit_message_text(
        "👥 Управление пользователями",
        reply_markup=keyboard
    )


@admin_router.callback_query(F.data == "admin_channels")
async def admin_channels(query: CallbackQuery):
    """Manage channels."""
    await query.answer()

    db = get_db()

    try:
        channels = await ChannelService.get_all_active_channels(db)

        keyboard_buttons = []
        for channel in channels:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📢 {channel.name}",
                    callback_data=f"admin_channel_edit_{channel.id}"
                )
            ])

        keyboard_buttons.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin_channel_add")])
        keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await query.edit_message_text(
            "📋 Управление каналами",
            reply_markup=keyboard
        )

    finally:
        close_db(db)


@admin_router.callback_query(F.data == "admin_watermark")
async def admin_watermark(query: CallbackQuery):
    """Manage watermarks."""
    await query.answer()

    db = get_db()

    try:
        channels = await ChannelService.get_all_active_channels(db)

        keyboard_buttons = []
        for channel in channels:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"💧 {channel.name}",
                    callback_data=f"admin_watermark_edit_{channel.id}"
                )
            ])

        keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await query.edit_message_text(
            "💧 Управление водянкой",
            reply_markup=keyboard
        )

    finally:
        close_db(db)


@admin_router.callback_query(F.data == "admin_applications")
async def admin_applications(query: CallbackQuery):
    """Manage applications."""
    await query.answer()

    db = get_db()

    try:
        channels = await ChannelService.get_all_active_channels(db)

        keyboard_buttons = []
        for channel in channels:
            count = db.query(Application).filter(
                Application.channel_id == channel.id,
                Application.status == "pending"
            ).count()

            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📩 {channel.name} ({count})",
                    callback_data=f"admin_app_channel_{channel.id}"
                )
            ])

        keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await query.edit_message_text(
            "📩 Заявки по каналам",
            reply_markup=keyboard
        )

    finally:
        close_db(db)


@admin_router.callback_query(F.data == "admin_admins")
async def admin_admins(query: CallbackQuery):
    """Manage admins."""
    await query.answer()

    db = get_db()

    try:
        admins = db.query(User).filter(User.is_admin == True).all()

        text = "👥 Администраторы\n\n"
        for admin in admins:
            status = "👑" if admin.user_id == OWNER_ID else "🔑"
            text += f"{status} @{admin.username or admin.user_id}\n"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data="admin_add_admin")],
            [InlineKeyboardButton(text="➖ Удалить", callback_data="admin_remove_admin")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
        ])

        await query.edit_message_text(text, reply_markup=keyboard)

    finally:
        close_db(db)


@admin_router.callback_query(F.data == "admin_broadcast_bot")
async def admin_broadcast_bot(query: CallbackQuery, state: FSMContext):
    """Send broadcast to all bot users."""
    await query.answer()

    user_id = query.from_user.id
    db = get_db()

    try:
        user = db.query(User).filter(User.user_id == user_id).first()

        if not user or (not user.is_admin and user_id != OWNER_ID):
            await query.edit_message_text("❌ У вас нет доступа к этой функции.")
            return

        await query.edit_message_text(
            "📢 Отправьте сообщение для рассылки всем пользователям:"
        )

        await state.update_data(in_broadcast=True)
        await state.set_state(UserStates.WAITING_FOR_BOT_BROADCAST)

    finally:
        close_db(db)


@admin_router.callback_query(F.data == "admin_auto_delete")
async def admin_auto_delete(query: CallbackQuery):
    """Manage auto-delete."""
    await query.answer()

    db = get_db()

    try:
        posts = db.query(Post).filter(
            Post.auto_delete_time.isnot(None),
            Post.is_deleted == False
        ).all()

        if not posts:
            await query.edit_message_text("✅ Нет постов с автоудалением.")
            return

        text = "⏰ Посты с автоудалением\n\n"
        for post in posts[:5]:
            delete_time = post.auto_delete_time.strftime("%d.%m.%Y %H:%M")
            text += f"Пост #{post.id} - удалится {delete_time}\n"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить все прямо", callback_data="admin_delete_all_now")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
        ])

        await query.edit_message_text(text, reply_markup=keyboard)

    finally:
        close_db(db)


@admin_router.callback_query(F.data == "admin_broadcast_channels")
async def admin_broadcast_channels(query: CallbackQuery, state: FSMContext):
    """Start broadcast to channels."""
    await query.answer()

    user_id = query.from_user.id

    if user_id != OWNER_ID:
        await query.edit_message_text("❌ Только владелец может делать рассылку по каналам.")
        return

    db = get_db()

    try:
        channels = await ChannelService.get_all_active_channels(db)

        broadcast_channels = {}
        for channel in channels:
            broadcast_channels[channel.id] = False

        await state.update_data(broadcast_channels=broadcast_channels)
        await show_channel_selection(query, broadcast_channels)

    finally:
        close_db(db)


async def show_channel_selection(query: CallbackQuery, channels_dict: dict):
    """Show channel selection for broadcast."""
    keyboard_buttons = []

    db = get_db()
    try:
        channels = await ChannelService.get_all_active_channels(db)

        for channel in channels:
            is_selected = channels_dict.get(channel.id, False)
            status = "✅" if is_selected else "⬜"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"{status} {channel.name}",
                    callback_data=f"toggle_channel_{channel.id}"
                )
            ])

        keyboard_buttons.append([InlineKeyboardButton(text="✅ Выбрать все", callback_data="broadcast_select_all")])
        keyboard_buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")])
        keyboard_buttons.append([InlineKeyboardButton(text="▶️ Далее", callback_data="broadcast_next")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await query.edit_message_text(
            "📢 Выберите каналы для рассылки:",
            reply_markup=keyboard
        )

    finally:
        close_db(db)


@admin_router.callback_query(F.data == "admin_back")
async def admin_back(query: CallbackQuery):
    """Go back to admin panel."""
    await query.answer()

    keyboard = create_admin_panel_keyboard()

    await query.edit_message_text(
        "👨‍💼 Админ-панель",
        reply_markup=keyboard
    )

