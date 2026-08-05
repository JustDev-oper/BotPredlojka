from aiogram.fsm.state import State, StatesGroup


class PostFlow(StatesGroup):
    waiting_post = State()          # пользователь выбрал канал, ждём контент поста


class AdminReply(StatesGroup):
    waiting_reply = State()         # админ цитирует пост и пишет ответ (обрабатывается через reply, но
                                     # оставлено на случай FSM-варианта)


class ChannelAdd(StatesGroup):
    waiting_forward = State()       # ждём пересланное сообщение из канала, чтобы получить chat_id


class ChannelRename(StatesGroup):
    waiting_new_title = State()


class WaterSetup(StatesGroup):
    waiting_channel = State()
    waiting_text = State()


class BroadcastBot(StatesGroup):
    waiting_message = State()


class BroadcastChannels(StatesGroup):
    choosing_channels = State()
    waiting_autodelete = State()
    waiting_post = State()
    waiting_confirm = State()


class UsersManage(StatesGroup):
    waiting_id_ban = State()
    waiting_id_unban = State()
    waiting_id_mute = State()
    waiting_id_unmute = State()
    waiting_id_addadmin = State()
    waiting_id_deladmin = State()


class FakeStats(StatesGroup):
    waiting_users = State()
    waiting_posts = State()


class RescheduleDelete(StatesGroup):
    waiting_datetime = State()
