from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import Order
from bot.handlers.texts import order_text
from bot.keyboards.user import currency_picker, order_cancel, order_list, payment_actions
from bot.services.orders import transition_order
from bot.states import UserOrderStates

router = Router()


@router.callback_query(lambda query: query.data == "orders:list")
async def my_orders(callback: CallbackQuery, session: AsyncSession):
    orders = (
        await session.scalars(
            select(Order)
            .where(Order.telegram_user_id == callback.from_user.id)
            .order_by(Order.created_at.desc())
            .limit(20)
        )
    ).all()
    await callback.message.edit_text(
        "📋 <b>My Orders</b>\n\n" + ("Select an order to view details." if orders else "You have no orders yet."),
        reply_markup=order_list(orders),
    )
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("orders:view:"))
async def order_details(callback: CallbackQuery, session: AsyncSession):
    order_id = callback.data.rsplit(":", 1)[-1]
    order = await session.scalar(
        select(Order)
        .options(selectinload(Order.product))
        .where(Order.order_id == order_id, Order.telegram_user_id == callback.from_user.id)
    )
    if order is None:
        await callback.answer("Order not found.", show_alert=True)
        return
    if order.status == "pending":
        markup = currency_picker(order_id)
    elif order.status in {"awaiting_payment", "payment_detected"}:
        markup = payment_actions(order_id, allow_cancel=order.status == "awaiting_payment")
    else:
        markup = order_cancel(order_id, cancellable=False)
    await callback.message.edit_text(order_text(order), reply_markup=markup)
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("orders:cancel:"))
async def cancel_order(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    order_id = callback.data.rsplit(":", 1)[-1]
    order = await session.scalar(
        select(Order).where(Order.order_id == order_id, Order.telegram_user_id == callback.from_user.id)
    )
    if order is None or order.status not in {"pending", "awaiting_payment"}:
        await callback.answer("This order cannot be cancelled.", show_alert=True)
        return
    try:
        await transition_order(
            session,
            order_id,
            action="cancel",
            admin_id=callback.from_user.id,
            details="Cancelled by customer",
            audit_action=False,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    if await state.get_state() == UserOrderStates.waiting_for_transaction_hash.state:
        state_data = await state.get_data()
        if state_data.get("order_id") == order_id:
            await state.clear()
    await callback.message.edit_text(f"❌ Order #{order_id} cancelled. Reserved stock has been released.")
    await callback.answer("Order cancelled.")
