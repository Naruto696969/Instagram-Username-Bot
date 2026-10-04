from decimal import Decimal

import httpx

from bot.payments.base import PaymentCheck


class LitecoinPaymentProvider:
    """Uses a Litecoin mempool.space-compatible explorer API endpoint."""

    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")

    async def get_transaction(self, transaction_hash: str) -> PaymentCheck:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.api_url}/tx/{transaction_hash}")
            if response.status_code == 404:
                return PaymentCheck(False, message="Transaction not found")
            response.raise_for_status()
            tx = response.json()
            status = tx.get("status", {})
            height = status.get("block_height")
            tip = await client.get(f"{self.api_url}/blocks/tip/height")
            tip.raise_for_status()
            confirmations = max(0, int(tip.text) - int(height) + 1) if height else 0
            return PaymentCheck(
                True,
                Decimal(sum(int(v.get("value", 0)) for v in tx.get("vout", []))) / Decimal(100_000_000),
                confirmations,
                message="Transaction located",
            )

    async def get_confirmations(self, transaction_hash: str) -> int:
        return (await self.get_transaction(transaction_hash)).confirmations

    async def verify_payment(self, transaction_hash: str, receiving_address: str, expected_amount: Decimal, required_confirmations: int) -> PaymentCheck:
        check = await self.get_transaction(transaction_hash)
        if not check.found:
            return check
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.api_url}/tx/{transaction_hash}")
            response.raise_for_status()
            tx = response.json()
        received = sum(
            (Decimal(int(output.get("value", 0))) / Decimal(100_000_000))
            for output in tx.get("vout", [])
            if output.get("scriptpubkey_address") == receiving_address
        )
        ok = received >= expected_amount and check.confirmations >= required_confirmations
        return PaymentCheck(True, received, check.confirmations, receiving_address, "Verified" if ok else "Amount or confirmations insufficient")
