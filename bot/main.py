from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import Settings
from bot.database.session import create_database, initialize_database
from bot.handlers import admin, checkout, orders, payments, shop, start, support, terms
from bot.middlewares.database import DatabaseSessionMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.services.orders import expire_due
from bot.utils.logging import configure_logging

logger = logging.getLogger(__name__)


async def _expiration_worker(bot: Bot, session_factory, interval_seconds: int = 30) -> None:
    while True:
        try:
            async with session_factory() as session:
                expired_orders = await expire_due(session)
            for order in expired_orders:
                try:
                    await bot.send_message(
                        order.telegram_user_id,
                        f"⌛ Order #{order.order_id} expired. Its reserved stock has been released.",
                    )
                except TelegramAPIError:
                    logger.exception("Could not notify user about expired order %s", order.order_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Order expiration worker failed")
        await asyncio.sleep(interval_seconds)


async def run() -> None:
    configure_logging()
    settings = Settings.from_env()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required. Copy .env.example to .env and configure it.")
    if not settings.admin_ids:
        logger.warning("ADMIN_IDS is empty; admin features will be inaccessible.")

    engine, session_factory = create_database(settings.database_url)
    await initialize_database(engine, session_factory)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher["settings"] = settings
    rate_limiter = RateLimitMiddleware(settings.rate_limit_per_minute)
    dispatcher.message.outer_middleware(rate_limiter)
    dispatcher.callback_query.outer_middleware(rate_limiter)
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware(session_factory))
    dispatcher.include_routers(
        start.router,
        shop.router,
        checkout.router,
        terms.router,
        payments.router,
        orders.router,
        support.router,
        admin.router,
    )

    @dispatcher.errors()
    async def on_error(event: ErrorEvent) -> bool:
        logger.error(
            "Unhandled Telegram update error",
            exc_info=(type(event.exception), event.exception, event.exception.__traceback__),
        )
        update = event.update
        try:
            if update.callback_query:
                await update.callback_query.answer("Something went wrong. Please try again.", show_alert=True)
            elif update.message:
                await update.message.answer("Something went wrong. Please try again later.")
        except TelegramAPIError:
            logger.exception("Could not notify user about handler error")
        return True

    expiration_task = asyncio.create_task(_expiration_worker(bot, session_factory))
    try:
        await dispatcher.start_polling(bot)
    finally:
        expiration_task.cancel()
        with suppress(asyncio.CancelledError):
            await expiration_task
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
