from enum import Enum

class UserState(str, Enum):
    """Состояния пользователя в диалогах"""
    NONE = "none"
    
    # Состояния продажи
    SELL_AWAITING_PHONE = "sell_awaiting_phone"
    SELL_AWAITING_DESCRIPTION = "sell_awaiting_description"
    SELL_AWAITING_PRICE = "sell_awaiting_price"
    SELL_AWAITING_CONFIRMATION = "sell_awaiting_confirmation"
    SELL_AWAITING_CODE = "sell_awaiting_code"
    SELL_AWAITING_PASSWORD = "sell_awaiting_password"
    
    # Состояния перепродажи
    RESALE_AWAITING_DESCRIPTION = "resale_awaiting_description"
    RESALE_AWAITING_PRICE = "resale_awaiting_price"
    RESALE_AWAITING_CONFIRMATION = "resale_awaiting_confirmation"
    
    # Админские состояния
    ADMIN_AWAITING_USERNAME = "admin_awaiting_username"
    ADMIN_AWAITING_AMOUNT = "admin_awaiting_amount"
