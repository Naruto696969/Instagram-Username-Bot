from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AdminAuditLog, Order, Product, User, utcnow

ACTIVE_RESERVATION_STATUSES = ("pending", "awaiting_payment")


async def seed_products(session: AsyncSession) -> None:
    products = (
        ("3L Claimer", "claimer", "Digital 3L Claimer service.", Decimal("1500.00")),
        ("2L Claimer", "claimer", "Digital 2L Claimer service.", Decimal("5000.00")),
        ("Swapper", "swapper", "Digital Swapper service.", Decimal("50.00")),
    )
    for name, category, description, price in products:
        if await session.scalar(select(Product.id).where(Product.name == name)) is None:
            session.add(Product(name=name, category=category, description=description, usd_price=price))
    await session.commit()


async def reserve_order(
    session: AsyncSession,
    *,
    order_id: str,
    user: User,
    product_id: int,
    expiry_minutes: int,
) -> Order | None:
    if session.in_transaction():
        await session.commit()
    async with session.begin():
        result = await session.execute(
            update(Product)
            .where(
                Product.id == product_id,
                Product.enabled.is_(True),
                Product.deleted.is_(False),
                Product.stock_quantity - Product.reserved_quantity >= 1,
            )
            .values(reserved_quantity=Product.reserved_quantity + 1, updated_at=utcnow())
        )
        if result.rowcount != 1:
            return None
        product = await session.get(Product, product_id)
        if product is None:
            raise RuntimeError("Product disappeared while reserving stock")
        order = Order(
            order_id=order_id,
            telegram_user_id=user.telegram_user_id,
            telegram_username=user.username,
            product_id=product_id,
            quantity=1,
            usd_total=product.usd_price,
            status="pending",
            expires_at=utcnow() + timedelta(minutes=expiry_minutes),
        )
        session.add(order)
        await session.flush()
        return order


async def set_stock(
    session: AsyncSession,
    product_id: int,
    quantity: int,
    mode: str,
    admin_user_id: int,
) -> Product:
    if quantity < 0 or quantity > 1_000_000_000 or mode not in {"add", "remove", "set"}:
        raise ValueError("Invalid stock update")
    if session.in_transaction():
        await session.commit()
    async with session.begin():
        conditions = [Product.id == product_id, Product.deleted.is_(False)]
        if mode == "remove":
            conditions.append(Product.stock_quantity - Product.reserved_quantity >= quantity)
            values = {"stock_quantity": Product.stock_quantity - quantity}
        elif mode == "set":
            conditions.append(Product.reserved_quantity <= quantity)
            values = {"stock_quantity": quantity}
        else:
            conditions.append(Product.stock_quantity + quantity <= 1_000_000_000)
            values = {"stock_quantity": Product.stock_quantity + quantity}
        result = await session.execute(
            update(Product)
            .where(*conditions)
            .values(**values, updated_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            exists = await session.get(Product, product_id)
            if exists is None:
                raise ValueError("Product not found")
            if mode == "remove":
                raise ValueError("Cannot remove reserved or unavailable stock")
            if mode == "set":
                raise ValueError("Stock cannot be set below currently reserved units")
            if mode == "add":
                raise ValueError("Stock cannot exceed 1,000,000,000 units")
        product = await session.scalar(
            select(Product)
            .where(Product.id == product_id)
            .execution_options(populate_existing=True)
        )
        if product is None:
            raise ValueError("Product not found")
        session.add(
            AdminAuditLog(
                admin_user_id=admin_user_id,
                action=f"stock_{mode}",
                details=f"{product.name}: quantity={quantity}; stock={product.stock_quantity}; reserved={product.reserved_quantity}",
            )
        )
    return product


async def set_product_enabled(
    session: AsyncSession,
    product_id: int,
    enabled: bool,
    admin_user_id: int,
) -> Product:
    if session.in_transaction():
        await session.commit()
    async with session.begin():
        product = await session.scalar(
            select(Product)
            .where(Product.id == product_id, Product.deleted.is_(False))
            .with_for_update()
        )
        if product is None or product.deleted:
            raise ValueError("Product not found")
        product.enabled = enabled
        product.updated_at = utcnow()
        session.add(
            AdminAuditLog(
                admin_user_id=admin_user_id,
                action="product_enabled" if enabled else "product_disabled",
                details=f"{product.name}: enabled={enabled}; stock={product.stock_quantity}; reserved={product.reserved_quantity}",
            )
        )
    return product


async def delete_product(
    session: AsyncSession,
    product_id: int,
    admin_user_id: int,
) -> Product:
    if session.in_transaction():
        await session.commit()
    async with session.begin():
        product = await session.scalar(
            select(Product)
            .where(Product.id == product_id, Product.deleted.is_(False))
            .with_for_update()
        )
        if product is None:
            raise ValueError("Product not found")
        if product.reserved_quantity:
            raise ValueError("Cannot delete a product while orders have reserved stock")
        product.deleted = True
        product.enabled = False
        product.stock_quantity = 0
        product.updated_at = utcnow()
        session.add(
            AdminAuditLog(
                admin_user_id=admin_user_id,
                action="product_deleted",
                details=f"{product.name}: removed from storefront; retained for order history",
            )
        )
    return product


async def expire_orders(session: AsyncSession) -> list[Order]:
    expired: list[Order] = []
    async with session.begin():
        orders = (
            await session.scalars(
                select(Order)
                .where(Order.status.in_(ACTIVE_RESERVATION_STATUSES), Order.expires_at <= utcnow())
                .with_for_update()
            )
        ).all()
        for order in orders:
            result = await session.execute(
                update(Order).where(Order.order_id == order.order_id, Order.status.in_(ACTIVE_RESERVATION_STATUSES))
                .values(status="expired")
            )
            if result.rowcount:
                await session.execute(
                    update(Product).where(Product.id == order.product_id)
                    .values(reserved_quantity=Product.reserved_quantity - order.quantity, updated_at=utcnow())
                )
                order.status = "expired"
                expired.append(order)
    return expired
