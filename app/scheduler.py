"""Фоновая проверка сроков подписки (напоминания и деактивация)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import and_, select

from app.database import User, async_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

_REMIND_DAYS = (3, 2, 1)


def _reminder_text(days: int) -> str:
    if days == 1:
        return "Ваша подписка истекает через 1 день."
    return f"Ваша подписка истекает через {days} дня."


_EXPIRED_TEXT = "Ваша подписка истекла."


def reminder_window(now: datetime, days: int) -> tuple[datetime, datetime]:
    """UTC-окно [now+N, now+N+1) для напоминания за N дней."""
    return now + timedelta(days=days), now + timedelta(days=days + 1)


def classify_subscription_action(
    *,
    is_active: bool,
    subscription_end: datetime | None,
    now: datetime,
) -> str | None:
    """Чистая классификация: remind_3|remind_2|remind_1|expire|None."""
    if not is_active or subscription_end is None:
        return None
    if subscription_end < now:
        return "expire"
    for days in _REMIND_DAYS:
        window_start, window_end = reminder_window(now, days)
        if window_start <= subscription_end < window_end:
            return f"remind_{days}"
    return None


async def check_subscriptions(
    bot: Bot,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    now: datetime | None = None,
) -> None:
    """Напоминания за 3/2/1 день и деактивация истекших подписок."""
    factory = session_factory or async_session
    check_now = now if now is not None else datetime.utcnow()

    async with factory() as session:
        for days in _REMIND_DAYS:
            window_start, window_end = reminder_window(check_now, days)
            result = await session.execute(
                select(User).where(
                    and_(
                        User.is_active.is_(True),
                        User.subscription_end.is_not(None),
                        User.subscription_end >= window_start,
                        User.subscription_end < window_end,
                    )
                )
            )
            users = result.scalars().all()
            text = _reminder_text(days)
            for user in users:
                try:
                    await bot.send_message(user.id, text)
                except Exception:
                    logger.exception(
                        "Failed to send subscription reminder to user %s", user.id
                    )

        expired_result = await session.execute(
            select(User).where(
                and_(
                    User.is_active.is_(True),
                    User.subscription_end.is_not(None),
                    User.subscription_end < check_now,
                )
            )
        )
        expired_users = expired_result.scalars().all()
        for user in expired_users:
            user.is_active = False
        if expired_users:
            await session.commit()

        for user in expired_users:
            try:
                await bot.send_message(user.id, _EXPIRED_TEXT)
            except Exception:
                logger.exception(
                    "Failed to send subscription expired notice to user %s", user.id
                )


def start_scheduler(bot: Bot) -> None:
    """Регистрирует ежедневный job и запускает планировщик."""
    scheduler.add_job(
        check_subscriptions,
        trigger="cron",
        hour=10,
        minute=0,
        args=[bot],
        id="check_subscriptions",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()


def stop_scheduler() -> None:
    """Останавливает планировщик, если он запущен."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
