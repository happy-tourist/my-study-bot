"""Admin panel handlers: stats, lists, search FSM, user card mutations."""

from __future__ import annotations

from datetime import datetime

import app.keyboards as kb
from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    can_ban_user,
    can_demote_user,
    can_promote_user,
    can_unban_user,
    extend_subscription,
    has_active_subscription,
    is_admin_user,
    parse_admin_ids,
)
from app.database import User
from app.states import AdminSearchForm

router = Router()

_ACCESS_CLOSED = "Доступ закрыт."
_USER_NOT_FOUND = "Пользователь не найден."
_HOME_TEXT = (
    "Админ-панель\n\n"
    "Статистика, списки пользователей, поиск и управление доступом."
)


class IsAdminFilter(BaseFilter):
    """Router-level gate: actor is bootstrap ADMIN_IDS or User.is_admin."""

    async def __call__(
        self,
        event: Message | CallbackQuery,
        session: AsyncSession,
    ) -> bool:
        if event.from_user is None:
            return False
        telegram_id = event.from_user.id
        result = await session.execute(select(User).where(User.id == telegram_id))
        user = result.scalar_one_or_none()
        return is_admin_user(user, telegram_id=telegram_id)


admin_only = Router()
admin_only.message.filter(IsAdminFilter())
admin_only.callback_query.filter(IsAdminFilter())
router.include_router(admin_only)


