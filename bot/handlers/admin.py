from __future__ import annotations

import asyncio
import logging
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import Settings
from bot.database.models import AdminAuditLog, Order, Product, User, utcnow
from bot.handlers.texts import order_text
from bot.keyboards.admin import (
    admin_menu,
    admin_order_actions,
    admin_order_list,
    broadcast_confirmation,
    delete_product_confirmation,
    price_confirmation,
    product_admin_list,
    stock_dashboard,
)
from bot.services.inventory import delete_product, set_product_enabled, set_stock
from bot.services.orders import audit, order_counts, transition_order
from bot.states import AdminInputStates
from bot.utils.formatting import usd
from bot.utils.validators import parse_positive_int

router = Router()
logger = logging.getLogger(__name__)


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids


async def _guard(callback: CallbackQuery, settings: Settings) -> bool:
    if _is_admin(callback.from_user.id, settings):
        return True
    await callback.answer("Admin access required.", show_alert=True)
    return False


async def _products(session: AsyncSession):
    return (
        await session.scalars(
            select(Product).where(Product.deleted.is_(False)).order_by(Product.id)
        )
    ).all()


def _stock_product_text(product: Product) -> str:
    if product.available_quantity == 0:
        status = "🔴 SOLD OUT"
    elif not product.enabled:
        status = "🔴 SOLD OUT"
    else:
        status = "🟢 Available"
    return (
        f"📦 <b>{product.name}</b>\n"
        f"Status: {status}\n"
        f"Sales: {'🟢 Enabled' if product.enabled else '🔴 Disabled by admin'}\n"
        f"Stock: {product.stock_quantity} · {product.available_quantity} available\n"
        f"Price: {usd(product.usd_price)}"
    )


def _stock_dashboard_text(products: list[Product]) -> str:
    text = "📦 <b>Manage Stock</b>\n\n" + "\n\n".join(
        _stock_product_text(product) for product in products
    )
    return text if products else text + "No active products."


async def _render_stock_dashboard(callback: CallbackQuery, session: AsyncSession) -> None:
    products = await _products(session)
    await callback.message.edit_text(_stock_dashboard_text(products), reply_markup=stock_dashboard(products))


async def _notify_stock_waitlist(bot, session: AsyncSession, product: Product) -> None:
    if product.deleted or not product.enabled or product.available_quantity <= 0:
        return
    from bot.database.models import StockNotification

    user_ids = (
        await session.scalars(
            select(StockNotification.telegram_user_id).where(
                StockNotification.product_id == product.id
            )
        )
    ).all()
    if not user_ids:
        return
    await session.execute(
        StockNotification.__table__.delete().where(
            StockNotification.product_id == product.id,
            StockNotification.telegram_user_id.in_(user_ids),
        )
    )
    await session.commit()
    for user_id in user_ids:
        try:
            await bot.send_message(
                user_id,
                f"🔔 <b>{product.name}</b> is now available with {product.available_quantity} in stock.",
            )
        except Exception:
            logger.exception("Could not notify stock waitlist user %s", user_id)


async def _load_order(session: AsyncSession, order_id: str) -> Order | None:
    return await session.scalar(
        select(Order).options(selectinload(Order.product)).where(Order.order_id == order_id.upper())
    )


async def _show_order(callback: CallbackQuery, session: AsyncSession, order_id: str):
    order = await _load_order(session, order_id)
    if order is None:
        await callback.answer("Order not found.", show_alert=True)
        return
    details = order_text(order) + f"\n\nTelegram user: <code>{order.telegram_user_id}</code>"
    await callback.message.edit_text(details, reply_markup=admin_order_actions(order))
    await callback.answer()


@router.message(Command("admin"))
async def admin_start(message: Message, settings: Settings):
    if not _is_admin(message.from_user.id, settings):
        await message.answer("⛔ Admin access required.")
        return
    await message.answer("⚙️ <b>Admin Panel</b>\n\nSelect an action.", reply_markup=admin_menu())


