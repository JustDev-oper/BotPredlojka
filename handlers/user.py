from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from config import ANTISPAM_POST_LIMIT, ANTISPAM_WINDOW_SECONDS
from keyboards import channels_list_kb, check_sub_kb
from states import PostFlow
from utils import extract_content, is_subscribed, send_content

router = Router(name="user")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    if await db.is_banned(message.from_user.id):
        await message.answer("Вы заблокированы и не можете пользоваться ботом.")
        return

    channels = await db.list_channels()
    if not channels:
        await message.answer("Пока нет доступных каналов.")
        return

    await message.answer("Выберите канал для публикации поста:", reply_markup=channels_list_kb(channels))


@router.callback_query(F.data.startswith("ch:"))
async def choose_channel(call: CallbackQuery, bot: Bot, state: FSMContext):
    channel_id = int(call.data.split(":")[1])
    channel = await db.get_channel(channel_id)
    if not channel or channel["archived"]:
        await call.answer("Канал недоступен", show_alert=True)
        return

    if await db.is_banned(call.from_user.id):
        await call.answer("Вы заблокированы.", show_alert=True)
        return

    subscribed = await is_subscribed(bot, channel["chat_id"], call.from_user.id)

    if not subscribed:
        # Пользователь ещё не подписан -> создаём заявку, показываем ссылку и кнопку проверки.
        # Важно: заявка уже позволяет отправлять посты, не дожидаясь принятия.
        await db.create_application(call.from_user.id, channel_id)
        await call.message.edit_text(
            f"Для отправки поста в «{channel['title']}» подпишитесь на канал.",
            reply_markup=check_sub_kb(channel_id, channel["invite_link"]),
        )
        await call.answer()
        return

    await state.update_data(channel_id=channel_id)
    await state.set_state(PostFlow.waiting_post)
    await call.message.edit_text(
        f"Канал: «{channel['title']}»\nПришлите пост (текст, фото, видео или документ)."
    )
    await call.answer()


@router.callback_query(F.data.startswith("checksub:"))
async def check_sub(call: CallbackQuery, bot: Bot, state: FSMContext):
    channel_id = int(call.data.split(":")[1])
    channel = await db.get_channel(channel_id)
    if not channel:
        await call.answer("Канал не найден", show_alert=True)
        return

    subscribed = await is_subscribed(bot, channel["chat_id"], call.from_user.id)
    if not subscribed:
        await call.answer("Вы всё ещё не подписаны на канал.", show_alert=True)
        return

    await state.update_data(channel_id=channel_id)
    await state.set_state(PostFlow.waiting_post)
    await call.message.edit_text(
        f"Канал: «{channel['title']}»\nПришлите пост (текст, фото, видео или документ)."
    )
    await call.answer()


@router.message(PostFlow.waiting_post)
async def receive_post(message: Message, bot: Bot, state: FSMContext):
    if await db.is_banned(message.from_user.id):
        await message.answer("Вы заблокированы.")
        await state.clear()
        return
    if await db.is_muted(message.from_user.id):
        await message.answer("Вам временно запрещено отправлять посты.")
        return

    data = await state.get_data()
    channel_id = data.get("channel_id")
    channel = await db.get_channel(channel_id) if channel_id else None
    if not channel:
        await message.answer("Сначала выберите канал: /start")
        await state.clear()
        return

    # --- антиспам: 2 поста -> таймер 1 час -------------------------------------
    recent = await db.recent_post_count(message.from_user.id, ANTISPAM_WINDOW_SECONDS)
    if recent >= ANTISPAM_POST_LIMIT:
        await message.answer(
            "⛔️ Вы превысили лимит постов (2 в час). Попробуйте позже."
        )
        return

    content_type, content_data = extract_content(message)
    post_id = await db.create_post(message.from_user.id, channel_id, content_type, content_data)
    await db.register_post_sent(message.from_user.id)

    await message.answer("Ваш пост отправлен на модерацию.")
    await state.clear()

    # уведомляем всех админов/модераторов
    from handlers.moderation import notify_admins_new_post  # local import avoids circular import

    await notify_admins_new_post(bot, post_id)
