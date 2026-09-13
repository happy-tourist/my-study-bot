import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import BigInteger, Boolean, DateTime, String, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

load_dotenv()

DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///data/db.sqlite3")

engine = create_async_engine(DB_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# SQLite create_all не добавляет колонки к существующим таблицам — догоняем при старте.
_SQLITE_USER_COLUMN_DDL: dict[str, str] = {
    "trial_used": "ALTER TABLE users ADD COLUMN trial_used BOOLEAN DEFAULT 0 NOT NULL",
    "is_admin": "ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0 NOT NULL",
    "is_banned": "ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT 0 NOT NULL",
}


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram ID
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subscription_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def _ensure_sqlite_user_columns(sync_conn) -> None:
    """Idempotent ALTER for columns missing on an existing `users` table."""
    rows = sync_conn.execute(text("PRAGMA table_info(users)")).fetchall()
    if not rows:
        return
    existing = {row[1] for row in rows}
    for name, ddl in _SQLITE_USER_COLUMN_DDL.items():
        if name not in existing:
            sync_conn.execute(text(ddl))


async def init_db():
    """Создаёт таблицы и догоняет недостающие колонки на существующем SQLite."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_sqlite_user_columns)
