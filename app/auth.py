"""Subscription access checks for gated handlers."""

from datetime import datetime

from app.database import User


def has_active_subscription(user: User | None, *, now: datetime | None = None) -> bool:
    """True when user exists, is_active, and subscription_end is strictly after now."""
    now = now or datetime.utcnow()
    if user is None or not user.is_active:
        return False
    if user.subscription_end is None:
        return False
    return user.subscription_end > now
