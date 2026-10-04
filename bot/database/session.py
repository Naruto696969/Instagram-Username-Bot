from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.database.base import Base


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


def create_database(database_url: str):
    engine = create_async_engine(normalize_database_url(database_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def initialize_database(engine, session_factory) -> None:
    import bot.database.models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        product_columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"] for column in inspect(sync_connection).get_columns("products")
            }
        )
        if "deleted" not in product_columns:
            await connection.exec_driver_sql(
                "ALTER TABLE products ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT FALSE"
            )
    from bot.services.inventory import seed_products

    async with session_factory() as session:
        await seed_products(session)
