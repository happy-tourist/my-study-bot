import os
import sys
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommandScopeDefault, MenuButtonCommands
from dotenv import load_dotenv

from app.bot_commands import learner_bot_commands
from app.handlers import router
from app.handlers_admin import router as admin_router
from app.database import init_db
from app.middlewares import DbSessionMiddleware
from app.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


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
    dp.include_router(admin_router)
    dp.startup.register(startup)
    dp.shutdown.register(shutdown)
    await dp.start_polling(bot)


async def startup(dispatcher: Dispatcher, bot: Bot):
    print("Bot starting up....")
    try:
        await bot.set_my_commands(
            learner_bot_commands(),
            scope=BotCommandScopeDefault(),
        )
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception:
        # Soft-fail: keep polling + expiry scheduler even if Menu Button API is down.
        logger.exception("Failed to set default Menu Button commands on startup")
    start_scheduler(bot)


async def shutdown(dispatcher: Dispatcher):
    print("Bot is shutting down...")
    stop_scheduler()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user...")
