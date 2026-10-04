from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_UP

import httpx

from bot.config import Settings


COIN_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "LTC": "litecoin"}


async def quote_crypto_amount(settings: Settings, currency: str, usd_amount: Decimal) -> Decimal | None:
    if not settings.crypto_price_api_url:
        return None
    url = settings.crypto_price_api_url
    headers = {"x-cg-demo-api-key": settings.crypto_price_api_key} if settings.crypto_price_api_key else {}
    params = {"ids": COIN_IDS[currency], "vs_currencies": "usd"}
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
    try:
        usd_per_coin = Decimal(str(data[COIN_IDS[currency]]["usd"]))
        if usd_per_coin <= 0:
            return None
        return (usd_amount / usd_per_coin).quantize(Decimal("0.00000001"), rounding=ROUND_UP)
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise ValueError("The configured crypto price API returned an invalid response") from exc
