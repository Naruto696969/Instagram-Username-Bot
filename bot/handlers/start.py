from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.texts import home_text
from bot.keyboards.user import main_menu
from bot.services.orders import ensure_user

router = Router()


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession):
    await ensure_user(session, message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(home_text(), reply_markup=main_menu())


@router.callback_query(lambda query: query.data == "menu:home")
async def home(callback: CallbackQuery):
    await callback.message.edit_text(home_text(), reply_markup=main_menu())
    await callback.answer()
