import asyncio
import logging
import sys
from datetime import datetime, timezone, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import config
from handlers import get_routers
from services.auto_delete import auto_delete_loop

MSK = timezone(timedelta(hours=3))


class MSKFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=MSK)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(MSKFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler])


async def main() -> None:
    if not config.BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в .env")
    if not config.OWNER_ID:
        raise ValueError("OWNER_ID не задан в .env")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_routers(*get_routers())

    logging.info("Бот запущен")
    try:
        await asyncio.gather(
            dp.start_polling(bot),
            auto_delete_loop(bot),
        )
    finally:
        logging.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
