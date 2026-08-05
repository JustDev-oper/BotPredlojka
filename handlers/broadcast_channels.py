import time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from config import AUTODELETE_OPTIONS
from keyboards import (
    autodelete_choice_kb, back_to_panel_kb, bcast_channels_kb, confirm_kb,
)
from states import BroadcastChannels
from utils import extract_content, send_content

router = Router(name="broadcast_channels")

_selected: dict[int, set] = {}


async def _require_owner(call: CallbackQuery) -> bool:
    return await db.is_owner(call.from_user.id)


@router.callback_query(F.data == "adm:bcastchannels")
async def start(call: CallbackQuery, state: FSMContext):
    if not await _require_owner(call):
        await call.answer("Доступно только владельцу", show_alert=True)
        return
    _selected[call.from_user.id] = set()
    channels = await db.list_channels()
    await state.set_state(BroadcastChannels.choosing_channels)
    await call.message.edit_text("📢 Рассылка по каналам — выберите каналы:", reply_markup=bcast_channels_kb(channels, set()))
    await call.answer()


@router.callback_query(BroadcastChannels.choosing_channels, F.data.startswith("bc:toggle:"))
async def toggle(call: CallbackQuery):
    channel_id = int(call.data.split(":")[2])
    selected = _selected.setdefault(call.from_user.id, set())
    if channel_id in selected:
        selected.discard(channel_id)
    else:
        selected.add(channel_id)
    channels = await db.list_channels()
    await call.message.edit_reply_markup(reply_markup=bcast_channels_kb(channels, selected))
    await call.answer()


@router.callback_query(BroadcastChannels.choosing_channels, F.data == "bc:all")
async def select_all(call: CallbackQuery):
    channels = await db.list_channels()
    _selected[call.from_user.id] = {c["channel_id"] for c in channels}
    await call.message.edit_reply_markup(reply_markup=bcast_channels_kb(channels, _selected[call.from_user.id]))
    await call.answer()


@router.callback_query(BroadcastChannels.choosing_channels, F.data == "bc:confirm")
async def confirm_selection(call: CallbackQuery, state: FSMContext):
    selected = _selected.get(call.from_user.id, set())
    if not selected:
        await call.answer("Выберите хотя бы один канал", show_alert=True)
        return
    await state.update_data(channel_ids=list(selected))
    await state.set_state(BroadcastChannels.waiting_autodelete)
    await call.message.edit_text(
        "⏰ Автоудаление этого поста — выберите время:", reply_markup=autodelete_choice_kb()
    )
    await call.answer()


@router.callback_query(BroadcastChannels.waiting_autodelete, F.data.startswith("bc:ad:"))
async def choose_autodelete(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":")[2]
    await state.update_data(autodelete_key=key)
    await state.set_state(BroadcastChannels.waiting_post)
    await call.message.edit_text("Пришлите пост, который нужно опубликовать во все выбранные каналы.")
    await call.answer()


@router.message(BroadcastChannels.waiting_post)
async def receive_post(message: Message, state: FSMContext):
    content_type, content_data = extract_content(message)
    await state.update_data(content_type=content_type, content_data=content_data)

    data = await state.get_data()
    channels = [await db.get_channel(cid) for cid in data["channel_ids"]]
    names = ", ".join(c["title"] for c in channels if c)

    await state.set_state(BroadcastChannels.waiting_confirm)
    await message.answer(
        f"Превью выше. Вы уверены, что хотите опубликовать в {len(channels)} каналов ({names})?",
        reply_markup=confirm_kb("bc:send"),
    )


@router.callback_query(BroadcastChannels.waiting_confirm, F.data == "bc:send:no")
async def send_no(call: CallbackQuery, state: FSMContext):
    await state.clear()
    _selected.pop(call.from_user.id, None)
    await call.message.edit_text("Рассылка отменена.", reply_markup=back_to_panel_kb())
    await call.answer()


@router.callback_query(BroadcastChannels.waiting_confirm, F.data == "bc:send:yes")
async def send_yes(call: CallbackQuery, bot: Bot, state: FSMContext):
    data = await state.get_data()
    content_type = data["content_type"]
    content_data = data["content_data"]
    autodelete_key = data.get("autodelete_key", "none")
    delta = AUTODELETE_OPTIONS.get(autodelete_key)

    published, failed = 0, 0
    for cid in data["channel_ids"]:
        channel = await db.get_channel(cid)
        if not channel:
            failed += 1
            continue
        try:
            sent = await send_content(
                bot,
                channel["chat_id"],
                content_type,
                content_data,
                disable_notification=True,
                disable_web_page_preview=True,
            )
            published += 1
            delete_at = int(time.time()) + delta if delta else None
            await db.add_scheduled_deletion(cid, channel["chat_id"], sent.message_id, delete_at)
        except Exception:
            failed += 1

    await state.clear()
    _selected.pop(call.from_user.id, None)
    await call.message.edit_text(
        f"Готово. Опубликовано в {published} каналах, ошибок: {failed}.",
        reply_markup=back_to_panel_kb(),
    )
    await call.answer()
