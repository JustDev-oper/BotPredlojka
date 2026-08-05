from aiogram.fsm.state import State, StatesGroup


class AdminPanelStates(StatesGroup):
    waiting_ban_target = State()
    waiting_unban_target = State()
    waiting_mute_target = State()
    waiting_mute_minutes = State()
    waiting_unmute_target = State()
    waiting_user_search = State()
    waiting_broadcast_content = State()
    waiting_new_admin_data = State()
    waiting_del_admin_data = State()
    waiting_fake_stat_value = State()
    waiting_channel_username = State()
    waiting_channel_rename = State()
    waiting_watermark_text = State()
    waiting_broadcast_channel_select = State()
    waiting_broadcast_channel_post = State()
    waiting_auto_delete_time = State()


class UserStates(StatesGroup):
    choosing_channel = State()
    waiting_post_content = State()
