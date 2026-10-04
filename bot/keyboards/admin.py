from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_menu() -> InlineKeyboardMarkup:
    labels = [
        ("📦 Manage Stock", "admin:stock"),
        ("💰 Manage Prices", "admin:prices"),
        ("📋 Orders", "admin:orders"),
        ("🔎 Search Order", "admin:search"),
        ("✅ Approve Payment", "admin:review"),
        ("❌ Reject Payment", "admin:review"),
        ("📊 Statistics", "admin:stats"),
        ("⚙️ Products", "admin:products"),
        ("📢 Broadcast", "admin:broadcast"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in labels]
        + [[InlineKeyboardButton(text="⬅️ Main Menu", callback_data="menu:home")]]
    )


def product_admin_list(products, action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=product.name, callback_data=f"admin:{action}:{product.id}")]
            for product in products
        ]
        + [[InlineKeyboardButton(text="⬅️ Admin Menu", callback_data="admin:home")]]
    )


def stock_dashboard(products) -> InlineKeyboardMarkup:
    rows = []
    for product in products:
        rows.append(
            [
                InlineKeyboardButton(text="➕ Add Stock", callback_data=f"admin:stockop:add:{product.id}"),
                InlineKeyboardButton(text="➖ Remove Stock", callback_data=f"admin:stockop:remove:{product.id}"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="✏️ Set Stock", callback_data=f"admin:stockop:set:{product.id}"),
                InlineKeyboardButton(text="🗑 Delete Stock", callback_data=f"admin:delete:ask:{product.id}"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🟢 Available" + (" ✓" if product.enabled else ""),
                    callback_data=f"admin:availability:{product.id}:on",
                ),
                InlineKeyboardButton(
                    text="🔴 Sold Out" + (" ✓" if not product.enabled else ""),
                    callback_data=f"admin:availability:{product.id}:off",
                ),
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Admin Menu", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_product_confirmation(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Confirm Delete", callback_data=f"admin:delete:confirm:{product_id}")],
            [InlineKeyboardButton(text="❌ Keep Product", callback_data="admin:stock")],
        ]
    )


def admin_order_list(orders) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"#{order.order_id} · {order.status}", callback_data=f"admin:order:{order.order_id}")]
            for order in orders
        ]
        + [[InlineKeyboardButton(text="⬅️ Admin Menu", callback_data="admin:home")]]
    )


def admin_order_actions(order) -> InlineKeyboardMarkup:
    rows = []
    if order.status == "payment_detected":
        rows.append([InlineKeyboardButton(text="✅ Approve", callback_data=f"admin:approve:{order.order_id}"),
                     InlineKeyboardButton(text="❌ Reject", callback_data=f"admin:reject:{order.order_id}")])
    if order.status == "paid":
        rows.append([InlineKeyboardButton(text="⚙️ Mark Processing", callback_data=f"admin:processing:{order.order_id}")])
    if order.status == "processing":
        rows.append([InlineKeyboardButton(text="✅ Mark Completed", callback_data=f"admin:complete:{order.order_id}")])
    if order.status in {"pending", "awaiting_payment", "payment_detected"}:
        rows.append([InlineKeyboardButton(text="🚫 Cancel", callback_data=f"admin:cancel:{order.order_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orders", callback_data="admin:orders")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def price_confirmation() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm price", callback_data="admin:priceconfirm")],
            [InlineKeyboardButton(text="❌ Discard", callback_data="admin:pricediscard")],
        ]
    )


def broadcast_confirmation() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Send broadcast", callback_data="admin:broadcastconfirm")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="admin:broadcastcancel")],
        ]
    )
