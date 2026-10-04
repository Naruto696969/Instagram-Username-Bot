import unittest

from bot.database.session import normalize_database_url


class DatabaseUrlTests(unittest.TestCase):
    def test_render_postgres_url_uses_asyncpg_driver(self):
        self.assertEqual(
            normalize_database_url("postgres://user:secret@host/db"),
            "postgresql+asyncpg://user:secret@host/db",
        )
        self.assertEqual(
            normalize_database_url("postgresql://user:secret@host/db"),
            "postgresql+asyncpg://user:secret@host/db",
        )

    def test_existing_async_urls_are_unchanged(self):
        sqlite_url = "sqlite+aiosqlite:///bot.db"
        postgres_url = "postgresql+asyncpg://user:secret@host/db"
        self.assertEqual(normalize_database_url(sqlite_url), sqlite_url)
        self.assertEqual(normalize_database_url(postgres_url), postgres_url)


if __name__ == "__main__":
    unittest.main()
