"""Фоновая проверка сроков подписки (напоминания и деактивация)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import and_, select

from app.database import User, async_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

_REMIND_NS = (3, 2, 1)

# Temporary harness (OpenSpec add-subscription-tariffs-trial D6): minute windows
# + every-minute cron. Restore day + Europe/Moscow 10:00 with ЮKassa later.
ExpiryWindowUnit = Literal["day", "minute"]
EXPIRY_WINDOW_UNIT: ExpiryWindowUnit = "minute"


def _reminder_text(n: int, *, unit: ExpiryWindowUnit | None = None) -> str:
    window_unit = unit or EXPIRY_WINDOW_UNIT
    if window_unit == "minute":
        if n == 1:
            return "Ваша подписка истекает через 1 минуту."
        return f"Ваша подписка истекает через {n} минуты."
    if n == 1:
        return "Ваша подписка истекает через 1 день."
    return f"Ваша подписка истекает через {n} дня."


_EXPIRED_TEXT = "Ваша подписка истекла."


def reminder_window(
    now: datetime,
    n: int,
    *,
    unit: ExpiryWindowUnit | None = None,
) -> tuple[datetime, datetime]:
    """UTC-окно [now+N, now+N+1) для напоминания за N единиц (день или минута)."""
    window_unit = unit or EXPIRY_WINDOW_UNIT
    delta = timedelta(minutes=n) if window_unit == "minute" else timedelta(days=n)
    delta_next = (
        timedelta(minutes=n + 1) if window_unit == "minute" else timedelta(days=n + 1)
    )
    return now + delta, now + delta_next


def classify_subscription_action(
    *,
    is_active: bool,
    subscription_end: datetime | None,
    now: datetime,
    unit: ExpiryWindowUnit | None = None,
) -> str | None:
    """Чистая классификация: remind_3|remind_2|remind_1|expire|None."""
    window_unit = unit or EXPIRY_WINDOW_UNIT
    if not is_active or subscription_end is None:
        return None
    if subscription_end < now:
        return "expire"
    for n in _REMIND_NS:
        window_start, window_end = reminder_window(now, n, unit=window_unit)
        if window_start <= subscription_end < window_end:
            return f"remind_{n}"
    return None


async def check_subscriptions(
    bot: Bot,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    now: datetime | None = None,
    unit: ExpiryWindowUnit | None = None,
) -> None:
    """Напоминания за 3/2/1 единицу окна и деактивация истекших подписок."""
    factory = session_factory or async_session
    check_now = now if now is not None else datetime.utcnow()
    window_unit = unit or EXPIRY_WINDOW_UNIT

    async with factory() as session:
        for n in _REMIND_NS:
            window_start, window_end = reminder_window(check_now, n, unit=window_unit)
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
            text = _reminder_text(n, unit=window_unit)
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
    """Регистрирует minutely job и запускает планировщик (временный harness)."""
    scheduler.add_job(
        check_subscriptions,
        trigger="cron",
        minute="*",
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
