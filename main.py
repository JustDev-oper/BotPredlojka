import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from middlewares import BanCheckMiddleware
from scheduler import autodelete_loop

from handlers import (
    admin, applications, autodelete, broadcast_bot, broadcast_channels,
    join_request, moderation, user,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def main() -> None:
    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())

    # Порядок важен: более специфичные роутеры (admin/moderation/...) регистрируем раньше,
    # user-роутер — последним, т.к. содержит "ловящие всё" хендлеры по состоянию FSM.
    dp.include_router(admin.router)
    dp.include_router(applications.router)
    dp.include_router(broadcast_bot.router)
    dp.include_router(broadcast_channels.router)
    dp.include_router(autodelete.router)
    dp.include_router(join_request.router)
    dp.include_router(moderation.router)
    dp.include_router(user.router)

    asyncio.create_task(autodelete_loop(bot))

    log.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
