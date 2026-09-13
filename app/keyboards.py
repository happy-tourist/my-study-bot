from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

MENU_CARS = "menu:cars"
MENU_HOUSES = "menu:houses"
MENU_SUBSCRIPTION = "menu:subscription"
MENU_BACK = "menu:back"

TARIFF_PREFIX = "tariff:"

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


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🚗 Машины", callback_data=MENU_CARS)
    b.button(text="🏠 Дома", callback_data=MENU_HOUSES)
    b.button(text="💳 Подписка", callback_data=MENU_SUBSCRIPTION)
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


def tariffs_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for tariff_id, tariff in TARIFFS.items():
        b.button(
            text=f"{tariff['title']} — {tariff['price']}",
            callback_data=f"{TARIFF_PREFIX}{tariff_id}",
        )
    b.button(text="⬅️ Назад в меню", callback_data=MENU_BACK)
    b.adjust(1)
    return b.as_markup()
