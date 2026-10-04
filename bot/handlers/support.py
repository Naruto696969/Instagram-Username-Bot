from aiogram import Router
from aiogram.types import CallbackQuery

from bot.config import Settings
from bot.keyboards.user import back_home

router = Router()


@router.callback_query(lambda query: query.data == "support:open")
async def support(callback: CallbackQuery, settings: Settings):
    if settings.support_username:
        text = f"🆘 <b>Support</b>\n\nFor help with orders or payments, contact @{settings.support_username}."
    else:
        text = "🆘 <b>Support</b>\n\nSupport contact is not configured yet."
    await callback.message.edit_text(text, reply_markup=back_home())
    await callback.answer()


@router.callback_query(lambda query: query.data == "payment:info")
async def payment_info(callback: CallbackQuery):
    await callback.message.edit_text(
        "💳 <b>Deposit / Payment</b>\n\n"
        "Payments are linked to a specific order. Start a purchase and select SOL, ETH, BTC, or LTC to receive its payment instructions. "
        "Do not send funds without an active order, and never share private keys or seed phrases.",
        reply_markup=back_home(),
    )
    await callback.answer()
