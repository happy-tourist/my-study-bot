"""Unit tests for has_active_subscription (SC-GATE allow/deny conditions)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.auth import has_active_subscription
from app.database import User

NOW = datetime(2026, 9, 13, 12, 0, 0)


def _user(
    *,
    is_active: bool = True,
    subscription_end: datetime | None = None,
) -> User:
    return User(
        id=1,
        username="u1",
        is_active=is_active,
        subscription_end=subscription_end,
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
