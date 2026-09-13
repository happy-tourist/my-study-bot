from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

MENU_CARS = "menu:cars"
MENU_HOUSES = "menu:houses"
MENU_SUBSCRIPTION = "menu:subscription"
MENU_BACK = "menu:back"


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
