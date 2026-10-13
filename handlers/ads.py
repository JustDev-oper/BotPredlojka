import json

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from keyboards import ad_admin_menu_kb, ad_list_kb, ad_manage_kb, back_to_panel_kb
from states import AdPromo
from utils import extract_content, send_ad_content

router = Router(name="ads")


def _ad_payload(ad_row) -> dict:
    return json.loads(ad_row["content_data"])


async def _render_ad_preview(bot: Bot, chat_id: int, ad: dict, manage_markup=None):
    data = _ad_payload(ad)
    try:
        await send_ad_content(bot, chat_id, ad["content_type"], data)
    except Exception:
        await bot.send_message(chat_id, "Не удалось показать рекламный пост.")
    if manage_markup is not None:
        await bot.send_message(chat_id, "Управление рекламой:", reply_markup=manage_markup)


@router.callback_query(F.data == "adm:ads")
async def ads_menu(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text("📣 Реклама:", reply_markup=ad_admin_menu_kb())
    await call.answer()


@router.callback_query(F.data == "ad:list")
async def ad_list(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    ads = await db.list_ad_posts()
    if not ads:
        await call.message.edit_text("Список рекламы пуст.", reply_markup=back_to_panel_kb())
    else:
        await call.message.edit_text("Список рекламы:", reply_markup=ad_list_kb(ads))
    await call.answer()


@router.callback_query(F.data.startswith("ad:preview:"))
async def ad_preview(call: CallbackQuery, bot: Bot):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    ad_id = int(call.data.split(":")[2])
    ad = await db.get_ad_post(ad_id)
    if not ad:
        await call.answer("Реклама не найдена", show_alert=True)
        return
    await call.message.edit_text("Рекламный пост:", reply_markup=None)
    await _render_ad_preview(bot, call.message.chat.id, dict(ad), ad_manage_kb(ad_id))
    await call.answer()


@router.callback_query(F.data.startswith("ad:delete:"))
async def ad_delete(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    ad_id = int(call.data.split(":")[2])
    await db.delete_ad_post(ad_id)
    await call.answer("Удалено")
    await call.message.edit_text("Список рекламы:", reply_markup=ad_list_kb(await db.list_ad_posts()))


@router.callback_query(F.data.startswith("ad:hide:"))
async def ad_hide(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    ad_id = int(call.data.split(":")[2])
    ad = await db.get_ad_post(ad_id)
    if not ad:
        await call.answer("Реклама не найдена", show_alert=True)
        return
    await db.set_ad_active(ad_id, False)
    await call.answer("Убрано из показа")
    await call.message.edit_text("Список рекламы:", reply_markup=ad_list_kb(await db.list_ad_posts()))


@router.callback_query(F.data.startswith("ad:main:"))
async def ad_make_main(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    ad_id = int(call.data.split(":")[2])
    await db.set_ad_main(ad_id)
    await call.answer("Сделано основным для показа")
    await call.message.edit_text("Список рекламы:", reply_markup=ad_list_kb(await db.list_ad_posts()))


@router.callback_query(F.data.startswith("ad:random:"))
async def ad_set_random(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await db.set_ads_mode("random")
    await call.answer("Режим случайного показа включён")
    await call.message.edit_text("Список рекламы:", reply_markup=ad_list_kb(await db.list_ad_posts()))


@router.callback_query(F.data.startswith("ad:edit:"))
async def ad_edit_start(call: CallbackQuery, state: FSMContext):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    ad_id = int(call.data.split(":")[2])
    await state.update_data(edit_ad_id=ad_id)
    await state.set_state(AdPromo.waiting_post)
    await call.message.edit_text(
        "Пришлите новый рекламный пост. Он заменит текущее объявление без потери форматирования.")
    await call.answer()


@router.callback_query(F.data == "ad:pending")
async def ad_pending(call: CallbackQuery, state: FSMContext):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.update_data(edit_ad_id=None)
    await state.set_state(AdPromo.waiting_post)
    await call.message.edit_text(
        "Пришлите рекламный пост для сохранения в систему. Он будет сохранён полностью с оформлением.")
    await call.answer()


@router.message(AdPromo.waiting_post)
async def ad_pending_save(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    edit_ad_id = data.get("edit_ad_id")
    content_type, content_data = extract_content(message)
    if edit_ad_id is not None:
        await db.update_ad_post(edit_ad_id, content_type, content_data)
        await message.answer(f"Реклама #{edit_ad_id} обновлена.", reply_markup=back_to_panel_kb())
    else:
        ad_id = await db.add_ad_post(message.from_user.id, content_type, content_data)
        await message.answer(f"Реклама #{ad_id} сохранена.", reply_markup=back_to_panel_kb())
    await state.clear()


@router.callback_query(F.data == "ad:sent")
async def ad_sent(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer("Функция активна: после модерации реклама отправляется пользователю в ЛС.")


@router.callback_query(F.data == "ad:toggle")
async def ad_toggle(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    enabled = await db.toggle_ads_enabled()
    await call.answer("Реклама включена" if enabled else "Реклама выключена")
    await call.message.edit_text(f"📣 Реклама {'включена' if enabled else 'выключена'}.",
                                 reply_markup=ad_admin_menu_kb())


async def send_ad_to_user(bot: Bot, user_id: int) -> bool:
    if not await db.ads_enabled():
        return False
    ad = await db.pick_ad_for_user()
    if not ad:
        return False
    try:
        data = _ad_payload(ad)
        await send_ad_content(bot, user_id, ad["content_type"], data)
        return True
    except Exception:
        return False
