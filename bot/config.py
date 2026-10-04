from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    database_url: str
    wallets: dict[str, str]
    support_username: str
    order_expiry_minutes: int
    confirmations: dict[str, int]
    manual_payment_approval: bool
    terms_version: str
    terms_text: str
    crypto_price_api_url: str
    crypto_price_api_key: str
    btc_api_url: str
    eth_api_url: str
    sol_api_url: str
    ltc_api_url: str
    high_value_order_usd: Decimal
    rate_limit_per_minute: int
    broadcast_max_users: int

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        admin_ids: set[int] = set()
        for raw_id in os.getenv("ADMIN_IDS", "").split(","):
            if raw_id.strip():
                try:
                    admin_ids.add(int(raw_id.strip()))
                except ValueError as exc:
                    raise ValueError("ADMIN_IDS must be comma-separated Telegram user IDs") from exc
        return cls(
            bot_token=os.getenv("BOT_TOKEN", "").strip(),
            admin_ids=frozenset(admin_ids),
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db").strip(),
            wallets={
                "SOL": os.getenv("SOL_ADDRESS", "").strip(),
                "ETH": os.getenv("ETH_ADDRESS", "").strip(),
                "BTC": os.getenv("BTC_ADDRESS", "").strip(),
                "LTC": os.getenv("LTC_ADDRESS", "").strip(),
            },
            support_username=os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@"),
            order_expiry_minutes=max(1, _as_int(os.getenv("ORDER_EXPIRY_MINUTES"), 30)),
            confirmations={
                "BTC": max(1, _as_int(os.getenv("BTC_CONFIRMATIONS"), 2)),
                "ETH": max(1, _as_int(os.getenv("ETH_CONFIRMATIONS"), 12)),
                "SOL": max(1, _as_int(os.getenv("SOL_CONFIRMATIONS"), 32)),
                "LTC": max(1, _as_int(os.getenv("LTC_CONFIRMATIONS"), 6)),
            },
            manual_payment_approval=_as_bool(os.getenv("MANUAL_PAYMENT_APPROVAL"), True),
            terms_version=os.getenv("TERMS_VERSION", "1").strip(),
            terms_text=(os.getenv("TERMS_TEXT", "").strip() or
                "Digital services are provided as described on each product page. "
                "Orders are processed after payment is verified. Cryptocurrency "
                "payments are generally irreversible. Never share wallet passwords, "
                "private keys, or seed phrases with anyone."),
            crypto_price_api_url=os.getenv("CRYPTO_PRICE_API_URL", "").strip(),
            crypto_price_api_key=os.getenv("CRYPTO_PRICE_API_KEY", "").strip(),
            btc_api_url=os.getenv("BTC_API_URL", "https://mempool.space/api").strip().rstrip("/"),
            eth_api_url=os.getenv("ETH_API_URL", "").strip().rstrip("/"),
            sol_api_url=os.getenv("SOL_API_URL", "").strip(),
            ltc_api_url=os.getenv("LTC_API_URL", "").strip().rstrip("/"),
            high_value_order_usd=Decimal(os.getenv("HIGH_VALUE_ORDER_USD", "1000")),
            rate_limit_per_minute=max(5, _as_int(os.getenv("RATE_LIMIT_PER_MINUTE"), 30)),
            broadcast_max_users=max(1, _as_int(os.getenv("BROADCAST_MAX_USERS"), 5000)),
        )
