from bot.config import Settings
from bot.payments.bitcoin import BitcoinPaymentProvider
from bot.payments.ethereum import EthereumPaymentProvider
from bot.payments.litecoin import LitecoinPaymentProvider
from bot.payments.solana import SolanaPaymentProvider


def get_provider(settings: Settings, currency: str):
    if currency == "BTC":
        return BitcoinPaymentProvider(settings.btc_api_url)
    if currency == "ETH" and settings.eth_api_url:
        return EthereumPaymentProvider(settings.eth_api_url)
    if currency == "SOL" and settings.sol_api_url:
        return SolanaPaymentProvider(settings.sol_api_url)
    if currency == "LTC" and settings.ltc_api_url:
        return LitecoinPaymentProvider(settings.ltc_api_url)
    raise ValueError(f"{currency} blockchain verification is not configured")
