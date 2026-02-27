from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def back_keyboard(destination="main"):
    """Кнопка назад"""
    if destination == "main":
        callback = "back_to_main"
    elif destination == "market":
        callback = "back_to_market"
    elif destination == "purchases":
        callback = "back_to_purchases"
    else:
        callback = "back_to_main"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=callback)]]
    return InlineKeyboardMarkup(keyboard)

def main_menu_keyboard(is_admin=False):
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton("🏪 Рынок", callback_data="market")],
        [InlineKeyboardButton("💰 Продать", callback_data="sell")],
        [InlineKeyboardButton("📦 Мои покупки", callback_data="my_purchases")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton("💳 Пополнить", callback_data="deposit"),
         InlineKeyboardButton("💸 Вывести", callback_data="withdraw")]
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(keyboard)

def admin_panel_keyboard():
    """Админ-панель"""
    keyboard = [
        [InlineKeyboardButton("➕ Пополнить баланс", callback_data="admin_add_balance")],
        [InlineKeyboardButton("➖ Списать баланс", callback_data="admin_subtract_balance")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def market_keyboard(accounts):
    """Клавиатура рынка"""
    keyboard = []
    for acc in accounts[:10]:
        btn_text = f"📱 #{acc['account_id']} - {acc['phone_number']} - {acc['price']}₽"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"item_{acc['account_id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def confirmation_keyboard(action, item_id=None):
    """Клавиатура подтверждения"""
    if action == 'sell':
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_sell")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_sell")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("✅ Купить", callback_data=f"confirm_buy_{item_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_buy")]
        ]
    return InlineKeyboardMarkup(keyboard)

def resale_confirmation_keyboard():
    """Клавиатура подтверждения перепродажи"""
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить перепродажу", callback_data="confirm_resale")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_resale")]
    ]
    return InlineKeyboardMarkup(keyboard)

def item_details_keyboard(account_id):
    """Клавиатура для деталей товара с проверкой"""
    keyboard = [
        [InlineKeyboardButton("🔍 Проверить валидность", callback_data=f"validate_before_buy_{account_id}")],
        [InlineKeyboardButton("✅ Купить", callback_data=f"confirm_buy_{account_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_market")]
    ]
    return InlineKeyboardMarkup(keyboard)

def purchases_keyboard(purchases):
    """Клавиатура списка покупок"""
    keyboard = []
    for purchase in purchases[:10]:
        btn_text = f"📱 #{purchase['account_id']} - {purchase['phone_number']} - {purchase['price']}₽"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"purchase_{purchase['account_id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def purchase_action_keyboard(account_id, has_cloud_password=False, can_resale=True):
    """Клавиатура действий с купленным товаром"""
    keyboard = []
    
    keyboard.append([InlineKeyboardButton("🔑 Получить код", callback_data=f"get_code_{account_id}")])
    
    if has_cloud_password:
        keyboard.append([InlineKeyboardButton("☁️ Облачный пароль", callback_data=f"get_cloud_{account_id}")])
    
    if can_resale:
        keyboard.append([InlineKeyboardButton("🔄 Перепродать", callback_data=f"resale_{account_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_purchases")])
    
    return InlineKeyboardMarkup(keyboard)
