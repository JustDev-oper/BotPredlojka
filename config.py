import os

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key) or default


class Config:
    def __init__(self):
        self.BOT_TOKEN = _env("BOT_TOKEN") or _env("API_TOKEN") or _env("TELEGRAM_BOT_TOKEN")
        self.OWNER_ID = int(_env("OWNER_ID") or _env("GENERAL_ADMIN_ID", "5877007064"))

        self.MAX_MESSAGE_LENGTH = int(_env("MAX_MESSAGE_LENGTH", "4096"))

        # Антиспам: 2 поста → таймер 1 час
        self.SPAM_POST_THRESHOLD = int(_env("SPAM_POST_THRESHOLD", "2"))
        self.SPAM_COOLDOWN_SECONDS = int(_env("SPAM_COOLDOWN_SECONDS", "3600"))


config = Config()
