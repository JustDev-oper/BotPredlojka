import asyncio

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from keyboards import back_to_panel_kb
from states import BroadcastBot

router = Router(name="broadcast_bot")


@router.callback_query(F.data == "adm:bcastbot")
async def bcast_bot_start(call: CallbackQuery, state: FSMContext):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text(
        "Пришлите сообщение (текст/фото/видео, с форматированием), которое нужно разослать всем "
        "пользователям бота."
    )
    await state.set_state(BroadcastBot.waiting_message)
    await call.answer()


@router.message(BroadcastBot.waiting_message)
async def bcast_bot_send(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    user_ids = await db.all_user_ids()
    sent, failed = 0, 0

    for uid in user_ids:
        try:
            await bot.copy_message(uid, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # мягкий троттлинг, чтобы не упереться в лимиты Telegram

    await message.answer(
        f"Рассылка завершена.\nОтправлено: {sent}\nНе доставлено: {failed}",
        reply_markup=back_to_panel_kb(),
    )
