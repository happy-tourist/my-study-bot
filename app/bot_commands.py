"""Telegram Bot Commands builders and per-chat sync helpers."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat

logger = logging.getLogger(__name__)


def learner_bot_commands() -> list[BotCommand]:
    """Default Menu Button list (no admin)."""
    return [
        BotCommand(command="start", description="Запуск и главное меню"),
        BotCommand(command="cars", description="🚗 Машины"),
        BotCommand(command="houses", description="🏠 Дома"),
        BotCommand(command="computers", description="💻 Компьютеры"),
        BotCommand(command="chinese", description="🇨🇳 Курсы китайского"),
        BotCommand(command="subscription", description="💳 Подписка"),
        BotCommand(command="help", description="Справка и список команд"),
    ]


def admin_bot_commands() -> list[BotCommand]:
    """Learner list plus admin panel command."""
    return [
        *learner_bot_commands(),
        BotCommand(command="admin", description="🛠 Админ"),
    ]


async def sync_commands_for_user(
    bot: Bot,
    chat_id: int,
    *,
    is_admin: bool,
) -> None:
    """Set chat-scoped command list for a private chat (admin or learner).

    Soft-fails on Telegram API errors so /start greet and promote/demote
    confirmation still complete after a successful DB commit; next /start
    re-syncs the Menu Button.
    """
    commands = admin_bot_commands() if is_admin else learner_bot_commands()
    try:
        await bot.set_my_commands(
            commands,
            scope=BotCommandScopeChat(chat_id=chat_id),
        )
    except Exception:
        logger.exception(
            "Failed to sync Menu Button commands for chat_id=%s is_admin=%s",
            chat_id,
            is_admin,
        )