async def _load_user(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _actor_is_admin(session: AsyncSession, telegram_id: int) -> bool:
    user = await _load_user(session, telegram_id)
    return is_admin_user(user, telegram_id=telegram_id)


def _target_is_bootstrap(user_id: int) -> bool:
    return user_id in parse_admin_ids()


def _format_user_card(user: User) -> str:
    now = datetime.utcnow()
    uname = f"@{user.username}" if user.username else "—"
    sub_active = has_active_subscription(user, now=now)
    if user.subscription_end is not None:
        sub_end = user.subscription_end.strftime("%d.%m.%Y %H:%M") + " UTC"
    else:
        sub_end = "нет"
    admin_mark = "да" if is_admin_user(user, telegram_id=user.id) else "нет"
    banned_mark = "да" if user.is_banned else "нет"
    trial_mark = "да" if user.trial_used else "нет"
    active_mark = "да" if sub_active else "нет"
    return (
        f"Карточка пользователя\n\n"
        f"ID: {user.id}\n"
        f"Username: {uname}\n"
        f"Админ: {admin_mark}\n"
        f"Бан: {banned_mark}\n"
        f"Подписка активна: {active_mark}\n"
        f"Окончание подписки: {sub_end}\n"
        f"Пробный период использован: {trial_mark}\n"
        f"is_active: {'да' if user.is_active else 'нет'}"
    )


async def _show_user_card(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    *,
    actor_id: int,
) -> None:
    await callback.message.edit_text(
        _format_user_card(user),
        reply_markup=kb.admin_user_card_kb(
            user,
            actor_id=actor_id,
            is_bootstrap=_target_is_bootstrap(user.id),
        ),
    )
    await callback.answer()


async def _show_users_page(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    page: int,
    banned_only: bool,
) -> None:
    page = max(0, page)
    page_size = kb.ADMIN_PAGE_SIZE
    filters = [User.is_banned.is_(True)] if banned_only else []

    count_stmt = select(func.count()).select_from(User)
    list_stmt = select(User).order_by(User.id.asc())
    if filters:
        count_stmt = count_stmt.where(*filters)
        list_stmt = list_stmt.where(*filters)

    total = int((await session.execute(count_stmt)).scalar_one())
    result = await session.execute(
        list_stmt.offset(page * page_size).limit(page_size)
    )
    users = list(result.scalars().all())
    list_prefix = kb.ADMIN_BANNED_PREFIX if banned_only else kb.ADMIN_USERS_PREFIX
    title = "Забаненные пользователи" if banned_only else "Пользователи"
    if total == 0:
        body = f"{title}\n\nСписок пуст."
    else:
        max_page = max(0, (total - 1) // page_size)
        body = f"{title}\n\nСтраница {page + 1} из {max_page + 1} (всего {total})."

    await callback.message.edit_text(
        body,
        reply_markup=kb.admin_users_list_kb(
            users,
            page=page,
            total=total,
            list_prefix=list_prefix,
        ),
    )
    await callback.answer()


# --- Entry: /admin and menu:admin (refuse non-admin with Russian copy) ---


@router.message(Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    if not await _actor_is_admin(session, message.from_user.id):
        await message.answer(_ACCESS_CLOSED)
        return
    await message.answer(_HOME_TEXT, reply_markup=kb.admin_home_kb())


@router.callback_query(F.data == kb.MENU_ADMIN)
async def menu_admin(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    if not await _actor_is_admin(session, callback.from_user.id):
        await callback.message.edit_text(_ACCESS_CLOSED)
        await callback.answer()
        return
    await callback.message.edit_text(_HOME_TEXT, reply_markup=kb.admin_home_kb())
    await callback.answer()


@router.callback_query(F.data.startswith(kb.ADMIN_PREFIX), ~IsAdminFilter())
async def admin_refuse_non_admin(callback: CallbackQuery):
    await callback.answer(_ACCESS_CLOSED, show_alert=True)


# --- Admin-only panel ---


@admin_only.callback_query(F.data == kb.ADMIN_HOME)
async def admin_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(_HOME_TEXT, reply_markup=kb.admin_home_kb())
    await callback.answer()


@admin_only.callback_query(F.data == kb.ADMIN_STATS)
async def admin_stats(callback: CallbackQuery, session: AsyncSession):
    now = datetime.utcnow()
    total = int(
        (await session.execute(select(func.count()).select_from(User))).scalar_one()
    )
    active_sub = int(
        (
            await session.execute(
                select(func.count())
                .select_from(User)
                .where(
                    User.is_active.is_(True),
                    User.subscription_end.is_not(None),
                    User.subscription_end > now,
                )
            )
        ).scalar_one()
    )
    trial_used = int(
        (
            await session.execute(
                select(func.count())
                .select_from(User)
                .where(User.trial_used.is_(True))
            )
        ).scalar_one()
    )
    banned = int(
        (
            await session.execute(
                select(func.count())
                .select_from(User)
                .where(User.is_banned.is_(True))
            )
        ).scalar_one()
    )
    text = (
        "Статистика\n\n"
        f"Всего пользователей: {total}\n"
        f"Активная подписка: {active_sub}\n"
        f"Использовали пробный период: {trial_used}\n"
        f"Забанено: {banned}"
    )
    await callback.message.edit_text(text, reply_markup=kb.admin_back_home_kb())
    await callback.answer()


@admin_only.callback_query(F.data.startswith(kb.ADMIN_USERS_PREFIX))
async def admin_users_list(callback: CallbackQuery, session: AsyncSession):
    raw = callback.data.removeprefix(kb.ADMIN_USERS_PREFIX)
    try:
        page = int(raw)
    except ValueError:
        page = 0
    await _show_users_page(callback, session, page=page, banned_only=False)


@admin_only.callback_query(F.data.startswith(kb.ADMIN_BANNED_PREFIX))
async def admin_banned_list(callback: CallbackQuery, session: AsyncSession):
    raw = callback.data.removeprefix(kb.ADMIN_BANNED_PREFIX)
    try:
        page = int(raw)
    except ValueError:
        page = 0
    await _show_users_page(callback, session, page=page, banned_only=True)


@admin_only.callback_query(F.data == kb.ADMIN_SEARCH)
async def admin_search_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSearchForm.waiting_query)
    await callback.message.edit_text(
        "Поиск пользователя\n\n"
        "Отправь числовой Telegram id или @username.",
        reply_markup=kb.admin_back_home_kb(),
    )
    await callback.answer()


@admin_only.message(AdminSearchForm.waiting_query)
async def admin_search_query(message: Message, session: AsyncSession, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введи id или @username.")
        return

    users: list[User] = []
    if query.startswith("@"):
        uname = query[1:].strip()
        if uname:
            result = await session.execute(
                select(User).where(User.username == uname).order_by(User.id.asc())
            )
            users = list(result.scalars().all())
    elif query.isdigit():
        user = await _load_user(session, int(query))
        if user is not None:
            users = [user]
    else:
        result = await session.execute(
            select(User).where(User.username == query).order_by(User.id.asc())
        )
        users = list(result.scalars().all())

    if not users:
        await message.answer(_USER_NOT_FOUND, reply_markup=kb.admin_back_home_kb())
        return

    await state.clear()
    if len(users) == 1:
        user = users[0]
        await message.answer(
            _format_user_card(user),
            reply_markup=kb.admin_user_card_kb(
                user,
                actor_id=message.from_user.id,
                is_bootstrap=_target_is_bootstrap(user.id),
            ),
        )
        return

    # Several username matches — show a compact chooser list.
    await message.answer(
        "Найдено несколько пользователей. Выбери карточку:",
        reply_markup=kb.admin_users_list_kb(
            users[: kb.ADMIN_PAGE_SIZE],
            page=0,
            total=len(users),
            list_prefix=kb.ADMIN_USERS_PREFIX,
        ),
    )


@admin_only.callback_query(F.data.startswith(kb.ADMIN_USER_PREFIX))
async def admin_user_card(callback: CallbackQuery, session: AsyncSession):
    raw = callback.data.removeprefix(kb.ADMIN_USER_PREFIX)
    try:
        user_id = int(raw)
    except ValueError:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return
    user = await _load_user(session, user_id)
    if user is None:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return
    await _show_user_card(callback, session, user, actor_id=callback.from_user.id)


# --- Mutations (re-check admin via admin_only filter) ---


@admin_only.callback_query(F.data.startswith(kb.ADMIN_PROMOTE_PREFIX))
async def admin_promote(callback: CallbackQuery, session: AsyncSession):
    raw = callback.data.removeprefix(kb.ADMIN_PROMOTE_PREFIX)
    try:
        user_id = int(raw)
    except ValueError:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return
    user = await _load_user(session, user_id)
    if user is None:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return

    ok, reason = can_promote_user(user)
    if not ok:
        await callback.answer(reason, show_alert=True)
        return

    user.is_admin = True
    await session.commit()
    await callback.message.edit_text(
        _format_user_card(user) + "\n\nПользователь назначен администратором.",
        reply_markup=kb.admin_user_card_kb(
            user,
            actor_id=callback.from_user.id,
            is_bootstrap=_target_is_bootstrap(user.id),
        ),
    )
    await callback.answer("Админ-права выданы.")


@admin_only.callback_query(F.data.startswith(kb.ADMIN_DEMOTE_PREFIX))
async def admin_demote(callback: CallbackQuery, session: AsyncSession):
    raw = callback.data.removeprefix(kb.ADMIN_DEMOTE_PREFIX)
    try:
        user_id = int(raw)
    except ValueError:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return
    user = await _load_user(session, user_id)
    if user is None:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return

    ok, reason = can_demote_user(user, actor_id=callback.from_user.id)
    if not ok:
        await callback.answer(reason, show_alert=True)
        return

    user.is_admin = False
    await session.commit()
    await callback.message.edit_text(
        _format_user_card(user) + "\n\nАдмин-права сняты.",
        reply_markup=kb.admin_user_card_kb(
            user,
            actor_id=callback.from_user.id,
            is_bootstrap=_target_is_bootstrap(user.id),
        ),
    )
    await callback.answer("Админ-права сняты.")


@admin_only.callback_query(F.data.startswith(kb.ADMIN_BAN_PREFIX))
async def admin_ban(callback: CallbackQuery, session: AsyncSession):
    raw = callback.data.removeprefix(kb.ADMIN_BAN_PREFIX)
    try:
        user_id = int(raw)
    except ValueError:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return
    user = await _load_user(session, user_id)
    if user is None:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return

    ok, reason = can_ban_user(user)
    if not ok:
        await callback.answer(reason, show_alert=True)
        return

    user.is_banned = True
    await session.commit()
    await callback.message.edit_text(
        _format_user_card(user) + "\n\nПользователь забанен.",
        reply_markup=kb.admin_user_card_kb(
            user,
            actor_id=callback.from_user.id,
            is_bootstrap=_target_is_bootstrap(user.id),
        ),
    )
    await callback.answer("Пользователь забанен.")


@admin_only.callback_query(F.data.startswith(kb.ADMIN_UNBAN_PREFIX))
async def admin_unban(callback: CallbackQuery, session: AsyncSession):
    raw = callback.data.removeprefix(kb.ADMIN_UNBAN_PREFIX)
    try:
        user_id = int(raw)
    except ValueError:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return
    user = await _load_user(session, user_id)
    if user is None:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return

    ok, reason = can_unban_user(user)
    if not ok:
        await callback.answer(reason, show_alert=True)
        return

    user.is_banned = False
    await session.commit()
    await callback.message.edit_text(
        _format_user_card(user) + "\n\nПользователь разбанен.",
        reply_markup=kb.admin_user_card_kb(
            user,
            actor_id=callback.from_user.id,
            is_bootstrap=_target_is_bootstrap(user.id),
        ),
    )
    await callback.answer("Пользователь разбанен.")


@admin_only.callback_query(F.data.startswith(kb.ADMIN_GRANT_MENU_PREFIX))
async def admin_grant_menu(callback: CallbackQuery, session: AsyncSession):
    raw = callback.data.removeprefix(kb.ADMIN_GRANT_MENU_PREFIX)
    try:
        user_id = int(raw)
    except ValueError:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return
    user = await _load_user(session, user_id)
    if user is None:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return
    await callback.message.edit_text(
        f"Выдать тариф пользователю {user.id}:",
        reply_markup=kb.admin_grant_tariffs_kb(user.id),
    )
    await callback.answer()


@admin_only.callback_query(F.data.startswith(kb.ADMIN_GRANT_PREFIX))
async def admin_grant_tariff(callback: CallbackQuery, session: AsyncSession):
    # admin:g:{tariff_id}:{user_id}
    payload = callback.data.removeprefix(kb.ADMIN_GRANT_PREFIX)
    parts = payload.rsplit(":", 1)
    if len(parts) != 2:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    tariff_id, raw_uid = parts
    tariff = kb.TARIFFS.get(tariff_id)
    if tariff is None:
        await callback.answer("Неизвестный тариф.", show_alert=True)
        return
    try:
        user_id = int(raw_uid)
    except ValueError:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return
    user = await _load_user(session, user_id)
    if user is None:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return

    extend_subscription(user, tariff["minutes"])
    await session.commit()
    await callback.message.edit_text(
        _format_user_card(user)
        + f"\n\nТариф выдан: {tariff['title']}.",
        reply_markup=kb.admin_user_card_kb(
            user,
            actor_id=callback.from_user.id,
            is_bootstrap=_target_is_bootstrap(user.id),
        ),
    )
    await callback.answer("Подписка выдана.")


@admin_only.callback_query(F.data.startswith(kb.ADMIN_REVOKE_PREFIX))
async def admin_revoke(callback: CallbackQuery, session: AsyncSession):
    raw = callback.data.removeprefix(kb.ADMIN_REVOKE_PREFIX)
    try:
        user_id = int(raw)
    except ValueError:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return
    user = await _load_user(session, user_id)
    if user is None:
        await callback.answer(_USER_NOT_FOUND, show_alert=True)
        return

    user.subscription_end = None
    user.is_active = False
    await session.commit()
    await callback.message.edit_text(
        _format_user_card(user) + "\n\nПодписка снята.",
        reply_markup=kb.admin_user_card_kb(
            user,
            actor_id=callback.from_user.id,
            is_bootstrap=_target_is_bootstrap(user.id),
        ),
    )
    await callback.answer("Подписка снята.")
