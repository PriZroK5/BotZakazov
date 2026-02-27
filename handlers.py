import logging
import asyncio
import re
from datetime import datetime
from typing import Dict, Any, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from database import Database
from keyboards import *
from states import UserState
from userbot import user_bot, AccountLoginError, LoginTimeoutError
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

db = Database()

waiting_for_input: Dict[int, asyncio.Future] = {}
waiting_for_code_request: Dict[int, int] = {}

PRIVACY_POLICY_URL = "https://telegra.ph/Politika-obrabotki-dannyh-02-27-2"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    db_user = db.get_user(user.id)
    
    if db_user and db_user.get('privacy_accepted', False):
        await show_main_menu_after_accept(update, user)
        return
    
    db_user = db.get_or_create_user(
        user.id,
        user.username,
        user.first_name
    )
    
    text = (
        f"👋 Добро пожаловать в Маркетплейс, {user.first_name}!\n\n"
        f"Перед началом работы необходимо принять "
        f"<a href='{PRIVACY_POLICY_URL}'>политику обработки данных</a>.\n\n"
        f"Пожалуйста, ознакомьтесь с документом и подтвердите свое согласие."
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Принять", callback_data="accept_privacy"),
            InlineKeyboardButton("❌ Отклонить", callback_data="reject_privacy")
        ]
    ])
    
    await update.message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode='HTML',
        disable_web_page_preview=True
    )

async def show_main_menu_after_accept(update: Update, user):
    db_user = db.get_user(user.id)
    if db_user is None:
        db_user = db.get_or_create_user(user.id, user.username, user.first_name)
    
    text = (
        f"👋 С возвращением, {user.first_name}!\n\n"
        f"✅ Баланс: {db_user['balance']}₽\n\n"
        f"❓ Почему именно мы?\n"
        f"• Мгновенные выплаты\n"
        f"• Техподдержка 24/7\n"
        f"• Проверенные продавцы\n"
        f"• Автоматическая выдача товаров\n\n"
        f"🏪 Используйте кнопки ниже для навигации."
    )
    
    await update.message.reply_text(
        text,
        reply_markup=main_menu_keyboard(db_user.get('is_admin', False))
    )
    
    db.clear_state(user.id)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    
    logger.info(f"Callback от {user.id}: {data}")
    
    if data == "accept_privacy":
        await accept_privacy(query, user)
        return
    
    if data == "reject_privacy":
        await reject_privacy(query, user)
        return
    
    db_user = db.get_user(user.id)
    if not db_user or not db_user.get('privacy_accepted', False):
        await query.edit_message_text(
            "⚠️ Для доступа к функционалу необходимо принять политику обработки данных.\n\n"
            "Введите /start для ознакомления.",
            reply_markup=None
        )
        return
    
    if data == "back_to_main":
        await show_main_menu(query, user)
        return
    
    if data == "back_to_market":
        await show_market(query)
        return
    
    if data == "back_to_purchases":
        await show_purchases(query, user.id)
        return
    
    if data == "profile":
        await show_profile(query, user)
    
    elif data == "market":
        await show_market(query)
    
    elif data == "sell":
        await start_sell(query, user.id)
    
    elif data == "my_purchases":
        await show_purchases(query, user.id)
    
    elif data.startswith("resale_"):
        account_id = int(data.split("_")[1])
        await start_resale(query, user.id, account_id)
        return
    
    elif data == "deposit":
        await query.edit_message_text(
            "💳 Для пополнения баланса напишите @Fedolinov",
            reply_markup=back_keyboard()
        )
    
    elif data == "withdraw":
        await query.edit_message_text(
            "💸 Для вывода средств напишите @Fedolinov",
            reply_markup=back_keyboard()
        )
    
    elif data == "admin_panel":
        await show_admin_panel(query)
    
    elif data == "admin_add_balance":
        await start_admin_balance_op(query, user.id, 'add')
    
    elif data == "admin_subtract_balance":
        await start_admin_balance_op(query, user.id, 'subtract')
    
    elif data == "confirm_sell":
        await confirm_sell(query, user.id, context)
    
    elif data == "cancel_sell":
        await cancel_sell(query, user.id)
    
    elif data == "confirm_resale":
        await confirm_resale(query, user.id, context)
    
    elif data == "cancel_resale":
        await cancel_resale(query, user.id)
    
    elif data.startswith("item_"):
        account_id = int(data.split("_")[1])
        await show_item_details(query, user.id, account_id)
    
    elif data.startswith("validate_before_buy_"):
        account_id = int(data.split("_")[3])
        await validate_account_before_buy(query, user.id, account_id, context)
        return
    
    elif data.startswith("confirm_buy_"):
        account_id = int(data.split("_")[2])
        await confirm_purchase(query, user.id, account_id, context)
    
    elif data == "cancel_buy":
        await cancel_purchase(query, user.id)
    
    elif data.startswith("purchase_"):
        account_id = int(data.split("_")[1])
        await show_purchase_actions(query, user.id, account_id)
    
    elif data.startswith("get_code_"):
        account_id = int(data.split("_")[2])
        await request_code_for_item(query, user.id, account_id, context)
    
    elif data.startswith("get_cloud_"):
        account_id = int(data.split("_")[2])
        await get_cloud_password(query, user.id, account_id)

