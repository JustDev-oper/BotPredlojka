from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from config import OWNER_ID
from keyboards import (
    admin_panel_kb, admins_menu_kb, back_to_panel_kb, banlist_kb,
    channels_menu_kb, channels_pick_kb, fake_stats_kb, users_menu_kb,
    water_channels_kb,
)
from states import (
    ChannelAdd, ChannelRename, FakeStats, UsersManage, WaterSetup,
)

router = Router(name="admin")


async def _require_admin(obj) -> bool:
    user_id = obj.from_user.id
    return await db.is_admin(user_id)


# --- entry point -------------------------------------------------------------------

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    if not await db.is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ-панели.")
        return
    await message.answer(
        "Админ-панель:", reply_markup=admin_panel_kb(await db.is_owner(message.from_user.id))
    )


@router.message(Command("rndadm"))
async def cmd_rndadm(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    await db.restore_owner()
    await message.answer("Права владельца восстановлены.")


@router.callback_query(F.data == "adm:menu")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not await db.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text(
        "Админ-панель:", reply_markup=admin_panel_kb(await db.is_owner(call.from_user.id))
    )
    await call.answer()


# --- статистика ------------------------------------------------------------------

@router.callback_query(F.data == "adm:stats")
async def show_stats(call: CallbackQuery):
    if not await _require_admin(call):
        await call.answer("Нет доступа", show_alert=True)
        return
    users = len(await db.all_user_ids())
    posts = await db.count_posts()
    channels = len(await db.list_channels(include_archived=True))
    text = (
        "📊 Реальная статистика\n\n"
        f"Пользователей: {users}\n"
        f"Опубликовано постов: {posts}\n"
        f"Каналов: {channels}"
    )
    await call.message.edit_text(text, reply_markup=back_to_panel_kb())
    await call.answer()


# --- фейк-статистика ------------------------------------------------------------------

@router.callback_query(F.data == "adm:fakestats")
async def fake_stats_menu(call: CallbackQuery):
    if not await _require_admin(call):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text("📈 Фейк-статистика для рекламодателей:", reply_markup=fake_stats_kb())
    await call.answer()


@router.callback_query(F.data == "fs:users")
async def fs_users(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введите число пользователей:")
    await state.set_state(FakeStats.waiting_users)
    await call.answer()


@router.message(FakeStats.waiting_users)
async def fs_users_save(message: Message, state: FSMContext):
    await db.set_fake_stat("users", message.text.strip())
    await state.clear()
    await message.answer("Сохранено.", reply_markup=fake_stats_kb())


@router.callback_query(F.data == "fs:posts")
async def fs_posts(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введите число постов:")
    await state.set_state(FakeStats.waiting_posts)
    await call.answer()


@router.message(FakeStats.waiting_posts)
async def fs_posts_save(message: Message, state: FSMContext):
    await db.set_fake_stat("posts", message.text.strip())
    await state.clear()
    await message.answer("Сохранено.", reply_markup=fake_stats_kb())


@router.callback_query(F.data == "fs:show")
async def fs_show(call: CallbackQuery):
    users = await db.get_fake_stat("users") or "—"
    posts = await db.get_fake_stat("posts") or "—"
    text = f"📈 Статистика бота:\n\nПользователей: {users}\nПостов: {posts}"
    await call.message.edit_text(text, reply_markup=fake_stats_kb())
    await call.answer()


# --- бан-лист ------------------------------------------------------------------

@router.callback_query(F.data == "adm:banlist")
async def show_banlist(call: CallbackQuery):
    if not await _require_admin(call):
        await call.answer("Нет доступа", show_alert=True)
        return
    banned = await db.banned_list()
    if not banned:
        await call.message.edit_text("Бан-лист пуст.", reply_markup=back_to_panel_kb())
    else:
        await call.message.edit_text("🚫 Бан-лист:", reply_markup=banlist_kb(banned))
    await call.answer()


@router.callback_query(F.data.startswith("ban:unban:"))
async def unban_from_list(call: CallbackQuery):
    user_id = int(call.data.split(":")[2])
    await db.set_ban(user_id, False)
    banned = await db.banned_list()
    if not banned:
        await call.message.edit_text("Бан-лист пуст.", reply_markup=back_to_panel_kb())
    else:
        await call.message.edit_text("🚫 Бан-лист:", reply_markup=banlist_kb(banned))
    await call.answer("Разбанен")


# --- пользователи (бан/разбан/мут/размут/+админ/-админ) ------------------------------

@router.callback_query(F.data == "adm:users")
async def users_menu(call: CallbackQuery):
    if not await _require_admin(call):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text("👥 Управление пользователями:", reply_markup=users_menu_kb())
    await call.answer()


_USERS_ACTIONS = {
    "users:ban": (UsersManage.waiting_id_ban, "Введите ID или @username пользователя для бана:"),
    "users:unban": (UsersManage.waiting_id_unban, "Введите ID или @username пользователя для разбана:"),
    "users:mute": (UsersManage.waiting_id_mute, "Введите ID или @username пользователя для мута:"),
    "users:unmute": (UsersManage.waiting_id_unmute, "Введите ID или @username пользователя для размута:"),
    "users:addadmin": (UsersManage.waiting_id_addadmin, "Введите ID или @username нового модератора:"),
    "users:deladmin": (UsersManage.waiting_id_deladmin, "Введите ID или @username модератора для удаления:"),
}


@router.callback_query(F.data.in_(_USERS_ACTIONS.keys()))
async def users_action_prompt(call: CallbackQuery, state: FSMContext):
    if not await _require_admin(call):
        await call.answer("Нет доступа", show_alert=True)
        return
    state_obj, prompt = _USERS_ACTIONS[call.data]
    await call.message.edit_text(prompt)
    await state.set_state(state_obj)
    await call.answer()


async def _resolve_user_id(bot: Bot, raw: str) -> int | None:
    raw = raw.strip()
    if raw.startswith("@"):
        try:
            chat = await bot.get_chat(raw)
            return chat.id
        except Exception:
            return None
    try:
        return int(raw)
    except ValueError:
        return None


@router.message(UsersManage.waiting_id_ban)
async def do_ban(message: Message, bot: Bot, state: FSMContext):
    uid = await _resolve_user_id(bot, message.text)
    if uid is None:
        await message.answer("Не удалось распознать пользователя.")
        return
    await db.set_ban(uid, True)
    await state.clear()
    await message.answer(f"Пользователь {uid} забанен.", reply_markup=users_menu_kb())


@router.message(UsersManage.waiting_id_unban)
async def do_unban(message: Message, bot: Bot, state: FSMContext):
    uid = await _resolve_user_id(bot, message.text)
    if uid is None:
        await message.answer("Не удалось распознать пользователя.")
        return
    await db.set_ban(uid, False)
    await state.clear()
    await message.answer(f"Пользователь {uid} разбанен.", reply_markup=users_menu_kb())


@router.message(UsersManage.waiting_id_mute)
async def do_mute(message: Message, bot: Bot, state: FSMContext):
    uid = await _resolve_user_id(bot, message.text)
    if uid is None:
        await message.answer("Не удалось распознать пользователя.")
        return
    await db.set_mute(uid, True)
    await state.clear()
    await message.answer(f"Пользователь {uid} в муте.", reply_markup=users_menu_kb())


@router.message(UsersManage.waiting_id_unmute)
async def do_unmute(message: Message, bot: Bot, state: FSMContext):
    uid = await _resolve_user_id(bot, message.text)
    if uid is None:
        await message.answer("Не удалось распознать пользователя.")
        return
    await db.set_mute(uid, False)
    await state.clear()
    await message.answer(f"Пользователь {uid} размучен.", reply_markup=users_menu_kb())


@router.message(UsersManage.waiting_id_addadmin)
async def do_addadmin(message: Message, bot: Bot, state: FSMContext):
    if not await db.is_owner(message.from_user.id):
        await message.answer("Только владелец может назначать модераторов.")
        await state.clear()
        return
    uid = await _resolve_user_id(bot, message.text)
    if uid is None:
        await message.answer("Не удалось распознать пользователя.")
        return
    await db.add_admin(uid)
    await state.clear()
    await message.answer(f"Пользователь {uid} назначен модератором.", reply_markup=users_menu_kb())


@router.message(UsersManage.waiting_id_deladmin)
async def do_deladmin(message: Message, bot: Bot, state: FSMContext):
    if not await db.is_owner(message.from_user.id):
        await message.answer("Только владелец может удалять модераторов.")
        await state.clear()
        return
    uid = await _resolve_user_id(bot, message.text)
    if uid is None:
        await message.answer("Не удалось распознать пользователя.")
        return
    await db.remove_admin(uid)
    await state.clear()
    await message.answer(f"Модератор {uid} удалён.", reply_markup=users_menu_kb())


# --- каналы ------------------------------------------------------------------

@router.callback_query(F.data == "adm:channels")
async def channels_menu(call: CallbackQuery, state: FSMContext):
    if not await _require_admin(call):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text("📋 Управление каналами:", reply_markup=channels_menu_kb())
    await call.answer()


@router.callback_query(F.data == "chan:add")
async def chan_add_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "Перешлите (forward) любое сообщение из канала, который нужно добавить, "
        "или добавьте бота администратором канала и пришлите его @username."
    )
    await state.set_state(ChannelAdd.waiting_forward)
    await call.answer()


@router.message(ChannelAdd.waiting_forward)
async def chan_add_finish(message: Message, bot: Bot, state: FSMContext):
    chat_id = None
    title = None

    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id
        title = message.forward_from_chat.title
    elif message.text and message.text.startswith("@"):
        try:
            chat = await bot.get_chat(message.text.strip())
            chat_id = chat.id
            title = chat.title
        except Exception:
            await message.answer("Не удалось найти канал. Убедитесь, что бот добавлен туда админом.")
            return
    else:
        await message.answer("Перешлите сообщение из канала или пришлите @username канала.")
        return

    invite_link = None
    try:
        chat = await bot.get_chat(chat_id)
        invite_link = chat.invite_link
        if not invite_link:
            invite_link = await bot.export_chat_invite_link(chat_id)
    except Exception:
        pass

    await db.add_channel(chat_id, title or str(chat_id), invite_link)
    await state.clear()
    await message.answer(f"Канал «{title}» добавлен.", reply_markup=channels_menu_kb())


@router.callback_query(F.data == "chan:rename")
async def chan_rename_pick(call: CallbackQuery):
    channels = await db.list_channels(include_archived=True)
    await call.message.edit_text(
        "Выберите канал для переименования:", reply_markup=channels_pick_kb(channels, "chan:rn")
    )
    await call.answer()


@router.callback_query(F.data.startswith("chan:rn:"))
async def chan_rename_start(call: CallbackQuery, state: FSMContext):
    channel_id = int(call.data.split(":")[2])
    await state.update_data(channel_id=channel_id)
    await state.set_state(ChannelRename.waiting_new_title)
    await call.message.edit_text("Введите новое название канала:")
    await call.answer()


@router.message(ChannelRename.waiting_new_title)
async def chan_rename_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.rename_channel(data["channel_id"], message.text.strip())
    await state.clear()
    await message.answer("Название обновлено.", reply_markup=channels_menu_kb())


@router.callback_query(F.data == "chan:archive")
async def chan_archive_pick(call: CallbackQuery):
    channels = await db.list_channels(include_archived=True)
    await call.message.edit_text(
        "Выберите канал (архивировать/восстановить):",
        reply_markup=channels_pick_kb(channels, "chan:tglarch"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("chan:tglarch:"))
async def chan_archive_toggle(call: CallbackQuery):
    channel_id = int(call.data.split(":")[2])
    channel = await db.get_channel(channel_id)
    if not channel:
        await call.answer("Канал не найден", show_alert=True)
        return
    await db.archive_channel(channel_id, not channel["archived"])
    channels = await db.list_channels(include_archived=True)
    await call.message.edit_text(
        "Выберите канал (архивировать/восстановить):",
        reply_markup=channels_pick_kb(channels, "chan:tglarch"),
    )
    await call.answer("Готово")


# --- водянка ------------------------------------------------------------------

@router.callback_query(F.data == "adm:water")
async def water_menu(call: CallbackQuery, state: FSMContext):
    if not await _require_admin(call):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    channels = await db.list_channels()
    await call.message.edit_text("💧 Выберите канал для настройки водянки:", reply_markup=water_channels_kb(channels))
    await call.answer()


@router.callback_query(F.data.startswith("water:pick:"))
async def water_pick(call: CallbackQuery, state: FSMContext):
    channel_id = int(call.data.split(":")[2])
    await state.update_data(channel_id=channel_id)
    await state.set_state(WaterSetup.waiting_text)
    await call.message.edit_text(
        "Пришлите текст со встроенной ссылкой в одном сообщении.\n"
        "Пример: Подпишись на наш канал https://t.me/example"
    )
    await call.answer()


@router.message(WaterSetup.waiting_text)
async def water_save(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.set_water(data["channel_id"], message.html_text or message.text)
    await state.clear()
    channels = await db.list_channels()
    await message.answer("Водянка сохранена.", reply_markup=water_channels_kb(channels))


# --- администраторы (только владелец) ------------------------------------------------

@router.callback_query(F.data == "adm:admins")
async def admins_menu(call: CallbackQuery):
    if not await db.is_owner(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    admins = await db.list_admins()
    await call.message.edit_text("👥 Администраторы:", reply_markup=admins_menu_kb(admins))
    await call.answer()


@router.callback_query(F.data.startswith("admmg:del:"))
async def admins_del(call: CallbackQuery):
    if not await db.is_owner(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    user_id = int(call.data.split(":")[2])
    await db.remove_admin(user_id)
    admins = await db.list_admins()
    await call.message.edit_text("👥 Администраторы:", reply_markup=admins_menu_kb(admins))
    await call.answer("Удалён")


@router.callback_query(F.data == "admmg:add")
async def admins_add_prompt(call: CallbackQuery, state: FSMContext):
    if not await db.is_owner(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text("Введите ID или @username нового модератора:")
    await state.set_state(UsersManage.waiting_id_addadmin)
    await call.answer()
