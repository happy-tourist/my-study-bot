"""SC-CMD-01…10, SC-HELP-01…03, SC-ADM-CMD-01/02: Menu Button builders, slash, /help, /start sync."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from aiogram.types import BotCommandScopeChat
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot_commands import (
    admin_bot_commands,
    learner_bot_commands,
    sync_commands_for_user,
)
from app.database import User
from app.handlers import (
    _SUBSCRIPTION_REQUIRED_TEXT,
    cmd_cars,
    cmd_chinese,
    cmd_computers,
    cmd_help,
    cmd_houses,
    cmd_start,
    cmd_subscription,
)

NOW = datetime(2026, 9, 13, 12, 0, 0)
BOOTSTRAP_ID = 463353358

LEARNER_COMMANDS = (
    "start",
    "cars",
    "houses",
    "computers",
    "chinese",
    "subscription",
    "help",
)
SECTION_DESCRIPTIONS = {
    "cars": "🚗 Машины",
    "houses": "🏠 Дома",
    "computers": "💻 Компьютеры",
    "chinese": "🇨🇳 Курсы китайского",
    "subscription": "💳 Подписка",
}


def _freeze_utcnow(monkeypatch, fixed_now: datetime = NOW) -> None:
    stub = type("dt", (), {"utcnow": staticmethod(lambda: fixed_now)})
    monkeypatch.setattr("app.handlers.datetime", stub)
    monkeypatch.setattr("app.auth.datetime", stub)


def _make_message(*, user_id: int, username: str = "learner", first_name: str = "Ann"):
    message = AsyncMock()
    message.from_user.id = user_id
    message.from_user.username = username
    message.from_user.first_name = first_name
    message.answer = AsyncMock()
    message.bot = AsyncMock()
    message.bot.set_my_commands = AsyncMock()
    return message


async def _seed_user(
    session: AsyncSession,
    *,
    user_id: int,
    trial_used: bool = True,
    is_active: bool = False,
    subscription_end: datetime | None = None,
    is_admin: bool = False,
    is_banned: bool = False,
) -> User:
    user = User(
        id=user_id,
        username=f"u{user_id}",
        trial_used=trial_used,
        is_active=is_active,
        subscription_end=subscription_end,
        is_admin=is_admin,
        is_banned=is_banned,
    )
    session.add(user)
    await session.commit()
    return user


def _command_names(commands) -> list[str]:
    return [c.command for c in commands]


def _command_map(commands) -> dict[str, str]:
    return {c.command: c.description for c in commands}


def _assert_learner_descriptions(commands) -> None:
    by_name = _command_map(commands)
    for name, description in SECTION_DESCRIPTIONS.items():
        assert by_name[name] == description
    assert by_name["start"] == "Запуск и главное меню"
    assert by_name["help"] == "Справка и список команд"
    assert "🚗" not in by_name["start"]
    assert "🏠" not in by_name["help"]


# --- Builders (SC-CMD-01, SC-ADM-CMD-01/02) ---


def test_learner_bot_commands_sc_cmd_01():
    commands = learner_bot_commands()
    names = _command_names(commands)
    assert names == list(LEARNER_COMMANDS)
    assert "admin" not in names
    _assert_learner_descriptions(commands)


def test_admin_bot_commands_sc_adm_cmd_01():
    commands = admin_bot_commands()
    names = _command_names(commands)
    assert names[: len(LEARNER_COMMANDS)] == list(LEARNER_COMMANDS)
    assert names[-1] == "admin"
    assert _command_map(commands)["admin"] == "🛠 Админ"
    _assert_learner_descriptions(commands)


def test_learner_omits_admin_sc_adm_cmd_02():
    assert "admin" not in _command_names(learner_bot_commands())


async def test_sync_commands_soft_fails_on_api_error():
    """API error must not raise — callers still greet / confirm after commit."""
    bot = AsyncMock()
    bot.set_my_commands = AsyncMock(side_effect=RuntimeError("telegram down"))
    await sync_commands_for_user(bot, chat_id=42, is_admin=False)
    bot.set_my_commands.assert_awaited_once()


# --- Slash section commands (SC-CMD-02…08) ---


async def test_cmd_cars_active_subscriber_sc_cmd_02(session: AsyncSession, monkeypatch):
    _freeze_utcnow(monkeypatch)
    await _seed_user(
        session,
        user_id=501,
        is_active=True,
        subscription_end=NOW + timedelta(minutes=5),
    )

    message = _make_message(user_id=501)
    await cmd_cars(message, session)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert text == "Раздел «Машины»\nЗдесь будет контент."
    assert message.answer.await_args.kwargs["reply_markup"] is not None
    labels = [
        btn.text
        for row in message.answer.await_args.kwargs["reply_markup"].inline_keyboard
        for btn in row
    ]
    assert any("Назад" in t for t in labels)


async def test_cmd_houses_without_subscription_sc_cmd_03(
    session: AsyncSession, monkeypatch
):
    _freeze_utcnow(monkeypatch)
    await _seed_user(
        session,
        user_id=502,
        is_active=False,
        subscription_end=NOW - timedelta(minutes=1),
    )

    message = _make_message(user_id=502)
    await cmd_houses(message, session)

    text = message.answer.await_args.args[0]
    assert text == _SUBSCRIPTION_REQUIRED_TEXT
    assert "Раздел «Дома»" not in text


async def test_cmd_computers_banned_sc_cmd_04(session: AsyncSession, monkeypatch):
    _freeze_utcnow(monkeypatch)
    await _seed_user(
        session,
        user_id=503,
        is_banned=True,
        is_active=True,
        subscription_end=NOW + timedelta(minutes=5),
    )

    message = _make_message(user_id=503)
    await cmd_computers(message, session)

    assert message.answer.await_args.args[0] == "Доступ закрыт."
    assert "Компьютеры" not in message.answer.await_args.args[0]


async def test_cmd_subscription_opens_tariffs_sc_cmd_05(session: AsyncSession):
    await _seed_user(
        session,
        user_id=504,
        is_active=False,
        subscription_end=None,
    )

    message = _make_message(user_id=504)
    await cmd_subscription(message, session)

    text = message.answer.await_args.args[0]
    assert "тариф" in text.lower()
    assert _SUBSCRIPTION_REQUIRED_TEXT not in text
    markup = message.answer.await_args.kwargs["reply_markup"]
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("1 месяц" in t for t in labels)
    assert any("Назад" in t for t in labels)


async def test_cmd_cars_unregistered_sc_cmd_06(session: AsyncSession):
    message = _make_message(user_id=505)
    await cmd_cars(message, session)

    assert message.answer.await_args.args[0] == "Сначала нажми /start"
    assert "Раздел" not in message.answer.await_args.args[0]


async def test_cmd_computers_active_subscriber_sc_cmd_07(
    session: AsyncSession, monkeypatch
):
    _freeze_utcnow(monkeypatch)
    await _seed_user(
        session,
        user_id=506,
        is_active=True,
        subscription_end=NOW + timedelta(minutes=5),
    )

    message = _make_message(user_id=506)
    await cmd_computers(message, session)

    assert message.answer.await_args.args[0] == "Раздел «Компьютеры»\nЗдесь будет контент."
    assert message.answer.await_args.kwargs["reply_markup"] is not None


async def test_cmd_chinese_active_subscriber_sc_cmd_10(
    session: AsyncSession, monkeypatch
):
    _freeze_utcnow(monkeypatch)
    await _seed_user(
        session,
        user_id=508,
        is_active=True,
        subscription_end=NOW + timedelta(minutes=5),
    )

    message = _make_message(user_id=508)
    await cmd_chinese(message, session)

    assert (
        message.answer.await_args.args[0]
        == "Раздел «Курсы китайского»\nЗдесь будет контент."
    )
    assert message.answer.await_args.kwargs["reply_markup"] is not None


async def test_cmd_subscription_banned_sc_cmd_08(session: AsyncSession):
    await _seed_user(session, user_id=507, is_banned=True, trial_used=True)

    message = _make_message(user_id=507)
    await cmd_subscription(message, session)

    assert message.answer.await_args.args[0] == "Доступ закрыт."
    assert "тариф" not in message.answer.await_args.args[0].lower()


# --- /start sync (SC-CMD-09) ---


def _assert_set_commands(message, *, expect_admin: bool) -> None:
    message.bot.set_my_commands.assert_awaited()
    args, kwargs = message.bot.set_my_commands.await_args
    commands = args[0] if args else kwargs.get("commands")
    scope = kwargs.get("scope") or (args[1] if len(args) > 1 else None)
    names = _command_names(commands)
    if expect_admin:
        assert "admin" in names
    else:
        assert "admin" not in names
        assert names == list(LEARNER_COMMANDS)
    assert isinstance(scope, BotCommandScopeChat)
    assert scope.chat_id == message.from_user.id


async def test_start_syncs_learner_commands_sc_cmd_09(
    session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=601, trial_used=True, is_admin=False)

    order: list[str] = []
    message = _make_message(user_id=601, first_name="Bob")

    async def _set_cmds(*args, **kwargs):
        order.append("sync")

    async def _answer(*args, **kwargs):
        order.append("answer")

    message.bot.set_my_commands = AsyncMock(side_effect=_set_cmds)
    message.answer = AsyncMock(side_effect=_answer)

    await cmd_start(message, session)

    assert order == ["sync", "answer"]
    _assert_set_commands(message, expect_admin=False)
    assert "С возвращением, Bob!" in message.answer.await_args.args[0]


async def test_start_syncs_admin_flag_and_bootstrap_sc_cmd_09(
    session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=602, trial_used=True, is_admin=True)
    message_flag = _make_message(user_id=602, first_name="Flag")
    await cmd_start(message_flag, session)
    _assert_set_commands(message_flag, expect_admin=True)

    monkeypatch.setenv("ADMIN_IDS", str(BOOTSTRAP_ID))
    await _seed_user(session, user_id=BOOTSTRAP_ID, trial_used=True, is_admin=False)
    message_boot = _make_message(user_id=BOOTSTRAP_ID, first_name="Boot")
    await cmd_start(message_boot, session)
    _assert_set_commands(message_boot, expect_admin=True)


async def test_start_syncs_banned_user_sc_cmd_09(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=603, trial_used=True, is_banned=True)

    order: list[str] = []
    message = _make_message(user_id=603)

    async def _set_cmds(*args, **kwargs):
        order.append("sync")

    async def _answer(*args, **kwargs):
        order.append("answer")

    message.bot.set_my_commands = AsyncMock(side_effect=_set_cmds)
    message.answer = AsyncMock(side_effect=_answer)

    await cmd_start(message, session)

    assert order == ["sync", "answer"]
    _assert_set_commands(message, expect_admin=False)
    assert message.answer.await_args.args[0] == "Доступ закрыт."
    assert message.answer.await_args.kwargs.get("reply_markup") is None


# --- /help (SC-HELP-01…03) ---


async def test_help_learner_omits_admin_sc_help_01(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=701, trial_used=True, is_admin=False)

    message = _make_message(user_id=701)
    await cmd_help(message, session)

    text = message.answer.await_args.args[0]
    assert "бот для обучения" in text.lower() or "Команды:" in text
    for name in LEARNER_COMMANDS:
        assert f"/{name}" in text
    assert "/admin" not in text
    assert message.answer.await_args.kwargs.get("reply_markup") is None


async def test_help_admin_includes_admin_sc_help_02(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "")
    await _seed_user(session, user_id=702, trial_used=True, is_admin=True)

    message = _make_message(user_id=702)
    await cmd_help(message, session)

    text = message.answer.await_args.args[0]
    assert "/admin" in text
    assert "🛠 Админ" in text
    for name in LEARNER_COMMANDS:
        assert f"/{name}" in text


async def test_help_unregistered_and_banned_sc_help_03(
    session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("ADMIN_IDS", "")

    unregistered = _make_message(user_id=703)
    await cmd_help(unregistered, session)
    text_u = unregistered.answer.await_args.args[0]
    assert "Сначала нажми /start" not in text_u
    assert "/cars" in text_u
    assert "/admin" not in text_u
    assert "Раздел «" not in text_u
    assert "тариф" not in text_u.lower()

    await _seed_user(session, user_id=704, trial_used=True, is_banned=True)
    banned = _make_message(user_id=704)
    await cmd_help(banned, session)
    text_b = banned.answer.await_args.args[0]
    assert "/help" in text_b
    assert "/admin" not in text_b
    assert text_b != "Доступ закрыт."
    assert "Раздел «" not in text_b
