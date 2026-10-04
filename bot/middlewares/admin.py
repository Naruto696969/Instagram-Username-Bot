from aiogram.filters import BaseFilter
from aiogram.types import Message


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message, settings) -> bool:
        return bool(event.from_user and event.from_user.id in settings.admin_ids)
