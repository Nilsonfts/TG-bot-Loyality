# -*- coding: utf-8 -*-

"""
Главный файл бота.
Инициализирует бота, настраивает обработчики из модулей
и запускает цикл опроса.
"""

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
import registration_handlers # Новый обработчик
import form_handlers
import search_handlers
import settings_handlers
import admin_handlers
import reports  # Новый импорт для отчетов
import utils

# --- НАСТРОЙКА СРЕДЫ И ЛОГГИРОВАНИЯ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Инициализирует и запускает бота."""
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен.")
        return

    # Инициализируем локальную базу данных
    if utils.init_local_db():
        logger.info("Локальная база данных успешно инициализирована")
    else:
        logger.warning("Не удалось инициализировать локальную базу данных, работаем только с Google Sheets")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Фильтры для кнопок меню ---
    filters_map = {
        'reg': filters.Regex(f"^{constants.MENU_TEXT_REGISTER}$"),
        'submit': filters.Regex(f"^{constants.MENU_TEXT_SUBMIT}$"),
        'search': filters.Regex(f"^{constants.MENU_TEXT_SEARCH}$"),
        'settings': filters.Regex(f"^{constants.MENU_TEXT_SETTINGS}$"),
        'main': filters.Regex(f"^{constants.MENU_TEXT_MAIN_MENU}$")
    }

    combined_menu_filter = (
        filters_map['reg'] | filters_map['submit'] | filters_map['search'] |
        filters_map['settings'] | filters_map['main']
    )
    text_filter = filters.TEXT & ~filters.COMMAND & ~combined_menu_filter

    # --- Обработчики отмены и возврата в меню ---
    fallback_handler = MessageHandler(filters_map['main'], navigation_handlers.end_conversation_and_show_menu)
    cancel_handler = CommandHandler("cancel", navigation_handlers.cancel)

    # --- ДИАЛОГ РЕГИСТРАЦИИ ---
    reg_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['reg'], registration_handlers.start_registration)],
        states={
            constants.REGISTER_CONTACT: [MessageHandler(filters.CONTACT, registration_handlers.handle_contact)],
            constants.REGISTER_FIO: [MessageHandler(text_filter, registration_handlers.get_fio)],
            constants.REGISTER_EMAIL: [MessageHandler(text_filter, registration_handlers.get_email)],
            constants.REGISTER_JOB_TITLE: [MessageHandler(text_filter, registration_handlers.get_job_title_and_finish)],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    # --- ДИАЛОГ ПОДАЧИ ЗАЯВКИ ---
    form_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['submit'], form_handlers.start_form_conversation)],
        states={
            constants.OWNER_LAST_NAME: [MessageHandler(text_filter, form_handlers.get_owner_last_name)],
            constants.OWNER_FIRST_NAME: [MessageHandler(text_filter, form_handlers.get_owner_first_name)],
            constants.REASON: [MessageHandler(text_filter, form_handlers.get_reason)],
            constants.CARD_TYPE: [CallbackQueryHandler(form_handlers.get_card_type)],
            constants.CARD_NUMBER: [MessageHandler(text_filter, form_handlers.get_card_number)],
            constants.CATEGORY: [CallbackQueryHandler(form_handlers.get_category)],
            constants.AMOUNT: [MessageHandler(text_filter, form_handlers.get_amount)],
            constants.FREQUENCY: [CallbackQueryHandler(form_handlers.get_frequency)],
            constants.ISSUE_LOCATION: [MessageHandler(text_filter, form_handlers.get_issue_location)],
            constants.CONFIRMATION: [
                CallbackQueryHandler(form_handlers.submit, "^submit$"),
                CallbackQueryHandler(form_handlers.restart_conversation, "^restart$")
            ],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    # --- ДИАЛОГ ПОИСКА ---
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['search'], search_handlers.search_command)],
        states={
            constants.SEARCH_CHOOSE_FIELD: [CallbackQueryHandler(search_handlers.search_field_chosen)],
            constants.AWAIT_SEARCH_QUERY: [MessageHandler(text_filter, search_handlers.perform_search)]
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    # --- ДИАЛОГ АДМИНСКИХ ДЕЙСТВИЙ ---
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_handlers.reject_request_start, f"^{constants.CALLBACK_REJECT_PREFIX}")],
        states={
            constants.AWAIT_REJECT_REASON: [MessageHandler(text_filter, admin_handlers.reject_request_reason)]
        },
        fallbacks=[cancel_handler],
    )

    # --- Добавляем все обработчики в приложение ---
    application.add_handler(CommandHandler("start", navigation_handlers.start_command))
    application.add_handler(MessageHandler(filters_map['main'], navigation_handlers.main_menu_command))
    application.add_handler(MessageHandler(filters_map['settings'], settings_handlers.show_settings))

    application.add_handler(reg_conv) # Новый диалог
    application.add_handler(form_conv)
    application.add_handler(search_conv)
    application.add_handler(admin_conv) # Админский диалог

    # Обработчики колбэков для меню настроек
    # ... (здесь ваш код для обработчиков кнопок из settings_handlers остается без изменений)
    application.add_handler(CallbackQueryHandler(settings_handlers.my_cards_command, "^settings_my_cards$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.help_callback, "^help_show$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.stats_callback, "^stats_show$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.export_csv_callback, "^export_csv$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.back_to_settings_callback, "^back_to_settings$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.handle_pagination, r"^paginate_"))
    application.add_handler(CallbackQueryHandler(settings_handlers.noop_callback, r"^noop$"))

    # Обработчики админских колбэков (отдельно от ConversationHandler для корректной работы)
    application.add_handler(CallbackQueryHandler(admin_handlers.approve_request, f"^{constants.CALLBACK_APPROVE_PREFIX}"))
    
    # ВАЖНО: CallbackQueryHandler для reject должен быть в ConversationHandler выше!

    # Добавляем периодические задачи
    job_queue = application.job_queue
    if job_queue:
        # Ежедневные отчеты админу в 9:00
        job_queue.run_daily(reports.send_daily_summary, time=datetime.time(hour=9, minute=0), days=(0, 1, 2, 3, 4, 5, 6))
        
        # Еженедельная аналитика по понедельникам в 10:00
        job_queue.run_daily(reports.send_weekly_analytics, time=datetime.time(hour=10, minute=0), days=(0,))  # 0 = понедельник
        
        # Напоминания пользователям по средам в 14:00
        job_queue.run_daily(reports.send_user_reminders, time=datetime.time(hour=14, minute=0), days=(2,))  # 2 = среда
        
        # Очистка кэша каждые 6 часов
        job_queue.run_repeating(utils.cleanup_old_cache, interval=21600, first=10)  # 21600 сек = 6 часов
        
        # Резервное копирование БД каждый день в 02:00
        job_queue.run_daily(utils.backup_local_db, time=datetime.time(hour=2, minute=0), days=(0, 1, 2, 3, 4, 5, 6))
        
        logger.info("Все периодические задачи настроены")

    # --- Запускаем бота ---
    logger.info("Бот запускается с разделенной логикой регистрации...")
    application.run_polling()


if __name__ == "__main__":
    main()
