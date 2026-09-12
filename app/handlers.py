import asyncio
import app.keyboards as kb

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
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
        await message.answer("Привет! Я тебя запомнил 👋")
    else:
        await message.answer(f"С возвращением, {message.from_user.first_name}!")
