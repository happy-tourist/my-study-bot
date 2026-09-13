"""Unit tests for has_active_subscription and admin/ban helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.auth import (
    has_active_subscription,
    is_admin_user,
    is_banned_user,
    parse_admin_ids,
)
from app.database import User

NOW = datetime(2026, 9, 13, 12, 0, 0)
BOOTSTRAP_ID = 463353358


def _user(
    *,
    user_id: int = 1,
    is_active: bool = True,
    subscription_end: datetime | None = None,
    is_admin: bool = False,
    is_banned: bool = False,
) -> User:
    return User(
        id=user_id,
        username="u1",
        is_active=is_active,
        subscription_end=subscription_end,
        is_admin=is_admin,
        is_banned=is_banned,
    )


def test_allow_active_future_end():
    user = _user(subscription_end=NOW + timedelta(minutes=5))
    assert has_active_subscription(user, now=NOW) is True


def test_deny_none_user():
    assert has_active_subscription(None, now=NOW) is False


def test_deny_inactive():
    user = _user(
        is_active=False,
        subscription_end=NOW + timedelta(minutes=5),
    )
    assert has_active_subscription(user, now=NOW) is False


def test_deny_missing_end():
    user = _user(subscription_end=None)
    assert has_active_subscription(user, now=NOW) is False


def test_deny_expired_end():
    user = _user(subscription_end=NOW - timedelta(seconds=1))
    assert has_active_subscription(user, now=NOW) is False


def test_deny_end_equal_to_now():
    user = _user(subscription_end=NOW)
    assert has_active_subscription(user, now=NOW) is False


def test_parse_admin_ids_csv_and_empty():
    assert parse_admin_ids("463353358, 99") == frozenset({463353358, 99})
    assert parse_admin_ids("") == frozenset()
    assert parse_admin_ids("  ") == frozenset()
    assert parse_admin_ids("463353358,not-a-number,42") == frozenset({463353358, 42})


def test_is_admin_bootstrap_id(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_IDS", str(BOOTSTRAP_ID))
    user = _user(user_id=BOOTSTRAP_ID, is_admin=False)
    assert is_admin_user(user) is True
    # Bootstrap remains admin even when DB flag is cleared.
    assert is_admin_user(None, telegram_id=BOOTSTRAP_ID) is True


def test_is_admin_db_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    user = _user(user_id=1001, is_admin=True)
    assert is_admin_user(user) is True


def test_is_admin_false_for_regular_user(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_IDS", str(BOOTSTRAP_ID))
    user = _user(user_id=1002, is_admin=False)
    assert is_admin_user(user) is False
    assert is_admin_user(None, telegram_id=1002) is False


def test_is_banned_true_and_false():
    assert is_banned_user(_user(is_banned=True)) is True
    assert is_banned_user(_user(is_banned=False)) is False
    assert is_banned_user(None) is False
