import app.keyboards as kb

from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import has_active_subscription
from app.database import User


router = Router()

TRIAL_MINUTES = 3

_SUBSCRIPTION_REQUIRED_TEXT = (
    "Доступ к разделу требует активной подписки.\n"
    "Оформи подписку в разделе «Подписка»."
)


async def _load_user(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _refuse_without_subscription(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        _SUBSCRIPTION_REQUIRED_TEXT,
        reply_markup=kb.subscription_required_kb(),
    )
    await callback.answer()


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
        await message.answer(
            "Привет! Я тебя запомнил 👋\n\n"
            "Тебе активирован пробный период на 3 дня (3 мин).\n\n"
            "Выбери раздел:",
            reply_markup=kb.main_menu_kb(),
        )
    else:
        await message.answer(
            f"С возвращением, {message.from_user.first_name}!\n\nВыбери раздел:",
            reply_markup=kb.main_menu_kb(),
        )


@router.callback_query(F.data == kb.MENU_CARS)
async def menu_cars(callback: CallbackQuery, session: AsyncSession):
    user = await _load_user(session, callback.from_user.id)
    if not has_active_subscription(user):
        await _refuse_without_subscription(callback)
        return

    await callback.message.edit_text(
        "Раздел «Машины»\nЗдесь будет контент.",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == kb.MENU_HOUSES)
async def menu_houses(callback: CallbackQuery, session: AsyncSession):
    user = await _load_user(session, callback.from_user.id)
    if not has_active_subscription(user):
        await _refuse_without_subscription(callback)
        return

    await callback.message.edit_text(
        "Раздел «Дома»\nЗдесь будет контент.",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == kb.MENU_SUBSCRIPTION)
async def menu_subscription(callback: CallbackQuery, session: AsyncSession):
    user = await _load_user(session, callback.from_user.id)
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
        await callback.answer("Сначала нажми /start", show_alert=True)
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
        reply_markup=kb.main_menu_kb(),
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
        await callback.answer("Сначала нажми /start", show_alert=True)
        return

    now = datetime.utcnow()
    if user.subscription_end is not None and user.subscription_end > now:
        base = user.subscription_end
    else:
        base = now

    user.subscription_end = base + timedelta(minutes=tariff["minutes"])
    user.is_active = True
    await session.commit()

    await callback.message.edit_text(
        f"Подписка активирована: {tariff['title']}.\n"
        f"Действует до {user.subscription_end.strftime('%d.%m.%Y %H:%M')} UTC.",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == kb.MENU_BACK)
async def menu_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выбери раздел:",
        reply_markup=kb.main_menu_kb(),
    )
    await callback.answer()
