from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def moderation_keyboard(post_id: int, user_tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"pub:{post_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"rej:{post_id}"),
            ],
            [
                InlineKeyboardButton(text="🚫 Бан", callback_data=f"block:{user_tg_id}:{post_id}"),
                InlineKeyboardButton(text="📩 ВЫБРАТЬ КАНАЛЫ", callback_data=f"change_ch:{post_id}"),
            ],
        ]
    )


def post_status_keyboard(status: str) -> InlineKeyboardMarkup:
    labels = {
        "published": "✅ ОПУБЛИКОВАНО",
        "rejected": "❌ ОТКЛОНЕНО",
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=labels.get(status, "—"), callback_data="noop")],
        ]
    )


def banlist_keyboard(users: list) -> InlineKeyboardMarkup:
    buttons = []
    for user in users[:20]:
        name = user["full_name"] or str(user["tg_id"])
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🔓 Разбанить: {name[:30]}",
                    callback_data=f"unblock:{user['tg_id']}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text="◀️ Панель", callback_data="ap:open")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить всем", callback_data="bc_send"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="bc_cancel"),
            ],
        ]
    )


def channel_select_keyboard(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        title = ch["channel_title"] or f"@{ch['channel_username']}"
        prefix = "🔒 " if ch["require_subscription"] else "📢 "
        buttons.append([
            InlineKeyboardButton(
                text=f"{prefix}{title}",
                callback_data=f"select_ch:{ch['id']}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def channel_select_keyboard_for_moderation(channels: list, post_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        title = ch["channel_title"] or f"@{ch['channel_username']}"
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {title}",
                callback_data=f"mod_ch:{ch['id']}:{post_id}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def channels_list_keyboard(channels_with_stats: list[dict], *, is_owner: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels_with_stats:
        title = ch["channel_title"] or f"@{ch['channel_username']}"
        count = ch["post_count"]
        suffix = " пост" if count % 10 == 1 and count % 100 != 11 else (
            " поста" if 2 <= count % 10 <= 4 and not (12 <= count % 100 <= 14) else " постов"
        )
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {title} | {count}{suffix}",
                callback_data=f"ch_menu:{ch['id']}",
            )
        ])
    if is_owner:
        buttons.append(
            [InlineKeyboardButton(text="➕ Добавить канал", callback_data="ap:add_channel")]
        )
    buttons.append(
        [InlineKeyboardButton(text="◀️ Назад", callback_data="ap:open")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def channel_detail_keyboard(channel_id: int, *, is_owner: bool = False, require_subscription: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if is_owner:
        sub_text = "✅ Под обязательной подпиской" if require_subscription else "⬜ Подписка не обязательна"
        rows.append([InlineKeyboardButton(text=sub_text, callback_data=f"ch_toggle_sub:{channel_id}")])
        rows.append([InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"ch_rename:{channel_id}")])
        rows.append([InlineKeyboardButton(text="📦 Архивировать", callback_data=f"ch_archive:{channel_id}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад к каналам", callback_data="ap:channels")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscription_check_keyboard(channel_link: str, channel_id: int) -> InlineKeyboardMarkup:
    rows = []
    if channel_link:
        rows.append([InlineKeyboardButton(text="📢 Перейти в канал", url=channel_link)])
    rows.append([InlineKeyboardButton(text="✅ Проверить", callback_data=f"check_sub:{channel_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
