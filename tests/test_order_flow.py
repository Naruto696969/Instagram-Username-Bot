import unittest
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.base import Base
from bot.database.models import AdminAuditLog, Order, Product, User
from bot.services.inventory import (
    delete_product,
    expire_orders,
    reserve_order,
    seed_products,
    set_product_enabled,
    set_stock,
)
from bot.services.orders import select_payment, submit_transaction, transition_order


class OrderFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with self.session_factory() as session:
            await seed_products(session)
            product = await session.scalar(select(Product).where(Product.name == "Swapper"))
            product.stock_quantity = 1
            user = User(telegram_user_id=1234, username="buyer", first_name="Buyer")
            session.add(user)
            await session.commit()
            self.product_id = product.id
            self.user = user

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_paid_order_decrements_stock_exactly_once(self):
        async with self.session_factory() as session:
            order = await reserve_order(
                session, order_id="TEST0001", user=self.user, product_id=self.product_id, expiry_minutes=30
            )
            self.assertIsNotNone(order)
            product = await session.get(Product, self.product_id)
            self.assertEqual(product.stock_quantity, 1)
            self.assertEqual(product.reserved_quantity, 1)
            self.assertEqual(product.available_quantity, 0)

            await select_payment(session, order.order_id, self.user.telegram_user_id, "BTC", "bc1-test", Decimal("0.001"))
            await submit_transaction(session, order.order_id, self.user.telegram_user_id, "a" * 64, "BTC")
            order_id = order.order_id
            await transition_order(session, order_id, action="approve", admin_id=7)
            with self.assertRaises(ValueError):
                await transition_order(session, order_id, action="approve", admin_id=7)

            product = await session.get(Product, self.product_id)
            persisted_order = await session.get(Order, order_id)
            self.assertEqual(product.stock_quantity, 0)
            self.assertEqual(product.reserved_quantity, 0)
            self.assertEqual(persisted_order.status, "paid")

    async def test_cancel_releases_reserved_stock(self):
        async with self.session_factory() as session:
            order = await reserve_order(
                session, order_id="TEST0002", user=self.user, product_id=self.product_id, expiry_minutes=30
            )
            await transition_order(session, order.order_id, action="cancel", admin_id=7)
            product = await session.get(Product, self.product_id)
            self.assertEqual(product.stock_quantity, 1)
            self.assertEqual(product.reserved_quantity, 0)
            self.assertEqual(product.available_quantity, 1)

    async def test_expired_unpaid_order_releases_reservation(self):
        async with self.session_factory() as session:
            order = await reserve_order(
                session, order_id="TEST0003", user=self.user, product_id=self.product_id, expiry_minutes=0
            )
            expired = await expire_orders(session)
            self.assertEqual([entry.order_id for entry in expired], [order.order_id])
            product = await session.get(Product, self.product_id)
            self.assertEqual(product.reserved_quantity, 0)
            self.assertEqual((await session.get(Order, order.order_id)).status, "expired")

    async def test_stock_changes_are_audited_and_disabled_state_is_preserved(self):
        async with self.session_factory() as session:
            product = await set_stock(session, self.product_id, 3, "add", admin_user_id=7)
            self.assertEqual(product.stock_quantity, 4)
            await set_product_enabled(session, self.product_id, False, admin_user_id=7)
            product = await set_stock(session, self.product_id, 2, "add", admin_user_id=7)
            self.assertEqual(product.stock_quantity, 6)
            self.assertFalse(product.enabled)
            audit_rows = (
                await session.scalars(
                    select(AdminAuditLog).where(AdminAuditLog.admin_user_id == 7)
                )
            ).all()
            self.assertEqual(
                [entry.action for entry in audit_rows],
                ["stock_add", "product_disabled", "stock_add"],
            )

    async def test_stock_cannot_be_removed_from_reserved_quantity(self):
        async with self.session_factory() as session:
            await reserve_order(
                session, order_id="TEST0004", user=self.user, product_id=self.product_id, expiry_minutes=30
            )
            with self.assertRaisesRegex(ValueError, "reserved or unavailable"):
                await set_stock(session, self.product_id, 1, "remove", admin_user_id=7)
            product = await session.get(Product, self.product_id)
            self.assertEqual(product.stock_quantity, 1)
            self.assertEqual(product.reserved_quantity, 1)

    async def test_delete_archives_product_and_preserves_order_history(self):
        async with self.session_factory() as session:
            order = await reserve_order(
                session, order_id="TEST0005", user=self.user, product_id=self.product_id, expiry_minutes=30
            )
            order_id = order.order_id
            with self.assertRaisesRegex(ValueError, "reserved stock"):
                await delete_product(session, self.product_id, admin_user_id=7)
            await transition_order(session, order_id, action="cancel", admin_id=7)
            product = await delete_product(session, self.product_id, admin_user_id=7)
            persisted_order = await session.get(Order, order_id)
            self.assertTrue(product.deleted)
            self.assertEqual(product.stock_quantity, 0)
            self.assertEqual(persisted_order.product.name, "Swapper")
            audit_rows = (
                await session.scalars(
                    select(AdminAuditLog).where(
                        AdminAuditLog.admin_user_id == 7,
                        AdminAuditLog.action == "product_deleted",
                    )
                )
            ).all()
            self.assertEqual(len(audit_rows), 1)


if __name__ == "__main__":
    unittest.main()