async def accept_privacy(query, user):
    db.accept_privacy(user.id)
    
    db_user = db.get_user(user.id)
    
    text = (
        f"✅ Спасибо! Вы приняли политику обработки данных.\n\n"
        f"👋 Добро пожаловать в Маркетплейс, {user.first_name}!\n\n"
        f"✅ Баланс: {db_user['balance']}₽\n\n"
        f"❓ Почему именно мы?\n"
        f"• Мгновенные выплаты\n"
        f"• Техподдержка 24/7\n"
        f"• Проверенные продавцы\n"
        f"• Автоматическая выдача товаров\n\n"
        f"🏪 Используйте кнопки ниже для навигации."
    )
    
    try:
        await query.edit_message_text(
            text,
            reply_markup=main_menu_keyboard(db_user.get('is_admin', False))
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in accept_privacy: {e}")

async def reject_privacy(query, user):
    text = (
        f"❌ Вы отклонили политику обработки данных.\n\n"
        f"К сожалению, без принятия условий использования бот не может предоставить свои услуги.\n\n"
        f"Если вы передумаете, нажмите /start для повторного ознакомления."
    )
    
    try:
        await query.edit_message_text(text, reply_markup=None)
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in reject_privacy: {e}")

async def show_main_menu(query, user):
    db_user = db.get_user(user.id)
    if db_user is None:
        db_user = db.get_or_create_user(user.id, user.username, user.first_name)
    
    if not db_user.get('privacy_accepted', False):
        await query.edit_message_text(
            "⚠️ Для доступа к функционалу необходимо принять политику обработки данных.\n\n"
            "Введите /start для ознакомления.",
            reply_markup=None
        )
        return
    
    try:
        await query.edit_message_text(
            "🏠 Главное меню\n\nВыберите раздел:",
            reply_markup=main_menu_keyboard(db_user.get('is_admin', False))
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in show_main_menu: {e}")

async def show_profile(query, user):
    db_user = db.get_user(user.id)
    if db_user is None:
        db_user = db.get_or_create_user(user.id, user.username, user.first_name)
    
    registered = datetime.fromisoformat(db_user['registered_at']).strftime("%d.%m.%Y")
    
    text = (
        f"👤 Ваш профиль\n\n"
        f"🆔 ID: {user.id}\n"
        f"📝 Ник: @{db_user['username'] or 'не указан'}\n"
        f"💰 Баланс: {db_user['balance']}₽\n"
        f"📊 Продаж: {db_user['sales_count']}\n"
        f"📥 Покупок: {db_user['purchases_count']}\n"
        f"📅 На сервисе с: {registered}"
    )
    
    try:
        await query.edit_message_text(
            text,
            reply_markup=back_keyboard()
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in show_profile: {e}")

async def show_market(query):
    accounts = db.get_active_accounts()
    
    if not accounts:
        try:
            await query.edit_message_text(
                "🏪 Рынок пуст\n\nНа данный момент нет активных товаров.",
                reply_markup=back_keyboard()
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in show_market: {e}")
        return
    
    try:
        await query.edit_message_text(
            "🏪 Рынок товаров\n\nВыберите товар:",
            reply_markup=market_keyboard(accounts)
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in show_market: {e}")

async def show_admin_panel(query):
    try:
        await query.edit_message_text(
            "⚙️ Админ-панель\n\nВыберите действие:",
            reply_markup=admin_panel_keyboard()
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in show_admin_panel: {e}")

async def start_sell(query, user_id):
    pending = db.get_pending_accounts(user_id)
    if pending:
        try:
            await query.edit_message_text(
                f"⚠️ У вас есть незавершенные аккаунты\n"
                f"Количество: {len(pending)}\n"
                f"Сначала завершите их активацию.",
                reply_markup=back_keyboard()
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in start_sell: {e}")
        return
    
    db.set_state(user_id, "SELL_AWAITING_PHONE")
    
    try:
        await query.edit_message_text(
            "📱 Введите номер аккаунта\n\nФормат: +79001234567",
            reply_markup=back_keyboard()
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in start_sell: {e}")

async def start_resale(query, user_id, account_id):
    account = db.get_purchased_account_details(user_id, account_id)
    
    if not account:
        try:
            await query.edit_message_text(
                "❌ Аккаунт не найден или не принадлежит вам",
                reply_markup=back_keyboard("purchases")
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in start_resale: {e}")
        return
    
    context = query
    context.user_data['resale_data'] = {
        'original_account_id': account_id,
        'phone': account['phone_number'],
        'session_path': account['session_path'],
        'cloud_password': account['cloud_password']
    }
    
    db.set_state(user_id, "RESALE_AWAITING_DESCRIPTION", {
        'original_account_id': account_id,
        'phone': account['phone_number']
    })
    
    try:
        await query.edit_message_text(
            f"📝 Перепродажа аккаунта #{account_id}\n\n"
            f"📞 Номер: {account['phone_number']}\n\n"
            f"Введите новое описание товара:",
            reply_markup=back_keyboard()
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in start_resale: {e}")

async def confirm_resale(query, user_id, context):
    state, data = db.get_state(user_id)
    
    if not data or not all(k in data for k in ['original_account_id', 'phone', 'description', 'price']):
        try:
            await query.edit_message_text(
                "❌ Ошибка данных. Начните заново.",
                reply_markup=back_keyboard()
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in confirm_resale: {e}")
        db.clear_state(user_id)
        return
    
    original_account = db.get_account(data['original_account_id'])
    if not original_account:
        try:
            await query.edit_message_text(
                "❌ Исходный аккаунт не найден",
                reply_markup=back_keyboard()
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in confirm_resale: {e}")
        db.clear_state(user_id)
        return
    
    try:
        account_id = db.create_account(
            seller_id=user_id,
            phone_number=data['phone'],
            description=data['description'],
            price=data['price'],
            original_account_id=data['original_account_id']
        )
        
        db.activate_account(
            account_id,
            original_account['session_path'],
            original_account['cloud_password']
        )
        
        async def code_callback(code):
            for buyer_id, acc_id in waiting_for_code_request.items():
                if acc_id == account_id:
                    try:
                        await context.bot.send_message(
                            chat_id=buyer_id,
                            text=f"✅ Код найден!\n\n"
                                 f"🔑 Код подтверждения: {code}"
                        )
                    except Exception as e:
                        logger.error(f"Error sending code to buyer: {e}")
        
        await user_bot.monitor_account_codes(account_id, data['phone'], code_callback)
        
        db.clear_state(user_id)
        
        cloud_password_text = original_account['cloud_password'] if original_account['cloud_password'] else "не установлен"
        
        await query.edit_message_text(
            f"✅ Аккаунт успешно выставлен на перепродажу!\n\n"
            f"Товар #{account_id}\n"
            f"📞 Номер: {data['phone']}\n"
            f"💰 Цена: {data['price']}₽\n"
            f"🔐 Облачный пароль: {cloud_password_text}\n\n"
            f"Исходный аккаунт #{data['original_account_id']} останется в ваших покупках.",
            reply_markup=back_keyboard("main")
        )
        
    except Exception as e:
        logger.error(f"Resale error: {e}")
        await query.edit_message_text(
            f"❌ Ошибка при перепродаже\n\n{str(e)}",
            reply_markup=back_keyboard()
        )
        db.clear_state(user_id)

async def cancel_resale(query, user_id):
    db.clear_state(user_id)
    
    try:
        await query.edit_message_text(
            "❌ Перепродажа отменена.",
            reply_markup=back_keyboard("purchases")
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in cancel_resale: {e}")

async def confirm_sell(query, user_id, context):
    state, data = db.get_state(user_id)
    
    if not data or not all(k in data for k in ['phone', 'description', 'price']):
        try:
            await query.edit_message_text(
                "❌ Ошибка данных. Начните заново.",
                reply_markup=back_keyboard()
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in confirm_sell: {e}")
        db.clear_state(user_id)
        return
    
    available, message = db.check_phone_available_for_sale(data['phone'], user_id)
    if not available:
        try:
            await query.edit_message_text(
                f"❌ {message}",
                reply_markup=back_keyboard()
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in confirm_sell: {e}")
        db.clear_state(user_id)
        return
    
    context.user_data['sell_data'] = data
    db.set_state(user_id, "SELL_AWAITING_CODE", data)
    
    try:
        await query.edit_message_text(
            f"🔐 Подтверждение доступа к аккаунту\n\n"
            f"📞 Номер: {data['phone']}\n\n"
            f"Инструкция:\n"
            f"1️⃣ Бот пытается войти в аккаунт\n"
            f"2️⃣ Вам придет код подтверждения в Telegram\n"
            f"3️⃣ Отправьте его сюда (просто цифры, без слова 'code')\n\n"
            f"⏳ Ожидаю код..."
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in confirm_sell: {e}")
    
    loop = asyncio.get_running_loop()
    input_future = loop.create_future()
    waiting_for_input[user_id] = input_future
    
    asyncio.create_task(process_account_login(context, user_id, data, input_future))

async def process_account_login(context, user_id, data, input_future):
    login_stage = "code"
    cloud_password = None
    
    try:
        async def get_code():
            nonlocal login_stage
            login_stage = "code"
            try:
                response = await asyncio.wait_for(input_future, timeout=300)
                return response
            except asyncio.TimeoutError:
                raise LoginTimeoutError("Время ожидания кода истекло")
        
        async def get_password():
            nonlocal login_stage
            nonlocal cloud_password
            login_stage = "password"
            password_future = asyncio.get_running_loop().create_future()
            waiting_for_input[user_id] = password_future
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🔐 Требуется облачный пароль\n\n"
                     f"На аккаунте включена двухфакторная аутентификация.\n"
                     f"Введите облачный пароль:"
            )
            
            try:
                password = await asyncio.wait_for(password_future, timeout=300)
                cloud_password = password
                return password
            except asyncio.TimeoutError:
                raise LoginTimeoutError("Время ожидания пароля истекло")
        
        session_path = await user_bot.login_account(
            phone=data['phone'],
            code_callback=get_code,
            password_callback=get_password
        )
        
        account_id = db.create_account(
            seller_id=user_id,
            phone_number=data['phone'],
            description=data['description'],
            price=data['price']
        )
        
        db.activate_account(account_id, session_path, cloud_password)
        
        async def code_callback(code):
            for buyer_id, acc_id in waiting_for_code_request.items():
                if acc_id == account_id:
                    try:
                        await context.bot.send_message(
                            chat_id=buyer_id,
                            text=f"✅ Код найден!\n\n"
                                 f"🔑 Код подтверждения: {code}"
                        )
                    except Exception as e:
                        logger.error(f"Error sending code to buyer: {e}")
        
        await user_bot.monitor_account_codes(account_id, data['phone'], code_callback)
        
        db.clear_state(user_id)
        waiting_for_input.pop(user_id, None)
        
        cloud_password_text = cloud_password if cloud_password else "не установлен"
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ Аккаунт успешно активирован!\n\n"
                 f"Товар #{account_id} выставлен на продажу.\n"
                 f"💰 Цена: {data['price']}₽\n"
                 f"🔐 Облачный пароль: {cloud_password_text}"
        )
        
    except AccountLoginError as e:
        error_text = str(e)
        
        if "Неверный код" in error_text:
            new_future = asyncio.get_running_loop().create_future()
            waiting_for_input[user_id] = new_future
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ {error_text}\n\n"
                     f"Попробуйте еще раз. Вам должен прийти новый код.\n"
                     f"Введите код подтверждения (просто цифры):"
            )
            
            await process_account_login(context, user_id, data, new_future)
            
        elif "Неверный облачный пароль" in error_text:
            new_future = asyncio.get_running_loop().create_future()
            waiting_for_input[user_id] = new_future
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ {error_text}\n\n"
                     f"Попробуйте еще раз.\n"
                     f"Введите облачный пароль:"
            )
            
            await process_account_login(context, user_id, data, new_future)
            
        elif "2FA" in error_text or "облачный пароль" in error_text.lower():
            pass
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Ошибка входа\n\n{error_text}"
            )
            db.clear_state(user_id)
            waiting_for_input.pop(user_id, None)
            
    except LoginTimeoutError:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"⏰ Таймаут\n\nВы не отправили {'код' if login_stage == 'code' else 'пароль'} в течение 5 минут."
        )
        db.clear_state(user_id)
        waiting_for_input.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ Неизвестная ошибка\n\nПопробуйте позже."
        )
        db.clear_state(user_id)
        waiting_for_input.pop(user_id, None)

async def cancel_sell(query, user_id):
    db.clear_state(user_id)
    if user_id in waiting_for_input:
        waiting_for_input.pop(user_id, None)
    
    try:
        await query.edit_message_text(
            "❌ Продажа отменена.",
            reply_markup=back_keyboard()
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in cancel_sell: {e}")

async def show_item_details(query, user_id, account_id):
    account = db.get_account(account_id)
    if not account or account['status'] != 'active':
        try:
            await query.edit_message_text(
                "❌ Товар недоступен\n\nЭтот товар уже куплен или снят с продажи.",
                reply_markup=back_keyboard("market")
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in show_item_details: {e}")
        return
    
    user = db.get_user(user_id)
    if user is None:
        user = db.get_or_create_user(user_id, None, None)
    
    text = (
        f"📱 Товар #{account['account_id']}\n\n"
        f"📞 Номер: {account['phone_number']}\n"
        f"📝 Описание: {account['description']}\n"
        f"💰 Цена: {account['price']}₽\n"
        f"👤 Продавец: @{account['seller_username'] or 'unknown'}\n\n"
        f"💳 Ваш баланс: {user['balance']}₽"
    )
    
    try:
        await query.edit_message_text(
            text,
            reply_markup=item_details_keyboard(account_id)
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in show_item_details: {e}")

async def validate_account_before_buy(query, user_id, account_id, context):
    account = db.get_account(account_id)
    
    if not account or account['status'] != 'active':
        try:
            await query.edit_message_text(
                "❌ Товар недоступен",
                reply_markup=back_keyboard("market")
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in validate_account_before_buy: {e}")
        return
    
    try:
        await query.edit_message_text(
            f"🔍 Проверяю аккаунт #{account_id}...\n\n"
            f"⏳ Это может занять несколько секунд..."
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in validate_account_before_buy: {e}")
    
    asyncio.create_task(validate_purchase_account(context, user_id, account_id, account))

async def validate_purchase_account(context, user_id, account_id, account):
    try:
        is_valid, message = await user_bot.validate_session(account['session_path'])
        
        if is_valid:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Аккаунт #{account_id} валиден!\n\n"
                     f"📞 Номер: {account['phone_number']}\n"
                     f"📝 Сессия работает корректно\n"
                     f"💰 Цена: {account['price']}₽\n\n"
                     f"Можете смело покупать!"
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⚠️ Аккаунт #{account_id} может быть невалиден!\n\n"
                     f"Причина: {message}\n\n"
                     f"Рекомендуется воздержаться от покупки или связаться с продавцом."
            )
            
    except Exception as e:
        logger.error(f"Validation error for account {account_id}: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ Ошибка при проверке аккаунта #{account_id}\n\n"
                 f"Техническая ошибка. Попробуйте позже."
        )

async def confirm_purchase(query, buyer_id, account_id, context):
    success, msg = db.purchase_account(account_id, buyer_id)
    
    if success:
        account = db.get_account(account_id)
        
        try:
            await query.edit_message_text(
                f"✅ Покупка успешна!\n\n"
                f"Товар #{account_id} с номером {account['phone_number']} оплачен.\n\n"
                f"🔑 Как получить доступ:\n"
                f"1. Вернитесь в главное меню\n"
                f"2. Нажмите 'Мои покупки'\n"
                f"3. Выберите этот товар\n"
                f"4. Там будут кнопки 'Получить код' и 'Перепродать'",
                reply_markup=back_keyboard("main")
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in confirm_purchase: {e}")
        
        try:
            await context.bot.send_message(
                chat_id=account['seller_id'],
                text=f"✅ Ваш товар продан!\n\n"
                     f"Товар #{account_id}\n"
                     f"💰 Цена: {account['price']}₽\n\n"
                     f"Средства зачислены на ваш баланс."
            )
        except:
            pass
    else:
        try:
            await query.edit_message_text(
                f"❌ Ошибка покупки\n\n{msg}",
                reply_markup=back_keyboard("market")
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in confirm_purchase: {e}")

async def cancel_purchase(query, user_id):
    try:
        await query.edit_message_text(
            "❌ Покупка отменена.",
            reply_markup=back_keyboard("market")
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in cancel_purchase: {e}")

async def show_purchases(query, user_id):
    purchases = db.get_user_purchases(user_id)
    
    if not purchases:
        try:
            await query.edit_message_text(
                "📦 У вас нет покупок",
                reply_markup=back_keyboard()
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in show_purchases: {e}")
        return
    
    try:
        await query.edit_message_text(
            "📦 Ваши покупки\n\nВыберите товар:",
            reply_markup=purchases_keyboard(purchases)
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in show_purchases: {e}")

async def show_purchase_actions(query, user_id, account_id):
    purchases = db.get_user_purchases(user_id)
    purchase = next((p for p in purchases if p['account_id'] == account_id), None)
    
    if not purchase:
        try:
            await query.edit_message_text(
                "❌ Товар не найден",
                reply_markup=back_keyboard("main")
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in show_purchase_actions: {e}")
        return
    
    resale_count = purchase.get('resale_count', 0)
    
    text = (
        f"📱 Товар #{account_id}\n\n"
        f"📞 Номер: {purchase['phone_number']}\n"
        f"📝 Описание: {purchase['description']}\n"
        f"💰 Цена при покупке: {purchase['price']}₽\n"
        f"👤 Продавец: @{purchase['seller_username'] or 'unknown'}\n"
        f"🔄 Перепродаж: {resale_count}"
    )
    
    try:
        await query.edit_message_text(
            text,
            reply_markup=purchase_action_keyboard(
                account_id,
                bool(purchase.get('cloud_password')),
                can_resale=True
            )
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in show_purchase_actions: {e}")

async def request_code_for_item(query, user_id, account_id, context):
    purchases = db.get_user_purchases(user_id)
    purchase = next((p for p in purchases if p['account_id'] == account_id), None)
    
    if not purchase:
        try:
            await query.edit_message_text(
                "❌ Товар не найден",
                reply_markup=back_keyboard("main")
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in request_code_for_item: {e}")
        return
    
    waiting_for_code_request[user_id] = account_id
    
    try:
        await query.edit_message_text(
            f"🔑 Запрос кода для товара #{account_id}\n\n"
            f"📞 Номер: {purchase['phone_number']}\n\n"
            f"⏳ Ожидаю код подтверждения...\n"
            f"Когда на этот номер придет код, я его перехвачу и отправлю вам.",
            reply_markup=purchase_action_keyboard(
                account_id,
                bool(purchase.get('cloud_password')),
                can_resale=True
            )
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in request_code_for_item: {e}")

async def get_cloud_password(query, user_id, account_id):
    purchases = db.get_user_purchases(user_id)
    purchase = next((p for p in purchases if p['account_id'] == account_id), None)
    
    if not purchase:
        try:
            await query.edit_message_text(
                "❌ Товар не найден",
                reply_markup=back_keyboard("main")
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in get_cloud_password: {e}")
        return
    
    cloud_password = purchase.get('cloud_password')
    
    if cloud_password:
        text = f"☁️ Облачный пароль:\n\n{cloud_password}"
    else:
        text = "☁️ Облачный пароль не установлен!"
    
    try:
        await query.edit_message_text(
            text,
            reply_markup=purchase_action_keyboard(account_id, bool(cloud_password), can_resale=True)
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in get_cloud_password: {e}")

async def start_admin_balance_op(query, admin_id, op_type):
    user = db.get_user(admin_id)
    if not user or not user.get('is_admin'):
        try:
            await query.edit_message_text(
                "⛔ Доступ запрещен",
                reply_markup=back_keyboard()
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error in start_admin_balance_op: {e}")
        return
    
    db.set_state(admin_id, "ADMIN_AWAITING_USERNAME", {'op_type': op_type})
    
    text = "➕ Введите @username или ID пользователя для пополнения:" if op_type == 'add' else "➖ Введите @username или ID пользователя для списания:"
    
    try:
        await query.edit_message_text(
            text,
            reply_markup=back_keyboard()
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in start_admin_balance_op: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    
    db_user = db.get_user(user.id)
    if not db_user or not db_user.get('privacy_accepted', False):
        await update.message.reply_text(
            f"⚠️ Для использования бота необходимо принять политику обработки данных.\n\n"
            f"Ознакомьтесь с документом: {PRIVACY_POLICY_URL}\n\n"
            f"Затем нажмите /start для продолжения."
        )
        return
    
    state, data = db.get_state(user.id)
    
    if user.id in waiting_for_input and waiting_for_input[user.id] and not waiting_for_input[user.id].done():
        waiting_for_input[user.id].set_result(text)
        await update.message.reply_text("✅ Получено, выполняю вход...")
        return
    
    if not state:
        await update.message.reply_text(
            "Используйте кнопки меню для навигации.",
            reply_markup=back_keyboard()
        )
        return
    
    # Убираем префикс UserState. если он есть
    if state.startswith('UserState.'):
        state = state.replace('UserState.', '')
    
    try:
        state_enum = UserState[state]
    except KeyError:
        logger.error(f"Unknown state: {state}")
        db.clear_state(user.id)
        await update.message.reply_text(
            "❌ Неизвестное состояние. Начните заново.",
            reply_markup=back_keyboard()
        )
        return
    
    # Состояния продажи
    if state_enum == UserState.SELL_AWAITING_PHONE:
        phone = re.sub(r'\D', '', text)
        if len(phone) < 10 or len(phone) > 15:
            await update.message.reply_text(
                "❌ Неверный формат\n\nВведите номер в международном формате: +79001234567"
            )
            return
        
        if not phone.startswith('+'):
            phone = '+' + phone
        
        data = {'phone': phone}
        db.set_state(user.id, "SELL_AWAITING_DESCRIPTION", data)
        
        await update.message.reply_text(
            "📝 Введите описание товара\n\nОпишите аккаунт (наличие, особенности и т.д.):"
        )
    
    elif state_enum == UserState.SELL_AWAITING_DESCRIPTION:
        if len(text) < 10 or len(text) > 500:
            await update.message.reply_text(
                f"❌ Ошибка\n\nОписание должно быть от 10 до 500 символов.\nСейчас: {len(text)} символов."
            )
            return
        
        data['description'] = text.strip()
        db.set_state(user.id, "SELL_AWAITING_PRICE", data)
        
        await update.message.reply_text(
            "💰 Введите цену\n\nУкажите цену в рублях (только число):"
        )
    
    elif state_enum == UserState.SELL_AWAITING_PRICE:
        try:
            price = int(text.strip())
            if price < 1 or price > 1000000:
                raise ValueError
        except:
            await update.message.reply_text(
                "❌ Ошибка\n\nВведите число от 1 до 1 000 000:"
            )
            return
        
        data['price'] = price
        db.set_state(user.id, "SELL_AWAITING_CONFIRMATION", data)
        
        await update.message.reply_text(
            f"📱 Подтверждение товара\n\n"
            f"📞 Номер: {data['phone']}\n"
            f"📝 Описание: {data['description'][:100]}...\n"
            f"💰 Цена: {data['price']}₽\n\n"
            f"Подтверждаете?",
            reply_markup=confirmation_keyboard('sell')
        )
    
    # Состояния перепродажи
    elif state_enum == UserState.RESALE_AWAITING_DESCRIPTION:
        if len(text) < 10 or len(text) > 500:
            await update.message.reply_text(
                f"❌ Ошибка\n\nОписание должно быть от 10 до 500 символов.\nСейчас: {len(text)} символов."
            )
            return
        
        data['description'] = text.strip()
        db.set_state(user.id, "RESALE_AWAITING_PRICE", data)
        
        await update.message.reply_text(
            "💰 Введите новую цену для перепродажи\n\nУкажите цену в рублях (только число):"
        )
    
    elif state_enum == UserState.RESALE_AWAITING_PRICE:
        try:
            price = int(text.strip())
            if price < 1 or price > 1000000:
                raise ValueError
        except:
            await update.message.reply_text(
                "❌ Ошибка\n\nВведите число от 1 до 1 000 000:"
            )
            return
        
        data['price'] = price
        db.set_state(user.id, "RESALE_AWAITING_CONFIRMATION", data)
        
        original_account = db.get_account(data['original_account_id'])
        
        await update.message.reply_text(
            f"📱 Подтверждение перепродажи\n\n"
            f"📞 Номер: {data['phone']}\n"
            f"📝 Новое описание: {data['description'][:100]}...\n"
            f"💰 Новая цена: {data['price']}₽\n"
            f"🔄 Исходный аккаунт: #{data['original_account_id']}\n\n"
            f"Подтверждаете перепродажу?",
            reply_markup=resale_confirmation_keyboard()
        )
    
    # Админские состояния
    elif state_enum == UserState.ADMIN_AWAITING_USERNAME:
        clean_input = text.strip()
        
        target = db.get_user_by_username(clean_input)
        
        if not target and clean_input.lstrip('-').isdigit():
            user_id = int(clean_input)
            target = db.get_user(user_id)
            if target:
                logger.info(f"Найден пользователь по ID: {user_id}")
        
        if not target:
            await update.message.reply_text(
                f"❌ Пользователь не найден\n\nЗапрос: '{clean_input}'\n\n"
                f"Убедитесь что:\n"
                f"• Пользователь запускал бота (/start)\n"
                f"• Вы правильно ввели username или ID\n\n"
                f"Попробуйте еще раз или введите другой username/ID:"
            )
            return
        
        data['target_id'] = target['user_id']
        data['target_name'] = target['username'] or str(target['user_id'])
        db.set_state(user.id, "ADMIN_AWAITING_AMOUNT", data)
        
        op = "пополнения" if data['op_type'] == 'add' else "списания"
        await update.message.reply_text(
            f"✅ Пользователь найден\n\n"
            f"👤 @{target['username'] or 'нет username'}\n"
            f"🆔 ID: {target['user_id']}\n"
            f"💰 Текущий баланс: {target['balance']}₽\n\n"
            f"Введите сумму для {op}:"
        )
    
    elif state_enum == UserState.ADMIN_AWAITING_AMOUNT:
        try:
            amount = int(text.strip())
            if amount < 1:
                raise ValueError
        except:
            await update.message.reply_text(
                "❌ Ошибка\n\nВведите положительное число:"
            )
            return
        
        op_type = data['op_type']
        success, new_balance = db.update_balance(data['target_id'], amount, op_type)
        
        if success:
            op_word = "пополнен" if op_type == 'add' else "списан"
            await update.message.reply_text(
                f"✅ Баланс обновлен\n\n"
                f"Пользователь: @{data['target_name']}\n"
                f"Операция: {op_word}\n"
                f"Сумма: {amount}₽\n"
                f"Новый баланс: {new_balance}₽",
                reply_markup=back_keyboard()
            )
            
            try:
                await context.bot.send_message(
                    chat_id=data['target_id'],
                    text=f"💰 Баланс обновлен\n\n"
                         f"{'+' if op_type == 'add' else '-'}{amount}₽\n"
                         f"Новый баланс: {new_balance}₽"
                )
            except:
                pass
        else:
            await update.message.reply_text(
                "❌ Ошибка операции\n\nВозможно недостаточно средств для списания.",
                reply_markup=back_keyboard()
            )
        
        db.clear_state(user.id)
    
    else:
        db.clear_state(user.id)
        await update.message.reply_text(
            "❌ Неизвестное состояние",
            reply_markup=back_keyboard()
        )

def start_polling():
    from config import BOT_TOKEN
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("✅ Бот запущен и готов к работе")
    app.run_polling()

if __name__ == "__main__":
    start_polling()
