from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Claimer", callback_data="shop:category:claimer")],
            [InlineKeyboardButton(text="🔄 Swapper", callback_data="shop:category:swapper")],
            [InlineKeyboardButton(text="📦 Available Stock", callback_data="shop:stock")],
            [InlineKeyboardButton(text="💳 Deposit / Payment", callback_data="payment:info")],
            [InlineKeyboardButton(text="📋 My Orders", callback_data="orders:list")],
            [InlineKeyboardButton(text="📜 Terms & Conditions", callback_data="terms:show")],
            [InlineKeyboardButton(text="🆘 Support", callback_data="support:open")],
        ]
    )


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back", callback_data="menu:home")]])


def product_list(products) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"{product.name} · ${product.usd_price:,.2f}"
                    + (
                        " · 🟢 Available"
                        if product.enabled and product.available_quantity > 0
                        else " · 🔴 SOLD OUT"
                    )
                ),
                callback_data=f"shop:product:{product.id}",
            )
        ]
        for product in products
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Main Menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_page(product, accepted: bool) -> InlineKeyboardMarkup:
    rows = []
    if product.available_quantity > 0 and product.enabled:
        rows.append([InlineKeyboardButton(text="💳 Buy", callback_data=f"shop:buy:{product.id}")])
    else:
        rows.append([InlineKeyboardButton(text="🔔 Notify Me", callback_data=f"shop:notify:{product.id}")])
    rows.append([InlineKeyboardButton(text="📜 Terms", callback_data="terms:show")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=f"shop:category:{product.category}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def terms_page(accepted: bool, product_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    if not accepted:
        callback = f"terms:agree:{product_id}" if product_id is not None else "terms:agree"
        rows.append([InlineKeyboardButton(text="✅ I Agree", callback_data=callback)])
    rows.append([InlineKeyboardButton(text="⬅️ Main Menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def currency_picker(order_id: str) -> InlineKeyboardMarkup:
    currencies = ("SOL", "ETH", "BTC", "LTC")
    rows = [
        [InlineKeyboardButton(text=currency, callback_data=f"pay:currency:{order_id}:{currency}")]
        for currency in currencies
    ]
    rows.append([InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"orders:cancel:{order_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_actions(order_id: str, allow_cancel: bool = True) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔍 Check Payment", callback_data=f"pay:check:{order_id}")],
        [InlineKeyboardButton(text="📤 Submit TX Hash", callback_data=f"pay:submit:{order_id}")],
    ]
    if allow_cancel:
        rows.append([InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"orders:cancel:{order_id}")])
    rows.append([InlineKeyboardButton(text="📋 My Orders", callback_data="orders:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_list(orders) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"#{order.order_id} · {order.status}", callback_data=f"orders:view:{order.order_id}")]
        for order in orders
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Main Menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_cancel(order_id: str, cancellable: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if cancellable:
        rows.append([InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"orders:cancel:{order_id}")])
    rows.append([InlineKeyboardButton(text="📋 My Orders", callback_data="orders:list")])
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )
