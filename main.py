#!/usr/bin/env python3
import asyncio
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Запуск всего говна"""
    from handlers import start_polling
    from userbot import user_bot
    
    logger.info("🚀 Запуск Маркетплейс Бота")
    
    # Запускаем основного бота
    await start_polling()
    
    # Юзер-бот запускается автоматически при продаже, не нужен отдельно

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Остановлено")
        sys.exit(0)
