"""Subscription and admin access checks for gated handlers."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from app.database import User


def parse_admin_ids(raw: str | None = None) -> frozenset[int]:
    """Parse CSV of numeric Telegram ids from ADMIN_IDS (or given string)."""
    value = raw if raw is not None else os.getenv("ADMIN_IDS", "")
    ids: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return frozenset(ids)


def extend_subscription(
    user: User,
    minutes: int,
    *,
    now: datetime | None = None,
) -> None:
    """Stack tariff minutes onto a still-future end (learner and admin grant)."""
    now = now or datetime.utcnow()
    if user.subscription_end is not None and user.subscription_end > now:
        base = user.subscription_end
    else:
        base = now
    user.subscription_end = base + timedelta(minutes=minutes)
    user.is_active = True


def is_admin_user(user: User | None, *, telegram_id: int | None = None) -> bool:
    """True if telegram id is in ADMIN_IDS bootstrap or user.is_admin is set."""
    uid = telegram_id if telegram_id is not None else (user.id if user is not None else None)
    if uid is not None and uid in parse_admin_ids():
        return True
    if user is not None and user.is_admin:
        return True
    return False


def is_banned_user(user: User | None) -> bool:
    """True when the user row exists and is_banned is set."""
    return user is not None and bool(user.is_banned)


def has_active_subscription(user: User | None, *, now: datetime | None = None) -> bool:
    """True when user exists, is_active, and subscription_end is strictly after now."""
    now = now or datetime.utcnow()
    if user is None or not user.is_active:
        return False
    if user.subscription_end is None:
        return False
    return user.subscription_end > now


def can_promote_user(target: User) -> tuple[bool, str | None]:
    """Promote only non-banned users. Returns (ok, Russian refusal or None)."""
    if target.is_banned:
        return False, "Нельзя назначить админом забаненного пользователя."
    if is_admin_user(target, telegram_id=target.id):
        return False, "Пользователь уже администратор."
    return True, None


def can_demote_user(target: User, *, actor_id: int) -> tuple[bool, str | None]:
    """Refuse demote self or bootstrap ADMIN_IDS. Returns (ok, Russian refusal or None)."""
    if target.id == actor_id:
        return False, "Нельзя снять права администратора у себя."
    if target.id in parse_admin_ids():
        return False, "Нельзя снять права у bootstrap-админа."
    if not target.is_admin:
        return False, "Пользователь не является администратором."
    return True, None


def can_ban_user(target: User) -> tuple[bool, str | None]:
    """Refuse ban if target is admin (incl. bootstrap). Returns (ok, Russian refusal or None)."""
    if is_admin_user(target, telegram_id=target.id):
        return False, "Нельзя забанить администратора."
    if target.is_banned:
        return False, "Пользователь уже забанен."
    return True, None


def can_unban_user(target: User) -> tuple[bool, str | None]:
    if not target.is_banned:
        return False, "Пользователь не забанен."
    return True, None
