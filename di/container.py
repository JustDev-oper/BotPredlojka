"""Dependency injection container for the Telegram bot."""

from __future__ import annotations

from aiogram import Dispatcher

from db.database import Database


def setup_di(container: dict) -> None:
    """Register dependencies in the DI container."""
    dp: Dispatcher = container["dp"]
    db: Database = container["db"]

    dp["db"] = db
    # future: bot, config, etc.
