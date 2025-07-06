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
import form_handlers
import search_handlers
import settings_handlers
import admin_handlers
import reports

# --- НАСТРОЙКА СРЕДЫ И ЛОГГИРОВАНИЯ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOSS_ID = os.getenv("BOSS_ID")
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

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    filters_map = {
        'submit': filters.Regex(f"^{constants.MENU_TEXT_SUBMIT}$"),
        'search': filters.Regex(f"^{constants.MENU_TEXT_SEARCH}$"),
        'settings': filters.Regex(f"^{constants.MENU_TEXT_SETTINGS}$"),
        'main': filters.Regex(f"^{constants.MENU_TEXT_MAIN_MENU}$")
    }
    combined_menu_filter = (filters_map['submit'] | filters_map['search'] | filters_map['settings'] | filters_map['main'])
    text_filter = filters.TEXT & ~filters.COMMAND & ~combined_menu_filter

    fallback_handler = MessageHandler(filters_map['main'], navigation_handlers.end_conversation_and_show_menu)
    cancel_handler = CommandHandler("cancel", navigation_handlers.cancel)

    # --- Диалог для админа (отклонение заявки) ---
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_handlers.reject_request_start, pattern=f"^{constants.CALLBACK_REJECT_PREFIX}")],
        states={
            constants.AWAIT_REJECT_REASON: [MessageHandler(text_filter, admin_handlers.reject_request_reason)],
        },
        fallbacks=[cancel_handler],
        conversation_timeout=300,
        per_message=True  # <-- ДОБАВЛЕНО для исправления предупреждения
    )

    # --- Диалог подачи заявки ---
    form_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['submit'], form_handlers.start_form_conversation)],
        states={
            constants.REGISTER_CONTACT: [MessageHandler(filters.CONTACT, form_handlers.handle_contact_registration)],
            constants.REGISTER_FIO: [MessageHandler(text_filter, form_handlers.get_registration_fio)],
            constants.REGISTER_EMAIL: [MessageHandler(text_filter, form_handlers.get_registration_email)],
            constants.REGISTER_JOB_TITLE: [MessageHandler(text_filter, form_handlers.get_registration_job_title)],
            constants.OWNER_LAST_NAME: [MessageHandler(text_filter, form_handlers.get_owner_last_name)],
            constants.OWNER_FIRST_NAME: [MessageHandler(text_filter, form_handlers.get_owner_first_name)],
            constants.REASON: [MessageHandler(text_filter, form_handlers.get_reason)],
            constants.CARD_TYPE: [CallbackQueryHandler(form_handlers.get_card_type)],
            constants.CARD_NUMBER: [MessageHandler(text_filter, form_handlers.get_card_number)],
            constants.CATEGORY: [CallbackQueryHandler(form_handlers.get_category)],
            constants.AMOUNT: [MessageHandler(text_filter, form_handlers.get_amount)],
            constants.FREQUENCY: [CallbackQueryHandler(form_handlers.get_frequency)],
            constants.ISSUE_LOCATION: [
                CallbackQueryHandler(form_handlers.get_issue_location_from_button),
                MessageHandler(text_filter, form_handlers.get_issue_location_from_text)
            ],
            constants.CONFIRMATION: [
                CallbackQueryHandler(form_handlers.submit, "^submit$"),
                CallbackQueryHandler(form_handlers.restart_conversation, "^restart$")
            ],
        },
        fallbacks=[fallback_handler, cancel_handler],
        per_message=True # <-- ДОБАВЛЕНО для исправления предупреждения
    )

    # --- Диалог поиска ---
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['search'], search_handlers.search_command)],
        states={
            constants.SEARCH_CHOOSE_FIELD: [CallbackQueryHandler(search_handlers.search_field_chosen)],
            constants.AWAIT_SEARCH_QUERY: [MessageHandler(text_filter, search_handlers.perform_search)]
        },
        fallbacks=[fallback_handler, cancel_handler],
        per_message=True # <-- ДОБАВЛЕНО для исправления предупреждения
    )

    # --- Добавляем все обработчики ---
    application.add_handler(CommandHandler("start", navigation_handlers.start_command))
    application.add_handler(MessageHandler(filters_map['main'], navigation_handlers.main_menu_command))
    application.add_handler(MessageHandler(filters_map['settings'], settings_handlers.show_settings))

    application.add_handler(form_conv)
    application.add_handler(search_conv)
    application.add_handler(admin_conv)

    # Обработчики колбэков
    application.add_handler(CallbackQueryHandler(admin_handlers.approve_request, pattern=f"^{constants.CALLBACK_APPROVE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(settings_handlers.my_profile_callback, "^settings_my_profile$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.my_cards_command, "^settings_my_cards$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.help_callback, "^help_show$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.stats_callback, "^stats_show$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.export_csv_callback, "^export_csv$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.back_to_settings_callback, "^back_to_settings$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.handle_pagination, r"^paginate_"))
    application.add_handler(CallbackQueryHandler(settings_handlers.noop_callback, r"^noop$"))
    
    # --- Планировщик отчетов ---
    if BOSS_ID:
        job_queue = application.job_queue
        # Устанавливаем часовой пояс, например, МСК (UTC+3)
        tz = datetime.timezone(datetime.timedelta(hours=3))
        # Запускать каждый день в 09:00 по указанному часовому поясу
        job_queue.run_daily(reports.send_daily_summary, time=datetime.time(hour=9, minute=0, tzinfo=tz))
        logger.info(f"Scheduled daily reports for the boss at 09:00 in {tz}.")

    # --- Запускаем бота ---
    logger.info("Бот запускается с системой согласования и отчетами...")
    application.run_polling()

if __name__ == "__main__":
    main()
