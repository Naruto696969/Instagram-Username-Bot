import unittest
from decimal import Decimal

from bot.database.models import Product
from bot.handlers.texts import product_text
from bot.keyboards.admin import stock_dashboard
from bot.keyboards.user import product_page


class CatalogStockDisplayTests(unittest.TestCase):
    def make_product(self, *, stock: int, enabled: bool = True) -> Product:
        return Product(
            id=1,
            name="3L Claimer",
            category="claimer",
            description="Test service",
            usd_price=Decimal("1500"),
            stock_quantity=stock,
            reserved_quantity=0,
            enabled=enabled,
        )

    def test_empty_product_shows_sold_out_and_notify_not_buy(self):
        product = self.make_product(stock=0)
        text = product_text(product)
        callbacks = [
            button.callback_data
            for row in product_page(product, accepted=True).inline_keyboard
            for button in row
        ]
        self.assertIn("🔴 SOLD OUT", text)
        self.assertIn("shop:notify:1", callbacks)
        self.assertNotIn("shop:buy:1", callbacks)

    def test_admin_stock_dashboard_has_stock_and_availability_actions(self):
        product = self.make_product(stock=4)
        callbacks = [
            button.callback_data
            for row in stock_dashboard([product]).inline_keyboard
            for button in row
        ]
        self.assertIn("admin:stockop:add:1", callbacks)
        self.assertIn("admin:stockop:remove:1", callbacks)
        self.assertIn("admin:stockop:set:1", callbacks)
        self.assertIn("admin:delete:ask:1", callbacks)
        self.assertIn("admin:availability:1:on", callbacks)
        self.assertIn("admin:availability:1:off", callbacks)

    def test_manually_disabled_product_is_sold_out_even_with_stock(self):
        product = self.make_product(stock=4, enabled=False)
        self.assertIn("🔴 SOLD OUT", product_text(product))


if __name__ == "__main__":
    unittest.main()
