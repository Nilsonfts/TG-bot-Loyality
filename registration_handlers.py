# -*- coding: utf-8 -*-

import logging
import re
from datetime import datetime

from telegram import Update, ReplyKeyboardRemove, KeyboardButton, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

import g_sheets
import navigation_handlers
from constants import States

logger = logging.getLogger(__name__)

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    """Начинает диалог регистрации нового пользователя."""
    context.user_data.clear()
    keyboard = [[KeyboardButton("📱 Поделиться контактом", request_contact=True)]]
    await update.message.reply_text(
        "Добро пожаловать! Давайте пройдем быструю регистрацию.\n\n"
        "Пожалуйста, поделитесь своим контактом, нажав на кнопку ниже.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return States.REGISTER_CONTACT

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    contact, user = update.message.contact, update.effective_user
    context.user_data['initiator_phone'] = contact.phone_number.replace('+', '')
    context.user_data['initiator_username'] = f"@{user.username}" if user.username else "–"
    await update.message.reply_text("✅ Контакт получен!\n\n👤 Введите ваше <b>полное ФИО</b>.", reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
    return States.REGISTER_FIO

async def get_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    context.user_data['initiator_fio'] = update.message.text
    await update.message.reply_text("✅ ФИО принято.\n\n📧 Введите вашу <b>рабочую почту</b>.", parse_mode=ParseMode.HTML)
    return States.REGISTER_EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    email = update.message.text
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        await update.message.reply_text("❌ Формат почты неверный. Попробуйте еще раз.")
        return States.REGISTER_EMAIL
    context.user_data['initiator_email'] = email
    await update.message.reply_text("✅ Почта принята.\n\n🏢 Введите вашу <b>должность</b>.", parse_mode=ParseMode.HTML)
    return States.REGISTER_JOB_TITLE

async def get_job_title_and_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Получает должность, НЕ записывает данные в таблицу, а только кэширует их.
    Запись в таблицу произойдет при первой подаче заявки.
    """
    context.user_data['initiator_job_title'] = update.message.text
    
    await update.message.reply_text("Сохраняю ваши данные...")

    user_id = str(update.effective_user.id)
    
    # --- ИЗМЕНЕНИЕ ---
    # Мы больше НЕ вызываем g_sheets.write_row() на этом этапе.
    # Строка будет создана только при подаче заявки.
    # success = g_sheets.write_row(data_to_write)

    await update.message.reply_text(
        "🎉 <b>Регистрация успешно завершена!</b>\n\n"
        "Теперь вы можете подавать заявки через главное меню.", 
        parse_mode=ParseMode.HTML
    )
    
    # Логика кэширования остается. Это КЛЮЧЕВОЙ момент.
    # При первой подаче заявки, данные будут взяты именно из этого кэша.
    initiator_data_to_cache = {
        'initiator_username': context.user_data.get('initiator_username'),
        'initiator_email': context.user_data.get('initiator_email'),
        'initiator_fio': context.user_data.get('initiator_fio'),
        'initiator_job_title': context.user_data.get('initiator_job_title'),
        'initiator_phone': context.user_data.get('initiator_phone'),
    }
    g_sheets.INITIATOR_DATA_CACHE[user_id] = {
        'data': initiator_data_to_cache,
        'timestamp': datetime.now()
    }
    g_sheets.REGISTRATION_STATUS_CACHE[user_id] = {'timestamp': datetime.now()}
    logger.info(f"User {user_id} data and registration status were cached after registration. No row was written to the sheet.")

    context.user_data.clear()
    await navigation_handlers.main_menu_command(update, context)
    return ConversationHandler.END
