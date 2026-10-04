from aiogram.fsm.state import State, StatesGroup


class UserOrderStates(StatesGroup):
    waiting_for_transaction_hash = State()


class AdminInputStates(StatesGroup):
    waiting_for_stock_quantity = State()
    waiting_for_price = State()
    confirming_price = State()
    waiting_for_order_search = State()
    waiting_for_broadcast = State()
    confirming_broadcast = State()
