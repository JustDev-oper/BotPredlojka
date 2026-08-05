"""
Anti-spam service for handling spam prevention.
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database.models import Post, User
from config import SPAM_LIMIT, SPAM_COOLDOWN_HOURS


class AntiSpamService:
    """Service for managing anti-spam functionality."""

    @staticmethod
    async def check_spam(db_user_id: int, db: Session) -> tuple[bool, str]:
        """
        Check if user is spamming.

        Args:
            db_user_id: Internal users.id (FK used in Post.user_id)

        Returns:
            Tuple[is_spam, message]
        """
        time_threshold = datetime.utcnow() - timedelta(hours=SPAM_COOLDOWN_HOURS)

        recent_posts = db.query(Post).filter(
            Post.user_id == db_user_id,
            Post.status.in_(["pending", "approved", "published"]),
            Post.created_at > time_threshold
        ).count()

        if recent_posts >= SPAM_LIMIT:
            cooldown_minutes = SPAM_COOLDOWN_HOURS * 60
            return True, f"⏰ Вы отправили много постов. Попробуйте через {cooldown_minutes} минут."

        return False, ""

    @staticmethod
    async def get_user_post_count(db_user_id: int, db: Session, hours: int = 1) -> int:
        """Get count of posts sent by user in last N hours."""
        time_threshold = datetime.utcnow() - timedelta(hours=hours)

        return db.query(Post).filter(
            Post.user_id == db_user_id,
            Post.status.in_(["pending", "approved", "published"]),
            Post.created_at > time_threshold
        ).count()

