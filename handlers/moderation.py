from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

import database as db
from keyboards import moderation_kb, pick_channel_kb
from utils import load_content, send_content

router = Router(name="moderation")


def _format_caption(user, channel_title: str) -> str:
    username = f"@{user.username}" if user.username else "—"
    name = user.first_name or "—"
    return (
        "\n\n——————————————————\n"
        f"Канал: {channel_title}\n"
        f"Ник: {name}\n"
        f"Юзернейм: {username}\n"
        f"ID: {user.id}"
    )


async def notify_admins_new_post(bot: Bot, post_id: int) -> None:
    post = await db.get_post(post_id)
    if not post:
        return
    channel = await db.get_channel(post["channel_id"])
    data = load_content(post)

    try:
        user_chat = await bot.get_chat(post["user_id"])
        username = user_chat.username
        first_name = user_chat.first_name
    except Exception:
        username = None
        first_name = None

    footer = "\n\n——————————————————\n"
    footer += f"Канал: {channel['title'] if channel else '—'}\n"
    footer += f"Ник: {first_name or '—'}\n"
    footer += f"Юзернейм: {'@' + username if username else '—'}\n"
    footer += f"ID: {post['user_id']}"

    admins = await db.list_admins()
    if not admins:
        return

    # Отправляем первому в списке (обычно так и достаточно — модерация видна всем админам,
    # т.к. каждый из них может открыть /admin, но карточка с кнопками рассылается всем).
    for admin in admins:
        try:
            sent = None
            if post["content_type"] == "text":
                text = data.get("text", "") + footer
                sent = await bot.send_message(admin["user_id"], text, parse_mode="HTML")
            else:
                caption = (data.get("caption") or "") + footer
                sent = await send_content(
                    bot, admin["user_id"], post["content_type"],
                    {**data, "caption": caption},
                )
            await bot.edit_message_reply_markup(
                chat_id=admin["user_id"],
                message_id=sent.message_id,
                reply_markup=moderation_kb(post_id),
            )
            # запоминаем только первое админ-сообщение как основное для дальнейших правок карточки
            existing = await db.get_post(post_id)
            if not existing["admin_chat_id"]:
                await db.set_post_admin_message(post_id, admin["user_id"], sent.message_id)
        except Exception:
            continue


@router.callback_query(F.data.startswith("mod:pub:"))
async def publish_post(call: CallbackQuery, bot: Bot):
    post_id = int(call.data.split(":")[2])
    post = await db.get_post(post_id)
    if not post or post["status"] != "pending":
        await call.answer("Пост уже обработан", show_alert=True)
        return

    channel = await db.get_channel(post["channel_id"])
    if not channel:
        await call.answer("Канал не найден", show_alert=True)
        return

    data = load_content(post)
    water = channel["water_text"]
    if water:
        if post["content_type"] == "text":
            data["text"] = (data.get("text", "") + "\n" + water).strip()
        else:
            data["caption"] = (data.get("caption", "") + "\n" + water).strip()

    sent = await send_content(bot, channel["chat_id"], post["content_type"], data, disable_notification=True)
    await db.mark_post_published(post_id, channel["chat_id"], sent.message_id)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
        await bot.send_message(call.message.chat.id, f"✅ Пост №{post_id} опубликован в «{channel['title']}».")
    except Exception:
        pass

    try:
        await bot.send_message(post["user_id"], "✅ Ваш пост опубликован!")
    except Exception:
        pass

    await call.answer("Опубликовано")


@router.callback_query(F.data.startswith("mod:rej:"))
async def reject_post(call: CallbackQuery, bot: Bot):
    post_id = int(call.data.split(":")[2])
    post = await db.get_post(post_id)
    if not post or post["status"] != "pending":
        await call.answer("Пост уже обработан", show_alert=True)
        return

    await db.mark_post_rejected(post_id)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
        await bot.send_message(call.message.chat.id, f"❌ Пост №{post_id} отклонён.")
    except Exception:
        pass
    try:
        await bot.send_message(post["user_id"], "❌ Ваш пост отклонён модератором.")
    except Exception:
        pass
    await call.answer("Отклонено")


@router.callback_query(F.data.startswith("mod:ban:"))
async def ban_from_post(call: CallbackQuery, bot: Bot):
    post_id = int(call.data.split(":")[2])
    post = await db.get_post(post_id)
    if not post:
        await call.answer("Пост не найден", show_alert=True)
        return

    await db.set_ban(post["user_id"], True)
    if post["status"] == "pending":
        await db.mark_post_rejected(post_id)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
        await bot.send_message(call.message.chat.id, f"🚫 Пользователь {post['user_id']} забанен.")
    except Exception:
        pass
    await call.answer("Пользователь забанен")


@router.callback_query(F.data.startswith("mod:pick:"))
async def pick_channel_start(call: CallbackQuery):
    post_id = int(call.data.split(":")[2])
    channels = await db.list_channels()
    await call.message.edit_reply_markup(reply_markup=pick_channel_kb(post_id, channels))
    await call.answer()


@router.callback_query(F.data.startswith("mod:cancelpick:"))
async def pick_channel_cancel(call: CallbackQuery):
    post_id = int(call.data.split(":")[2])
    await call.message.edit_reply_markup(reply_markup=moderation_kb(post_id))
    await call.answer()


@router.callback_query(F.data.startswith("mod:setch:"))
async def pick_channel_set(call: CallbackQuery):
    _, _, post_id, channel_id = call.data.split(":")
    post_id, channel_id = int(post_id), int(channel_id)
    await db.set_post_channel(post_id, channel_id)
    channel = await db.get_channel(channel_id)
    await call.message.edit_reply_markup(reply_markup=moderation_kb(post_id))
    await call.answer(f"Канал изменён на «{channel['title']}»" if channel else "Канал изменён")


# --- ответ пользователю через цитирование (без отдельного чата) -----------------

@router.message(F.reply_to_message, F.from_user.id)
async def reply_to_user_via_quote(message: Message, bot: Bot):
    # Срабатывает, когда админ отвечает (reply) на карточку модерации бота своим текстом.
    if not await db.is_admin(message.from_user.id):
        return
    if not message.reply_to_message or message.reply_to_message.from_user.id != bot.id:
        return
    if not message.text:
        return

    # Ищем пост, чья карточка была отправлена именно этим сообщением
    reply_id = message.reply_to_message.message_id
    # Простая эвристика: ищем среди последних постов этого админ-чата
    import aiosqlite
    from config import DB_PATH

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM posts WHERE admin_chat_id=? AND admin_message_id=?",
            (message.chat.id, reply_id),
        )
        post = await cur.fetchone()

    if not post:
        return

    try:
        await bot.send_message(
            post["user_id"],
            f"📩 На ваш пост ответил модератор:\n\n{message.text}",
        )
        await message.reply("Ответ отправлен пользователю.")
    except Exception:
        await message.reply("Не удалось отправить ответ пользователю.")
