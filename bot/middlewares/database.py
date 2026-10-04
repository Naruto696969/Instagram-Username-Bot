from aiogram import BaseMiddleware


class DatabaseSessionMiddleware(BaseMiddleware):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def __call__(self, handler, event, data):
        async with self.session_factory() as session:
            data["session"] = session
            return await handler(event, data)
