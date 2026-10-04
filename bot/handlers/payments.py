from decimal import Decimal, InvalidOperation
import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import Settings
from bot.database.models import Order, PaymentTransaction
from bot.handlers.texts import order_payment_text
from bot.keyboards.user import payment_actions
from bot.services.orders import transition_order
from bot.services.payments import get_provider
from bot.services.pricing import quote_crypto_amount
from bot.states import UserOrderStates
from bot.utils.validators import valid_transaction_hash

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(lambda query: query.data and query.data.startswith("pay:currency:"))
async def choose_currency(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    _, _, order_id, currency = callback.data.split(":")
    if currency not in settings.wallets:
        await callback.answer("Unsupported currency.", show_alert=True)
        return
    address = settings.wallets[currency]
    if not address:
        await callback.answer(f"{currency} payments are not configured.", show_alert=True)
        return
    if not settings.manual_payment_approval:
        try:
            get_provider(settings, currency)
        except ValueError:
            await callback.answer(f"Automatic {currency} verification is not configured.", show_alert=True)
            return
    order = await session.scalar(
        select(Order)
        .options(selectinload(Order.product))
        .where(Order.order_id == order_id, Order.telegram_user_id == callback.from_user.id)
    )
    if order is None or order.status != "pending":
        await callback.answer("This order is no longer available.", show_alert=True)
        return
    try:
        amount = await quote_crypto_amount(settings, currency, order.usd_total)
    except (ValueError, InvalidOperation):
        logger.exception("Crypto pricing provider failed for order %s", order_id)
        await callback.answer("Price quote unavailable. Try again later.", show_alert=True)
        return
    except Exception:
        logger.exception("Crypto pricing provider failed for order %s", order_id)
        await callback.answer("Price quote unavailable. Try again later.", show_alert=True)
        return
    if not settings.manual_payment_approval and amount is None:
        await callback.answer("Automatic verification requires a configured price quote API.", show_alert=True)
        return
    from bot.services.orders import select_payment

    order = await select_payment(session, order_id, callback.from_user.id, currency, address, amount)
    if order is None:
        await callback.answer("This order expired or is no longer available.", show_alert=True)
        return
    suffix = ""
    if amount is None:
        suffix = "\nThe exact crypto amount is not calculated in manual mode; confirm the amount in your wallet."
    await callback.message.edit_text(order_payment_text(order) + suffix, reply_markup=payment_actions(order.order_id))
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("pay:submit:"))
async def request_transaction_hash(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    order_id = callback.data.rsplit(":", 1)[-1]
    order = await session.scalar(
        select(Order).where(
            Order.order_id == order_id,
            Order.telegram_user_id == callback.from_user.id,
            Order.status == "awaiting_payment",
        )
    )
    if order is None or order.selected_currency is None:
        await callback.answer("This order cannot accept a transaction hash.", show_alert=True)
        return
    await state.set_state(UserOrderStates.waiting_for_transaction_hash)
    await state.update_data(order_id=order_id, currency=order.selected_currency)
    await callback.message.answer(f"Send the {order.selected_currency} transaction hash for order #{order_id}. Never send a private key or seed phrase.")
    await callback.answer()


@router.message(UserOrderStates.waiting_for_transaction_hash)
async def receive_transaction_hash(message: Message, state: FSMContext, session: AsyncSession, settings: Settings):
    data = await state.get_data()
    tx_hash = (message.text or "").strip()
    currency = data.get("currency", "")
    if not valid_transaction_hash(currency, tx_hash):
        await message.answer(f"That does not look like a valid {currency} transaction hash. Please try again.")
        return
    if currency != "SOL":
        tx_hash = tx_hash.lower()
    try:
        from bot.services.orders import submit_transaction

        order = await submit_transaction(session, data["order_id"], message.from_user.id, tx_hash, currency)
    except ValueError as exc:
        await message.answer(str(exc))
        await state.clear()
        return
    if order is None:
        await message.answer("This order is no longer awaiting a payment hash.")
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"🔎 Transaction received for order #{order.order_id}. It is not considered paid until verified.",
        reply_markup=payment_actions(order.order_id),
    )
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                f"🔎 Transaction submitted for review\nOrder: #{order.order_id}\nUser: {message.from_user.id}\nCurrency: {currency}\nHash: {tx_hash}",
            )
        except Exception:
            logger.exception("Could not notify admin %s", admin_id)


@router.callback_query(lambda query: query.data and query.data.startswith("pay:check:"))
async def check_payment(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    order_id = callback.data.rsplit(":", 1)[-1]
    order = await session.scalar(
        select(Order).where(Order.order_id == order_id, Order.telegram_user_id == callback.from_user.id)
    )
    if order is None:
        await callback.answer("Order not found.", show_alert=True)
        return
    if order.status == "paid":
        await callback.answer("Payment has already been approved.")
        return
    if order.status == "payment_detected" and settings.manual_payment_approval:
        await callback.answer("Transaction submitted. It is awaiting admin review.", show_alert=True)
        return
    if order.status != "payment_detected" or not order.transaction_hash or not order.selected_currency:
        await callback.answer("Submit your transaction hash first.", show_alert=True)
        return
    if order.crypto_amount_expected is None or not order.receiving_address:
        await callback.answer("This order has no verifiable price/address. Contact support.", show_alert=True)
        return
    try:
        provider = get_provider(settings, order.selected_currency)
        result = await provider.verify_payment(
            order.transaction_hash,
            order.receiving_address,
            order.crypto_amount_expected,
            settings.confirmations[order.selected_currency],
        )
    except Exception:
        logger.exception("Payment verification failed for order %s", order_id)
        await callback.answer("Payment verification is temporarily unavailable.", show_alert=True)
        return
    tx = await session.scalar(select(PaymentTransaction).where(PaymentTransaction.transaction_hash == order.transaction_hash))
    if tx:
        tx.confirmations = result.confirmations
        tx.amount = result.amount
        await session.commit()
    if result.found and result.message == "Verified":
        try:
            await transition_order(
                session,
                order_id,
                action="approve",
                admin_id=0,
                details=f"Automatically verified; confirmations={result.confirmations}",
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await callback.message.answer("✅ Payment verified and approved. Your order is being prepared.")
        await callback.answer("Payment confirmed.")
        return
    await callback.answer(
        f"Payment not confirmed yet. Confirmations: {result.confirmations}/{settings.confirmations[order.selected_currency]}",
        show_alert=True,
    )
