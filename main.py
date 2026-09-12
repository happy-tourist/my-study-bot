import os
import sys
import asyncio

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from app.handlers import router
from app.database import init_db
from app.middlewares import DbSessionMiddleware


async def main():
    load_dotenv()

    if sys.platform == "win32":
        # Локальная отладка на Windows (VPN, SSL-обход, IPv4)
        import ssl
        import socket
        from aiogram.client.session.aiohttp import AiohttpSession

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        session = AiohttpSession()
        session._connector_init.update({
            "family": socket.AF_INET,
            "ssl": ssl_context,
        })
        bot = Bot(token=os.getenv("TG_TOKEN"), session=session)
    else:
        # Linux / сервер — чистый вариант
        bot = Bot(token=os.getenv("TG_TOKEN"))

    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware())
    await init_db()

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
