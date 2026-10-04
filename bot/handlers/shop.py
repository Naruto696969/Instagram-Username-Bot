from html import escape

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.database.models import Product, StockNotification
from bot.handlers.texts import product_text
from bot.keyboards.user import product_list, product_page, terms_page
from bot.services.orders import has_accepted_terms
from bot.services.orders import ensure_user

router = Router()


@router.callback_query(lambda query: query.data and query.data.startswith("shop:category:"))
async def category(callback: CallbackQuery, session: AsyncSession):
    category_name = callback.data.rsplit(":", 1)[-1]
    if category_name not in {"claimer", "swapper"}:
        await callback.answer("Invalid category.", show_alert=True)
        return
    products = (
        await session.scalars(
            select(Product)
            .where(Product.category == category_name, Product.deleted.is_(False))
            .order_by(Product.id)
        )
    ).all()
    title = "🛒 <b>Claimer Services</b>" if category_name == "claimer" else "🔄 <b>Swapper Service</b>"
    text = title + "\n\n" + ("\n".join(f"• {p.name} — ${p.usd_price:,.2f}" for p in products) if products else "No products are currently available.")
    await callback.message.edit_text(text, reply_markup=product_list(products))
    await callback.answer()


@router.callback_query(lambda query: query.data == "shop:stock")
async def available_stock(callback: CallbackQuery, session: AsyncSession):
    products = (
        await session.scalars(
            select(Product)
            .where(
                Product.deleted.is_(False),
                Product.enabled.is_(True),
                Product.stock_quantity > Product.reserved_quantity,
            )
            .order_by(Product.id)
        )
    ).all()
    if not products:
        text = "📦 <b>Available Stock</b>\n\nThere are no products in stock right now."
    else:
        lines = ["📦 <b>Available Stock</b>\n"]
        for product in products:
            lines.extend(
                [
                    f"<b>{product.name}</b>",
                    f"Price: ${product.usd_price:,.2f}",
                    f"Stock: {product.available_quantity} available",
                    "",
                ]
            )
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=product_list(products))
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("shop:product:"))
async def product_detail(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    try:
        product_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Invalid product.", show_alert=True)
        return
    product = await session.get(Product, product_id)
    if product is None or product.deleted:
        await callback.answer("This product is unavailable.", show_alert=True)
        return
    accepted = await has_accepted_terms(session, callback.from_user.id, settings.terms_version)
    await callback.message.edit_text(product_text(product), reply_markup=product_page(product, accepted))
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("shop:buy:"))
async def buy(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    try:
        product_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Invalid product.", show_alert=True)
        return
    product = await session.get(Product, product_id)
    if product is None or product.deleted or not product.enabled or product.available_quantity < 1:
        await callback.answer("This product is out of stock.", show_alert=True)
        return
    if not await has_accepted_terms(session, callback.from_user.id, settings.terms_version):
        await callback.message.edit_text(
            "📜 <b>Terms &amp; Conditions</b>\n\n"
            f"{escape(settings.terms_text)}\n\n"
            "You must accept the current terms before placing an order.",
            reply_markup=terms_page(False, product_id),
        )
        await callback.answer()
        return
    from bot.handlers.checkout import create_order

    await create_order(callback, session, settings, product)


@router.callback_query(lambda query: query.data and query.data.startswith("shop:notify:"))
async def notify_when_available(callback: CallbackQuery, session: AsyncSession):
    try:
        product_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Invalid product.", show_alert=True)
        return
    product = await session.get(Product, product_id)
    if product is None or product.deleted:
        await callback.answer("This product is no longer available.", show_alert=True)
        return
    if product.enabled and product.available_quantity > 0:
        await callback.answer("This product is available now.", show_alert=True)
        return
    await ensure_user(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name,
    )
    existing = await session.scalar(
        select(StockNotification.id).where(
            StockNotification.telegram_user_id == callback.from_user.id,
            StockNotification.product_id == product_id,
        )
    )
    if existing is None:
        try:
            async with session.begin_nested():
                session.add(
                    StockNotification(
                        telegram_user_id=callback.from_user.id,
                        product_id=product_id,
                    )
                )
                await session.flush()
        except IntegrityError:
            pass
    await session.commit()
    await callback.answer("🔔 We'll notify you when this service is available.")
