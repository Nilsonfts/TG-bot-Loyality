# -*- coding: utf-8 -*-

import logging
import re
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

import g_sheets
import keyboards
from constants import REGISTER_CONTACT, REGISTER_FIO, REGISTER_EMAIL, REGISTER_JOB_TITLE

logger = logging.getLogger(__name__)


async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс регистрации."""
    context.user_data.clear()
    keyboard = [[KeyboardButton("📱 Поделиться контактом", request_contact=True)]]
    await update.message.reply_text(
        "Начинаем регистрацию. Пожалуйста, поделитесь своим контактом.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return REGISTER_CONTACT


async def handle_contact_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает получение контакта пользователя."""
    contact, user = update.message.contact, update.effective_user
    # В этой проверке нет необходимости, так как кнопка всегда отправляет свой контакт
    # if contact.user_id != user.id:
    #     await update.message.reply_text("Пожалуйста, поделитесь своим собственным контактом.", reply_markup=ReplyKeyboardRemove())
    #     return await cancel(update, context) # 'cancel' теперь в navigation_handlers

    context.user_data['initiator_phone'] = contact.phone_number.replace('+', '')
    context.user_data['initiator_username'] = f"@{user.username}" if user.username else "–"
    await update.message.reply_text("✅ Контакт получен!\n\n👤 Введите ваше <b>полное ФИО</b>.", reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
    return REGISTER_FIO


async def get_registration_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает ФИО пользователя."""
    context.user_data['initiator_fio'] = update.message.text
    await update.message.reply_text("✅ ФИО принято.\n\n📧 Введите вашу <b>рабочую почту</b>.", parse_mode=ParseMode.HTML)
    return REGISTER_EMAIL


async def get_registration_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает и валидирует email."""
    email = update.message.text
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text("❌ Формат почты неверный. Попробуйте еще раз.")
        return REGISTER_EMAIL
    context.user_data['initiator_email'] = email
    await update.message.reply_text("✅ Почта принята.\n\n🏢 Введите вашу <b>должность</b>.", parse_mode=ParseMode.HTML)
    return REGISTER_JOB_TITLE


async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершает регистрацию, сохраняет данные и кэширует их."""
    user_id = str(update.effective_user.id)
    context.user_data['initiator_job_title'] = update.message.text

    success = g_sheets.write_to_sheet(
        data=context.user_data,
        submission_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        tg_user_id=user_id
    )

    if success:
        g_sheets.cache_user_data(user_id, context.user_data)
        await update.message.reply_text("🎉 <b>Регистрация успешно завершена!</b>", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
        full_keyboard = keyboards.get_main_menu_keyboard(is_registered=True)
        await update.message.reply_text("Теперь вам доступны все функции бота.", reply_markup=full_keyboard)
    else:
        await update.message.reply_text(
            "❌ Ошибка при сохранении регистрации. Пожалуйста, попробуйте снова.",
            reply_markup=keyboards.get_main_menu_keyboard(is_registered=False)
        )

    context.user_data.clear()
    return ConversationHandler.END
