"""
Channel management service.
"""

from sqlalchemy.orm import Session
from database.models import Channel, Subscription, User


class ChannelService:
    """Service for managing channels."""

    @staticmethod
    async def create_channel(name: str, channel_id: int, channel_username: str, description: str, db: Session) -> Channel:
        """Create new channel."""
        channel = Channel(
            name=name,
            channel_id=channel_id,
            channel_username=channel_username,
            description=description
        )
        db.add(channel)
        db.commit()
        return channel

    @staticmethod
    async def get_all_active_channels(db: Session) -> list[Channel]:
        """Get all non-archived channels."""
        return db.query(Channel).filter(Channel.is_archived == False).all()

    @staticmethod
    async def get_channel_by_id(channel_id: int, db: Session) -> Channel | None:
        """Get channel by ID."""
        return db.query(Channel).filter(Channel.id == channel_id).first()

    @staticmethod
    async def update_watermark(channel_id: int, watermark: str, db: Session) -> bool:
        """Update channel watermark."""
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            return False

        channel.watermark = watermark
        db.commit()
        return True

    @staticmethod
    async def archive_channel(channel_id: int, db: Session) -> bool:
        """Archive channel."""
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            return False

        channel.is_archived = True
        db.commit()
        return True

    @staticmethod
    async def add_channel_admin(channel_id: int, user_id: int, db: Session) -> bool:
        """Add admin to channel."""
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        user = db.query(User).filter(User.user_id == user_id).first()

        if not channel or not user:
            return False

        if user not in channel.admins:
            channel.admins.append(user)
            db.commit()

        return True

    @staticmethod
    async def remove_channel_admin(channel_id: int, user_id: int, db: Session) -> bool:
        """Remove admin from channel."""
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        user = db.query(User).filter(User.user_id == user_id).first()

        if not channel or not user:
            return False

        if user in channel.admins:
            channel.admins.remove(user)
            db.commit()

        return True

