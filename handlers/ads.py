import json

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from keyboards import ad_admin_menu_kb, ad_list_kb, ad_manage_kb, ad_pending_kb, back_to_panel_kb
from states import AdPromo
from utils import collect_album, extract_album, extract_content, send_ad_content

router = Router(name="ads")

MODE_TITLES = {"main": "основная реклама", "random": "рандом"}


async def _guard(call: CallbackQuery) -> bool:
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return False
    return True


async def _replace(call: CallbackQuery, text: str, markup=None):
    """Edit the message; if it's a media post (can't edit_text) delete it and send a fresh one."""
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.bot.send_message(call.message.chat.id, text, reply_markup=markup)


async def _menu_text() -> str:
    enabled = await db.ads_enabled()
    mode = MODE_TITLES.get(await db.get_ads_mode(), "основная реклама")
    return f"📣 Реклама: {'включена ✅' if enabled else 'остановлена ⏸'}\nРежим показа: {mode}"


async def _list_text() -> str:
    mode = MODE_TITLES.get(await db.get_ads_mode(), "основная реклама")
    return f"Список рекламы (режим: {mode}):\n★ — основная, 🔒 — убрана из показа"


async def _show_list(call: CallbackQuery):
    ads = await db.list_ad_posts()
    if not ads:
        await _replace(call, "Список рекламы пуст.", back_to_panel_kb())
    else:
        await _replace(call, await _list_text(), ad_list_kb(ads))


@router.callback_query(F.data == "adm:ads")
async def ads_menu(call: CallbackQuery):
    if not await _guard(call):
        return
    await _replace(call, await _menu_text(), ad_admin_menu_kb(await db.ads_enabled()))
    await call.answer()


@router.callback_query(F.data == "adv:list")
async def ad_list(call: CallbackQuery):
    if not await _guard(call):
        return
    await _show_list(call)
    await call.answer()


@router.callback_query(F.data.startswith("adv:preview:"))
async def ad_preview(call: CallbackQuery, bot: Bot):
    if not await _guard(call):
        return
    ad_id = int(call.data.split(":")[2])
    ad = await db.get_ad_post(ad_id)
    if not ad:
        await call.answer("Реклама не найдена", show_alert=True)
        return
    markup = ad_manage_kb(ad_id)
    chat_id = call.message.chat.id  # только чат админа, нажавшего кнопку
    try:
        await call.message.delete()
    except Exception:
        pass
    try:
        # кнопки управления — прямо под рекламным постом
        await send_ad_content(bot, chat_id, ad["content_type"], json.loads(ad["content_data"]),
                              reply_markup=markup)
    except Exception:
        await bot.send_message(chat_id, "Не удалось показать рекламный пост.", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("adv:delete:"))
async def ad_delete(call: CallbackQuery):
    if not await _guard(call):
        return
    await db.delete_ad_post(int(call.data.split(":")[2]))
    await call.answer("Удалено")
    await _show_list(call)


@router.callback_query(F.data.startswith("adv:hide:"))
async def ad_hide(call: CallbackQuery):
    if not await _guard(call):
        return
    ad_id = int(call.data.split(":")[2])
    if not await db.get_ad_post(ad_id):
        await call.answer("Реклама не найдена", show_alert=True)
        return
    await db.set_ad_active(ad_id, False)
    await call.answer("Убрано из показа")
    await _show_list(call)


@router.callback_query(F.data.startswith("adv:main:"))
async def ad_make_main(call: CallbackQuery):
    if not await _guard(call):
        return
    ad_id = int(call.data.split(":")[2])
    if not await db.get_ad_post(ad_id):
        await call.answer("Реклама не найдена", show_alert=True)
        return
    await db.set_ad_main(ad_id)
    await call.answer("Сделано основным для показа")
    await _show_list(call)


@router.callback_query(F.data.startswith("adv:random:"))
async def ad_set_random(call: CallbackQuery):
    if not await _guard(call):
        return
    await db.set_ads_mode("random")
    await call.answer("Включён рандомный показ среди активных реклам")
    await _show_list(call)


