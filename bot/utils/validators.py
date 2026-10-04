import re


TX_HASH_PATTERNS = {
    "BTC": re.compile(r"^[a-fA-F0-9]{64}$"),
    "LTC": re.compile(r"^[a-fA-F0-9]{64}$"),
    "ETH": re.compile(r"^0x[a-fA-F0-9]{64}$"),
    "SOL": re.compile(r"^[1-9A-HJ-NP-Za-km-z]{64,100}$"),
}


def valid_transaction_hash(currency: str, value: str) -> bool:
    pattern = TX_HASH_PATTERNS.get(currency)
    return bool(pattern and pattern.fullmatch(value.strip()))


def parse_positive_int(value: str) -> int:
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("Enter a whole number greater than zero.")
    return int(value)
