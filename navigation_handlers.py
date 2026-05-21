# -*- coding: utf-8 -*-

import logging
import asyncio
import time
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

import g_sheets
import keyboards

logger = logging.getLogger(__name__)

# Простая защита от кратких дублей отправки главного меню на одного пользователя
LAST_MENU_SENT: dict = {}
DEBOUNCE_SECONDS = 1.5


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Точка входа. Проверяет регистрацию и показывает правильное главное меню.
    """
    user = update.effective_user
    if not user:
        logger.error("Не удалось определить пользователя в start_command.")
        return

    # Используем улучшенную функцию проверки регистрации
    is_registered = await asyncio.to_thread(g_sheets.is_user_registered, str(user.id))
    keyboard = keyboards.get_main_menu_keyboard(is_registered)

    # Определяем, как отправлять сообщение (от команды или от кнопки)
    message_sender = update.message or (update.callback_query and update.callback_query.message)
    if not message_sender:
        logger.error("Не удалось найти объект сообщения для ответа в start_command.")
        return

    chat_id = user.id
    text_to_send = "Вы в главном меню:" if is_registered else "Здравствуйте! Для начала работы пройдите регистрацию, нажав кнопку ниже."

    # Debounce: если мы уже отправляли меню этому пользователю недавно — пропускаем
    try:
        last = LAST_MENU_SENT.get(chat_id)
        now = time.time()
        if last and (now - last) < DEBOUNCE_SECONDS:
            logger.info(f"Пропускаем дублирующую отправку главного меню для {chat_id} (прошло {now-last:.2f}s)")
            return
    except Exception:
        # В редких случаях словарь может содержать неожиданные данные — просто продолжаем
        logger.debug("Не удалось проверить debounce для start_command", exc_info=True)
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

    # Запоминаем момент последней отправки меню этому пользователю
    try:
        LAST_MENU_SENT[chat_id] = time.time()
    except Exception:
        logger.debug("Не удалось установить метку последней отправки меню", exc_info=True)


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
