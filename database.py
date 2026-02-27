import sqlite3
import json
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
import logging

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

class Database:
    """Потокобезопасное соединение с БД"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Инициализация с созданием всех таблиц"""
        self._init_db()

    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для соединения"""
        conn = sqlite3.connect(DATABASE_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Создание всех таблиц и индексов"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    balance INTEGER DEFAULT 0 NOT NULL,
                    sales_count INTEGER DEFAULT 0 NOT NULL,
                    purchases_count INTEGER DEFAULT 0 NOT NULL,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_admin BOOLEAN DEFAULT 0 NOT NULL,
                    privacy_accepted BOOLEAN DEFAULT 0 NOT NULL,
                    CHECK (balance >= 0)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id INTEGER NOT NULL,
                    phone_number TEXT NOT NULL,
                    description TEXT NOT NULL,
                    price INTEGER NOT NULL CHECK (price > 0),
                    session_path TEXT,
                    cloud_password TEXT,
                    status TEXT DEFAULT 'pending' NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    activated_at TIMESTAMP,
                    sold_at TIMESTAMP,
                    buyer_id INTEGER,
                    resale_count INTEGER DEFAULT 0 NOT NULL,
                    original_account_id INTEGER,
                    FOREIGN KEY (seller_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (buyer_id) REFERENCES users(user_id) ON DELETE SET NULL,
                    FOREIGN KEY (original_account_id) REFERENCES accounts(account_id) ON DELETE SET NULL
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS purchases (
                    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    buyer_id INTEGER NOT NULL,
                    seller_id INTEGER NOT NULL,
                    price INTEGER NOT NULL,
                    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE,
                    FOREIGN KEY (buyer_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (seller_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_states (
                    user_id INTEGER PRIMARY KEY,
                    state TEXT NOT NULL,
                    data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_accounts_seller ON accounts(seller_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_accounts_buyer ON accounts(buyer_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_accounts_phone ON accounts(phone_number)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_purchases_buyer ON purchases(buyer_id)')

            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'privacy_accepted' not in columns:
                try:
                    cursor.execute('''
                        ALTER TABLE users 
                        ADD COLUMN privacy_accepted BOOLEAN DEFAULT 0 NOT NULL
                    ''')
                    logger.info("Added privacy_accepted column to users table")
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not add privacy_accepted column: {e}")

            cursor.execute("PRAGMA table_info(accounts)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'resale_count' not in columns:
                try:
                    cursor.execute('''
                        ALTER TABLE accounts 
                        ADD COLUMN resale_count INTEGER DEFAULT 0 NOT NULL
                    ''')
                    logger.info("Added resale_count column to accounts table")
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not add resale_count column: {e}")
            
            if 'original_account_id' not in columns:
                try:
                    cursor.execute('''
                        ALTER TABLE accounts 
                        ADD COLUMN original_account_id INTEGER
                    ''')
                    logger.info("Added original_account_id column to accounts table")
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not add original_account_id column: {e}")

            conn.commit()

    def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None) -> Dict[str, Any]:
        """Получить или создать пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()

            if not user:
                from config import ADMIN_IDS
                is_admin = 1 if user_id in ADMIN_IDS else 0

                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, balance, is_admin, privacy_accepted)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, 0, is_admin, 0))

                cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                user = cursor.fetchone()

            return dict(user)

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
            return dict(user) if user else None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Найти пользователя по username"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            clean_username = username.strip().lstrip('@').lower()

            cursor.execute(
                "SELECT * FROM users WHERE LOWER(username) = ?",
                (clean_username,)
            )
            user = cursor.fetchone()

            if user:
                return dict(user)

            cursor.execute(
                "SELECT * FROM users WHERE LOWER(username) LIKE ?",
                (f"%{clean_username}%",)
            )
            user = cursor.fetchone()

            if user:
                return dict(user)

            return None

    def accept_privacy(self, user_id: int) -> bool:
        """Отметить, что пользователь принял политику обработки данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    UPDATE users 
                    SET privacy_accepted = 1 
                    WHERE user_id = ?
                ''', (user_id,))
                
                success = cursor.rowcount > 0
                if success:
                    logger.info(f"User {user_id} accepted privacy policy")
                return success
                
            except sqlite3.Error as e:
                logger.error(f"Error updating privacy_accepted for user {user_id}: {e}")
                return False

    def update_balance(self, user_id: int, amount: int, operation: str = 'add') -> Tuple[bool, int]:
        """Обновить баланс пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            try:
                if operation == 'add':
                    cursor.execute('''
                        UPDATE users
                        SET balance = balance + ?
                        WHERE user_id = ?
                    ''', (amount, user_id))

                    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
                    result = cursor.fetchone()
                    if result:
                        return True, result['balance']
                    return False, 0

                else:
                    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
                    current = cursor.fetchone()
                    if not current or current['balance'] < amount:
                        return False, 0

                    cursor.execute('''
                        UPDATE users
                        SET balance = balance - ?
                        WHERE user_id = ?
                    ''', (amount, user_id))

                    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
                    result = cursor.fetchone()
                    if result:
                        return True, result['balance']
                    return False, 0

            except sqlite3.Error as e:
                logger.error(f"Balance update error: {e}")
                return False, 0

    def check_phone_available_for_sale(self, phone_number: str, user_id: int) -> Tuple[bool, str]:
        """Проверить, доступен ли номер для продажи (не был куплен этим пользователем ранее)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COUNT(*) as count FROM purchases p
                JOIN accounts a ON p.account_id = a.account_id
                WHERE a.phone_number = ? AND p.buyer_id = ?
            ''', (phone_number, user_id))
            
            result = cursor.fetchone()
            if result and result['count'] > 0:
                return False, "Этот номер уже был вами куплен ранее. Перепродажа доступна через кнопку 'Перепродать' в разделе 'Мои покупки'."
            
            cursor.execute('''
                SELECT COUNT(*) as count FROM accounts
                WHERE phone_number = ? AND seller_id = ? AND status != 'sold'
            ''', (phone_number, user_id))
            
            result = cursor.fetchone()
            if result and result['count'] > 0:
                return False, "Этот номер уже выставлен вами на продажу."
            
            return True, "OK"

    def create_account(self, seller_id: int, phone_number: str, description: str, price: int, original_account_id: int = None) -> int:
        """Создать запись об аккаунте"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if original_account_id:
                cursor.execute('''
                    INSERT INTO accounts (seller_id, phone_number, description, price, status, original_account_id, resale_count)
                    VALUES (?, ?, ?, ?, 'pending', ?, (SELECT resale_count + 1 FROM accounts WHERE account_id = ?))
                ''', (seller_id, phone_number, description, price, original_account_id, original_account_id))
            else:
                cursor.execute('''
                    INSERT INTO accounts (seller_id, phone_number, description, price, status)
                    VALUES (?, ?, ?, ?, 'pending')
                ''', (seller_id, phone_number, description, price))
            
            return cursor.lastrowid

    def activate_account(self, account_id: int, session_path: str, cloud_password: str = None) -> bool:
        """Активировать аккаунт"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE accounts
                SET status = 'active',
                    session_path = ?,
                    cloud_password = ?,
                    activated_at = CURRENT_TIMESTAMP
                WHERE account_id = ? AND status = 'pending'
            ''', (session_path, cloud_password, account_id))
            return cursor.rowcount > 0

    def get_pending_accounts(self, seller_id: int) -> List[Dict[str, Any]]:
        """Получить ожидающие активации аккаунты"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM accounts
                WHERE seller_id = ? AND status = 'pending'
                ORDER BY created_at DESC
            ''', (seller_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_active_accounts(self) -> List[Dict[str, Any]]:
        """Получить все активные аккаунты"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.*, u.username as seller_username
                FROM accounts a
                JOIN users u ON a.seller_id = u.user_id
                WHERE a.status = 'active'
                ORDER BY a.created_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def get_account(self, account_id: int) -> Optional[Dict[str, Any]]:
        """Получить аккаунт по ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.*, u.username as seller_username
                FROM accounts a
                LEFT JOIN users u ON a.seller_id = u.user_id
                WHERE a.account_id = ?
            ''', (account_id,))
            account = cursor.fetchone()
            return dict(account) if account else None

    def get_account_by_phone(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Получить аккаунт по номеру телефона"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM accounts
                WHERE phone_number = ? AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
            ''', (phone_number,))
            account = cursor.fetchone()
            return dict(account) if account else None

    def purchase_account(self, account_id: int, buyer_id: int) -> Tuple[bool, str]:
        """Купить аккаунт"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("BEGIN TRANSACTION")

                cursor.execute('''
                    SELECT * FROM accounts
                    WHERE account_id = ? AND status = 'active'
                ''', (account_id,))
                account = cursor.fetchone()

                if not account:
                    cursor.execute("ROLLBACK")
                    return False, "Аккаунт не найден или уже продан"

                cursor.execute("SELECT balance FROM users WHERE user_id = ?", (buyer_id,))
                buyer = cursor.fetchone()

                if not buyer or buyer['balance'] < account['price']:
                    cursor.execute("ROLLBACK")
                    return False, "Недостаточно средств"

                cursor.execute('''
                    UPDATE users SET balance = balance - ?
                    WHERE user_id = ?
                ''', (account['price'], buyer_id))

                cursor.execute('''
                    UPDATE users SET balance = balance + ?
                    WHERE user_id = ?
                ''', (account['price'], account['seller_id']))

                cursor.execute('''
                    UPDATE users SET purchases_count = purchases_count + 1
                    WHERE user_id = ?
                ''', (buyer_id,))

                cursor.execute('''
                    UPDATE users SET sales_count = sales_count + 1
                    WHERE user_id = ?
                ''', (account['seller_id'],))

                cursor.execute('''
                    UPDATE accounts
                    SET status = 'sold',
                        buyer_id = ?,
                        sold_at = CURRENT_TIMESTAMP
                    WHERE account_id = ?
                ''', (buyer_id, account_id))

                cursor.execute('''
                    INSERT INTO purchases (account_id, buyer_id, seller_id, price)
                    VALUES (?, ?, ?, ?)
                ''', (account_id, buyer_id, account['seller_id'], account['price']))

                cursor.execute("COMMIT")
                return True, "Покупка успешно завершена"

            except sqlite3.Error as e:
                cursor.execute("ROLLBACK")
                logger.error(f"Purchase error: {e}")
                return False, f"Ошибка базы данных при покупке: {e}"

    def get_user_purchases(self, user_id: int) -> List[Dict[str, Any]]:
        """Получить покупки пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.*, u.username as seller_username, p.purchased_at
                FROM purchases p
                JOIN accounts a ON p.account_id = a.account_id
                JOIN users u ON a.seller_id = u.user_id
                WHERE p.buyer_id = ?
                ORDER BY p.purchased_at DESC
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_purchased_account_details(self, user_id: int, account_id: int) -> Optional[Dict[str, Any]]:
        """Получить детали купленного аккаунта для перепродажи"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.*, p.purchased_at
                FROM purchases p
                JOIN accounts a ON p.account_id = a.account_id
                WHERE p.buyer_id = ? AND a.account_id = ?
            ''', (user_id, account_id))
            account = cursor.fetchone()
            return dict(account) if account else None

    def set_state(self, user_id: int, state: str, data: dict = None):
        """Установить состояние пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            data_json = json.dumps(data) if data else None

            cursor.execute('''
                INSERT INTO user_states (user_id, state, data, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    state = excluded.state,
                    data = excluded.data,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, state, data_json))

    def get_state(self, user_id: int) -> Tuple[Optional[str], dict]:
        """Получить состояние пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT state, data FROM user_states WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                data = json.loads(row['data']) if row['data'] else {}
                return row['state'], data
            return None, {}

    def clear_state(self, user_id: int):
        """Очистить состояние"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
