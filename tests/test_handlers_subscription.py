"""SC-START-01…03, SC-TAR-01…05, SC-GATE-01…04, SC-MENU-01…04: trial, tariffs, gate."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.keyboards as kb
from app.database import User
from app.handlers import (
    TRIAL_MINUTES,
    _SUBSCRIPTION_REQUIRED_TEXT,
    claim_trial,
    cmd_start,
    menu_back,
    menu_cars,
    menu_houses,
    menu_subscription,
    tariff_grant,
)

NOW = datetime(2026, 9, 13, 12, 0, 0)


def _freeze_utcnow(monkeypatch, fixed_now: datetime = NOW) -> None:
    """Pin naive UTC clock in handlers and auth (gate uses wall-clock otherwise)."""
    stub = type("dt", (), {"utcnow": staticmethod(lambda: fixed_now)})
    monkeypatch.setattr("app.handlers.datetime", stub)
    monkeypatch.setattr("app.auth.datetime", stub)


def _make_message(*, user_id: int, username: str = "learner", first_name: str = "Ann"):
    message = AsyncMock()
    message.from_user.id = user_id
    message.from_user.username = username
    message.from_user.first_name = first_name
    message.answer = AsyncMock()
    return message


def _make_callback(*, user_id: int, data: str):
    callback = AsyncMock()
    callback.from_user.id = user_id
    callback.data = data
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


async def _seed_user(
    session: AsyncSession,
    *,
    user_id: int,
    trial_used: bool = False,
    is_active: bool = False,
    subscription_end: datetime | None = None,
) -> User:
    user = User(
        id=user_id,
        username=f"u{user_id}",
        trial_used=trial_used,
        is_active=is_active,
        subscription_end=subscription_end,
    )
    session.add(user)
    await session.commit()
    return user


async def _count_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(User))
    return int(result.scalar_one())


# --- /start trial (SC-START-01…03) ---


async def test_start_first_visit_grants_trial_sc_start_01(session: AsyncSession, monkeypatch):
    _freeze_utcnow(monkeypatch)

    message = _make_message(user_id=101)
    await cmd_start(message, session)

    result = await session.execute(select(User).where(User.id == 101))
    user = result.scalar_one()
    assert user.trial_used is True
    assert user.is_active is True
    assert user.subscription_end == NOW + timedelta(minutes=TRIAL_MINUTES)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "Привет! Я тебя запомнил" in text
    assert "3 дня (3 мин)" in text
    assert "Выбери раздел:" in text
    assert message.answer.await_args.kwargs["reply_markup"] is not None


async def test_start_returning_no_new_trial_sc_start_02(session: AsyncSession):
    old_end = NOW + timedelta(minutes=1)
    await _seed_user(
        session,
        user_id=102,
        trial_used=True,
        is_active=True,
        subscription_end=old_end,
    )

    message = _make_message(user_id=102, first_name="Bob")
    await cmd_start(message, session)

    assert await _count_users(session) == 1
    result = await session.execute(select(User).where(User.id == 102))
    user = result.scalar_one()
    assert user.trial_used is True
    assert user.subscription_end == old_end

    text = message.answer.await_args.args[0]
    assert "С возвращением, Bob!" in text
    assert "3 дня (3 мин)" not in text
    assert "Выбери раздел:" in text


async def test_start_after_trial_expiry_no_reactivate_sc_start_03(session: AsyncSession):
    expired_end = NOW - timedelta(minutes=10)
    await _seed_user(
        session,
        user_id=103,
        trial_used=True,
        is_active=False,
        subscription_end=expired_end,
    )

    message = _make_message(user_id=103, first_name="Cat")
    await cmd_start(message, session)

    assert await _count_users(session) == 1
    result = await session.execute(select(User).where(User.id == 103))
    user = result.scalar_one()
    assert user.trial_used is True
    assert user.is_active is False
    assert user.subscription_end == expired_end
    assert "3 дня (3 мин)" not in message.answer.await_args.args[0]


# --- Tariff grant (SC-TAR-01…05) ---


async def test_tariffs_list_shows_three_plans_sc_tar_01(session: AsyncSession):
    await _seed_user(session, user_id=200, trial_used=True)

    callback = _make_callback(user_id=200, data=kb.MENU_SUBSCRIPTION)
    await menu_subscription(callback, session)

    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("1 месяц (30 мин)" in t for t in labels)
    assert any("3 месяца (90 мин)" in t for t in labels)
    assert any("Навсегда (36500 мин)" in t for t in labels)
    assert any("Назад в меню" in t for t in labels)
    assert not any("пробный период" in t.lower() for t in labels)
    callback.answer.assert_awaited_once()


async def test_subscription_shows_claim_trial_when_unused(session: AsyncSession):
    await _seed_user(session, user_id=210, trial_used=False)

    callback = _make_callback(user_id=210, data=kb.MENU_SUBSCRIPTION)
    await menu_subscription(callback, session)

    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Получить пробный период" in t for t in labels)


async def test_claim_trial_grants_once_for_legacy_user(session: AsyncSession, monkeypatch):
    _freeze_utcnow(monkeypatch)
    await _seed_user(
        session,
        user_id=211,
        trial_used=False,
        is_active=False,
        subscription_end=None,
    )

    callback = _make_callback(user_id=211, data=kb.CLAIM_TRIAL)
    await claim_trial(callback, session)

    result = await session.execute(select(User).where(User.id == 211))
    user = result.scalar_one()
    assert user.trial_used is True
    assert user.is_active is True
    assert user.subscription_end == NOW + timedelta(minutes=TRIAL_MINUTES)

    text = callback.message.edit_text.await_args.args[0]
    assert "3 дня (3 мин)" in text

    callback2 = _make_callback(user_id=211, data=kb.CLAIM_TRIAL)
    await claim_trial(callback2, session)
    callback2.answer.assert_awaited_once()
    assert "уже использован" in callback2.answer.await_args.args[0]
    assert user.subscription_end == NOW + timedelta(minutes=TRIAL_MINUTES)


@pytest.mark.parametrize(
    ("tariff_id", "minutes", "scenario"),
    [
        ("1_month", 30, "SC-TAR-02"),
        ("3_months", 90, "SC-TAR-03"),
        ("forever", 36500, "SC-TAR-04"),
    ],
)
async def test_tariff_grant_minutes(
    session: AsyncSession,
    monkeypatch,
    tariff_id: str,
    minutes: int,
    scenario: str,
):
    _freeze_utcnow(monkeypatch)
    user_id = 201 + minutes % 1000
    await _seed_user(
        session,
        user_id=user_id,
        trial_used=True,
        is_active=False,
        subscription_end=NOW - timedelta(minutes=5),
    )

    callback = _make_callback(user_id=user_id, data=f"{kb.TARIFF_PREFIX}{tariff_id}")
    await tariff_grant(callback, session)

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    assert user.is_active is True, scenario
    assert user.subscription_end == NOW + timedelta(minutes=minutes), scenario

    text = callback.message.edit_text.await_args.args[0]
    assert "Подписка активирована" in text
    assert kb.TARIFFS[tariff_id]["title"] in text
    callback.answer.assert_awaited_once()


async def test_tariff_stacks_onto_future_end_sc_tar_05(session: AsyncSession, monkeypatch):
    _freeze_utcnow(monkeypatch)
    future_end = NOW + timedelta(minutes=10)
    await _seed_user(
        session,
        user_id=205,
        trial_used=True,
        is_active=True,
        subscription_end=future_end,
    )

    callback = _make_callback(user_id=205, data=f"{kb.TARIFF_PREFIX}1_month")
    await tariff_grant(callback, session)

    result = await session.execute(select(User).where(User.id == 205))
    user = result.scalar_one()
    assert user.is_active is True
    assert user.subscription_end == future_end + timedelta(minutes=30)
    assert "Подписка активирована" in callback.message.edit_text.await_args.args[0]
    callback.answer.assert_awaited_once()


# --- Gate + menu (SC-GATE-01…04, SC-MENU-01…04) ---


async def test_active_subscriber_opens_cars_sc_gate_01(session: AsyncSession, monkeypatch):
    _freeze_utcnow(monkeypatch)
    await _seed_user(
        session,
        user_id=301,
        trial_used=True,
        is_active=True,
        subscription_end=NOW + timedelta(minutes=5),
    )

    callback = _make_callback(user_id=301, data=kb.MENU_CARS)
    await menu_cars(callback, session)

    text = callback.message.edit_text.await_args.args[0]
    assert "Машины" in text
    assert _SUBSCRIPTION_REQUIRED_TEXT not in text
    assert callback.message.edit_text.await_args.kwargs["reply_markup"] is not None
    callback.answer.assert_awaited_once()


async def test_active_subscriber_opens_houses_sc_gate_02(session: AsyncSession, monkeypatch):
    _freeze_utcnow(monkeypatch)
    await _seed_user(
        session,
        user_id=302,
        trial_used=True,
        is_active=True,
        subscription_end=NOW + timedelta(minutes=5),
    )

    callback = _make_callback(user_id=302, data=kb.MENU_HOUSES)
    await menu_houses(callback, session)

    text = callback.message.edit_text.await_args.args[0]
    assert "Дома" in text
    assert _SUBSCRIPTION_REQUIRED_TEXT not in text
    assert callback.message.edit_text.await_args.kwargs["reply_markup"] is not None
    callback.answer.assert_awaited_once()


async def test_inactive_refused_cars_sc_gate_03(session: AsyncSession, monkeypatch):
    _freeze_utcnow(monkeypatch)
    await _seed_user(
        session,
        user_id=303,
        trial_used=True,
        is_active=False,
        subscription_end=NOW - timedelta(minutes=1),
    )

    callback = _make_callback(user_id=303, data=kb.MENU_CARS)
    await menu_cars(callback, session)

    text = callback.message.edit_text.await_args.args[0]
    assert text == _SUBSCRIPTION_REQUIRED_TEXT
    assert "Раздел «Машины»" not in text
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Подписка" in t for t in labels)
    callback.answer.assert_awaited_once()


async def test_subscription_open_without_gate_sc_menu_03(session: AsyncSession):
    await _seed_user(
        session,
        user_id=304,
        trial_used=True,
        is_active=False,
        subscription_end=None,
    )

    callback = _make_callback(user_id=304, data=kb.MENU_SUBSCRIPTION)
    await menu_subscription(callback, session)

    text = callback.message.edit_text.await_args.args[0]
    assert "тариф" in text.lower()
    assert _SUBSCRIPTION_REQUIRED_TEXT not in text
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert markup is not None
    callback.answer.assert_awaited_once()


async def test_back_to_main_menu_sc_menu_04(session: AsyncSession):
    callback = _make_callback(user_id=305, data=kb.MENU_BACK)
    await menu_back(callback)

    text = callback.message.edit_text.await_args.args[0]
    assert text == "Выбери раздел:"
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Машины" in t for t in labels)
    assert any("Дома" in t for t in labels)
    assert any("Подписка" in t for t in labels)
    callback.answer.assert_awaited_once()
