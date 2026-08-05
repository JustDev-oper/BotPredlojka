"""
Main bot application for aiogram 3.x
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, DEBUG
from database.db import init_db
from handlers.user_handlers import user_router
from handlers.admin_handlers import admin_router
from handlers.moderation_handlers import moderation_router

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO if not DEBUG else logging.DEBUG
)
logger = logging.getLogger(__name__)


async def main():
    """Start the bot."""

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Initialize bot and dispatcher
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Include routers
    dp.include_router(user_router)
    dp.include_router(admin_router)
    dp.include_router(moderation_router)

    try:
        logger.info("Starting bot...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Check your .env file.")
    asyncio.run(main())
