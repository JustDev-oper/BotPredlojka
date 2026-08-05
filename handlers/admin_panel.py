import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from db.database import db
from keyboards.admin import (
    admin_cancel_keyboard,
    admin_panel_keyboard,
    auto_delete_detail_keyboard,
    auto_delete_list_keyboard,
    auto_delete_time_keyboard,
    broadcast_channels_select_keyboard,
    broadcast_channel_confirm_keyboard,
    fake_stats_keyboard,
    moderators_list_keyboard,
    requests_accept_keyboard,
    requests_channels_keyboard,
    user_action_keyboard,
    users_management_keyboard,
    watermark_channel_select_keyboard,
    watermark_detail_keyboard,
)
from keyboards.inline import (
    broadcast_confirm_keyboard,
    channels_list_keyboard,
    channel_detail_keyboard,
)
from services.broadcast import (
    payload_from_message,
    run_broadcast_background,
    run_channel_broadcast,
    send_preview,
)
from services.channels import verify_bot_in_channel, add_channel_to_db
from services.auto_delete import delete_post_messages
from states.admin import AdminPanelStates
from utils.helpers import format_statistics, is_owner, notify_user_banned

logger = logging.getLogger(__name__)

router = Router(name="admin_panel")

MSK = timezone(timedelta(hours=3))


def _panel_kb_for(user_id: int):
    return admin_panel_keyboard(is_owner=is_owner(user_id))


def _parse_user_target(text: str) -> int | None:
    text = text.strip()
    if text.startswith("@"):
        user = db.find_user_by_username(text)
        return user["tg_id"] if user else None
    if text.isdigit():
        return int(text)
    return None


async def _show_panel(target: Message | CallbackQuery, state: FSMContext) -> None:
    user_id = target.from_user.id
    if not is_owner(user_id):
        if isinstance(target, CallbackQuery):
            await target.answer("Нет доступа", show_alert=True)
        else:
            await target.answer("Нет доступа.")
        return

    await state.clear()
    text = "🛠 <b>Панель администратора</b>\n\nВыберите действие:"
    kb = _panel_kb_for(user_id)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


# ── Команды ───────────────────────────────────────────────────


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await _show_panel(message, state)


