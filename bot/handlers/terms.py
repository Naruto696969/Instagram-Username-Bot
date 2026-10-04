from html import escape

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.database.models import Product
from bot.handlers.texts import product_text
from bot.keyboards.user import product_page, terms_page
from bot.services.orders import accept_terms, has_accepted_terms

router = Router()


@router.callback_query(lambda query: query.data == "terms:show")
async def terms_show(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    accepted = await has_accepted_terms(session, callback.from_user.id, settings.terms_version)
    await callback.message.edit_text(
        f"📜 <b>Terms &amp; Conditions · Version {settings.terms_version}</b>\n\n"
        f"{escape(settings.terms_text)}\n\n"
        + ("✅ You have accepted this version." if accepted else "Please accept these terms before purchasing."),
        reply_markup=terms_page(accepted),
    )
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("terms:agree"))
async def terms_agree(callback: CallbackQuery, session: AsyncSession, settings: Settings):
    await accept_terms(session, callback.from_user.id, settings.terms_version)
    parts = callback.data.split(":")
    if len(parts) == 3:
        try:
            product_id = int(parts[2])
        except ValueError:
            await callback.answer("Invalid product.", show_alert=True)
            return
        product = await session.get(Product, product_id)
        if product is None or product.deleted:
            await callback.answer("This product is unavailable.", show_alert=True)
            return
        await callback.message.edit_text(
            "✅ Terms accepted.\n\n" + product_text(product),
            reply_markup=product_page(product, True),
        )
    else:
        await callback.message.edit_text(
            f"✅ You accepted Terms &amp; Conditions version {settings.terms_version}.",
            reply_markup=terms_page(True),
        )
    await callback.answer("Terms accepted.")
