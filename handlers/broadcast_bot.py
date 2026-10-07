import asyncio
import time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from keyboards import back_to_panel_kb, bcast_bot_confirm_kb, bcast_bot_time_kb
from states import BroadcastBot
from utils import extract_content, send_content
from middlewares import OwnerControlsMiddleware

router = Router(name="broadcast_bot")
_controls_guard = OwnerControlsMiddleware()
router.callback_query.middleware(_controls_guard)
router.message.middleware(_controls_guard)


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
async def bcast_bot_receive(message: Message, bot: Bot, state: FSMContext):
    content_type, content_data = extract_content(message)
    await state.update_data(content_type=content_type, content_data=content_data)
    await state.set_state(BroadcastBot.waiting_confirm)

    # Показываем ровно то, что уйдёт пользователям — чтобы можно было проверить,
    # что ссылки и оформление (жирный, курсив и т.д.) сохранились как надо.
    await message.answer("👇 Вот как будет выглядеть рассылка. Проверьте ссылки и оформление:")
    await send_content(bot, message.chat.id, content_type, content_data)
    await message.answer(
        "Всё верно? Разослать это сообщение всем пользователям бота?",
        reply_markup=bcast_bot_confirm_kb(),
    )


@router.callback_query(BroadcastBot.waiting_confirm, F.data == "bb:confirm:no")
async def bcast_bot_confirm_no(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Рассылка отменена.", reply_markup=back_to_panel_kb())
    await call.answer()


@router.callback_query(BroadcastBot.waiting_confirm, F.data == "bb:confirm:yes")
async def bcast_bot_confirm_yes(call: CallbackQuery):
    await call.message.edit_text("Когда отправить рассылку?", reply_markup=bcast_bot_time_kb())
    await call.answer()


@router.callback_query(BroadcastBot.waiting_confirm, F.data == "bb:cancel")
async def bcast_bot_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Рассылка отменена.", reply_markup=back_to_panel_kb())
    await call.answer()


@router.callback_query(BroadcastBot.waiting_confirm, F.data == "bb:now")
async def bcast_bot_send_now(call: CallbackQuery, bot: Bot, state: FSMContext):
    data = await state.get_data()
    content_type = data["content_type"]
    content_data = data["content_data"]
    await state.clear()

    await call.message.edit_text("⏳ Рассылаю всем пользователям…")
    user_ids = await db.all_user_ids()
    sent, failed = 0, 0
    for uid in user_ids:
        try:
            await send_content(bot, uid, content_type, content_data)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # мягкий троттлинг, чтобы не упереться в лимиты Telegram

    await call.message.edit_text(
        f"Рассылка завершена.\nОтправлено: {sent}\nНе доставлено: {failed}",
        reply_markup=back_to_panel_kb(),
    )
    await call.answer()


@router.callback_query(BroadcastBot.waiting_confirm, F.data == "bb:schedule")
async def bcast_bot_schedule_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastBot.waiting_datetime)
    await call.message.edit_text(
        "Введите дату и время отправки в формате ДД.ММ.ГГГГ ЧЧ:ММ\nНапример: 25.12.2026 18:30"
    )
    await call.answer()


@router.message(BroadcastBot.waiting_datetime)
async def bcast_bot_schedule_finish(message: Message, state: FSMContext):
    try:
        dt = time.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        send_at = int(time.mktime(dt))
    except ValueError:
        await message.answer("Неверный формат. Пример: 25.12.2026 18:30")
        return

    if send_at <= int(time.time()):
        await message.answer("Указанное время уже прошло. Введите время в будущем.")
        return

    data = await state.get_data()
    sched_id = await db.create_scheduled_broadcast(
        data["content_type"], data["content_data"], send_at, message.from_user.id
    )
    await state.clear()

    when = time.strftime("%d.%m.%Y %H:%M", time.localtime(send_at))
    await message.answer(
        f"✅ Рассылка №{sched_id} запланирована на {when}.\n"
        f"Бот разошлёт её всем пользователям точно в это время, без задержки.",
        reply_markup=back_to_panel_kb(),
    )
