from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from db.database import db
from keyboards.admin import admin_open_keyboard
from keyboards.inline import channel_select_keyboard

router = Router(name="start")

WELCOME_FULL = (
    "пришлите свой пост\n"
    "к посту можно прикрепить фотографию или видео"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )

    if db.is_owner(message.from_user.id):
        await message.answer(
            WELCOME_FULL + "\n\n🛠 У вас доступ к админ-панели.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_open_keyboard(),
        )
        return

    channels = db.get_active_channels()
    if not channels:
        await message.answer(WELCOME_FULL, parse_mode=ParseMode.HTML)
        return

    kb = channel_select_keyboard(channels)
    await message.answer(
        WELCOME_FULL + "\n\n📢 <b>Выберите канал для публикации:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
