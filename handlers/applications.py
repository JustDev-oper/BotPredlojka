from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import database as db
from keyboards import applications_kb

router = Router(name="applications")

# selected channel_ids per admin user_id, in-memory (только для текущей сессии выбора)
_selected: dict[int, set] = {}


async def _render(call: CallbackQuery):
    channels = await db.list_channels()
    counts = await db.pending_counts_by_channel()
    selected = _selected.setdefault(call.from_user.id, set())
    await call.message.edit_text("📩 Заявки:", reply_markup=applications_kb(channels, counts, selected))


@router.callback_query(F.data == "adm:apps")
async def apps_menu(call: CallbackQuery, state: FSMContext):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    _selected[call.from_user.id] = set()
    await _render(call)
    await call.answer()


@router.callback_query(F.data.startswith("apps:toggle:"))
async def apps_toggle(call: CallbackQuery):
    channel_id = int(call.data.split(":")[2])
    selected = _selected.setdefault(call.from_user.id, set())
    if channel_id in selected:
        selected.discard(channel_id)
    else:
        selected.add(channel_id)
    await _render(call)
    await call.answer()


@router.callback_query(F.data == "apps:accept")
async def apps_accept(call: CallbackQuery):
    selected = _selected.get(call.from_user.id, set())
    if not selected:
        await call.answer("Ничего не выбрано", show_alert=True)
        return
    await db.accept_applications(list(selected))
    _selected[call.from_user.id] = set()
    await _render(call)
    await call.answer("Заявки приняты")


@router.callback_query(F.data == "apps:acceptall")
async def apps_accept_all(call: CallbackQuery):
    await db.accept_all_applications()
    _selected[call.from_user.id] = set()
    await _render(call)
    await call.answer("Все заявки приняты")
