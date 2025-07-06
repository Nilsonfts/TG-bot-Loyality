# -*- coding: utf-8 -*-

import logging
import re
from datetime import datetime

from telegram import Update, ReplyKeyboardRemove, KeyboardButton, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

import g_sheets
import navigation_handlers
from constants import (
    REGISTER_CONTACT, REGISTER_FIO, REGISTER_EMAIL, REGISTER_JOB_TITLE
)

logger = logging.getLogger(__name__)

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог регистрации нового пользователя."""
    context.user_data.clear()
    keyboard = [[KeyboardButton("📱 Поделиться контактом", request_contact=True)]]
    await update.message.reply_text(
        "Добро пожаловать! Давайте пройдем быструю регистрацию.\n\n"
        "Пожалуйста, поделитесь своим контактом, нажав на кнопку ниже.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return REGISTER_CONTACT

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact, user = update.message.contact, update.effective_user
    context.user_data['initiator_phone'] = contact.phone_number.replace('+', '')
    context.user_data['initiator_username'] = f"@{user.username}" if user.username else "–"
    await update.message.reply_text("✅ Контакт получен!\n\n👤 Введите ваше <b>полное ФИО</b>.", reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
    return REGISTER_FIO

async def get_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['initiator_fio'] = update.message.text
    await update.message.reply_text("✅ ФИО принято.\n\n📧 Введите вашу <b>рабочую почту</b>.", parse_mode=ParseMode.HTML)
    return REGISTER_EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text("❌ Формат почты неверный. Попробуйте еще раз.")
        return REGISTER_EMAIL
    context.user_data['initiator_email'] = email
    await update.message.reply_text("✅ Почта принята.\n\n🏢 Введите вашу <b>должность</b>.", parse_mode=ParseMode.HTML)
    return REGISTER_JOB_TITLE

async def get_job_title_and_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает должность, записывает данные и кэширует их для избежания "гонки"."""
    context.user_data['initiator_job_title'] = update.message.text
    
    await update.message.reply_text("Проверяю данные и сохраняю...")

    user_id = str(update.effective_user.id)
    
    # Готовим данные для записи
    data_to_write = {
        'submission_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'tg_user_id': user_id,
        'initiator_username': context.user_data.get('initiator_username', '–'),
        'initiator_email': context.user_data.get('initiator_email'),
        'initiator_fio': context.user_data.get('initiator_fio'),
        'initiator_job_title': context.user_data.get('initiator_job_title'),
        'initiator_phone': context.user_data.get('initiator_phone'),
        'status': 'Зарегистрирован'
    }

    success = g_sheets.write_row(data_to_write)

    if success:
        await update.message.reply_text("🎉 <b>Регистрация успешно завершена!</b>\n\nТеперь вам доступны все функции бота.", parse_mode=ParseMode.HTML)
        
        # === ИСПРАВЛЕНИЕ ОШИБКИ ЗДЕСЬ ===
        initiator_data_to_cache = {
            'initiator_username': context.user_data.get('initiator_username'),
            'initiator_email': context.user_data.get('initiator_email'),
            'initiator_fio': context.user_data.get('initiator_fio'),
            'initiator_job_title': context.user_data.get('initiator_job_title'),
            'initiator_phone': context.user_data.get('initiator_phone'),
        }
        g_sheets.INITIATOR_DATA_CACHE[user_id] = {
            'data': initiator_data_to_cache,
            'timestamp': datetime.now() # <-- ИСПРАВЛЕНО
        }
        g_sheets.REGISTRATION_STATUS_CACHE[user_id] = {'timestamp': datetime.now()} # <-- ИСПРАВЛЕНО
        logger.info(f"User {user_id} data and registration status were cached immediately after registration.")

    else:
        await update.message.reply_text("❌ Произошла ошибка при сохранении данных. Попробуйте позже.")

    context.user_data.clear()
    await navigation_handlers.main_menu_command(update, context)
    return ConversationHandler.END
