"""
Moderation service for handling post moderation.
"""

from datetime import datetime
from sqlalchemy.orm import Session
from aiogram import Bot
from database.models import Post, User, Channel, Ban
from utils.helpers import format_post_info, create_moderation_keyboard


class ModerationService:
    """Service for managing post moderation."""

    @staticmethod
    async def send_post_to_moderation(post: Post, user: User, channel: Channel, bot: Bot, admin_chat_id: int):
        """Send post to admins for moderation."""
        if post.text_content:
            text = format_post_info(post, user, channel)
        else:
            text = f"[Медиа контент]\n\n{'—' * 20}\nКанал: {channel.name}\nНик: {user.first_name} {user.last_name or ''}\nЮзернейм: @{user.username or 'N/A'}\nID: {user.user_id}"

        keyboard = create_moderation_keyboard(post.id)
        send_kwargs = {"parse_mode": "HTML", "reply_markup": keyboard}

        if post.content_type == "text":
            await bot.send_message(
                chat_id=admin_chat_id,
                text=text,
                **send_kwargs
            )
        elif post.content_type == "photo":
            await bot.send_photo(
                chat_id=admin_chat_id,
                photo=post.media_file_id,
                caption=text,
                **send_kwargs
            )
        elif post.content_type == "video":
            await bot.send_video(
                chat_id=admin_chat_id,
                video=post.media_file_id,
                caption=text,
                **send_kwargs
            )
        elif post.content_type == "document":
            await bot.send_document(
                chat_id=admin_chat_id,
                document=post.media_file_id,
                caption=text,
                **send_kwargs
            )

    @staticmethod
    async def approve_post(post: Post, db: Session, bot: Bot) -> bool:
        """Approve and publish post."""
        if not post.channel:
            return False

        try:
            # Prepare text with watermark
            text = post.text_content or ""
            if post.channel.watermark:
                text += f"\n\n{post.channel.watermark}"

            # Send to channel based on content type
            if post.content_type == "text":
                message = await bot.send_message(
                    chat_id=post.channel.channel_id,
                    text=text,
                    parse_mode="HTML",
                    disable_notification=True
                )
            elif post.content_type == "photo":
                message = await bot.send_photo(
                    chat_id=post.channel.channel_id,
                    photo=post.media_file_id,
                    caption=text,
                    parse_mode="HTML",
                    disable_notification=True
                )
            elif post.content_type == "video":
                message = await bot.send_video(
                    chat_id=post.channel.channel_id,
                    video=post.media_file_id,
                    caption=text,
                    parse_mode="HTML",
                    disable_notification=True
                )
            elif post.content_type == "document":
                message = await bot.send_document(
                    chat_id=post.channel.channel_id,
                    document=post.media_file_id,
                    caption=text,
                    parse_mode="HTML",
                    disable_notification=True
                )
            else:
                return False

            # Update post status
            post.status = "published"
            post.published_at = datetime.utcnow()
            post.telegram_message_id = message.message_id
            db.commit()

            return True

        except Exception as e:
            print(f"Error approving post: {e}")
            return False

    @staticmethod
    async def reject_post(post: Post, reason: str, db: Session):
        """Reject post."""
        post.status = "rejected"
        post.is_rejected = True
        post.rejection_reason = reason
        db.commit()

    @staticmethod
    async def ban_user(user_id: int, reason: str, admin_id: int, db: Session):
        """Ban user."""
        # Check if already banned
        existing_ban = db.query(Ban).filter(Ban.user_id == user_id).first()
        if existing_ban:
            return False

        ban = Ban(
            user_id=user_id,
            reason=reason,
            banned_by=admin_id
        )
        db.add(ban)

        # Update user
        user = db.query(User).filter(User.user_id == user_id).first()
        if user:
            user.is_banned = True

        db.commit()
        return True

    @staticmethod
    async def unban_user(user_id: int, db: Session):
        """Unban user."""
        ban = db.query(Ban).filter(Ban.user_id == user_id).first()
        if not ban:
            return False

        db.delete(ban)

        user = db.query(User).filter(User.user_id == user_id).first()
        if user:
            user.is_banned = False

        db.commit()
        return True
