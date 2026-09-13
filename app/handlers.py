from datetime import datetime, timedelta

import app.keyboards as kb

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import User


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    user_id = message.from_user.id

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(id=user_id, username=message.from_user.username)
        session.add(user)
        await session.commit()
        await message.answer(
            "Привет! Я тебя запомнил 👋\n\nВыбери раздел:",
            reply_markup=kb.main_menu_kb(),
        )
    else:
        await message.answer(
            f"С возвращением, {message.from_user.first_name}!\n\nВыбери раздел:",
            reply_markup=kb.main_menu_kb(),
        )


@router.callback_query(F.data == kb.MENU_CARS)
async def menu_cars(callback: CallbackQuery):
    await callback.message.edit_text(
        "Раздел «Машины»\nЗдесь будет контент.",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == kb.MENU_HOUSES)
async def menu_houses(callback: CallbackQuery):
    await callback.message.edit_text(
        "Раздел «Дома»\nЗдесь будет контент.",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == kb.MENU_SUBSCRIPTION)
async def menu_subscription(callback: CallbackQuery):
    await callback.message.edit_text(
        "Раздел «Подписка»\nТестовая выдача срока (временно):",
        reply_markup=kb.subscription_kb(),
    )
    await callback.answer()


async def _grant_test_subscription(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    minutes: int,
) -> None:
    user_id = callback.from_user.id
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    end = datetime.utcnow() + timedelta(minutes=minutes)

    if user is None:
        user = User(
            id=user_id,
            username=callback.from_user.username,
            is_active=True,
            subscription_end=end,
        )
        session.add(user)
    else:
        user.is_active = True
        user.subscription_end = end
    await session.commit()

    if minutes == 1:
        confirm = "Тестовая подписка выдана на 1 минуту."
    else:
        confirm = f"Тестовая подписка выдана на {minutes} минут."

    await callback.message.edit_text(
        confirm,
        reply_markup=kb.subscription_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == kb.SUB_TEST_1M)
async def sub_test_1m(callback: CallbackQuery, session: AsyncSession):
    await _grant_test_subscription(callback, session, minutes=1)


@router.callback_query(F.data == kb.SUB_TEST_5M)
async def sub_test_5m(callback: CallbackQuery, session: AsyncSession):
    await _grant_test_subscription(callback, session, minutes=5)


@router.callback_query(F.data == kb.MENU_BACK)
async def menu_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выбери раздел:",
        reply_markup=kb.main_menu_kb(),
    )
    await callback.answer()
