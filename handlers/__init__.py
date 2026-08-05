from aiogram import Router

from . import admin_panel, callbacks, join_requests, posts, replies, start


def get_routers() -> list[Router]:
    return [
        start.router,
        admin_panel.router,
        callbacks.router,
        replies.router,
        posts.router,
        join_requests.router,
    ]
