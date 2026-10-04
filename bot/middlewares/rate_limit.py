from collections import defaultdict, deque
from time import monotonic

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self.events: dict[int, deque[float]] = defaultdict(deque)
        self.callback_ids: dict[int, deque[str]] = defaultdict(deque)

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        now = monotonic()
        history = self.events[user.id]
        while history and history[0] < now - 60:
            history.popleft()
        if len(history) >= self.max_per_minute:
            if isinstance(event, CallbackQuery):
                await event.answer("Please slow down and try again shortly.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("Please slow down and try again shortly.")
            return None
        history.append(now)
        if isinstance(event, CallbackQuery):
            ids = self.callback_ids[user.id]
            while len(ids) >= 100:
                ids.popleft()
            if event.id in ids:
                await event.answer("This action was already received.")
                return None
            ids.append(event.id)
        return await handler(event, data)
