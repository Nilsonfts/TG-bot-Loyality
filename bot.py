# -*- coding: utf-8 -*-

import logging
import os
import datetime
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)

import constants
# --- ОБНОВЛЕННЫЕ ИМПОРТЫ ---
import navigation_handlers
import form_handlers
import search_handlers
import settings_handlers
import admin_handlers # Новый
import reports # Новый

# --- НАСТРОЙКА СРЕДЫ И ЛОГГИРОВАНИЯ ---
# ... (как раньше)
BOSS_ID = os.getenv("BOSS_ID")

def main() -> None:
    # ... (инициализация application как раньше)

    # --- Обработчики отмены и возврата в меню ---
    fallback_handler = MessageHandler(filters.Regex(f"^{constants.MENU_TEXT_MAIN_MENU}$"), navigation_handlers.end_conversation_and_show_menu)
    cancel_handler = CommandHandler("cancel", navigation_handlers.cancel)

    # --- Админский диалог для отклонения заявки ---
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_handlers.reject_request_start, pattern=f"^{constants.CALLBACK_REJECT_PREFIX}")],
        states={
            constants.AWAIT_REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.reject_request_reason)],
        },
        fallbacks=[cancel_handler],
    )
    
    # ... (form_conv и search_conv без изменений)

    # --- Добавляем все обработчики в приложение ---
    application.add_handler(CommandHandler("start", navigation_handlers.start_command))
    
    # --- Основные диалоги ---
    application.add_handler(form_handlers.form_conv) # Предполагая, что вынесли его из main
    application.add_handler(search_handlers.search_conv)
    application.add_handler(admin_conv) # Новый админский диалог

    # --- Обработчики кнопок меню ---
    # ... (как раньше)

    # --- Обработчики колбэков ---
    # Админские
    application.add_handler(CallbackQueryHandler(admin_handlers.approve_request, pattern=f"^{constants.CALLBACK_APPROVE_PREFIX}"))
    # Настройки
    application.add_handler(CallbackQueryHandler(settings_handlers.my_profile_callback, "^settings_my_profile$"))
    # ... (остальные колбэки из settings_handlers)

    # --- Запускаем планировщик отчетов ---
    if BOSS_ID:
        job_queue = application.job_queue
        # Запускать каждый день в 09:00 по времени сервера
        job_queue.run_daily(reports.send_daily_summary, time=datetime.time(hour=9, minute=0))
        logger.info("Scheduled daily reports for the boss.")

    # --- Запускаем бота ---
    logger.info("Бот запускается с системой согласования и отчетами...")
    application.run_polling()

if __name__ == "__main__":
    main()
