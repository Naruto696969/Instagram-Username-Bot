from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.database.models import Product
from bot.keyboards.user import currency_picker, order_cancel
from bot.services.inventory import reserve_order
from bot.services.orders import ensure_user, new_order_id
from bot.utils.formatting import usd

router = Router()


async def create_order(callback: CallbackQuery, session: AsyncSession, settings: Settings, product: Product):
    user = await ensure_user(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name,
    )
    order = None
    for _ in range(3):
        order_id = new_order_id()
        order = await reserve_order(
            session,
            order_id=order_id,
            user=user,
            product_id=product.id,
            expiry_minutes=settings.order_expiry_minutes,
        )
        if order is not None:
            break
    if order is None:
        await callback.answer("Stock just changed. Please try again.", show_alert=True)
        return
    await callback.message.edit_text(
        "━━━━━━━━━━━━━━━━━━\n"
        f"🧾 ORDER <code>#{order.order_id}</code>\n\n"
        f"Product: {product.name}\n"
        f"Amount: {usd(order.usd_total)}\n"
        f"Reserved until: {order.expires_at.strftime('%H:%M UTC')}\n\n"
        "Choose a cryptocurrency to continue.\n"
        "━━━━━━━━━━━━━━━━━━",
        reply_markup=currency_picker(order.order_id),
    )
    await callback.answer("Order created.")
    if order.usd_total >= settings.high_value_order_usd:
        for admin_id in settings.admin_ids:
            try:
                await callback.bot.send_message(
                    admin_id,
                    f"💰 High-value order created: #{order.order_id} · {usd(order.usd_total)} · user {callback.from_user.id}",
                )
            except Exception:
                import logging

                logging.getLogger(__name__).exception("Could not notify admin %s", admin_id)