@router.message(Command("rndadm"))
async def cmd_rndadm(message: Message, state: FSMContext) -> None:
    if not is_owner(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    db.set_admin(message.from_user.id, True)
    await message.answer(
        "✅ Права владельца восстановлены.",
        reply_markup=admin_panel_keyboard(is_owner=True),
    )


# ── Панель ────────────────────────────────────────────────────


@router.callback_query(F.data == "ap:open")
async def cb_open_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_panel(callback, state)


@router.callback_query(F.data == "ap:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    current = await state.get_state()
    if current:
        await state.clear()
        await callback.answer("Отменено")
        await callback.message.edit_text(
            "🛠 <b>Панель администратора</b>\n\nДействие отменено. Выберите действие:",
            parse_mode="HTML",
            reply_markup=_panel_kb_for(callback.from_user.id),
        )
    else:
        await callback.answer("Нечего отменять", show_alert=True)


# ── Статистика ────────────────────────────────────────────────


@router.callback_query(F.data == "ap:stats")
async def cb_stats(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    stats = db.get_statistics()
    await callback.message.edit_text(
        format_statistics(stats),
        parse_mode="HTML",
        reply_markup=_panel_kb_for(callback.from_user.id),
    )
    await callback.answer()


# ── Фейк-статистика ───────────────────────────────────────────


def _format_fake_stats(values: dict[str, int]) -> str:
    return (
        "📈 <b>Фейк-статистика</b>\n\n"
        f"👥 Пользователей: <b>{values.get('users', 0)}</b>\n"
        f"📨 Постов: <b>{values.get('posts', 0)}</b>"
    )


@router.callback_query(F.data == "ap:fake_stats")
async def cb_fake_stats(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    values = db.get_fake_stats()
    await callback.message.edit_text(
        _format_fake_stats(values),
        parse_mode="HTML",
        reply_markup=fake_stats_keyboard(values),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ap:fs_edit:"))
async def cb_fs_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    key = callback.data.split(":", 2)[2]
    if key not in ("users", "posts"):
        await callback.answer("Неизвестное поле", show_alert=True)
        return
    label = "Пользователи" if key == "users" else "Посты"
    current = db.get_fake_stats().get(key, 0)
    await state.set_state(AdminPanelStates.waiting_fake_stat_value)
    await state.update_data(fake_stat_key=key)
    await callback.message.edit_text(
        f"✏️ <b>{label}</b>\n\n"
        f"Текущее значение: <b>{current}</b>\n\n"
        f"Введите новое числовое значение:",
        parse_mode="HTML",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPanelStates.waiting_fake_stat_value)
async def process_fs_value(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Введите целое число (0 или положительное).")
        return
    value = int(text)
    data = await state.get_data()
    key = data["fake_stat_key"]
    db.set_fake_stat(key, value)
    await state.clear()
    values = db.get_fake_stats()
    await message.answer(
        _format_fake_stats(values),
        parse_mode="HTML",
        reply_markup=fake_stats_keyboard(values),
    )


@router.callback_query(F.data == "ap:fs_show")
async def cb_fs_show(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    values = db.get_fake_stats()
    users = values.get("users", 0)
    posts = values.get("posts", 0)
    text = (
        f"📊 <b>Итоговая статистика</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"📨 Постов: <b>{posts}</b>\n"
        f"📢 Каналов: <b>{len(db.get_active_channels())}</b>"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=fake_stats_keyboard(values),
    )
    await callback.answer()


@router.callback_query(F.data == "ap:fs_clear")
async def cb_fs_clear(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    db.clear_all_fake_stats()
    await state.clear()
    values = db.get_fake_stats()
    await callback.message.edit_text(
        "🗑 Фейковые значения сброшены.\n\n" + _format_fake_stats(values),
        parse_mode="HTML",
        reply_markup=fake_stats_keyboard(values),
    )
    await callback.answer("Сброшено")


# ── Бан-лист ──────────────────────────────────────────────────


@router.callback_query(F.data == "ap:banlist")
async def cb_banlist(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    banned = db.get_banned_users()
    if not banned:
        await callback.message.edit_text(
            "🚫 Список заблокированных пуст.",
            reply_markup=_panel_kb_for(callback.from_user.id),
        )
        await callback.answer()
        return

    from keyboards.inline import banlist_keyboard
    lines = ["<b>🚫 Заблокированные:</b>\n"]
    for u in banned:
        uname = f"@{u['username']}" if u["username"] else "нет username"
        lines.append(f"• {u['full_name']} ({uname}) — <code>{u['tg_id']}</code>")
    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=banlist_keyboard(banned),
    )
    await callback.answer()


# ── Пользователи ──────────────────────────────────────────────


@router.callback_query(F.data == "ap:users")
async def cb_users(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    users = db.get_all_users()
    if not users:
        await callback.message.edit_text(
            "👥 Список пользователей пуст.",
            reply_markup=_panel_kb_for(callback.from_user.id),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "👥 <b>Пользователи</b>\n\nВыберите пользователя или найдите по ID / @:",
        parse_mode="HTML",
        reply_markup=users_management_keyboard(users),
    )
    await callback.answer()


@router.callback_query(F.data == "ap:user_search")
async def cb_user_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminPanelStates.waiting_user_search)
    await callback.message.edit_text(
        "🔍 Отправьте <b>@username</b> или <b>ID</b> пользователя:",
        parse_mode="HTML",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPanelStates.waiting_user_search)
async def process_user_search(message: Message, state: FSMContext) -> None:
    tg_id = _parse_user_target(message.text or "")
    if not tg_id:
        await message.answer("Не найден. Формат: @username или ID")
        return
    db.set_banned(tg_id, True)
    await notify_user_banned(bot, tg_id)
    user = db.get_user_by_telegram_id(tg_id)
    await callback.answer("Забанен")
    await _show_user_actions(callback, user)


@router.callback_query(F.data.startswith("usr_unban:"))
async def cb_user_unban(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        tg_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    db.set_banned(tg_id, False)
    db.reset_user_post_count(tg_id)
    user = db.get_user_by_telegram_id(tg_id)
    await callback.answer("Разбанен")
    await _show_user_actions(callback, user)


@router.callback_query(F.data.startswith("usr_mute:"))
async def cb_user_mute(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        tg_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    await state.set_state(AdminPanelStates.waiting_mute_minutes)
    await state.update_data(mute_target=tg_id)
    await callback.message.edit_text(
        f"🔇 Укажите количество минут мута для <code>{tg_id}</code>:",
        parse_mode="HTML",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPanelStates.waiting_mute_minutes)
async def process_mute_minutes(message: Message, state: FSMContext, bot: Bot) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("Введите положительное число минут.")
        return
    data = await state.get_data()
    tg_id = data["mute_target"]
    await _mute_user(bot, tg_id, int(text))
    await state.clear()
    user = db.get_user_by_telegram_id(tg_id)
    await _show_user_actions(message, user)


@router.callback_query(F.data.startswith("usr_unmute:"))
async def cb_user_unmute(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        tg_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    db.set_muted_until(tg_id, None)
    db.reset_user_post_count(tg_id)
    user = db.get_user_by_telegram_id(tg_id)
    await callback.answer("Мут снят")
    await _show_user_actions(callback, user)


@router.callback_query(F.data.startswith("usr_promote:"))
async def cb_user_promote(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    try:
        tg_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    db.set_admin(tg_id, True)
    user = db.get_user_by_telegram_id(tg_id)
    await callback.answer("Назначен админом")
    await _show_user_actions(callback, user)


@router.callback_query(F.data.startswith("usr_demote:"))
async def cb_user_demote(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    try:
        tg_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    if is_owner(tg_id):
        await callback.answer("Нельзя снять владельца", show_alert=True)
        return
    db.set_admin(tg_id, False)
    user = db.get_user_by_telegram_id(tg_id)
    await callback.answer("Снят с админов")
    await _show_user_actions(callback, user)


# ── Рассылка (бот) ────────────────────────────────────────────


@router.callback_query(F.data == "ap:broadcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminPanelStates.waiting_broadcast_content)
    await callback.message.edit_text(
        "📢 <b>Рассылка (бот)</b>\n\n"
        "Отправьте сообщение для всех пользователей бота:\n"
        "• текст\n"
        "• фото с подписью или без\n"
        "• видео с подписью или без\n"
        "• документ с подписью или без",
        parse_mode="HTML",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@router.message(
    AdminPanelStates.waiting_broadcast_content,
    F.text | F.photo | F.video | F.document,
)
async def process_broadcast_content(message: Message, state: FSMContext, bot: Bot) -> None:
    payload = payload_from_message(message)
    if not payload:
        await message.answer("Поддерживается: текст, фото, видео или документ.")
        return

    await state.update_data(broadcast=payload)
    await message.answer("👀 <b>Превью рассылки:</b>", parse_mode="HTML")
    await send_preview(bot, message.from_user.id, payload)
    await message.answer(
        "Отправить всем пользователям бота?",
        reply_markup=broadcast_confirm_keyboard(),
    )


@router.callback_query(F.data == "bc_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Рассылка отменена.",
        reply_markup=_panel_kb_for(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data == "bc_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    payload = data.get("broadcast")
    if not payload:
        await callback.answer("Нет данных. Начните заново.", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Рассылка запущена…")

    asyncio.create_task(run_broadcast_background(
        bot, callback.from_user.id, payload,
        disable_web_page_preview=True,
    ))
    await state.clear()


# ── Рассылка по каналам (только владелец) ─────────────────────


@router.callback_query(F.data == "ap:broadcast_channels")
async def cb_broadcast_channels_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    channels = db.get_active_channels()
    if not channels:
        await callback.answer("Нет каналов", show_alert=True)
        return
    await state.set_state(AdminPanelStates.waiting_broadcast_channel_select)
    await state.update_data(bc_channels=set())
    await callback.message.edit_text(
        "📢 <b>Рассылка по каналам</b>\n\n"
        "Выберите каналы:",
        parse_mode="HTML",
        reply_markup=broadcast_channels_select_keyboard(channels, set()),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bc_ch_toggle:"))
async def bc_ch_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        channel_id = int(callback.data.split(":", 2)[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    data = await state.get_data()
    selected = set(data.get("bc_channels", set()))
    if channel_id in selected:
        selected.discard(channel_id)
    else:
        selected.add(channel_id)
    await state.update_data(bc_channels=selected)
    channels = db.get_active_channels()
    await callback.message.edit_text(
        "📢 <b>Рассылка по каналам</b>\n\n"
        "Выберите каналы:",
        parse_mode="HTML",
        reply_markup=broadcast_channels_select_keyboard(channels, selected),
    )
    await callback.answer()


@router.callback_query(F.data == "bc_ch_all")
async def bc_ch_all(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    channels = db.get_active_channels()
    selected = {ch["id"] for ch in channels}
    await state.update_data(bc_channels=selected)
    await callback.message.edit_text(
        "📢 <b>Рассылка по каналам</b>\n\n"
        "Выбраны все каналы:",
        parse_mode="HTML",
        reply_markup=broadcast_channels_select_keyboard(channels, selected),
    )
    await callback.answer()


@router.callback_query(F.data == "bc_ch_confirm")
async def bc_ch_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    selected = set(data.get("bc_channels", set()))
    if not selected:
        await callback.answer("Выберите хотя бы один канал", show_alert=True)
        return
    await state.set_state(AdminPanelStates.waiting_broadcast_channel_post)
    await callback.message.edit_text(
        f"📢 Выбрано каналов: <b>{len(selected)}</b>\n\n"
        f"Отправьте пост для рассылки (текст, фото, видео или документ):",
        parse_mode="HTML",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@router.message(
    AdminPanelStates.waiting_broadcast_channel_post,
    F.text | F.photo | F.video | F.document,
)
async def process_broadcast_channel_post(message: Message, state: FSMContext, bot: Bot) -> None:
    payload = payload_from_message(message)
    if not payload:
        await message.answer("Поддерживается: текст, фото, видео или документ.")
        return

    data = await state.get_data()
    selected = set(data.get("bc_channels", set()))

    await state.update_data(bc_payload=payload, bc_auto_delete=0, bc_auto_delete_selected=False)
    await message.answer("👀 <b>Превью:</b>", parse_mode="HTML")
    await send_preview(bot, message.from_user.id, payload)
    await message.answer(
        f"Вы уверены, что хотите опубликовать в <b>{len(selected)}</b> каналов?",
        parse_mode="HTML",
        reply_markup=broadcast_channel_confirm_keyboard(),
    )


@router.callback_query(F.data == "bc_ad_time")
async def bc_ad_time(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    await state.update_data(bc_auto_delete_selected=True)
    ad_choice = data.get("bc_auto_delete", 0)
    await callback.message.edit_text(
        f"⏰ <b>Автоудаление</b>\n\n"
        f"Текущий выбор: {ad_choice if ad_choice else 'Не удалять'}\n\n"
        f"Выберите время:",
        parse_mode="HTML",
        reply_markup=auto_delete_time_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ad_time:"))
async def bc_ad_time_choice(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        hours = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    current_state = await state.get_state()

    # Если мы в процессе рассылки по каналам — сохраняем выбор и возвращаемся к подтверждению
    if current_state == AdminPanelStates.waiting_broadcast_channel_post.state:
        await state.update_data(bc_auto_delete=hours)
        data = await state.get_data()
        payload = data.get("bc_payload")
        selected = set(data.get("bc_channels", set()))
        await callback.message.edit_text(
            f"👀 <b>Превью:</b>\n\n"
            f"⏰ Автоудаление: {'через ' + str(hours) + ' ч' if hours else 'не удалять'}\n"
            f"Вы уверены, что хотите опубликовать в <b>{len(selected)}</b> каналов?",
            parse_mode="HTML",
            reply_markup=broadcast_channel_confirm_keyboard(),
        )
        await callback.answer()
        return

    # Если мы в панели автоудаления — это выбор времени для «Изменить дату» (не используется напрямую)
    await callback.answer("Используйте формат даты")


@router.callback_query(F.data == "bc_ch_send")
async def bc_ch_send(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    payload = data.get("bc_payload")
    selected = set(data.get("bc_channels", set()))
    auto_delete = data.get("bc_auto_delete", 0)
    if not payload or not selected:
        await callback.answer("Нет данных. Начните заново.", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Публикация запущена…")

    asyncio.create_task(run_channel_broadcast(
        bot, callback.from_user.id, payload, list(selected),
        auto_delete_hours=auto_delete,
    ))
    await state.clear()


# ── Каналы ────────────────────────────────────────────────────


async def _safe_edit(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)


@router.callback_query(F.data == "ap:channels")
async def cb_channels_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    channels = db.get_channels_with_stats()
    is_owner_flag = is_owner(callback.from_user.id)
    if not channels:
        await _safe_edit(callback, "📢 <b>Каналы</b>\n\nСписок каналов пуст.",
                         reply_markup=channels_list_keyboard([], is_owner=is_owner_flag))
    else:
        await _safe_edit(callback, "📢 <b>Каналы</b>\n\nВыберите канал:",
                         reply_markup=channels_list_keyboard(channels, is_owner=is_owner_flag))
    await callback.answer()


@router.callback_query(F.data == "ap:add_channel")
async def cb_add_channel_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    await state.set_state(AdminPanelStates.waiting_channel_username)
    await callback.message.edit_text(
        "➕ <b>Добавление канала</b>\n\n"
        "Отправьте <b>@username</b> канала.\n"
        "Бот должен быть добавлен в канал с правами администратора.",
        parse_mode="HTML",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPanelStates.waiting_channel_username)
async def process_add_channel(message: Message, state: FSMContext, bot: Bot) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    text = (message.text or "").strip().lstrip("@")
    if not text or " " in text:
        await message.answer("Отправьте @username канала (например: @mychannel)")
        return

    existing = db.get_channel_by_username(text.lower())
    if existing and existing["is_active"]:
        await state.clear()
        await message.answer(
            f"⚠️ Канал <b>@{text}</b> уже добавлен.",
            parse_mode="HTML",
            reply_markup=_panel_kb_for(message.from_user.id),
        )
        return

    ok, msg, title, tg_id = await verify_bot_in_channel(bot, text)
    if not ok:
        await message.answer(
            f"❌ {msg}",
            reply_markup=admin_cancel_keyboard(),
        )
        return

    if existing and not existing["is_active"]:
        channel_id = existing["id"]
        with db._transaction() as cur:
            cur.execute("UPDATE channels SET is_active = 1, channel_title = ?, channel_tg_id = ? WHERE id = ?",
                        (title, tg_id, channel_id))
    else:
        channel_id = add_channel_to_db(text.lower(), title, tg_id, message.from_user.id)

    # Создаём топики для всех админов
    admin_ids = db.get_all_admins()
    topics_created = 0
    for admin_id in admin_ids:
        existing_topic = db.get_admin_topic(admin_id, channel_id)
        if existing_topic:
            continue
        try:
            topic = await bot.create_forum_topic(
                chat_id=admin_id,
                name=f"📢 {title or text}",
            )
            db.save_admin_topic(admin_id, channel_id, topic.message_thread_id)
            topics_created += 1
        except Exception:
            logger.warning("Не удалось создать топик для админа %s", admin_id)

    await state.clear()
    topic_text = f"\n🗂 Топики созданы у {topics_created} админов." if topics_created else ""
    reconnected = " (повторно подключён)" if existing else ""
    await message.answer(
        f"✅ Канал <b>{title}</b> (<code>@{text}</code>) добавлен{reconnected}.{topic_text}",
        parse_mode="HTML",
        reply_markup=_panel_kb_for(message.from_user.id),
    )


@router.callback_query(F.data.startswith("ch_menu:"))
async def cb_channel_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    parts = callback.data.split(":")
    try:
        channel_id = int(parts[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    channel = db.get_channel_by_id(channel_id)
    if not channel or not channel["is_active"]:
        await callback.answer("Канал не найден", show_alert=True)
        return

    pending_count = db.count_posts_by_channel(channel_id, "pending")
    title = channel["channel_title"] or f"@{channel['channel_username']}"
    text = (
        f"📢 <b>{title}</b>\n"
        f"<code>@{channel['channel_username']}</code>\n\n"
        f"⏳ На модерации: <b>{pending_count}</b>"
    )
    await _safe_edit(
        callback, text,
        reply_markup=channel_detail_keyboard(
            channel_id, is_owner=is_owner(callback.from_user.id),
            require_subscription=bool(channel["require_subscription"])
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ch_toggle_sub:"))
async def cb_channel_toggle_sub(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    parts = callback.data.split(":")
    try:
        channel_id = int(parts[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    channel = db.get_channel_by_id(channel_id)
    if not channel or not channel["is_active"]:
        await callback.answer("Канал не найден", show_alert=True)
        return

    new_val = db.toggle_require_subscription(channel_id)
    status = "обязательна" if new_val else "не обязательна"
    await callback.answer(f"Подписка {status}", show_alert=False)

    title = channel["channel_title"] or f"@{channel['channel_username']}"
    pending_count = db.count_posts_by_channel(channel_id, "pending")
    text = (
        f"📢 <b>{title}</b>\n"
        f"<code>@{channel['channel_username']}</code>\n\n"
        f"⏳ На модерации: <b>{pending_count}</b>"
    )
    await callback.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=channel_detail_keyboard(channel_id, is_owner=True, require_subscription=new_val),
    )


@router.callback_query(F.data.startswith("ch_rename:"))
async def cb_channel_rename(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    parts = callback.data.split(":")
    try:
        channel_id = int(parts[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    await state.set_state(AdminPanelStates.waiting_channel_rename)
    await state.update_data(channel_rename_id=channel_id)
    await callback.message.edit_text(
        "✏️ Отправьте новое название канала:",
        parse_mode="HTML",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPanelStates.waiting_channel_rename)
async def process_channel_rename(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Название не может быть пустым.")
        return
    data = await state.get_data()
    channel_id = data["channel_rename_id"]
    db.rename_channel(channel_id, text)
    await state.clear()
    channel = db.get_channel_by_id(channel_id)
    title = channel["channel_title"] if channel else text
    await message.answer(
        f"✅ Канал переименован в <b>{title}</b>.",
        parse_mode="HTML",
        reply_markup=_panel_kb_for(message.from_user.id),
    )


@router.callback_query(F.data.startswith("ch_archive:"))
async def cb_channel_archive(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    parts = callback.data.split(":")
    try:
        channel_id = int(parts[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    topics = db.get_topics_for_channel(channel_id)
    for topic in topics:
        try:
            await bot.delete_forum_topic(topic["admin_tg_id"], topic["topic_id"])
        except Exception:
            pass
    db.delete_all_topics_for_channel(channel_id)
    db.deactivate_channel(channel_id)
    await state.clear()
    channels = db.get_channels_with_stats()
    await _safe_edit(callback, "✅ Канал заархивирован.\n\n📢 <b>Каналы</b>",
                     reply_markup=channels_list_keyboard(channels, is_owner=True))
    await callback.answer()


# ── Водянка ───────────────────────────────────────────────────


@router.callback_query(F.data == "ap:watermark")
async def cb_watermark(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    channels = db.get_active_channels()
    if not channels:
        await callback.message.edit_text(
            "💧 Нет каналов.",
            reply_markup=_panel_kb_for(callback.from_user.id),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "💧 <b>Водянка</b>\n\nВыберите канал для настройки:",
        parse_mode="HTML",
        reply_markup=watermark_channel_select_keyboard(channels),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wm_select:"))
async def cb_watermark_select(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        channel_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    channel = db.get_channel_by_id(channel_id)
    if not channel:
        await callback.answer("Канал не найден", show_alert=True)
        return

    existing = db.get_watermark(channel_id)
    if existing:
        await callback.message.edit_text(
            f"💧 <b>{channel['channel_title'] or '@' + channel['channel_username']}</b>\n\n"
            f"Текущая водянка:\n{existing}",
            parse_mode="HTML",
            reply_markup=watermark_detail_keyboard(channel_id, has_watermark=True),
        )
        await callback.answer()
        return

    await state.set_state(AdminPanelStates.waiting_watermark_text)
    await state.update_data(watermark_channel_id=channel_id)
    await callback.message.edit_text(
        f"💧 <b>{channel['channel_title'] or '@' + channel['channel_username']}</b>\n\n"
        f"Отправьте текст водянки со встроенной ссылкой в одном сообщении.\n"
        f"Пример: <i>Подпишись на наш канал https://t.me/example</i>",
        parse_mode="HTML",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPanelStates.waiting_watermark_text)
async def process_watermark_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст не может быть пустым.")
        return
    data = await state.get_data()
    channel_id = data["watermark_channel_id"]
    db.set_watermark(channel_id, text)
    await state.clear()
    channel = db.get_channel_by_id(channel_id)
    title = channel["channel_title"] if channel else f"ID {channel_id}"
    await message.answer(
        f"✅ Водянка для <b>{title}</b> сохранена.\n\n{text}",
        parse_mode="HTML",
        reply_markup=_panel_kb_for(message.from_user.id),
    )


@router.callback_query(F.data.startswith("wm_delete:"))
async def cb_watermark_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        channel_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    db.delete_watermark(channel_id)
    await state.clear()
    channel = db.get_channel_by_id(channel_id)
    title = channel["channel_title"] if channel else f"ID {channel_id}"
    await callback.message.edit_text(
        f"✅ Водянка для <b>{title}</b> удалена.",
        parse_mode="HTML",
        reply_markup=_panel_kb_for(callback.from_user.id),
    )
    await callback.answer()


# ── Заявки ─────────────────────────────────────────────────────


@router.callback_query(F.data == "ap:requests")
async def cb_requests(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    channels = db.get_channels_with_stats()
    await callback.message.edit_text(
        "📩 <b>Заявки</b>\n\n"
        "Отметьте каналы и примите заявки:",
        parse_mode="HTML",
        reply_markup=requests_channels_keyboard(channels, set()),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("req_toggle:"))
async def cb_request_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        channel_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    data = await state.get_data()
    selected = set(data.get("req_channels", set()))
    if channel_id in selected:
        selected.discard(channel_id)
    else:
        selected.add(channel_id)
    await state.update_data(req_channels=selected)
    channels = db.get_channels_with_stats()
    await callback.message.edit_text(
        "📩 <b>Заявки</b>\n\n"
        "Отметьте каналы и примите заявки:",
        parse_mode="HTML",
        reply_markup=requests_channels_keyboard(channels, selected),
    )
    await callback.answer()


@router.callback_query(F.data == "req_accept")
async def cb_request_accept(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    selected = set(data.get("req_channels", set()))
    if not selected:
        await callback.answer("Каналы не выбраны", show_alert=True)
        return
    await state.update_data(req_accept_channels=selected)
    await callback.message.edit_text(
        f"Принять заявки в <b>{len(selected)}</b> каналах?",
        parse_mode="HTML",
        reply_markup=requests_accept_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "req_accept_confirm")
async def cb_request_accept_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    selected = set(data.get("req_accept_channels", set()))
    total = 0
    for channel_id in selected:
        total += db.accept_all_requests(channel_id)
    await state.clear()
    channels = db.get_channels_with_stats()
    await callback.message.edit_text(
        f"✅ Принято заявок: <b>{total}</b>\n\n📩 <b>Заявки</b>",
        parse_mode="HTML",
        reply_markup=requests_channels_keyboard(channels, set()),
    )
    await callback.answer()


@router.callback_query(F.data == "req_accept_all")
async def cb_request_accept_all(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    channels = db.get_active_channels()
    total = 0
    for channel in channels:
        total += db.accept_all_requests(channel["id"])
    await state.clear()
    channels_stats = db.get_channels_with_stats()
    await callback.message.edit_text(
        f"✅ Принято заявок во всех каналах: <b>{total}</b>\n\n📩 <b>Заявки</b>",
        parse_mode="HTML",
        reply_markup=requests_channels_keyboard(channels_stats, set()),
    )
    await callback.answer()


# ── Администраторы ────────────────────────────────────────────


@router.callback_query(F.data == "ap:admins")
async def cb_admins(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    await state.clear()
    moderators = db.get_all_moderators()
    await callback.message.edit_text(
        "👥 <b>Администраторы</b>\n\nМодераторы:",
        parse_mode="HTML",
        reply_markup=moderators_list_keyboard(moderators),
    )
    await callback.answer()


@router.callback_query(F.data == "ap:add_moderator")
async def cb_add_moderator(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    await state.set_state(AdminPanelStates.waiting_new_admin_data)
    await callback.message.edit_text(
        "👥 Отправьте <b>@username</b> или <b>ID</b> для нового модератора.",
        parse_mode="HTML",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPanelStates.waiting_new_admin_data)
async def process_new_admin_id(message: Message, state: FSMContext, bot: Bot) -> None:
    tg_id = _parse_user_target(message.text or "")
    if not tg_id:
        await message.answer("Не найден. Формат: @username или ID")
        return
    db.set_admin(tg_id, True)
    await state.clear()

    from handlers.callbacks import create_topics_for_admin
    topics_created = await create_topics_for_admin(bot, tg_id)
    topic_text = f"\n🗂 Создано {topics_created} топиков для каналов." if topics_created else ""

    await message.answer(
        f"👥 Пользователь с ID <code>{tg_id}</code> назначен модератором.{topic_text}",
        parse_mode="HTML",
        reply_markup=_panel_kb_for(message.from_user.id),
    )
    try:
        await bot.send_message(
            tg_id,
            f"Теперь вы можете принимать посты.",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("ap:del_mod:"))
async def cb_del_moderator(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    try:
        tg_id = int(callback.data.split(":", 2)[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    if is_owner(tg_id):
        await callback.answer("Нельзя удалить владельца", show_alert=True)
        return
    db.set_admin(tg_id, False)
    await state.clear()
    moderators = db.get_all_moderators()
    await callback.message.edit_text(
        f"✅ Модератор <code>{tg_id}</code> удалён.\n\n👥 <b>Администраторы</b>",
        parse_mode="HTML",
        reply_markup=moderators_list_keyboard(moderators),
    )
    await callback.answer()
    try:
        await bot.send_message(tg_id, "😢 Вы больше не модератор.")
    except Exception:
        pass


# ── Автоудаление ──────────────────────────────────────────────


@router.callback_query(F.data == "ap:auto_delete")
async def cb_auto_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    ads = db.get_auto_delete_posts()
    if not ads:
        await callback.message.edit_text(
            "⏰ <b>Автоудаление</b>\n\nНет постов с автоудалением.",
            parse_mode="HTML",
            reply_markup=_panel_kb_for(callback.from_user.id),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "⏰ <b>Автоудаление</b>\n\nСписок постов:",
        parse_mode="HTML",
        reply_markup=auto_delete_list_keyboard(ads),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ad_view:"))
async def cb_ad_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        ad_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    ad = db.get_auto_delete(ad_id)
    if not ad or ad["is_cancelled"]:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    await state.update_data(ad_current=ad_id)
    await callback.message.edit_text(
        f"⏰ <b>Пост №{ad['id']}</b>\n"
        f"Удаление: {ad['delete_at'][:16]}\n\n"
        f"Выберите действие:",
        parse_mode="HTML",
        reply_markup=auto_delete_detail_keyboard(ad_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ad_delete_now:"))
async def cb_ad_delete_now(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        ad_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    ad = db.get_auto_delete(ad_id)
    if not ad:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    ok = await delete_post_messages(bot, ad)
    db.cancel_auto_delete(ad_id)
    await callback.answer()
    ads = db.get_auto_delete_posts()
    await callback.message.edit_text(
        f"{'✅ Пост удалён.' if ok else '⚠️ Не удалось удалить посты.'}\n\n⏰ <b>Автоудаление</b>",
        parse_mode="HTML",
        reply_markup=auto_delete_list_keyboard(ads) if ads else _panel_kb_for(callback.from_user.id),
    )


@router.callback_query(F.data.startswith("ad_cancel:"))
async def cb_ad_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        ad_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    db.cancel_auto_delete(ad_id)
    await state.clear()
    ads = db.get_auto_delete_posts()
    await callback.message.edit_text(
        "✅ Автоудаление отменено.\n\n⏰ <b>Автоудаление</b>",
        parse_mode="HTML",
        reply_markup=auto_delete_list_keyboard(ads) if ads else _panel_kb_for(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ad_change:"))
async def cb_ad_change(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        ad_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    await state.set_state(AdminPanelStates.waiting_auto_delete_time)
    await state.update_data(ad_change_id=ad_id)
    await callback.message.edit_text(
        "✏️ Отправьте новую дату и время в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Пример: <code>06.08.2026 18:30</code>",
        parse_mode="HTML",
        reply_markup=admin_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPanelStates.waiting_auto_delete_time)
async def process_auto_delete_time(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        dt = datetime.strptime(text, "%d.%m.%Y %H:%M")
        delete_at = dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        await message.answer("Неверный формат. Используйте: ДД.ММ.ГГГГ ЧЧ:ММ")
        return

    data = await state.get_data()
    ad_id = data["ad_change_id"]
    db.update_auto_delete_time(ad_id, delete_at)
    await state.clear()
    ads = db.get_auto_delete_posts()
    await message.answer(
        f"✅ Дата автоудаления изменена на <b>{text}</b>.",
        parse_mode="HTML",
        reply_markup=auto_delete_list_keyboard(ads) if ads else _panel_kb_for(message.from_user.id),
    )


@router.callback_query(F.data == "ad_delete_all")
async def cb_ad_delete_all(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    ads = db.get_auto_delete_posts()
    deleted = 0
    for ad in ads:
        ok = await delete_post_messages(bot, ad)
        if ok:
            deleted += 1
        db.cancel_auto_delete(ad["id"])
    await state.clear()
    await callback.message.edit_text(
        f"🗑 Удалено постов: <b>{deleted}</b>",
        parse_mode="HTML",
        reply_markup=_panel_kb_for(callback.from_user.id),
    )
    await callback.answer()
