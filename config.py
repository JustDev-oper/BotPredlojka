"""
Configuration module for the Telegram bot.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 5877007064))
_admin_chat_id = os.getenv("ADMIN_CHAT_ID")
ADMIN_CHAT_ID = int(_admin_chat_id) if _admin_chat_id else None
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# Project paths
BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.getenv("DATA_PATH", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Database configuration
DB_FILE = str(os.getenv("DATABASE_PATH", DATA_DIR / "bot.db"))
DATABASE_URL = f"sqlite:///{DB_FILE}"

# Constants
SPAM_LIMIT = 2
SPAM_COOLDOWN_HOURS = 1

# Auto-delete options (in hours)
AUTO_DELETE_OPTIONS = {
    "2h": 2,
    "24h": 24,
    "48h": 48,
    "72h": 72,
}

# User states for FSM
from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    WAITING_FOR_POST = State()
    WAITING_FOR_CHANNEL_SELECT = State()
    WAITING_FOR_WATERMARK_TEXT = State()
    WAITING_FOR_WATERMARK_CHANNEL = State()
    WAITING_FOR_BROADCAST_CHANNELS = State()
    WAITING_FOR_BROADCAST_CONTENT = State()
    WAITING_FOR_BOT_BROADCAST = State()
    WAITING_FOR_USER_ID = State()
    WAITING_FOR_CHANNEL_NAME = State()
    WAITING_FOR_CHANNEL_URL = State()


# Keyboard constants
POSTS_PER_PAGE = 5

# Default values
DEFAULT_MUTE_DURATION = 3600
