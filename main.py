import os
import ssl
import socket
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

from app.handlers import router

# Укажите здесь данные вашего прокси
# Формат: socks5://логин:пароль@хост:порт
PROXY_URL = "socks5://127.0.0.1:1080"  # <-- Замените на ваш прокси


async def main():
    load_dotenv()

    # --- Локальная отладка: SSL + IPv4 + Прокси ---
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # proxy= подключает ProxyConnector через aiohttp-socks
    session = AiohttpSession(proxy=PROXY_URL)
    session._connector_init.update({
        "family": socket.AF_INET,
        "ssl": ssl_context,
    })
    # -----------------------------------------------

    bot = Bot(token=os.getenv("TG_TOKEN"), session=session)
    dp = Dispatcher()
    dp.include_router(router)
    dp.startup.register(startup)
    dp.shutdown.register(shutdown)
    await dp.start_polling(bot)


async def startup(dispatcher: Dispatcher):
    print("Bot starting up....")


async def shutdown(dispatcher: Dispatcher):
    print("Bot is shutting down...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user...")
