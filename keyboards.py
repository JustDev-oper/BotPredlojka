from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import AUTODELETE_LABELS


# --- user side ---------------------------------------------------------------

def channels_list_kb(channels, prefix="ch") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=ch["title"], callback_data=f"{prefix}:{ch['channel_id']}")
    b.adjust(1)
    return b.as_markup()


def check_sub_kb(channel_id: int, invite_link: str | None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if invite_link:
        b.button(text="Перейти на канал", url=invite_link)
    b.button(text="Проверить ✅", callback_data=f"checksub:{channel_id}")
    b.adjust(1)
    return b.as_markup()


# --- admin panel ---------------------------------------------------------------

def admin_panel_kb(is_owner: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 Статистика", callback_data="adm:stats")
    b.button(text="📈 Фейк-статистика", callback_data="adm:fakestats")
    b.button(text="🚫 Бан-лист", callback_data="adm:banlist")
    b.button(text="👥 Пользователи", callback_data="adm:users")
    b.button(text="📢 Рассылка (бот)", callback_data="adm:bcastbot")
    b.button(text="📋 Каналы", callback_data="adm:channels")
    b.button(text="💧 Водянка", callback_data="adm:water")
    b.button(text="📩 Заявки", callback_data="adm:apps")
    b.button(text="⏰ Автоудаление", callback_data="adm:autodel")
    if is_owner:
        b.button(text="👥 Администраторы", callback_data="adm:admins")
        b.button(text="📢 Рассылка по каналам", callback_data="adm:bcastchannels")
    b.adjust(2)
    return b.as_markup()


def back_to_panel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Назад в меню", callback_data="adm:menu")
    return b.as_markup()


# --- moderation ---------------------------------------------------------------

def moderation_kb(post_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Опубликовать", callback_data=f"mod:pub:{post_id}")
    b.button(text="❌ Отклонить", callback_data=f"mod:rej:{post_id}")
    b.button(text="🚫 Бан", callback_data=f"mod:ban:{post_id}")
    b.button(text="📩 ВЫБРАТЬ КАНАЛЫ", callback_data=f"mod:pick:{post_id}")
    b.adjust(2, 1, 1)
    return b.as_markup()


def pick_channel_kb(post_id: int, channels) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=ch["title"], callback_data=f"mod:setch:{post_id}:{ch['channel_id']}")
    b.button(text="◀️ Отмена", callback_data=f"mod:cancelpick:{post_id}")
    b.adjust(1)
    return b.as_markup()


# --- users management -----------------------------------------------------------

def users_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Забанить", callback_data="users:ban")
    b.button(text="Разбанить", callback_data="users:unban")
    b.button(text="Мут", callback_data="users:mute")
    b.button(text="Размут", callback_data="users:unmute")
    b.button(text="+Админ", callback_data="users:addadmin")
    b.button(text="-Админ", callback_data="users:deladmin")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu"))
    return b.as_markup()


# --- channels management -------------------------------------------------------

def channels_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить канал", callback_data="chan:add")
    b.button(text="✏️ Переименовать", callback_data="chan:rename")
    b.button(text="🗄 Архивировать/восстановить", callback_data="chan:archive")
    b.button(text="◀️ Назад", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def channels_pick_kb(channels, prefix: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        label = ch["title"] + (" [архив]" if ch["archived"] else "")
        b.button(text=label, callback_data=f"{prefix}:{ch['channel_id']}")
    b.button(text="◀️ Отмена", callback_data="adm:channels")
    b.adjust(1)
    return b.as_markup()


# --- water -----------------------------------------------------------------------

def water_channels_kb(channels) -> InlineKeyboardMarkup:
    return channels_pick_kb(channels, "water:pick")


# --- applications ------------------------------------------------------------------

def applications_kb(channels, counts: dict, selected: set) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        cnt = counts.get(ch["channel_id"], 0)
        mark = "✅ " if ch["channel_id"] in selected else ""
        b.button(text=f"{mark}📢 {ch['title']} ({cnt})", callback_data=f"apps:toggle:{ch['channel_id']}")
    b.adjust(1)
    b.row(
        InlineKeyboardButton(text="Принять заявки", callback_data="apps:accept"),
        InlineKeyboardButton(text="Принять во всех", callback_data="apps:acceptall"),
    )
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="adm:menu"))
    return b.as_markup()


# --- broadcast by channels ---------------------------------------------------------

def bcast_channels_kb(channels, selected: set) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        mark = "✅ " if ch["channel_id"] in selected else ""
        b.button(text=f"{mark}{ch['title']}", callback_data=f"bc:toggle:{ch['channel_id']}")
    b.adjust(1)
    b.row(
        InlineKeyboardButton(text="Выбрать все", callback_data="bc:all"),
        InlineKeyboardButton(text="Отмена", callback_data="adm:menu"),
    )
    b.row(InlineKeyboardButton(text="Подтвердить", callback_data="bc:confirm"))
    return b.as_markup()


def autodelete_choice_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in AUTODELETE_LABELS.items():
        b.button(text=label, callback_data=f"bc:ad:{key}")
    b.adjust(2)
    return b.as_markup()


def confirm_kb(prefix: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Да", callback_data=f"{prefix}:yes")
    b.button(text="Нет", callback_data=f"{prefix}:no")
    b.adjust(2)
    return b.as_markup()


# --- autodelete admin list -----------------------------------------------------------

def autodel_item_kb(sched_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Удалить прямо сейчас", callback_data=f"ad:now:{sched_id}")
    b.button(text="Отменить автоудаление", callback_data=f"ad:cancel:{sched_id}")
    b.button(text="Изменить дату/время", callback_data=f"ad:reschedule:{sched_id}")
    b.adjust(1)
    return b.as_markup()


def autodel_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Список постов", callback_data="ad:list")
    b.button(text="Удалить все посты", callback_data="ad:deleteall")
    b.button(text="◀️ Назад", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


# --- fake stats -----------------------------------------------------------------------

def fake_stats_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Пользователи", callback_data="fs:users")
    b.button(text="Посты", callback_data="fs:posts")
    b.button(text="Показать итог", callback_data="fs:show")
    b.button(text="◀️ Назад", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


# --- admins management -----------------------------------------------------------------

def admins_menu_kb(admins) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in admins:
        if a["is_owner"]:
            continue
        b.button(text=f"➖ Удалить {a['user_id']}", callback_data=f"admmg:del:{a['user_id']}")
    b.button(text="➕ Добавить модератора", callback_data="admmg:add")
    b.button(text="◀️ Назад", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def banlist_kb(banned) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for u in banned:
        label = f"Разбанить {u['username'] or u['user_id']}"
        b.button(text=label, callback_data=f"ban:unban:{u['user_id']}")
    b.button(text="◀️ Назад", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()
