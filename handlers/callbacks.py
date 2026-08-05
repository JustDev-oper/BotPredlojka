"""
Callback handlers for the bot.
"""

from telegram import Update
from telegram.ext import ContextTypes

from handlers.admin_handlers import (
    admin_real_stats,
    admin_fake_stats,
    admin_banlist,
    admin_users,
    admin_channels,
    admin_watermark,
    admin_applications,
    admin_admins,
    admin_broadcast_bot,
    admin_auto_delete,
    admin_broadcast_channels,
    admin_back,
    show_channel_selection,
)
from handlers.user_handlers import (
    channel_selected,
    verify_subscription,
)
from handlers.moderation_handlers import (
    handle_approve_post,
    handle_reject_post,
    handle_ban_user,
    handle_select_channels,
)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback handler."""
    query = update.callback_query
    data = query.data

    # Admin panel callbacks
    if data == "admin_real_stats":
        await admin_real_stats(update, context)
    elif data == "admin_fake_stats":
        await admin_fake_stats(update, context)
    elif data == "admin_banlist":
        await admin_banlist(update, context)
    elif data == "admin_users":
        await admin_users(update, context)
    elif data == "admin_channels":
        await admin_channels(update, context)
    elif data == "admin_watermark":
        await admin_watermark(update, context)
    elif data == "admin_applications":
        await admin_applications(update, context)
    elif data == "admin_admins":
        await admin_admins(update, context)
    elif data == "admin_broadcast_bot":
        await admin_broadcast_bot(update, context)
    elif data == "admin_auto_delete":
        await admin_auto_delete(update, context)
    elif data == "admin_broadcast_channels":
        await admin_broadcast_channels(update, context)
    elif data == "admin_back":
        await admin_back(update, context)

    # User callbacks
    elif data.startswith("select_channel_"):
        await channel_selected(update, context)
    elif data.startswith("verify_sub_"):
        await verify_subscription(update, context)

    # Moderation callbacks
    elif data.startswith("approve_post_"):
        await handle_approve_post(update, context)
    elif data.startswith("reject_post_"):
        await handle_reject_post(update, context)
    elif data.startswith("ban_user_"):
        await handle_ban_user(update, context)
    elif data.startswith("select_channels_"):
        await handle_select_channels(update, context)

    # Broadcast channel selection
    elif data.startswith("toggle_channel_"):
        channel_id = int(data.split("_")[2])
        if "broadcast_channels" not in context.user_data:
            return

        context.user_data["broadcast_channels"][channel_id] = (
            not context.user_data["broadcast_channels"].get(channel_id, False)
        )

        await show_channel_selection(query, context.user_data["broadcast_channels"])

    elif data == "broadcast_select_all":
        if "broadcast_channels" in context.user_data:
            for channel_id in context.user_data["broadcast_channels"]:
                context.user_data["broadcast_channels"][channel_id] = True

        await show_channel_selection(query, context.user_data["broadcast_channels"])

    elif data == "broadcast_cancel":
        await query.answer()
        await admin_back(update, context)

    elif data == "broadcast_next":
        await query.answer()
        selected = sum(1 for v in context.user_data.get("broadcast_channels", {}).values() if v)

        if selected == 0:
            await query.answer("❌ Выберите хотя бы один канал", show_alert=True)
            return

        await query.edit_message_text(
            f"✅ Выбрано каналов: {selected}\n\n"
            f"Отправьте пост для рассылки:"
        )

        context.user_data["in_broadcast_to_channels"] = True

