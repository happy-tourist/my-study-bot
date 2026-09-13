"""Schema ensure: create_all + missing-column ALTER for existing SQLite files."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import _ensure_sqlite_user_columns


@pytest.mark.asyncio
async def test_ensure_adds_trial_used_to_legacy_users_table():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(64),
                    subscription_end DATETIME,
                    is_active BOOLEAN,
                    created_at DATETIME
                )
                """
            )
        )
        await conn.execute(
            text(
                "INSERT INTO users (id, username, is_active) VALUES (1, 'legacy', 1)"
            )
        )
        await conn.run_sync(_ensure_sqlite_user_columns)

        cols = {
            row[1]
            for row in (await conn.execute(text("PRAGMA table_info(users)"))).fetchall()
        }
        assert "trial_used" in cols

        trial = (
            await conn.execute(text("SELECT trial_used FROM users WHERE id = 1"))
        ).scalar_one()
        assert trial in (0, False)

        # Second run is idempotent (no duplicate-column error).
        await conn.run_sync(_ensure_sqlite_user_columns)

    await eng.dispose()


@pytest.mark.asyncio
async def test_ensure_noop_when_users_table_missing():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(_ensure_sqlite_user_columns)
        tables = (
            await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            )
        ).fetchall()
        assert tables == []
    await eng.dispose()
