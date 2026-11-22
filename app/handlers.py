import app.keyboards as kb

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, Message, CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    extend_subscription,
    has_active_subscription,
    is_admin_user,
    is_banned_user,
)
from app.bot_commands import admin_bot_commands, learner_bot_commands, sync_commands_for_user
from app.database import User


router = Router()

TRIAL_MINUTES = 3

_ACCESS_CLOSED_TEXT = "Доступ закрыт."

_START_FIRST_TEXT = "Сначала нажми /start"

_SUBSCRIPTION_REQUIRED_TEXT = (
    "Доступ к разделу требует активной подписки.\n"
    "Оформи подписку в разделе «Подписка»."
)

_HELP_INTRO_TEXT = (
    "Я бот для обучения: разделы контента и подписка.\n"
    "Команды:"
)

ReplySender = Callable[..., Awaitable[None]]


async def _load_user(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _refuse_access_closed(callback: CallbackQuery) -> None:
    await callback.message.edit_text(_ACCESS_CLOSED_TEXT)
    await callback.answer()


def _menu_markup(user: User | None, *, telegram_id: int) -> InlineKeyboardMarkup:
    return kb.main_menu_kb(show_admin=is_admin_user(user, telegram_id=telegram_id))


async def _send_gated_topic(
    user: User | None,
    *,
    section: str,
    send: ReplySender,
) -> None:
    """Ban → subscription gate → topic stub (shared by inline edit and slash answer)."""
    if is_banned_user(user):
        await send(_ACCESS_CLOSED_TEXT)
        return
    if not has_active_subscription(user):
        await send(
            _SUBSCRIPTION_REQUIRED_TEXT,
            reply_markup=kb.subscription_required_kb(),
        )
        return

    await send(
        f"Раздел «{section}»\nЗдесь будет контент.",
        reply_markup=kb.back_to_menu_kb(),
    )


async def _open_gated_topic_stub(
    callback: CallbackQuery, session: AsyncSession, *, section: str
) -> None:
    """Ban → subscription gate → topic stub (Cars/Houses/Computers)."""
    user = await _load_user(session, callback.from_user.id)

    async def send(text: str, reply_markup=None) -> None:
        await callback.message.edit_text(text, reply_markup=reply_markup)

    await _send_gated_topic(user, section=section, send=send)
    await callback.answer()


async def _cmd_gated_topic(
    message: Message, session: AsyncSession, *, section: str
) -> None:
    """Slash topic entry: unregistered → /start hint; else same ban→gate→stub as inline."""
    user = await _load_user(session, message.from_user.id)
    if user is None:
        await message.answer(_START_FIRST_TEXT)
        return

    async def send(text: str, reply_markup=None) -> None:
        await message.answer(text, reply_markup=reply_markup)

    await _send_gated_topic(user, section=section, send=send)


def _help_text(*, is_admin: bool) -> str:
    commands = admin_bot_commands() if is_admin else learner_bot_commands()
    lines = [_HELP_INTRO_TEXT]
    for cmd in commands:
        lines.append(f"/{cmd.command} — {cmd.description}")
    return "\n".join(lines)


async def _sync_start_commands(message: Message, user: User) -> None:
    telegram_id = message.from_user.id
    await sync_commands_for_user(
        message.bot,
        telegram_id,
        is_admin=is_admin_user(user, telegram_id=telegram_id),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    user_id = message.from_user.id
    user = await _load_user(session, user_id)

    if user is None:
        user = User(
            id=user_id,
            username=message.from_user.username,
            trial_used=True,
            is_active=True,
            subscription_end=datetime.utcnow() + timedelta(minutes=TRIAL_MINUTES),
        )
        session.add(user)
        await session.commit()
        await _sync_start_commands(message, user)
        await message.answer(
            "Привет! Я тебя запомнил 👋\n\n"
            "Тебе активирован пробный период на 3 дня (3 мин).\n\n"
            "Выбери раздел:",
            reply_markup=_menu_markup(user, telegram_id=user_id),
        )
        return

    await _sync_start_commands(message, user)

    if is_banned_user(user):
        await message.answer(_ACCESS_CLOSED_TEXT)
        return

    await message.answer(
        f"С возвращением, {message.from_user.first_name}!\n\nВыбери раздел:",
        reply_markup=_menu_markup(user, telegram_id=user_id),
    )


@router.message(Command("cars"))
async def cmd_cars(message: Message, session: AsyncSession):
    await _cmd_gated_topic(message, session, section="Машины")


@router.message(Command("houses"))
async def cmd_houses(message: Message, session: AsyncSession):
    await _cmd_gated_topic(message, session, section="Дома")


@router.message(Command("computers"))
async def cmd_computers(message: Message, session: AsyncSession):
    await _cmd_gated_topic(message, session, section="Компьютеры")


@router.message(Command("subscription"))
async def cmd_subscription(message: Message, session: AsyncSession):
    user = await _load_user(session, message.from_user.id)
    if user is None:
        await message.answer(_START_FIRST_TEXT)
        return
    if is_banned_user(user):
        await message.answer(_ACCESS_CLOSED_TEXT)
        return
    show_trial = not user.trial_used
    await message.answer(
        "Выбери тариф подписки:",
        reply_markup=kb.tariffs_kb(show_trial=show_trial),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, session: AsyncSession):
    user = await _load_user(session, message.from_user.id)
    await message.answer(
        _help_text(
            is_admin=is_admin_user(user, telegram_id=message.from_user.id),
        )
    )


@router.callback_query(F.data == kb.MENU_CARS)
async def menu_cars(callback: CallbackQuery, session: AsyncSession):
    await _open_gated_topic_stub(callback, session, section="Машины")


@router.callback_query(F.data == kb.MENU_HOUSES)
async def menu_houses(callback: CallbackQuery, session: AsyncSession):
    await _open_gated_topic_stub(callback, session, section="Дома")


@router.callback_query(F.data == kb.MENU_COMPUTERS)
async def menu_computers(callback: CallbackQuery, session: AsyncSession):
    await _open_gated_topic_stub(callback, session, section="Компьютеры")


@router.callback_query(F.data == kb.MENU_SUBSCRIPTION)
async def menu_subscription(callback: CallbackQuery, session: AsyncSession):
    user = await _load_user(session, callback.from_user.id)
    if is_banned_user(user):
        await _refuse_access_closed(callback)
        return
    show_trial = user is not None and not user.trial_used
    await callback.message.edit_text(
        "Выбери тариф подписки:",
        reply_markup=kb.tariffs_kb(show_trial=show_trial),
    )
    await callback.answer()


@router.callback_query(F.data == kb.CLAIM_TRIAL)
async def claim_trial(callback: CallbackQuery, session: AsyncSession):
    user = await _load_user(session, callback.from_user.id)
    if user is None:
        await callback.answer(_START_FIRST_TEXT, show_alert=True)
        return
    if is_banned_user(user):
        await _refuse_access_closed(callback)
        return
    if user.trial_used:
        await callback.answer("Пробный период уже использован", show_alert=True)
        return

    user.trial_used = True
    user.is_active = True
    user.subscription_end = datetime.utcnow() + timedelta(minutes=TRIAL_MINUTES)
    await session.commit()

    await callback.message.edit_text(
        "Тебе активирован пробный период на 3 дня (3 мин).\n\n"
        "Выбери раздел:",
        reply_markup=_menu_markup(user, telegram_id=callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(kb.TARIFF_PREFIX))
async def tariff_grant(callback: CallbackQuery, session: AsyncSession):
    tariff_id = callback.data.removeprefix(kb.TARIFF_PREFIX)
    tariff = kb.TARIFFS.get(tariff_id)
    if tariff is None:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    user = await _load_user(session, callback.from_user.id)
    if user is None:
        await callback.answer(_START_FIRST_TEXT, show_alert=True)
        return
    if is_banned_user(user):
        await _refuse_access_closed(callback)
        return

    extend_subscription(user, tariff["minutes"])
    await session.commit()

    await callback.message.edit_text(
        f"Подписка активирована: {tariff['title']}.\n"
        f"Действует до {user.subscription_end.strftime('%d.%m.%Y %H:%M')} UTC.",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == kb.MENU_BACK)
async def menu_back(callback: CallbackQuery, session: AsyncSession):
    user = await _load_user(session, callback.from_user.id)
    if is_banned_user(user):
        await _refuse_access_closed(callback)
        return
    await callback.message.edit_text(
        "Выбери раздел:",
        reply_markup=_menu_markup(user, telegram_id=callback.from_user.id),
    )
    await callback.answer()
