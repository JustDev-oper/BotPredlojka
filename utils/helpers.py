"""
Helper functions for common operations.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session
from database.models import User, Channel, Subscription, Ban
from datetime import datetime, timedelta


async def get_or_create_user(user_id: int, username: str, first_name: str, last_name: str, db: Session) -> User:
    """Get or create user in database."""
    user = db.query(User).filter(User.user_id == user_id).first()

    if not user:
        user = User(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        db.add(user)
        db.commit()
    else:
        user.last_activity = datetime.utcnow()
        db.commit()

    return user


async def check_user_banned(user_id: int, db: Session) -> bool:
    """Check if user is banned."""
    ban = db.query(Ban).filter(Ban.user_id == user_id).first()
    return ban is not None


async def is_user_admin(user_id: int, db: Session) -> bool:
    """Check if user is admin."""
    user = db.query(User).filter(User.user_id == user_id).first()
    return user and user.is_admin


async def is_user_muted(user_id: int, db: Session) -> bool:
    """Check if user is muted and if mute is still active."""
    user = db.query(User).filter(User.user_id == user_id).first()

    if not user or not user.is_muted:
        return False

    if user.mute_until and user.mute_until < datetime.utcnow():
        # Mute expired
        user.is_muted = False
        user.mute_until = None
        db.commit()
        return False

    return True


def create_channels_keyboard(channels: list, callback_prefix: str = "channel") -> InlineKeyboardMarkup:
    """Create inline keyboard with channels."""
    buttons = []
    for channel in channels:
        if not channel.is_archived:
            buttons.append([
                InlineKeyboardButton(
                    text=channel.name,
                    callback_data=f"{callback_prefix}_{channel.id}"
                )
            ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_confirmation_keyboard(yes_callback: str, no_callback: str) -> InlineKeyboardMarkup:
    """Create confirmation keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=yes_callback),
            InlineKeyboardButton(text="❌ Нет", callback_data=no_callback),
        ]
    ])


def create_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Create admin panel main keyboard."""
    buttons = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_real_stats")],
        [InlineKeyboardButton(text="📈 Фейк-статистика", callback_data="admin_fake_stats")],
        [InlineKeyboardButton(text="🚫 Бан-лист", callback_data="admin_banlist")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="📢 Рассылка (бот)", callback_data="admin_broadcast_bot")],
        [InlineKeyboardButton(text="📋 Каналы", callback_data="admin_channels")],
        [InlineKeyboardButton(text="💧 Водянка", callback_data="admin_watermark")],
        [InlineKeyboardButton(text="📩 Заявки", callback_data="admin_applications")],
        [InlineKeyboardButton(text="👥 Администраторы", callback_data="admin_admins")],
        [InlineKeyboardButton(text="⏰ Автоудаление", callback_data="admin_auto_delete")],
        [InlineKeyboardButton(text="📮 Рассылка по каналам", callback_data="admin_broadcast_channels")],
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_user_info(user: User) -> str:
    """Format user information for display."""
    status = "🔓 Активный"
    if user.is_banned:
        status = "🚫 Заблокирован"
    elif user.is_muted:
        status = "🔕 На муте"

    return f"""
ID: <code>{user.user_id}</code>
Username: @{user.username or 'N/A'}
Имя: {user.first_name} {user.last_name or ''}
Статус: {status}
Админ: {'✅ Да' if user.is_admin else '❌ Нет'}
Дата создания: {user.created_at.strftime('%d.%m.%Y %H:%M')}
"""


def format_post_info(post, user: User, channel: Channel) -> str:
    """Format post information for moderation."""
    return f"""
{post.text_content or '[Медиа]'}

{'—' * 20}
Канал: {channel.name}
Ник: {user.first_name} {user.last_name or ''}
Юзернейм: @{user.username or 'N/A'}
ID: <code>{user.user_id}</code>
"""

