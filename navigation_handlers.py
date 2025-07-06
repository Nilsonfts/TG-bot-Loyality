# -*- coding: utf-8 -*-

import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

import g_sheets
import keyboards

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Точка входа. Проверяет регистрацию и показывает правильное главное меню.
    """
    user = update.effective_user
    if not user:
        logger.error("Не удалось определить пользователя в start_command.")
        return

    # Используем улучшенную функцию проверки регистрации
    is_registered = g_sheets.is_user_registered(str(user.id))
    keyboard = keyboards.get_main_menu_keyboard(is_registered)

    # Определяем, как отправлять сообщение (от команды или от кнопки)
    message_sender = update.message or (update.callback_query and update.callback_query.message)
    if not message_sender:
        logger.error("Не удалось найти объект сообщения для ответа в start_command.")
        return

    chat_id = user.id
    text_to_send = "Вы в главном меню:" if is_registered else "Здравствуйте! Для начала работы, подайте вашу первую заявку."

    # --- ИЗМЕНЕНИЕ ЛОГИКИ ---
    # Мы больше не удаляем предыдущее сообщение.
    # Просто отправляем новое сообщение с главным меню.
    if update.callback_query:
        # Если это колбэк (например, после нажатия "Отправить заявку"),
        # отправляем новое сообщение, оставляя старое.
        await context.bot.send_message(
            chat_id=chat_id,
            text=text_to_send,
            reply_markup=keyboard
        )
    else:
        # Если это команда /start или текстовое сообщение
        await message_sender.reply_text(text_to_send, reply_markup=keyboard)


async def main_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Псевдоним для /start, чтобы показать главное меню."""
    await start_command(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет любой активный диалог и показывает главное меню."""
    await update.message.reply_text("Действие отменено.") # Убрали ReplyKeyboardRemove
    await start_command(update, context)
    return ConversationHandler.END


async def end_conversation_and_show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Правильно завершает любой активный диалог и показывает главное меню.
    Используется как fallback для кнопки 'Главное меню'.
    """
    await start_command(update, context)
    return ConversationHandler.END
