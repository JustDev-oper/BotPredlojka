from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_open_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Админка", callback_data="ap:open")],
        ]
    )


def admin_panel_keyboard(*, is_owner: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="ap:stats")],
        [InlineKeyboardButton(text="📈 Фейк-статистика", callback_data="ap:fake_stats")],
        [InlineKeyboardButton(text="🚫 Бан-лист", callback_data="ap:banlist")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="ap:users")],
        [InlineKeyboardButton(text="📢 Рассылка (бот)", callback_data="ap:broadcast")],
        [InlineKeyboardButton(text="📋 Каналы", callback_data="ap:channels")],
        [InlineKeyboardButton(text="💧 Водянка", callback_data="ap:watermark")],
        [InlineKeyboardButton(text="📩 Заявки", callback_data="ap:requests")],
        [InlineKeyboardButton(text="👥 Администраторы", callback_data="ap:admins")],
        [InlineKeyboardButton(text="⏰ Автоудаление", callback_data="ap:auto_delete")],
    ]
    if is_owner:
        rows.append(
            [InlineKeyboardButton(text="📢 Рассылка по каналам", callback_data="ap:broadcast_channels")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fake_stats_keyboard(values: dict[str, int]) -> InlineKeyboardMarkup:
    """Фейк-статистика: кнопки «Пользователи», «Посты», «Показать итог»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"👥 Пользователи: {values.get('users', 0)}", callback_data="ap:fs_edit:users")],
            [InlineKeyboardButton(text=f"📨 Посты: {values.get('posts', 0)}", callback_data="ap:fs_edit:posts")],
            [InlineKeyboardButton(text="📊 Показать итог", callback_data="ap:fs_show")],
            [InlineKeyboardButton(text="🗑 Сброс", callback_data="ap:fs_clear")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="ap:open")],
        ]
    )


def admin_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="ap:cancel")],
        ]
    )


def users_management_keyboard(users: list) -> InlineKeyboardMarkup:
    """Клавиатура управления пользователями с кнопками действий."""
    rows = []
    for u in users[:20]:
        uname = f"@{u['username']}" if u['username'] else "нет"
        name = u['full_name'] or str(u['tg_id'])
        label = f"{name} ({uname})"
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"usr_view:{u['tg_id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔍 Найти по ID или @", callback_data="ap:user_search")])
    rows.append([InlineKeyboardButton(text="◀️ Панель", callback_data="ap:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_action_keyboard(tg_id: int, is_banned: bool, is_admin: bool, is_muted: bool) -> InlineKeyboardMarkup:
    rows = []
    if is_banned:
        rows.append([InlineKeyboardButton(text="🔓 Разбанить", callback_data=f"usr_unban:{tg_id}")])
    else:
        rows.append([InlineKeyboardButton(text="🔒 Забанить", callback_data=f"usr_ban:{tg_id}")])
    if is_muted:
        rows.append([InlineKeyboardButton(text="🔊 Размутить", callback_data=f"usr_unmute:{tg_id}")])
    else:
        rows.append([InlineKeyboardButton(text="🔇 Замутить", callback_data=f"usr_mute:{tg_id}")])
    if is_admin:
        rows.append([InlineKeyboardButton(text="➖ Снять админа", callback_data=f"usr_demote:{tg_id}")])
    else:
        rows.append([InlineKeyboardButton(text="➕ Назначить админом", callback_data=f"usr_promote:{tg_id}")])
    rows.append([InlineKeyboardButton(text="◀️ К списку", callback_data="ap:users")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def moderators_list_keyboard(moderators: list) -> InlineKeyboardMarkup:
    rows = []
    for m in moderators:
        uname = f"@{m['username']}" if m['username'] else "нет username"
        label = f"{m['full_name']} ({uname})" if m['full_name'] else uname
        rows.append([
            InlineKeyboardButton(text=f"➖ {label}", callback_data=f"ap:del_mod:{m['tg_id']}")
        ])
    rows.append([InlineKeyboardButton(text="➕ Добавить модератора", callback_data="ap:add_moderator")])
    rows.append([InlineKeyboardButton(text="◀️ Панель", callback_data="ap:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def watermark_channel_select_keyboard(channels: list) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        title = ch["channel_title"] or f"@{ch['channel_username']}"
        rows.append([
            InlineKeyboardButton(text=title, callback_data=f"wm_select:{ch['id']}")
        ])
    rows.append([InlineKeyboardButton(text="◀️ Панель", callback_data="ap:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def watermark_detail_keyboard(channel_id: int, has_watermark: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_watermark:
        rows.append([InlineKeyboardButton(text="🗑 Удалить водянку", callback_data=f"wm_delete:{channel_id}")])
    rows.append([InlineKeyboardButton(text="◀️ К списку", callback_data="ap:watermark")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def requests_channels_keyboard(channels: list, selected: set[int]) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        cnt = ch.get("request_count", 0)
        title = ch["channel_title"] or f"@{ch['channel_username']}"
        check = "✅" if ch["id"] in selected else "⬜"
        rows.append([
            InlineKeyboardButton(
                text=f"{check} 📢 {title} ({cnt})",
                callback_data=f"req_toggle:{ch['id']}",
            )
        ])
    if selected:
        rows.append([InlineKeyboardButton(text="✅ Принять заявки", callback_data="req_accept")])
    rows.append([InlineKeyboardButton(text="✅ Принять во всех", callback_data="req_accept_all")])
    rows.append([InlineKeyboardButton(text="◀️ Панель", callback_data="ap:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def requests_accept_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, принять", callback_data="req_accept_confirm")],
            [InlineKeyboardButton(text="❌ Нет", callback_data="ap:requests")],
        ]
    )


def broadcast_channels_select_keyboard(channels: list, selected: set[int]) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        title = ch["channel_title"] or f"@{ch['channel_username']}"
        check = "✅" if ch["id"] in selected else "⬜"
        rows.append([
            InlineKeyboardButton(
                text=f"{check} {title}",
                callback_data=f"bc_ch_toggle:{ch['id']}",
            )
        ])
    nav = []
    nav.append(InlineKeyboardButton(text="✅ Выбрать все", callback_data="bc_ch_all"))
    nav.append(InlineKeyboardButton(text="❌ Отмена", callback_data="ap:cancel"))
    rows.append(nav)
    if selected:
        rows.append([InlineKeyboardButton(text="✅ Подтвердить", callback_data="bc_ch_confirm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def auto_delete_time_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="2 ч", callback_data="ad_time:2")],
            [InlineKeyboardButton(text="24 ч", callback_data="ad_time:24")],
            [InlineKeyboardButton(text="48 ч", callback_data="ad_time:48")],
            [InlineKeyboardButton(text="72 ч", callback_data="ad_time:72")],
            [InlineKeyboardButton(text="Не удалять", callback_data="ad_time:0")],
        ]
    )


def auto_delete_list_keyboard(ads: list) -> InlineKeyboardMarkup:
    rows = []
    for ad in ads:
        rows.append([
            InlineKeyboardButton(
                text=f"Пост №{ad['id']} — {ad['delete_at'][:16]}",
                callback_data=f"ad_view:{ad['id']}",
            )
        ])
    if ads:
        rows.append([InlineKeyboardButton(text="🗑 Удалить все посты", callback_data="ad_delete_all")])
    rows.append([InlineKeyboardButton(text="◀️ Панель", callback_data="ap:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def auto_delete_detail_keyboard(ad_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить сейчас", callback_data=f"ad_delete_now:{ad_id}")],
            [InlineKeyboardButton(text="❌ Отменить автоудаление", callback_data=f"ad_cancel:{ad_id}")],
            [InlineKeyboardButton(text="✏️ Изменить дату", callback_data=f"ad_change:{ad_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="ap:auto_delete")],
        ]
    )


def broadcast_channel_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏰ Автоудаление этого поста", callback_data="bc_ad_time")],
            [InlineKeyboardButton(text="✅ Да", callback_data="bc_ch_send")],
            [InlineKeyboardButton(text="❌ Нет", callback_data="ap:cancel")],
        ]
    )
