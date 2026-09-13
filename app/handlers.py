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
        "Раздел «Подписка»\nЗдесь будет контент.",
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
