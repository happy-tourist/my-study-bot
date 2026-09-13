"""SC-EXP-01…SC-EXP-06, SC-EXP-T04: минутные окна expiry (без Telegram/APScheduler)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.database import User
from app.scheduler import (
    _EXPIRED_TEXT,
    _reminder_text,
    check_subscriptions,
    classify_subscription_action,
)

# Фиксированная «сейчас» для детерминированных окон UTC-минут
NOW = datetime(2026, 9, 12, 12, 0, 0)

# Temporary harness: minute windows (SC-EXP delta); day unit still available via unit=
MINUTE = "minute"


async def _seed_user(
    session_factory,
    *,
    user_id: int,
    subscription_end: datetime | None,
    is_active: bool = True,
) -> None:
    async with session_factory() as session:
        session.add(
            User(
                id=user_id,
                username=f"u{user_id}",
                subscription_end=subscription_end,
                is_active=is_active,
            )
        )
        await session.commit()


async def _get_user(session_factory, user_id: int) -> User:
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one()


# --- Pure classify (selection) ---


@pytest.mark.parametrize(
    ("minutes", "scenario"),
    [
        (3, "SC-EXP-01"),
        (2, "SC-EXP-02"),
        (1, "SC-EXP-03"),
    ],
)
def test_classify_reminder_windows(minutes: int, scenario: str):
    end = NOW + timedelta(minutes=minutes, seconds=30)
    assert classify_subscription_action(
        is_active=True, subscription_end=end, now=NOW, unit=MINUTE
    ) == f"remind_{minutes}", scenario


def test_classify_no_end_sc_exp_04():
    assert (
        classify_subscription_action(
            is_active=True, subscription_end=None, now=NOW, unit=MINUTE
        )
        is None
    )


def test_classify_expired_sc_exp_05():
    end = NOW - timedelta(seconds=30)
    assert (
        classify_subscription_action(
            is_active=True, subscription_end=end, now=NOW, unit=MINUTE
        )
        == "expire"
    )


# --- check_subscriptions (actions + persistence, mocked Bot) ---


@pytest.mark.parametrize(
    ("minutes", "scenario"),
    [
        (3, "SC-EXP-01"),
        (2, "SC-EXP-02"),
        (1, "SC-EXP-03"),
    ],
)
async def test_reminder_sent_for_window(session_factory, minutes: int, scenario: str):
    user_id = 1000 + minutes
    await _seed_user(
        session_factory,
        user_id=user_id,
        subscription_end=NOW + timedelta(minutes=minutes, seconds=30),
    )
    bot = AsyncMock()
    bot.send_message = AsyncMock()

    await check_subscriptions(
        bot, session_factory=session_factory, now=NOW, unit=MINUTE
    )

    bot.send_message.assert_awaited_once_with(
        user_id, _reminder_text(minutes, unit=MINUTE)
    )
    user = await _get_user(session_factory, user_id)
    assert user.is_active is True, scenario


async def test_no_reminder_without_subscription_end_sc_exp_04(session_factory):
    await _seed_user(session_factory, user_id=2004, subscription_end=None)
    bot = AsyncMock()
    bot.send_message = AsyncMock()

    await check_subscriptions(
        bot, session_factory=session_factory, now=NOW, unit=MINUTE
    )

    bot.send_message.assert_not_awaited()
    user = await _get_user(session_factory, 2004)
    assert user.is_active is True


async def test_expired_deactivated_and_notified_sc_exp_05(session_factory):
    await _seed_user(
        session_factory,
        user_id=2005,
        subscription_end=NOW - timedelta(seconds=30),
    )
    bot = AsyncMock()
    bot.send_message = AsyncMock()

    await check_subscriptions(
        bot, session_factory=session_factory, now=NOW, unit=MINUTE
    )

    bot.send_message.assert_awaited_once_with(2005, _EXPIRED_TEXT)
    user = await _get_user(session_factory, 2005)
    assert user.is_active is False


async def test_failed_delivery_does_not_abort_sc_exp_06(session_factory):
    """Один fail send — остальные обрабатываются; деактивации сохранены."""
    await _seed_user(
        session_factory,
        user_id=3001,
        subscription_end=NOW - timedelta(seconds=30),
    )
    await _seed_user(
        session_factory,
        user_id=3002,
        subscription_end=NOW - timedelta(minutes=1),
    )
    await _seed_user(
        session_factory,
        user_id=3003,
        subscription_end=NOW + timedelta(minutes=2, seconds=30),
    )

    bot = AsyncMock()

    async def send_side_effect(chat_id, text, **_kwargs):
        if chat_id == 3001:
            raise RuntimeError("telegram unavailable")
        return AsyncMock()

    bot.send_message = AsyncMock(side_effect=send_side_effect)

    await check_subscriptions(
        bot, session_factory=session_factory, now=NOW, unit=MINUTE
    )

    # Напоминание N=2 всё равно ушло matching-пользователю
    assert any(
        call.args == (3003, _reminder_text(2, unit=MINUTE))
        for call in bot.send_message.await_args_list
    )
    # Уведомление об истечении второму expired-пользователю тоже ушло
    assert any(
        call.args == (3002, _EXPIRED_TEXT) for call in bot.send_message.await_args_list
    )

    user1 = await _get_user(session_factory, 3001)
    user2 = await _get_user(session_factory, 3002)
    user3 = await _get_user(session_factory, 3003)
    assert user1.is_active is False
    assert user2.is_active is False
    assert user3.is_active is True


def test_production_defaults_sc_exp_t04():
    """SC-EXP-T04: minute windows + minutely cron; no daily 10:00; no 1/5-min grants."""
    import inspect

    from app import keyboards as kb
    from app.scheduler import EXPIRY_WINDOW_UNIT, start_scheduler

    assert EXPIRY_WINDOW_UNIT == "minute"
    src = inspect.getsource(start_scheduler)
    assert 'minute="*"' in src
    assert "hour=10" not in src

    # Temporary one-/five-minute-only grant buttons must not be in tariffs
    assert set(kb.TARIFFS) == {"1_month", "3_months", "forever"}
    assert {t["minutes"] for t in kb.TARIFFS.values()} == {30, 90, 36500}
    assert 1 not in {t["minutes"] for t in kb.TARIFFS.values()}
    assert 5 not in {t["minutes"] for t in kb.TARIFFS.values()}
