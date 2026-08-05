"""
Database models for the Telegram bot.
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Table,
    Float,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

# Association table for Channel-Admin many-to-many relationship
channel_admin_association = Table(
    "channel_admin_association",
    Base.metadata,
    Column("channel_id", Integer, ForeignKey("channels.id")),
    Column("user_id", Integer, ForeignKey("users.id")),
)


class User(Base):
    """User model."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    is_muted = Column(Boolean, default=False)
    mute_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)

    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")
    applications = relationship(
        "Application", back_populates="user", cascade="all, delete-orphan"
    )
    subscriptions = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User {self.user_id} ({self.username})>"


class Channel(Base):
    """Channel model."""

    __tablename__ = "channels"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, index=True)
    channel_id = Column(Integer, unique=True, index=True)
    channel_username = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    is_archived = Column(Boolean, default=False)
    watermark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    posts = relationship("Post", back_populates="channel", cascade="all, delete-orphan")
    applications = relationship(
        "Application", back_populates="channel", cascade="all, delete-orphan"
    )
    subscriptions = relationship(
        "Subscription", back_populates="channel", cascade="all, delete-orphan"
    )
    admins = relationship(
        "User",
        secondary=channel_admin_association,
        backref="managed_channels",
    )

    def __repr__(self):
        return f"<Channel {self.name}>"


class Post(Base):
    """Post model."""

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=True, index=True)
    telegram_message_id = Column(Integer, nullable=True)
    content_type = Column(String(50))  # text, photo, video, document, etc.
    text_content = Column(Text, nullable=True)
    media_file_id = Column(String(255), nullable=True)
    status = Column(
        String(50), default="pending"
    )  # pending, approved, rejected, published
    is_rejected = Column(Boolean, default=False)
    rejection_reason = Column(Text, nullable=True)
    auto_delete_time = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="posts")
    channel = relationship("Channel", back_populates="posts")

    def __repr__(self):
        return f"<Post {self.id} by {self.user_id}>"


class Application(Base):
    """Application model for user requests to post in a channel."""

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), index=True)
    status = Column(String(50), default="pending")  # pending, approved, rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="applications")
    channel = relationship("Channel", back_populates="applications")

    def __repr__(self):
        return f"<Application user={self.user_id} channel={self.channel_id}>"


class Subscription(Base):
    """Subscription tracking model."""

    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), index=True)
    is_subscribed = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")
    channel = relationship("Channel", back_populates="subscriptions")

    def __repr__(self):
        return f"<Subscription user={self.user_id} channel={self.channel_id}>"


class Ban(Base):
    """Ban list model."""

    __tablename__ = "bans"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    reason = Column(Text, nullable=True)
    banned_by = Column(Integer, nullable=True)  # Admin who banned
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Ban user={self.user_id}>"


class Statistics(Base):
    """Fake statistics for advertisers."""

    __tablename__ = "statistics"

    id = Column(Integer, primary_key=True)
    stat_key = Column(String(100), unique=True, index=True)
    stat_value = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Statistics {self.stat_key}={self.stat_value}>"