@router.callback_query(lambda query: query.data == "admin:home")
async def admin_home(callback: CallbackQuery, settings: Settings):
    if not await _guard(callback, settings):
        return
    await callback.message.edit_text("⚙️ <b>Admin Panel</b>\n\nSelect an action.", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(lambda query: query.data == "admin:stock")
async def manage_stock(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    await _render_stock_dashboard(callback, session)
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("admin:stockop:"))
async def stock_operation(callback: CallbackQuery, state: FSMContext, settings: Settings, session: AsyncSession):
    if not await _guard(callback, settings):
        return
    _, _, mode, product_id_raw = callback.data.split(":")
    if mode not in {"add", "remove", "set"}:
        await callback.answer("Invalid stock operation.", show_alert=True)
        return
    try:
        product_id = int(product_id_raw)
    except ValueError:
        await callback.answer("Invalid product.", show_alert=True)
        return
    product = await session.get(Product, product_id)
    if product is None:
        await callback.answer("Product not found.", show_alert=True)
        return
    await state.set_state(AdminInputStates.waiting_for_stock_quantity)
    await state.update_data(product_id=product_id, stock_mode=mode)
    await callback.message.answer(f"Enter the quantity to {mode} for {product.name} (whole number, zero allowed only for Set).")
    await callback.answer()


@router.message(AdminInputStates.waiting_for_stock_quantity)
async def receive_stock_quantity(message: Message, state: FSMContext, settings: Settings, session: AsyncSession):
    if not _is_admin(message.from_user.id, settings):
        await state.clear()
        return
    data = await state.get_data()
    mode = data.get("stock_mode")
    raw = (message.text or "").strip()
    try:
        if mode == "set" and raw.isdigit():
            quantity = int(raw)
        else:
            quantity = parse_positive_int(raw)
        product = await set_stock(
            session,
            int(data["product_id"]),
            quantity,
            mode,
            admin_user_id=message.from_user.id,
        )
    except (ValueError, TypeError) as exc:
        await message.answer(str(exc) or "Enter a valid non-negative whole number.")
        return
    await state.clear()
    await _notify_stock_waitlist(message.bot, session, product)
    products = await _products(session)
    await message.answer(
        f"✅ Stock updated.\n\n{_stock_dashboard_text(products)}",
        reply_markup=stock_dashboard(products),
    )


@router.callback_query(lambda query: query.data and query.data.startswith("admin:availability:"))
async def set_product_availability(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    try:
        _, _, product_id_raw, state = callback.data.split(":")
        product_id = int(product_id_raw)
        if state not in {"on", "off"}:
            raise ValueError
    except ValueError:
        await callback.answer("Invalid availability action.", show_alert=True)
        return
    try:
        product = await set_product_enabled(
            session,
            product_id,
            enabled=state == "on",
            admin_user_id=callback.from_user.id,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await _notify_stock_waitlist(callback.bot, session, product)
    await _render_stock_dashboard(callback, session)
    await callback.answer("Sales enabled." if product.enabled else "Product marked sold out.")


@router.callback_query(lambda query: query.data and query.data.startswith("admin:delete:ask:"))
async def confirm_delete_product(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    try:
        product_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Invalid product.", show_alert=True)
        return
    product = await session.get(Product, product_id)
    if product is None or product.deleted:
        await callback.answer("Product not found.", show_alert=True)
        return
    await callback.message.edit_text(
        f"⚠️ <b>Delete {product.name}?</b>\n\n"
        "This permanently removes the product from the customer storefront and clears its unreserved stock. "
        "Existing order history is retained. Products with active stock reservations cannot be deleted.",
        reply_markup=delete_product_confirmation(product_id),
    )
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("admin:delete:confirm:"))
async def delete_product_confirmed(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    try:
        product_id = int(callback.data.rsplit(":", 1)[-1])
        product = await delete_product(session, product_id, callback.from_user.id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    from bot.database.models import StockNotification

    await session.execute(
        StockNotification.__table__.delete().where(StockNotification.product_id == product.id)
    )
    await session.commit()
    products = await _products(session)
    await callback.message.edit_text(
        f"🗑 <b>{product.name}</b> was removed from the storefront. Historical orders have been preserved.\n\n"
        f"{_stock_dashboard_text(products)}",
        reply_markup=stock_dashboard(products),
    )
    await callback.answer("Product deleted.")


@router.callback_query(lambda query: query.data == "admin:prices")
async def manage_prices(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    await callback.message.edit_text("💰 <b>Manage Prices</b>\n\nSelect a product.", reply_markup=product_admin_list(await _products(session), "price"))
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("admin:price:"))
async def choose_price(callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    try:
        product_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Invalid product.", show_alert=True)
        return
    product = await session.get(Product, product_id)
    if product is None:
        await callback.answer("Product not found.", show_alert=True)
        return
    await state.set_state(AdminInputStates.waiting_for_price)
    await state.update_data(product_id=product_id)
    await callback.message.answer(f"Current price for {product.name}: {usd(product.usd_price)}\nEnter the new USD price.")
    await callback.answer()


@router.message(AdminInputStates.waiting_for_price)
async def receive_price(message: Message, state: FSMContext, settings: Settings, session: AsyncSession):
    if not _is_admin(message.from_user.id, settings):
        await state.clear()
        return
    try:
        price = Decimal((message.text or "").strip().replace("$", "").replace(",", ""))
        if not price.is_finite() or price <= 0 or price > Decimal("1000000000"):
            raise InvalidOperation
        price = price.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        await message.answer("Enter a valid positive USD amount, for example 125.00.")
        return
    data = await state.get_data()
    product = await session.get(Product, int(data["product_id"]))
    if product is None:
        await state.clear()
        await message.answer("Product not found.")
        return
    await state.set_state(AdminInputStates.confirming_price)
    await state.update_data(new_price=str(price))
    await message.answer(
        f"Confirm price change for {product.name}:\n{usd(product.usd_price)} → {usd(price)}",
        reply_markup=price_confirmation(),
    )


@router.callback_query(lambda query: query.data == "admin:priceconfirm")
async def confirm_price(callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    if await state.get_state() != AdminInputStates.confirming_price.state:
        await callback.answer("No pending price change.", show_alert=True)
        return
    data = await state.get_data()
    product = await session.get(Product, int(data["product_id"]))
    if product is None:
        await state.clear()
        await callback.answer("Product not found.", show_alert=True)
        return
    old_price = product.usd_price
    product.usd_price = Decimal(data["new_price"])
    product.updated_at = utcnow()
    await session.commit()
    await audit(session, callback.from_user.id, "price_updated", f"{product.name}: {old_price} -> {product.usd_price}")
    await state.clear()
    await callback.message.edit_text(f"✅ Price updated for {product.name}: {usd(product.usd_price)}", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(lambda query: query.data == "admin:pricediscard")
async def discard_price(callback: CallbackQuery, state: FSMContext, settings: Settings):
    if not await _guard(callback, settings):
        return
    await state.clear()
    await callback.message.edit_text("Price change discarded.", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(lambda query: query.data == "admin:products")
async def product_settings(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    products = await _products(session)
    text = "⚙️ <b>Products</b>\n\n" + "\n".join(
        f"#{p.id} {p.name} · {'Enabled' if p.enabled else 'Disabled'}" for p in products
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{'Disable' if p.enabled else 'Enable'} · {p.name}", callback_data=f"admin:toggle:{p.id}")]
            for p in products
        ]
        + [[InlineKeyboardButton(text="⬅️ Admin Menu", callback_data="admin:home")]]
    )
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("admin:toggle:"))
async def toggle_product(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    try:
        product_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Invalid product.", show_alert=True)
        return
    product = await session.get(Product, product_id)
    if product is None or product.deleted:
        await callback.answer("Product not found.", show_alert=True)
        return
    try:
        product = await set_product_enabled(
            session,
            product_id,
            enabled=not product.enabled,
            admin_user_id=callback.from_user.id,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await _notify_stock_waitlist(callback.bot, session, product)
    await callback.answer(f"{product.name} {'enabled' if product.enabled else 'disabled'}.")
    await product_settings(callback, session, settings)


@router.callback_query(lambda query: query.data == "admin:orders")
async def admin_orders(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    orders = (
        await session.scalars(
            select(Order)
            .where(Order.status.in_(("pending", "awaiting_payment", "paid", "processing", "completed")))
            .order_by(Order.created_at.desc())
            .limit(30)
        )
    ).all()
    await callback.message.edit_text("📋 <b>Recent Orders</b>", reply_markup=admin_order_list(orders))
    await callback.answer()


@router.callback_query(lambda query: query.data == "admin:review")
async def review_orders(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    orders = (
        await session.scalars(
            select(Order)
            .where(Order.status == "payment_detected")
            .order_by(Order.created_at.asc())
            .limit(30)
        )
    ).all()
    await callback.message.edit_text(
        "✅ <b>Payments Requiring Review</b>\n\n" + ("No payments currently require review." if not orders else "Select an order."),
        reply_markup=admin_order_list(orders),
    )
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("admin:order:"))
async def admin_order(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    await _show_order(callback, session, callback.data.rsplit(":", 1)[-1])


@router.callback_query(lambda query: query.data and query.data.startswith(("admin:approve:", "admin:reject:", "admin:processing:", "admin:complete:", "admin:cancel:")))
async def order_action(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    _, action, order_id = callback.data.split(":")
    if action == "approve" and not settings.manual_payment_approval:
        tx = await session.scalar(select(Order.transaction_hash).where(Order.order_id == order_id))
        if tx:
            from bot.database.models import PaymentTransaction

            verified = await session.scalar(
                select(PaymentTransaction.verified).where(PaymentTransaction.transaction_hash == tx)
            )
        else:
            verified = False
        if not verified:
            await callback.answer("API-mode payments must pass blockchain verification first.", show_alert=True)
            return
    try:
        order = await transition_order(session, order_id, action=action, admin_id=callback.from_user.id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer(f"Order {order_id}: {order.status}.")
    messages = {
        "approve": "✅ Your payment was approved. Your order is being prepared.",
        "reject": "❌ Your transaction could not be approved. Please contact support or submit a valid payment hash.",
        "processing": "⚙️ Your order is now processing.",
        "complete": "✅ Your order has been marked completed.",
        "cancel": "🚫 Your order was cancelled.",
    }
    try:
        await callback.bot.send_message(order.telegram_user_id, f"{messages[action]}\nOrder: #{order_id}")
    except Exception:
        logger.exception("Could not notify customer for order %s", order_id)
    await _show_order(callback, session, order_id)


@router.callback_query(lambda query: query.data == "admin:stats")
async def statistics(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    counts = await order_counts(session)
    users = await session.scalar(select(func.count()).select_from(User)) or 0
    paid_total = await session.scalar(
        select(func.coalesce(func.sum(Order.usd_total), 0)).where(Order.status.in_(("paid", "processing", "completed")))
    )
    products = await _products(session)
    stock = "\n".join(f"{p.name}: {p.available_quantity} available" for p in products)
    body = "\n".join(f"{status.replace('_', ' ').title()}: {count}" for status, count in sorted(counts.items())) or "No orders yet."
    await callback.message.edit_text(
        f"📊 <b>Statistics</b>\n\nUsers: {users}\nGross approved sales: {usd(Decimal(str(paid_total)))}\n\n{body}\n\n<b>Available stock</b>\n{stock}",
        reply_markup=admin_menu(),
    )
    await callback.answer()


@router.callback_query(lambda query: query.data == "admin:search")
async def search_start(callback: CallbackQuery, state: FSMContext, settings: Settings):
    if not await _guard(callback, settings):
        return
    await state.set_state(AdminInputStates.waiting_for_order_search)
    await callback.message.answer("Enter an order ID or Telegram user ID to search.")
    await callback.answer()


@router.message(AdminInputStates.waiting_for_order_search)
async def search_order(message: Message, state: FSMContext, session: AsyncSession, settings: Settings):
    if not _is_admin(message.from_user.id, settings):
        await state.clear()
        return
    query = (message.text or "").strip()
    if not query or len(query) > 128:
        await message.answer("Enter a valid order ID or Telegram user ID.")
        return
    stmt = select(Order).options(selectinload(Order.product))
    if query.isdigit():
        stmt = stmt.where(Order.telegram_user_id == int(query))
    else:
        stmt = stmt.where(Order.order_id == query.upper())
    orders = (await session.scalars(stmt.order_by(Order.created_at.desc()).limit(20))).all()
    await state.clear()
    if not orders:
        await message.answer("No matching orders found.", reply_markup=admin_menu())
        return
    await message.answer("Search results:", reply_markup=admin_order_list(orders))


@router.callback_query(lambda query: query.data == "admin:broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext, settings: Settings):
    if not await _guard(callback, settings):
        return
    await state.set_state(AdminInputStates.waiting_for_broadcast)
    await callback.message.answer("Send the broadcast text. HTML formatting is supported; do not include secrets.")
    await callback.answer()


@router.message(AdminInputStates.waiting_for_broadcast)
async def broadcast_preview(message: Message, state: FSMContext, settings: Settings):
    if not _is_admin(message.from_user.id, settings):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text or len(text) > 4000:
        await message.answer("Broadcast must be 1–4000 characters.")
        return
    await state.set_state(AdminInputStates.confirming_broadcast)
    await state.update_data(broadcast_text=text)
    await message.answer(
        f"Preview (sent to at most {settings.broadcast_max_users} users):\n\n{text}",
        reply_markup=broadcast_confirmation(),
    )


@router.callback_query(lambda query: query.data == "admin:broadcastcancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext, settings: Settings):
    if not await _guard(callback, settings):
        return
    await state.clear()
    await callback.message.edit_text("Broadcast cancelled.", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(lambda query: query.data == "admin:broadcastconfirm")
async def broadcast_send(callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings):
    if not await _guard(callback, settings):
        return
    if await state.get_state() != AdminInputStates.confirming_broadcast.state:
        await callback.answer("No pending broadcast.", show_alert=True)
        return
    text = (await state.get_data()).get("broadcast_text", "")
    if not text:
        await state.clear()
        await callback.answer("Broadcast text is missing.", show_alert=True)
        return
    users = (
        await session.scalars(
            select(User.telegram_user_id).order_by(User.created_at).limit(settings.broadcast_max_users)
        )
    ).all()
    await session.commit()
    await state.clear()
    delivered = 0
    failed = 0
    for user_id in users:
        try:
            await callback.bot.send_message(user_id, text, parse_mode="HTML")
            delivered += 1
        except Exception:
            failed += 1
            logger.exception("Broadcast failed for user %s", user_id)
        await asyncio.sleep(0.05)
    await audit(session, callback.from_user.id, "broadcast", f"recipients={len(users)}, delivered={delivered}, failed={failed}")
    await callback.message.edit_text(
        f"📢 Broadcast complete.\nDelivered: {delivered}\nFailed: {failed}",
        reply_markup=admin_menu(),
    )
    await callback.answer()
