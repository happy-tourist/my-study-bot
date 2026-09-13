"""SC-ADM-01…14: admin panel access, stats, search, mutations, pagination."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.keyboards as kb
from app.database import User
from app.handlers_admin import (
    admin_ban,
    admin_demote,
    admin_grant_tariff,
    admin_promote,
    admin_revoke,
    admin_search_query,
    admin_stats,
    admin_unban,
    admin_users_list,
    cmd_admin,
)

NOW = datetime(2026, 9, 13, 12, 0, 0)
BOOTSTRAP_ID = 463353358
ADMIN_ID = 9001
LEARNER_ID = 9100


def _freeze_utcnow(monkeypatch, fixed_now: datetime = NOW) -> None:
    stub = type("dt", (), {"utcnow": staticmethod(lambda: fixed_now)})
    monkeypatch.setattr("app.handlers_admin.datetime", stub)
    monkeypatch.setattr("app.auth.datetime", stub)


def _make_message(*, user_id: int, text: str = "/admin"):
    message = AsyncMock()
    message.text = text
    message.from_user.id = user_id
    message.from_user.username = f"u{user_id}"
    message.from_user.first_name = "Admin"
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


def _make_state() -> AsyncMock:
    state = AsyncMock()
    state.clear = AsyncMock()
    state.set_state = AsyncMock()
    return state


async def _seed_user(
    session: AsyncSession,
    *,
    user_id: int,
    username: str | None = None,
    is_admin: bool = False,
    is_banned: bool = False,
    trial_used: bool = True,
    is_active: bool = False,
    subscription_end: datetime | None = None,
) -> User:
    user = User(
        id=user_id,
        username=username if username is not None else f"u{user_id}",
        is_admin=is_admin,
        is_banned=is_banned,
        trial_used=trial_used,
        is_active=is_active,
        subscription_end=subscription_end,
    )
    session.add(user)
    await session.commit()
    return user


async def test_admin_opens_panel_sc_adm_01(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)

    message = _make_message(user_id=ADMIN_ID)
    state = _make_state()
    await cmd_admin(message, session, state)

    text = message.answer.await_args.args[0]
    assert "Админ-панель" in text
    markup = message.answer.await_args.kwargs["reply_markup"]
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Статистика" in t for t in labels)
    assert any("Пользователи" in t for t in labels)
    state.clear.assert_awaited()


async def test_non_admin_refused_admin_sc_adm_02(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", str(BOOTSTRAP_ID))
    await _seed_user(session, user_id=LEARNER_ID, is_admin=False)

    message = _make_message(user_id=LEARNER_ID)
    state = _make_state()
    await cmd_admin(message, session, state)

    assert message.answer.await_args.args[0] == "Доступ закрыт."
    assert message.answer.await_args.kwargs.get("reply_markup") is None


async def test_admin_stats_sc_adm_03(session: AsyncSession, monkeypatch):
    _freeze_utcnow(monkeypatch)
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True, trial_used=True)
    await _seed_user(
        session,
        user_id=9101,
        trial_used=True,
        is_active=True,
        subscription_end=NOW + timedelta(minutes=5),
    )
    await _seed_user(session, user_id=9102, is_banned=True, trial_used=False)

    callback = _make_callback(user_id=ADMIN_ID, data=kb.ADMIN_STATS)
    await admin_stats(callback, session)

    text = callback.message.edit_text.await_args.args[0]
    assert "Всего пользователей: 3" in text
    assert "Активная подписка: 1" in text
    assert "Использовали пробный период: 2" in text
    assert "Забанено: 1" in text
    callback.answer.assert_awaited_once()


async def test_admin_search_by_id_sc_adm_04(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)
    await _seed_user(session, user_id=9200, username="target_user")

    message = _make_message(user_id=ADMIN_ID, text="9200")
    state = _make_state()
    await admin_search_query(message, session, state)

    text = message.answer.await_args.args[0]
    assert "Карточка пользователя" in text
    assert "ID: 9200" in text
    assert "@target_user" in text
    state.clear.assert_awaited()

    message2 = _make_message(user_id=ADMIN_ID, text="@target_user")
    state2 = _make_state()
    await admin_search_query(message2, session, state2)
    assert "ID: 9200" in message2.answer.await_args.args[0]


async def test_admin_promote_sc_adm_05(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)
    await _seed_user(session, user_id=9300, is_admin=False, is_banned=False)

    callback = _make_callback(user_id=ADMIN_ID, data=f"{kb.ADMIN_PROMOTE_PREFIX}9300")
    await admin_promote(callback, session)

    result = await session.execute(select(User).where(User.id == 9300))
    assert result.scalar_one().is_admin is True
    assert "назначен администратором" in callback.message.edit_text.await_args.args[0]
    callback.answer.assert_awaited()


async def test_admin_demote_sc_adm_06(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", str(BOOTSTRAP_ID))
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)
    await _seed_user(session, user_id=9301, is_admin=True)

    callback = _make_callback(user_id=ADMIN_ID, data=f"{kb.ADMIN_DEMOTE_PREFIX}9301")
    await admin_demote(callback, session)

    result = await session.execute(select(User).where(User.id == 9301))
    assert result.scalar_one().is_admin is False
    assert "Админ-права сняты" in callback.message.edit_text.await_args.args[0]
    callback.answer.assert_awaited()


async def test_admin_ban_non_admin_sc_adm_07(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)
    await _seed_user(session, user_id=9400, is_admin=False, is_banned=False)

    callback = _make_callback(user_id=ADMIN_ID, data=f"{kb.ADMIN_BAN_PREFIX}9400")
    await admin_ban(callback, session)

    result = await session.execute(select(User).where(User.id == 9400))
    assert result.scalar_one().is_banned is True
    assert "забанен" in callback.message.edit_text.await_args.args[0].lower()
    callback.answer.assert_awaited()


async def test_admin_cannot_ban_admin_sc_adm_08(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)
    await _seed_user(session, user_id=9401, is_admin=True)

    callback = _make_callback(user_id=ADMIN_ID, data=f"{kb.ADMIN_BAN_PREFIX}9401")
    await admin_ban(callback, session)

    result = await session.execute(select(User).where(User.id == 9401))
    assert result.scalar_one().is_banned is False
    assert "Нельзя забанить администратора" in callback.answer.await_args.args[0]
    callback.message.edit_text.assert_not_awaited()


async def test_admin_unban_sc_adm_09(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)
    await _seed_user(session, user_id=9402, is_banned=True)

    callback = _make_callback(user_id=ADMIN_ID, data=f"{kb.ADMIN_UNBAN_PREFIX}9402")
    await admin_unban(callback, session)

    result = await session.execute(select(User).where(User.id == 9402))
    assert result.scalar_one().is_banned is False
    assert "разбанен" in callback.message.edit_text.await_args.args[0].lower()
    callback.answer.assert_awaited()


async def test_cannot_promote_banned_sc_adm_10(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)
    await _seed_user(session, user_id=9500, is_admin=False, is_banned=True)

    callback = _make_callback(user_id=ADMIN_ID, data=f"{kb.ADMIN_PROMOTE_PREFIX}9500")
    await admin_promote(callback, session)

    result = await session.execute(select(User).where(User.id == 9500))
    assert result.scalar_one().is_admin is False
    assert "забаненного" in callback.answer.await_args.args[0]
    callback.message.edit_text.assert_not_awaited()


async def test_admin_grant_tariff_sc_adm_11(session: AsyncSession, monkeypatch):
    _freeze_utcnow(monkeypatch)
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)
    await _seed_user(
        session,
        user_id=9600,
        is_active=False,
        subscription_end=NOW - timedelta(minutes=1),
    )

    callback = _make_callback(
        user_id=ADMIN_ID,
        data=f"{kb.ADMIN_GRANT_PREFIX}1_month:9600",
    )
    await admin_grant_tariff(callback, session)

    result = await session.execute(select(User).where(User.id == 9600))
    user = result.scalar_one()
    assert user.is_active is True
    assert user.subscription_end == NOW + timedelta(minutes=30)
    assert "Тариф выдан" in callback.message.edit_text.await_args.args[0]
    callback.answer.assert_awaited()


async def test_admin_revoke_sc_adm_12(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)
    await _seed_user(
        session,
        user_id=9601,
        is_active=True,
        subscription_end=NOW + timedelta(minutes=30),
    )

    callback = _make_callback(user_id=ADMIN_ID, data=f"{kb.ADMIN_REVOKE_PREFIX}9601")
    await admin_revoke(callback, session)

    result = await session.execute(select(User).where(User.id == 9601))
    user = result.scalar_one()
    assert user.is_active is False
    assert user.subscription_end is None
    assert "Подписка снята" in callback.message.edit_text.await_args.args[0]
    callback.answer.assert_awaited()


async def test_admin_users_list_pagination_sc_adm_13(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)
    for uid in range(9700, 9700 + kb.ADMIN_PAGE_SIZE + 1):
        await _seed_user(session, user_id=uid)

    callback0 = _make_callback(user_id=ADMIN_ID, data=f"{kb.ADMIN_USERS_PREFIX}0")
    await admin_users_list(callback0, session)
    text0 = callback0.message.edit_text.await_args.args[0]
    assert "Страница 1" in text0
    markup0 = callback0.message.edit_text.await_args.kwargs["reply_markup"]
    next_datas = [
        btn.callback_data
        for row in markup0.inline_keyboard
        for btn in row
        if btn.callback_data == f"{kb.ADMIN_USERS_PREFIX}1"
    ]
    assert next_datas, "expected next-page control on page 0"
    callback0.answer.assert_awaited_once()

    callback1 = _make_callback(user_id=ADMIN_ID, data=f"{kb.ADMIN_USERS_PREFIX}1")
    await admin_users_list(callback1, session)
    text1 = callback1.message.edit_text.await_args.args[0]
    assert "Страница 2" in text1
    callback1.answer.assert_awaited_once()


async def test_cannot_demote_self_or_bootstrap_sc_adm_14(
    session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("ADMIN_IDS", str(BOOTSTRAP_ID))
    await _seed_user(session, user_id=ADMIN_ID, is_admin=True)
    await _seed_user(session, user_id=BOOTSTRAP_ID, is_admin=True)

    self_cb = _make_callback(user_id=ADMIN_ID, data=f"{kb.ADMIN_DEMOTE_PREFIX}{ADMIN_ID}")
    await admin_demote(self_cb, session)
    result = await session.execute(select(User).where(User.id == ADMIN_ID))
    assert result.scalar_one().is_admin is True
    assert "у себя" in self_cb.answer.await_args.args[0]

    boot_cb = _make_callback(
        user_id=ADMIN_ID, data=f"{kb.ADMIN_DEMOTE_PREFIX}{BOOTSTRAP_ID}"
    )
    await admin_demote(boot_cb, session)
    result = await session.execute(select(User).where(User.id == BOOTSTRAP_ID))
    assert result.scalar_one().is_admin is True
    assert "bootstrap" in boot_cb.answer.await_args.args[0].lower()
