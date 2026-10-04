from decimal import Decimal

import httpx

from bot.payments.base import PaymentCheck


class SolanaPaymentProvider:
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url

    async def _rpc(self, method: str, params: list):
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(
                self.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            )
            response.raise_for_status()
            result = response.json()
        if result.get("error"):
            raise ValueError("Solana RPC returned an error")
        return result.get("result")

    async def get_transaction(self, transaction_hash: str) -> PaymentCheck:
        tx = await self._rpc(
            "getTransaction",
            [transaction_hash, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}],
        )
        if not tx:
            return PaymentCheck(False, message="Transaction not found or not confirmed")
        confirmations, failed = await self._signature_status(transaction_hash)
        if failed:
            return PaymentCheck(False, confirmations=confirmations, message="Transaction failed")
        return PaymentCheck(
            True,
            confirmations=confirmations,
            message="Transaction located",
        )

    async def get_confirmations(self, transaction_hash: str) -> int:
        return (await self.get_transaction(transaction_hash)).confirmations

    async def _signature_status(self, transaction_hash: str) -> tuple[int, bool]:
        result = await self._rpc(
            "getSignatureStatuses",
            [[transaction_hash], {"searchTransactionHistory": True}],
        )
        statuses = (result or {}).get("value") or []
        status = statuses[0] if statuses else None
        if status is None:
            return 0, False
        if status.get("err"):
            return int(status.get("confirmations") or 0), True
        confirmations = status.get("confirmations")
        if confirmations is None and status.get("confirmationStatus") == "finalized":
            return 2**31 - 1, False
        return int(confirmations or 0), False

    async def verify_payment(self, transaction_hash: str, receiving_address: str, expected_amount: Decimal, required_confirmations: int) -> PaymentCheck:
        tx = await self._rpc(
            "getTransaction",
            [transaction_hash, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}],
        )
        if not tx:
            return PaymentCheck(False, message="Transaction not found or not confirmed")
        confirmations, failed = await self._signature_status(transaction_hash)
        meta = tx.get("meta") or {}
        received_lamports = 0
        for instruction in (tx.get("transaction", {}).get("message", {}).get("instructions", [])):
            parsed = instruction.get("parsed", {})
            info = parsed.get("info", {})
            if parsed.get("type") == "transfer" and info.get("destination") == receiving_address:
                received_lamports += int(info.get("lamports", 0))
        amount = Decimal(received_lamports) / Decimal(10**9)
        ok = amount >= expected_amount and confirmations >= required_confirmations and not meta.get("err") and not failed
        return PaymentCheck(True, amount, confirmations, receiving_address, "Verified" if ok else "Amount or confirmations insufficient")
