"""
Statistics service for tracking bot statistics.
"""

from sqlalchemy.orm import Session
from database.models import Statistics, User, Post, Channel


class StatisticsService:
    """Service for managing statistics."""

    @staticmethod
    async def get_real_statistics(db: Session) -> dict:
        """Get real statistics from database."""
        users_count = db.query(User).count()
        posts_count = db.query(Post).filter(Post.status == "published").count()
        channels_count = db.query(Channel).filter(Channel.is_archived == False).count()

        return {
            "users": users_count,
            "posts": posts_count,
            "channels": channels_count
        }

    @staticmethod
    async def set_fake_stat(key: str, value: int, db: Session):
        """Set fake statistic."""
        stat = db.query(Statistics).filter(Statistics.stat_key == key).first()

        if stat:
            stat.stat_value = value
        else:
            stat = Statistics(stat_key=key, stat_value=value)
            db.add(stat)

        db.commit()

    @staticmethod
    async def get_fake_stat(key: str, db: Session) -> int:
        """Get fake statistic."""
        stat = db.query(Statistics).filter(Statistics.stat_key == key).first()
        return stat.stat_value if stat else 0

    @staticmethod
    async def get_all_fake_stats(db: Session) -> dict:
        """Get all fake statistics."""
        stats = db.query(Statistics).all()
        return {stat.stat_key: stat.stat_value for stat in stats}

