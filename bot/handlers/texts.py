from html import escape

from bot.utils.formatting import order_time, usd


def home_text() -> str:
    return "━━━━━━━━━━━━━━━━━━\n🛍️ <b>Digital Services Store</b>\n\nChoose a service or browse currently available stock.\n━━━━━━━━━━━━━━━━━━"


def product_text(product) -> str:
    availability = (
        f"🟢 {product.available_quantity} Available"
        if product.enabled and product.available_quantity > 0
        else "🔴 SOLD OUT"
    )
    return (
        f"📦 <b>{escape(product.category.upper())}</b>\n\n"
        f"<b>{escape(product.name)}</b>\n"
        f"💵 {usd(product.usd_price)}\n"
        f"📊 {availability}\n\n"
        f"{escape(product.description)}\n\n"
        "Please review the Terms &amp; Conditions before purchasing.\n"
        "━━━━━━━━━━━━━━━━━━"
    )


def order_text(order) -> str:
    product_name = escape(order.product.name)
    payment = escape(order.selected_currency or "Not selected")
    hash_line = f"\nTransaction: <code>{escape(order.transaction_hash)}</code>" if order.transaction_hash else ""
    address_line = f"\nReceiving address: <code>{escape(order.receiving_address)}</code>" if order.receiving_address else ""
    crypto_line = f"\nCrypto amount: {order.crypto_amount_expected} {payment}" if order.crypto_amount_expected else ""
    return (
        "━━━━━━━━━━━━━━━━━━\n"
        f"🧾 ORDER <code>#{order.order_id}</code>\n\n"
        f"Product: {product_name}\n"
        f"Amount: {usd(order.usd_total)}\n"
        f"Payment: {payment}\n"
        f"Status: <b>{escape(order.status.replace('_', ' ').title())}</b>\n"
        f"Created: {order_time(order.created_at)}"
        f"{address_line}{crypto_line}{hash_line}\n"
        "━━━━━━━━━━━━━━━━━━"
    )


def order_payment_text(order) -> str:
    currency = escape(order.selected_currency or "")
    amount = f"\nApproximate amount: <b>{order.crypto_amount_expected} {currency}</b>" if order.crypto_amount_expected else ""
    return (
        "━━━━━━━━━━━━━━━━━━\n"
        f"🧾 ORDER <code>#{order.order_id}</code>\n\n"
        f"Product: {escape(order.product.name)}\n"
        f"Amount owed: <b>{usd(order.usd_total)}</b>{amount}\n"
        f"Payment: <b>{currency}</b>\n\n"
        "Send payment to:\n\n"
        f"<code>{escape(order.receiving_address or '')}</code>\n\n"
        "After sending payment, submit the transaction hash or press Check Payment.\n"
        "━━━━━━━━━━━━━━━━━━"
    )
