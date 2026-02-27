"""
МОДУЛЬ ДЛЯ РАБОТЫ С АККАУНТАМИ TELEGRAM
ПОЛНАЯ РАБОЧАЯ ВЕРСИЯ
"""
import os
import logging
import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Callable, Awaitable
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import (
    PhoneCodeInvalidError, SessionPasswordNeededError, 
    PasswordHashInvalidError, FloodWaitError, PhoneNumberUnoccupiedError,
    PhoneCodeExpiredError, PhoneCodeEmptyError
)
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import InputPeerEmpty
from telethon.tl.functions.account import GetPasswordRequest
from telethon import functions, types

from database import Database

logger = logging.getLogger(__name__)

class AccountLoginError(Exception):
    """Ошибка входа в аккаунт"""
    pass

class LoginTimeoutError(Exception):
    """Таймаут при ожидании кода"""
    pass

class UserBot:
    """Класс для управления пользовательскими аккаунтами Telegram"""
    
    def __init__(self):
        self.sessions_dir = Path("sessions")
        self.sessions_dir.mkdir(exist_ok=True)
        self.active_clients: Dict[int, TelegramClient] = {}
        self.monitoring_tasks: Dict[int, asyncio.Task] = {}
        self.code_callbacks: Dict[int, Callable] = {}
        self.db = Database()
        self.api_id = None
        self.api_hash = None
        
        self._load_api_credentials()
    
    def _load_api_credentials(self):
        """Загружает API ID и Hash из конфига"""
        try:
            from config import API_ID, API_HASH
            self.api_id = API_ID
            self.api_hash = API_HASH
        except ImportError:
            logger.error("API_ID и API_HASH не найдены в config.py")
            raise
    
    def _get_session_path(self, phone: str) -> Path:
        """Возвращает путь к файлу сессии для номера"""
        clean_phone = re.sub(r'\D', '', phone)
        return self.sessions_dir / f"{clean_phone}.session"
    
    async def login_account(
        self, 
        phone: str, 
        code_callback: Callable[[], Awaitable[str]],
        password_callback: Optional[Callable[[], Awaitable[str]]] = None
    ) -> str:
        """Выполняет вход в аккаунт Telegram"""
        session_path = self._get_session_path(phone)
        
        if session_path.exists():
            session_path.unlink()
        
        client = TelegramClient(str(session_path), self.api_id, self.api_hash)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                await client.send_code_request(phone)
                logger.info(f"Код подтверждения отправлен на {phone}")
                
                max_attempts = 3
                for attempt in range(max_attempts):
                    try:
                        code_input = await code_callback()
                        
                        code = re.sub(r'\D', '', code_input)
                        if not code or len(code) != 5:
                            if attempt < max_attempts - 1:
                                await asyncio.sleep(1)
                                continue
                            raise AccountLoginError("Неверный формат кода. Код должен содержать 5 цифр.")
                        
                        try:
                            await client.sign_in(phone, code)
                            break
                            
                        except SessionPasswordNeededError:
                            logger.info(f"Требуется облачный пароль для {phone}")
                            
                            if password_callback is None:
                                raise AccountLoginError("Требуется облачный пароль (2FA)")
                            
                            password_attempts = 3
                            for p_attempt in range(password_attempts):
                                try:
                                    password = await password_callback()
                                    
                                    if not password:
                                        if p_attempt < password_attempts - 1:
                                            continue
                                        raise AccountLoginError("Облачный пароль не может быть пустым")
                                    
                                    await client.sign_in(password=password)
                                    break
                                    
                                except PasswordHashInvalidError:
                                    if p_attempt < password_attempts - 1:
                                        await asyncio.sleep(1)
                                        continue
                                    raise AccountLoginError("Неверный облачный пароль")
                            
                            break
                            
                        except PhoneCodeInvalidError:
                            if attempt < max_attempts - 1:
                                await asyncio.sleep(1)
                                continue
                            raise AccountLoginError("Неверный код подтверждения")
                            
                        except PhoneCodeExpiredError:
                            raise AccountLoginError("Код подтверждения истек. Запросите новый код.")
                            
                        except PhoneCodeEmptyError:
                            if attempt < max_attempts - 1:
                                continue
                            raise AccountLoginError("Код не может быть пустым")
                            
                    except asyncio.CancelledError:
                        raise AccountLoginError("Операция входа отменена")
                
                else:
                    raise AccountLoginError("Превышено количество попыток ввода кода")
        
        except FloodWaitError as e:
            raise AccountLoginError(f"Слишком много попыток. Подождите {e.seconds} сек.")
        
        except Exception as e:
            await client.disconnect()
            if session_path.exists():
                session_path.unlink()
            raise AccountLoginError(str(e))
        
        await client.disconnect()
        logger.info(f"Успешный вход в аккаунт {phone}")
        
        return str(session_path)
    
    async def monitor_account_codes(self, account_id: int, phone: str, callback: Callable = None):
        """
        Запускает мониторинг входящих кодов для аккаунта
        """
        session_path = self._get_session_path(phone)
        
        if not session_path.exists():
            logger.error(f"Сессия для {phone} не найдена")
            return
        
        client = TelegramClient(str(session_path), self.api_id, self.api_hash)
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.error(f"Аккаунт {phone} не авторизован")
            await client.disconnect()
            return
        
        self.active_clients[account_id] = client
        
        if callback:
            self.code_callbacks[account_id] = callback
        
        self.monitoring_tasks[account_id] = asyncio.create_task(
            self._monitor_task(account_id, client)
        )
        
        logger.info(f"Запущен мониторинг для аккаунта {account_id}")
    
    async def _monitor_task(self, account_id: int, client: TelegramClient):
        """Фоновая задача для мониторинга сообщений"""
        try:
            @client.on(events.NewMessage(incoming=True))
            async def handler(event):
                """Обработчик новых сообщений"""
                try:
                    message = event.message.message
                    
                    if message and ("код" in message.lower() or "code" in message.lower()):
                        codes = re.findall(r'\b(\d{5})\b', message)
                        
                        for code in codes:
                            logger.info(f"Обнаружен код {code} для аккаунта {account_id}")
                            
                            if account_id in self.code_callbacks:
                                await self.code_callbacks[account_id](code)
                            
                except Exception as e:
                    logger.error(f"Ошибка в обработчике сообщений: {e}")
            
            await client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Ошибка мониторинга для аккаунта {account_id}: {e}")
        finally:
            await client.disconnect()
            if account_id in self.active_clients:
                del self.active_clients[account_id]
            if account_id in self.monitoring_tasks:
                del self.monitoring_tasks[account_id]
            if account_id in self.code_callbacks:
                del self.code_callbacks[account_id]
    
    async def get_recent_code(self, account_id: int, phone: str) -> Optional[str]:
        """Получает последний код из диалогов аккаунта"""
        session_path = self._get_session_path(phone)
        
        if not session_path.exists():
            logger.error(f"Сессия для {phone} не найдена")
            return None
        
        client = TelegramClient(str(session_path), self.api_id, self.api_hash)
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
        
        try:
            dialogs = await client.get_dialogs(limit=10)
            
            five_min_ago = datetime.now() - timedelta(minutes=5)
            
            for dialog in dialogs:
                try:
                    messages = await client.get_messages(dialog.entity, limit=20)
                    
                    for msg in messages:
                        if not msg.message or not msg.date:
                            continue
                        
                        msg_date = msg.date.replace(tzinfo=None) if msg.date.tzinfo else msg.date
                        if msg_date < five_min_ago:
                            continue
                        
                        if "код" in msg.message.lower() or "code" in msg.message.lower():
                            codes = re.findall(r'\b(\d{5})\b', msg.message)
                            if codes:
                                return codes[0]
                                
                except Exception as e:
                    logger.error(f"Ошибка при получении сообщений из диалога: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Ошибка при получении кода: {e}")
        finally:
            await client.disconnect()
        
        return None
    
    async def stop_monitoring(self, account_id: int):
        """Останавливает мониторинг для аккаунта"""
        if account_id in self.monitoring_tasks:
            self.monitoring_tasks[account_id].cancel()
            try:
                await self.monitoring_tasks[account_id]
            except asyncio.CancelledError:
                pass
            del self.monitoring_tasks[account_id]
        
        if account_id in self.active_clients:
            client = self.active_clients[account_id]
            await client.disconnect()
            del self.active_clients[account_id]
        
        if account_id in self.code_callbacks:
            del self.code_callbacks[account_id]
            
        logger.info(f"Остановлен мониторинг для аккаунта {account_id}")

user_bot = UserBot()
