"""
Конфигурация бота - ЗАПОЛНИ РЕАЛЬНЫМИ ДАННЫМИ!
"""
import os
from typing import List, Dict, Any

# ТОКЕН БОТА (получить у @BotFather)
BOT_TOKEN = "8499868686:AAGIAYJLKdghpe9ktHb1QZ8m9Y9m_QpDQv0"

# Данные для юзер-бота (получить на my.telegram.org)
API_ID = 20749177  # ЗАМЕНИТЬ!
API_HASH = "c4547190111b94e25c82a8f01d07ca43"  # ЗАМЕНИТЬ!

# ID АДМИНОВ (узнать у @userinfobot)
ADMIN_IDS: List[int] = [7833861550, 8489177322]  # ЗАМЕНИТЬ!

# Настройки
DATABASE_PATH = "marketplace.db"
SESSION_DIR = "sessions"
CODE_PATTERN = r'code(\d{5,6})'  # Формат: code12345
