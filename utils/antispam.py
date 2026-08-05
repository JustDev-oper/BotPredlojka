"""Anti-spam system for posts: 2 posts → 1 hour cooldown."""

from datetime import datetime, timedelta, timezone

from aiogram.types import Message

from config import config
from db.database import db
from utils.helpers import format_mute_time


class AntispamResult:
    def __init__(self, allowed: bool, reason: str = "", cooldown_sec: int = 0):
        self.allowed = allowed
        self.reason = reason
        self.cooldown_sec = cooldown_sec


def check_antispam(message: Message) -> AntispamResult:
    user_id = message.from_user.id

    if db.is_banned(user_id):
        return AntispamResult(False, "Вы заблокированы в боте.")

    if db.is_muted(user_id):
        remaining = db.get_mute_remaining(user_id)
        if remaining:
            return AntispamResult(
                False,
                f"Вы временно не можете отправлять посты. Осталось: {format_mute_time(remaining)}.",
                remaining,
            )
        db.set_muted_until(user_id, None)

    post_count = db.increment_user_post_count(user_id)

    if post_count > config.SPAM_POST_THRESHOLD:
        cooldown = config.SPAM_COOLDOWN_SECONDS
        until = datetime.now(timezone.utc) + timedelta(seconds=cooldown)
        db.set_muted_until(user_id, until)
        return AntispamResult(
            False,
            f"Слишком много постов. Подождите {format_mute_time(cooldown)}.",
            cooldown,
        )

    return AntispamResult(True)
