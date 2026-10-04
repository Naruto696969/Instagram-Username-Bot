from __future__ import annotations

import secrets
import string
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AdminAuditLog, Order, PaymentTransaction, Product, TermsAcceptance, User, utcnow


def new_order_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


async def ensure_user(session: AsyncSession, telegram_user_id: int, username: str | None, first_name: str | None) -> User:
    user = await session.get(User, telegram_user_id)
    if user is None:
        user = User(telegram_user_id=telegram_user_id, username=username, first_name=first_name)
        session.add(user)
    else:
        user.username = username
        user.first_name = first_name
        user.updated_at = utcnow()
    await session.commit()
    return user


async def has_accepted_terms(session: AsyncSession, user_id: int, version: str) -> bool:
    return bool(
        await session.scalar(
            select(TermsAcceptance.id).where(
                TermsAcceptance.telegram_user_id == user_id,
                TermsAcceptance.terms_version == version,
            )
        )
    )


async def accept_terms(session: AsyncSession, user_id: int, version: str) -> None:
    if not await has_accepted_terms(session, user_id, version):
        session.add(TermsAcceptance(telegram_user_id=user_id, terms_version=version))
        await session.commit()


async def select_payment(
    session: AsyncSession,
    order_id: str,
    user_id: int,
    currency: str,
    address: str,
    crypto_amount: Decimal | None,
) -> Order | None:
    if session.in_transaction():
        await session.commit()
    async with session.begin():
        order = await session.scalar(
            select(Order).where(
                Order.order_id == order_id,
                Order.telegram_user_id == user_id,
                Order.status == "pending",
                Order.expires_at > utcnow(),
            ).with_for_update()
        )
        if order is None:
            return None
        order.selected_currency = currency
        order.receiving_address = address
        order.crypto_amount_expected = crypto_amount
        order.status = "awaiting_payment"
    return order


async def submit_transaction(
    session: AsyncSession, order_id: str, user_id: int, tx_hash: str, currency: str
) -> Order | None:
    if session.in_transaction():
        await session.commit()
    async with session.begin():
        order = await session.scalar(
            select(Order).where(
                Order.order_id == order_id,
                Order.telegram_user_id == user_id,
                Order.status == "awaiting_payment",
                Order.expires_at > utcnow(),
                Order.selected_currency == currency,
            ).with_for_update()
        )
        if order is None:
            return None
        existing = await session.scalar(
            select(PaymentTransaction.id).where(PaymentTransaction.transaction_hash == tx_hash)
        )
        if existing is not None:
            raise ValueError("This transaction hash has already been submitted")
        order.transaction_hash = tx_hash
        order.status = "payment_detected"
        session.add(
            PaymentTransaction(
                order_id=order_id,
                currency=currency,
                transaction_hash=tx_hash,
            )
        )
    return order


async def transition_order(
    session: AsyncSession,
    order_id: str,
    *,
    action: str,
    admin_id: int,
    details: str = "",
    audit_action: bool = True,
) -> Order:
    allowed = {
        "approve": ("payment_detected", "paid"),
        "reject": ("payment_detected", "awaiting_payment"),
        "processing": ("paid", "processing"),
        "complete": ("processing", "completed"),
        "cancel": (("pending", "awaiting_payment", "payment_detected"), "cancelled"),
    }
    if action not in allowed:
        raise ValueError("Unsupported order action")
    source, target = allowed[action]
    sources = (source,) if isinstance(source, str) else source
    if session.in_transaction():
        await session.commit()
    async with session.begin():
        order = await session.scalar(select(Order).where(Order.order_id == order_id).with_for_update())
        if order is None:
            raise ValueError("Order not found")
        if order.status not in sources:
            raise ValueError(f"Cannot {action} an order in status {order.status}")
        if action in {"approve", "processing", "complete"}:
            if action == "approve":
                product = await session.scalar(
                    select(Product).where(Product.id == order.product_id).with_for_update()
                )
                if product is None or product.stock_quantity < order.quantity:
                    raise ValueError("Inventory no longer has the reserved quantity")
                if product.reserved_quantity < order.quantity:
                    raise ValueError("Order reservation is missing")
                product.stock_quantity -= order.quantity
                product.reserved_quantity -= order.quantity
                if not details:
                    details = (
                        f"{product.name}: approved {order.quantity} unit(s); "
                        f"stock={product.stock_quantity}; reserved={product.reserved_quantity}"
                    )
                order.paid_at = utcnow()
                transaction = await session.scalar(
                    select(PaymentTransaction).where(PaymentTransaction.transaction_hash == order.transaction_hash)
                )
                if transaction:
                    transaction.verified = True
            if action == "complete":
                order.completed_at = utcnow()
        elif action == "cancel":
            await session.execute(
                update(Product).where(Product.id == order.product_id)
                .values(reserved_quantity=Product.reserved_quantity - order.quantity, updated_at=utcnow())
            )
        order.status = target
        if audit_action:
            session.add(
                AdminAuditLog(
                    admin_user_id=admin_id,
                    action=action,
                    target_order_id=order_id,
                    details=details[:2000],
                )
            )
    return order


async def audit(session: AsyncSession, admin_id: int, action: str, details: str, order_id: str | None = None) -> None:
    session.add(
        AdminAuditLog(
            admin_user_id=admin_id,
            action=action,
            target_order_id=order_id,
            details=details[:2000],
        )
    )
    await session.commit()


async def expire_due(session: AsyncSession) -> list[Order]:
    from bot.services.inventory import expire_orders

    return await expire_orders(session)


async def order_counts(session: AsyncSession) -> dict[str, int]:
    rows = (await session.execute(select(Order.status, func.count()).group_by(Order.status))).all()
    return {status: count for status, count in rows}


async def set_order_expiry(session: AsyncSession, order_id: str, minutes: int) -> None:
    order = await session.get(Order, order_id)
    if order:
        order.expires_at = utcnow() + timedelta(minutes=minutes)
        await session.commit()
