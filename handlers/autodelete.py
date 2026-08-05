import time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from keyboards import autodel_item_kb, autodel_menu_kb, back_to_panel_kb
from states import RescheduleDelete

router = Router(name="autodelete")


@router.callback_query(F.data == "adm:autodel")
async def menu(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text("⏰ Автоудаление постов:", reply_markup=autodel_menu_kb())
    await call.answer()


@router.callback_query(F.data == "ad:list")
async def list_scheduled(call: CallbackQuery):
    items = await db.list_scheduled(active_only=True)
    if not items:
        await call.message.edit_text("Нет запланированных удалений.", reply_markup=autodel_menu_kb())
        await call.answer()
        return

    await call.message.edit_text(f"Найдено записей: {len(items)}. Отправляю список ниже 👇")
    for it in items:
        channel = await db.get_channel(it["channel_id"])
        when = "не удалять" if it["delete_at"] is None else time.strftime(
            "%d.%m.%Y %H:%M", time.localtime(it["delete_at"])
        )
        text = (
            f"Пост в канале «{channel['title'] if channel else '—'}»\n"
            f"Message ID: {it['message_id']}\n"
            f"Удаление: {when}"
        )
        await call.message.answer(text, reply_markup=autodel_item_kb(it["sched_id"]))
    await call.answer()


@router.callback_query(F.data.startswith("ad:now:"))
async def delete_now(call: CallbackQuery, bot: Bot):
    sched_id = int(call.data.split(":")[2])
    item = await db.get_scheduled(sched_id)
    if not item:
        await call.answer("Не найдено", show_alert=True)
        return
    try:
        await bot.delete_message(item["chat_id"], item["message_id"])
    except Exception:
        pass
    await db.mark_deleted(sched_id)
    await call.message.edit_text(f"Пост №{sched_id} удалён.")
    await call.answer()


@router.callback_query(F.data.startswith("ad:cancel:"))
async def cancel_deletion(call: CallbackQuery):
    sched_id = int(call.data.split(":")[2])
    await db.cancel_scheduled(sched_id)
    await call.message.edit_text(f"Автоудаление для записи №{sched_id} отменено.")
    await call.answer()


@router.callback_query(F.data.startswith("ad:reschedule:"))
async def reschedule_start(call: CallbackQuery, state: FSMContext):
    sched_id = int(call.data.split(":")[2])
    await state.update_data(sched_id=sched_id)
    await state.set_state(RescheduleDelete.waiting_datetime)
    await call.message.answer("Введите новую дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ")
    await call.answer()


@router.message(RescheduleDelete.waiting_datetime)
async def reschedule_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        dt = time.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        delete_at = int(time.mktime(dt))
    except ValueError:
        await message.answer("Неверный формат. Пример: 25.12.2026 18:30")
        return
    await db.reschedule(data["sched_id"], delete_at)
    await state.clear()
    await message.answer("Дата удаления обновлена.", reply_markup=back_to_panel_kb())


@router.callback_query(F.data == "ad:deleteall")
async def delete_all(call: CallbackQuery, bot: Bot):
    items = await db.list_scheduled(active_only=True)
    count = 0
    for it in items:
        try:
            await bot.delete_message(it["chat_id"], it["message_id"])
        except Exception:
            pass
        await db.mark_deleted(it["sched_id"])
        count += 1
    await call.message.edit_text(f"Удалено постов: {count}", reply_markup=autodel_menu_kb())
    await call.answer()
