from datetime import datetime
from decimal import Decimal


def usd(amount: Decimal) -> str:
    return f"${amount:,.2f}".removesuffix(".00")


def order_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC")


def safe_text(value: str, limit: int = 3500) -> str:
    return value[:limit]
