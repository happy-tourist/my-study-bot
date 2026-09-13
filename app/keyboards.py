from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

MENU_CARS = "menu:cars"
MENU_HOUSES = "menu:houses"
MENU_SUBSCRIPTION = "menu:subscription"
MENU_ADMIN = "menu:admin"
MENU_BACK = "menu:back"

TARIFF_PREFIX = "tariff:"
CLAIM_TRIAL = "trial:claim"

ADMIN_PREFIX = "admin:"
ADMIN_HOME = "admin:home"
ADMIN_STATS = "admin:stats"
ADMIN_SEARCH = "admin:search"
# List prefixes must not be prefixes of each other or of card/action tokens
# (avoid startswith collisions like admin:users: vs admin:u:, admin:banned: vs admin:ban:).
ADMIN_USERS_PREFIX = "admin:ulist:"
ADMIN_BANNED_PREFIX = "admin:blist:"
ADMIN_USER_PREFIX = "admin:u:"
ADMIN_BAN_PREFIX = "admin:ban:"
ADMIN_UNBAN_PREFIX = "admin:unb:"
ADMIN_PROMOTE_PREFIX = "admin:prm:"
ADMIN_DEMOTE_PREFIX = "admin:dem:"
ADMIN_GRANT_MENU_PREFIX = "admin:gm:"
ADMIN_GRANT_PREFIX = "admin:g:"
ADMIN_REVOKE_PREFIX = "admin:rev:"

ADMIN_PAGE_SIZE = 8

TARIFFS = {
    "1_month": {
        "title": "1 месяц (30 мин)",
        "minutes": 30,
        "price": "99 ₽",
    },
    "3_months": {
        "title": "3 месяца (90 мин)",
        "minutes": 90,
        "price": "249 ₽",
    },
    "forever": {
        "title": "Навсегда (36500 мин)",
        "minutes": 36500,
        "price": "999 ₽",
    },
}


def main_menu_kb(*, show_admin: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🚗 Машины", callback_data=MENU_CARS)
    b.button(text="🏠 Дома", callback_data=MENU_HOUSES)
    b.button(text="💳 Подписка", callback_data=MENU_SUBSCRIPTION)
    if show_admin:
        b.button(text="🛠 Админ", callback_data=MENU_ADMIN)
    b.adjust(1)
    return b.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад в меню", callback_data=MENU_BACK)
    return b.as_markup()


def subscription_required_kb() -> InlineKeyboardMarkup:
    """CTA after gate refuse: open tariffs or return to menu."""
    b = InlineKeyboardBuilder()
    b.button(text="💳 Подписка", callback_data=MENU_SUBSCRIPTION)
    b.button(text="⬅️ Назад в меню", callback_data=MENU_BACK)
    b.adjust(1)
    return b.as_markup()


def tariffs_kb(*, show_trial: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if show_trial:
        b.button(text="🎁 Получить пробный период", callback_data=CLAIM_TRIAL)
    for tariff_id, tariff in TARIFFS.items():
        b.button(
            text=f"{tariff['title']} — {tariff['price']}",
            callback_data=f"{TARIFF_PREFIX}{tariff_id}",
        )
    b.button(text="⬅️ Назад в меню", callback_data=MENU_BACK)
    b.adjust(1)
    return b.as_markup()


def admin_home_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 Статистика", callback_data=ADMIN_STATS)
    b.button(text="👥 Пользователи", callback_data=f"{ADMIN_USERS_PREFIX}0")
    b.button(text="🔎 Поиск", callback_data=ADMIN_SEARCH)
    b.button(text="🚫 Забаненные", callback_data=f"{ADMIN_BANNED_PREFIX}0")
    b.button(text="⬅️ В меню", callback_data=MENU_BACK)
    b.adjust(1)
    return b.as_markup()


def admin_back_home_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ В админ-панель", callback_data=ADMIN_HOME)
    return b.as_markup()


def admin_users_list_kb(
    users: list,
    *,
    page: int,
    total: int,
    list_prefix: str,
) -> InlineKeyboardMarkup:
    """Paginated user rows. `list_prefix` is ADMIN_USERS_PREFIX or ADMIN_BANNED_PREFIX."""
    b = InlineKeyboardBuilder()
    for user in users:
        uname = f"@{user.username}" if user.username else "—"
        label = f"{user.id} {uname}"
        if len(label) > 60:
            label = label[:57] + "…"
        b.button(text=label, callback_data=f"{ADMIN_USER_PREFIX}{user.id}")
    page_size = ADMIN_PAGE_SIZE
    max_page = max(0, (total - 1) // page_size) if total else 0
    nav: list[tuple[str, str]] = []
    if page > 0:
        nav.append(("⬅️ Назад", f"{list_prefix}{page - 1}"))
    if page < max_page:
        nav.append(("Вперёд ➡️", f"{list_prefix}{page + 1}"))
    for text, data in nav:
        b.button(text=text, callback_data=data)
    b.button(text="⬅️ В админ-панель", callback_data=ADMIN_HOME)
    # One user per row, then nav row(s), then home.
    b.adjust(1)
    return b.as_markup()


def admin_user_card_kb(
    user,
    *,
    actor_id: int,
    is_bootstrap: bool,
) -> InlineKeyboardMarkup:
    """Action buttons for a user card. Flags decide promote/demote/ban/unban."""
    b = InlineKeyboardBuilder()
    uid = user.id
    if user.is_banned:
        b.button(text="✅ Разбанить", callback_data=f"{ADMIN_UNBAN_PREFIX}{uid}")
    elif not (user.is_admin or is_bootstrap):
        b.button(text="🚫 Забанить", callback_data=f"{ADMIN_BAN_PREFIX}{uid}")

    if not user.is_banned and not (user.is_admin or is_bootstrap):
        b.button(text="⭐ Сделать админом", callback_data=f"{ADMIN_PROMOTE_PREFIX}{uid}")
    elif (user.is_admin or is_bootstrap) and uid != actor_id and not is_bootstrap:
        b.button(text="⬇️ Снять админа", callback_data=f"{ADMIN_DEMOTE_PREFIX}{uid}")

    b.button(text="💳 Выдать тариф", callback_data=f"{ADMIN_GRANT_MENU_PREFIX}{uid}")
    b.button(text="❌ Снять подписку", callback_data=f"{ADMIN_REVOKE_PREFIX}{uid}")
    b.button(text="⬅️ К списку", callback_data=f"{ADMIN_USERS_PREFIX}0")
    b.button(text="🏠 Админ-панель", callback_data=ADMIN_HOME)
    b.adjust(1)
    return b.as_markup()


def admin_grant_tariffs_kb(user_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for tariff_id, tariff in TARIFFS.items():
        data = f"{ADMIN_GRANT_PREFIX}{tariff_id}:{user_id}"
        b.button(text=tariff["title"], callback_data=data)
    b.button(text="⬅️ К карточке", callback_data=f"{ADMIN_USER_PREFIX}{user_id}")
    b.adjust(1)
    return b.as_markup()
