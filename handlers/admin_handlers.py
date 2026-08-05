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
            await message.answer("❌ У вас нет доступа к этой команде.")
            return

        keyboard = create_admin_panel_keyboard()

        await message.answer(
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

        await query.message.edit_text(text)

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

    await query.message.edit_text(
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
            await query.message.edit_text("✅ Бан-лист пуст.")
            return

        text = "🚫 Бан-лист\n\n"
        for ban in bans:
            text += f"ID: {ban.user_id}\nПричина: {ban.reason or 'Не указана'}\n\n"

        await query.message.edit_text(text)

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

    await query.message.edit_text(
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

        await query.message.edit_text(
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

        await query.message.edit_text(
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

        await query.message.edit_text(
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

        await query.message.edit_text(text, reply_markup=keyboard)

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
            await query.message.edit_text("❌ У вас нет доступа к этой функции.")
            return

        await query.message.edit_text(
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
            await query.message.edit_text("✅ Нет постов с автоудалением.")
            return

        text = "⏰ Посты с автоудалением\n\n"
        for post in posts[:5]:
            delete_time = post.auto_delete_time.strftime("%d.%m.%Y %H:%M")
            text += f"Пост #{post.id} - удалится {delete_time}\n"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить все прямо", callback_data="admin_delete_all_now")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    finally:
        close_db(db)


@admin_router.callback_query(F.data == "admin_broadcast_channels")
async def admin_broadcast_channels(query: CallbackQuery, state: FSMContext):
    """Start broadcast to channels."""
    await query.answer()

    user_id = query.from_user.id

    if user_id != OWNER_ID:
        await query.message.edit_text("❌ Только владелец может делать рассылку по каналам.")
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

        await query.message.edit_text(
            "📢 Выберите каналы для рассылки:",
            reply_markup=keyboard
        )

    finally:
        close_db(db)


@admin_router.callback_query(F.data.startswith("toggle_channel_"))
async def toggle_broadcast_channel(query: CallbackQuery, state: FSMContext):
    """Toggle channel selection for broadcast."""
    await query.answer()

    channel_id = int(query.data.split("_")[2])
    data = await state.get_data()
    broadcast_channels = data.get("broadcast_channels", {})
    broadcast_channels[channel_id] = not broadcast_channels.get(channel_id, False)
    await state.update_data(broadcast_channels=broadcast_channels)
    await show_channel_selection(query, broadcast_channels)


@admin_router.callback_query(F.data == "broadcast_select_all")
async def broadcast_select_all(query: CallbackQuery, state: FSMContext):
    """Select all channels for broadcast."""
    await query.answer()

    data = await state.get_data()
    broadcast_channels = data.get("broadcast_channels", {})
    for channel_id in broadcast_channels:
        broadcast_channels[channel_id] = True
    await state.update_data(broadcast_channels=broadcast_channels)
    await show_channel_selection(query, broadcast_channels)


@admin_router.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel(query: CallbackQuery, state: FSMContext):
    """Cancel channel broadcast selection."""
    await query.answer()
    await state.clear()

    keyboard = create_admin_panel_keyboard()
    await query.message.edit_text(
        "👨‍💼 Админ-панель",
        reply_markup=keyboard
    )


@admin_router.callback_query(F.data == "broadcast_next")
async def broadcast_next(query: CallbackQuery, state: FSMContext):
    """Proceed to broadcast content input."""
    data = await state.get_data()
    broadcast_channels = data.get("broadcast_channels", {})
    selected = sum(1 for v in broadcast_channels.values() if v)

    if selected == 0:
        await query.answer("❌ Выберите хотя бы один канал", show_alert=True)
        return

    await query.answer()
    await query.message.edit_text(
        f"✅ Выбрано каналов: {selected}\n\n"
        f"Отправьте пост для рассылки:"
    )
    await state.update_data(in_broadcast_to_channels=True)
    await state.set_state(UserStates.WAITING_FOR_BROADCAST_CONTENT)


@admin_router.message(UserStates.WAITING_FOR_BOT_BROADCAST)
async def receive_bot_broadcast(message: Message, state: FSMContext):
    """Send broadcast message to all bot users."""
    db = get_db()

    try:
        users = db.query(User).filter(User.is_banned == False).all()
        sent = 0
        for user in users:
            try:
                await message.copy_to(chat_id=user.user_id)
                sent += 1
            except Exception:
                pass

        await message.answer(f"✅ Рассылка завершена. Доставлено: {sent}/{len(users)}")
    finally:
        close_db(db)
        await state.clear()


@admin_router.message(UserStates.WAITING_FOR_BROADCAST_CONTENT)
async def receive_channel_broadcast(message: Message, state: FSMContext):
    """Send broadcast to selected channels."""
    data = await state.get_data()
    broadcast_channels = data.get("broadcast_channels", {})
    selected_ids = [cid for cid, selected in broadcast_channels.items() if selected]

    if not selected_ids:
        await message.answer("❌ Каналы не выбраны.")
        await state.clear()
        return

    db = get_db()

    try:
        sent = 0
        for channel_id in selected_ids:
            channel = await ChannelService.get_channel_by_id(channel_id, db)
            if not channel:
                continue
            try:
                await message.copy_to(chat_id=channel.channel_id)
                sent += 1
            except Exception:
                pass

        await message.answer(f"✅ Рассылка завершена. Опубликовано в {sent} канал(ов).")
    finally:
        close_db(db)
        await state.clear()


@admin_router.callback_query(F.data == "admin_back")
async def admin_back(query: CallbackQuery):
    """Go back to admin panel."""
    await query.answer()

    keyboard = create_admin_panel_keyboard()

    await query.message.edit_text(
        "👨‍💼 Админ-панель",
        reply_markup=keyboard
    )

