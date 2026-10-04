from decimal import Decimal

import httpx

from bot.payments.base import PaymentCheck


class EthereumPaymentProvider:
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url

    async def _rpc(self, method: str, params: list):
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                self.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            )
            response.raise_for_status()
            result = response.json()
        if result.get("error"):
            raise ValueError("Ethereum RPC returned an error")
        return result.get("result")

    async def get_transaction(self, transaction_hash: str) -> PaymentCheck:
        tx, receipt, block = await self._rpc("eth_getTransactionByHash", [transaction_hash]), await self._rpc(
            "eth_getTransactionReceipt", [transaction_hash]
        ), await self._rpc("eth_blockNumber", [])
        if not tx or not receipt:
            return PaymentCheck(False, message="Transaction not mined")
        if receipt.get("status") != "0x1":
            return PaymentCheck(False, message="Transaction failed")
        confirmations = max(0, int(block, 16) - int(receipt["blockNumber"], 16) + 1)
        amount = Decimal(int(tx.get("value", "0x0"), 16)) / Decimal(10**18)
        return PaymentCheck(True, amount, confirmations, tx.get("to"), "Transaction located")

    async def get_confirmations(self, transaction_hash: str) -> int:
        return (await self.get_transaction(transaction_hash)).confirmations

    async def verify_payment(self, transaction_hash: str, receiving_address: str, expected_amount: Decimal, required_confirmations: int) -> PaymentCheck:
        check = await self.get_transaction(transaction_hash)
        valid = (
            check.found
            and (check.destination or "").lower() == receiving_address.lower()
            and (check.amount or Decimal(0)) >= expected_amount
            and check.confirmations >= required_confirmations
        )
        return PaymentCheck(check.found, check.amount, check.confirmations, check.destination, "Verified" if valid else "Amount, destination, or confirmations insufficient")
