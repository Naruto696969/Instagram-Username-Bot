import unittest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import Product
from bot.database.session import initialize_database


class DatabaseUpgradeTests(unittest.IsolatedAsyncioTestCase):
    async def test_adds_availability_column_to_existing_database(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.exec_driver_sql(
                    """
                    CREATE TABLE products (
                        id INTEGER PRIMARY KEY,
                        name VARCHAR(120) NOT NULL UNIQUE,
                        category VARCHAR(40) NOT NULL,
                        description TEXT NOT NULL,
                        usd_price NUMERIC(12, 2) NOT NULL,
                        stock_quantity INTEGER NOT NULL DEFAULT 0,
                        reserved_quantity INTEGER NOT NULL DEFAULT 0,
                        enabled BOOLEAN NOT NULL DEFAULT 1,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
            await initialize_database(engine, session_factory)
            async with session_factory() as session:
                product = await session.scalar(
                    select(Product).where(Product.name == "3L Claimer")
                )
                self.assertIsNotNone(product)
                self.assertFalse(product.deleted)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