@router.callback_query(F.data.startswith("adv:edit:"))
async def ad_edit_start(call: CallbackQuery, state: FSMContext):
    if not await _guard(call):
        return
    await state.update_data(edit_ad_id=int(call.data.split(":")[2]))
    await state.set_state(AdPromo.waiting_post)
    await _replace(call, "Пришлите новый рекламный пост. Он заменит текущий с сохранением оформления.")
    await call.answer()


@router.callback_query(F.data == "adv:pending")
async def ad_pending(call: CallbackQuery):
    if not await _guard(call):
        return
    await _replace(call, "Пост на проверке — рекламный пост, который видит автор предложки.",
                   ad_pending_kb())
    await call.answer()


@router.callback_query(F.data == "adv:add")
async def ad_add_start(call: CallbackQuery, state: FSMContext):
    if not await _guard(call):
        return
    await state.update_data(edit_ad_id=None)
    await state.set_state(AdPromo.waiting_post)
    await _replace(call, "Пришлите рекламный пост (текст, фото, видео, файл или гиф). "
                         "Он сохранится полностью: ссылки, жирный и другое оформление.")
    await call.answer()


@router.message(AdPromo.waiting_post)
async def ad_pending_save(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        await state.clear()
        return
    if message.media_group_id:
        album = await collect_album(message)
        if album is None:
            return
        content_type, content_data = extract_album(album)
        await _save_ad(message, state, content_type, content_data)
        return
    unsupported = (message.sticker or message.voice or message.video_note
                   or message.audio or message.poll or message.location or message.contact)
    content_type, content_data = extract_content(message)
    empty = content_type == "text" and not (content_data.get("text") or "").strip()
    if unsupported or empty:
        await message.answer("Этот тип сообщения не поддерживается. Пришлите один пост: "
                             "текст, фото, видео, файл, гиф или альбом.")
        return
    await _save_ad(message, state, content_type, content_data)


async def _save_ad(message: Message, state: FSMContext, content_type: str, content_data: dict):
    edit_ad_id = (await state.get_data()).get("edit_ad_id")
    if edit_ad_id is not None:
        await db.update_ad_post(edit_ad_id, content_type, content_data)
        await message.answer(f"Реклама #{edit_ad_id} обновлена.", reply_markup=back_to_panel_kb())
    else:
        ad_id = await db.add_ad_post(message.from_user.id, content_type, content_data)
        await message.answer(f"Реклама #{ad_id} сохранена.", reply_markup=back_to_panel_kb())
    await state.clear()


@router.callback_query(F.data == "adv:sent")
async def ad_sent(call: CallbackQuery):
    if not await _guard(call):
        return
    await _replace(
        call,
        "Пост отправлен — второй этап.\n"
        "После решения модератора (опубликован / отклонён / автор забанен) реклама "
        "в любом случае отправляется автору поста в личные сообщения. "
        "В рабочий чат и админам она не приходит.\n\n" + await _menu_text(),
        ad_admin_menu_kb(await db.ads_enabled()),
    )
    await call.answer()


@router.callback_query(F.data == "adv:toggle")
async def ad_toggle(call: CallbackQuery):
    if not await _guard(call):
        return
    enabled = await db.toggle_ads_enabled()
    await call.answer("Реклама запущена" if enabled else "Реклама остановлена")
    await _replace(call, await _menu_text(), ad_admin_menu_kb(enabled))


async def send_ad_to_user(bot: Bot, user_id: int) -> bool:
    """Отправляет рекламу строго в ЛС автору поста (user_id = chat_id приватного чата)."""
    if not await db.ads_enabled():
        return False
    ad = await db.pick_ad_for_user(user_id)
    if not ad:
        return False
    try:
        await send_ad_content(bot, user_id, ad["content_type"], json.loads(ad["content_data"]))
        await db.set_last_ad_for_user(user_id, ad["ad_id"])
        return True
    except Exception:
        return False
