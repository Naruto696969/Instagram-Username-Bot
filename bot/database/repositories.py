from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Order, Product


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    return await session.get(Product, product_id)


async def get_order(session: AsyncSession, order_id: str) -> Order | None:
    return await session.scalar(select(Order).where(Order.order_id == order_id.upper()))
