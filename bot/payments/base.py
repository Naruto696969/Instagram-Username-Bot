from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class PaymentCheck:
    found: bool
    amount: Decimal | None = None
    confirmations: int = 0
    destination: str | None = None
    message: str = ""


class PaymentProvider(Protocol):
    async def verify_payment(
        self,
        transaction_hash: str,
        receiving_address: str,
        expected_amount: Decimal,
        required_confirmations: int,
    ) -> PaymentCheck: ...

    async def get_transaction(self, transaction_hash: str) -> PaymentCheck: ...

    async def get_confirmations(self, transaction_hash: str) -> int: ...
