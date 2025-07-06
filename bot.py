# -*- coding: utf-8 -*-

"""
Главный файл бота.
Инициализирует бота, настраивает обработчики из модулей
и запускает цикл опроса.
"""

import logging
import os
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)

import constants
# --- НОВЫЕ ИМПОРТЫ ОБРАБОТЧИКОВ ---
import navigation_handlers
import registration_handlers
import form_handlers
import search_handlers
import settings_handlers

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
    # Фильтр для текста, который не является ни командой, ни кнопкой меню.
    text_filter = filters.TEXT & ~filters.COMMAND & ~combined_menu_filter

    # --- Обработчики отмены и возврата в меню (ИСПРАВЛЕНО) ---
    # Этот обработчик теперь корректно завершает любой диалог
    fallback_handler = MessageHandler(filters_map['main'], navigation_handlers.end_conversation_and_show_menu)
    cancel_handler = CommandHandler("cancel", navigation_handlers.cancel)

    # --- Обработчики диалогов (Conversation Handlers) ---
    reg_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['reg'], registration_handlers.start_registration)],
        states={
            constants.REGISTER_CONTACT: [MessageHandler(filters.CONTACT, registration_handlers.handle_contact_registration)],
            constants.REGISTER_FIO: [MessageHandler(text_filter, registration_handlers.get_registration_fio)],
            constants.REGISTER_EMAIL: [MessageHandler(text_filter, registration_handlers.get_registration_email)],
            constants.REGISTER_JOB_TITLE: [MessageHandler(text_filter, registration_handlers.finish_registration)],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

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

    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['search'], search_handlers.search_command)],
        states={
            constants.SEARCH_CHOOSE_FIELD: [CallbackQueryHandler(search_handlers.search_field_chosen)],
            constants.AWAIT_SEARCH_QUERY: [MessageHandler(text_filter, search_handlers.perform_search)]
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    # --- Добавляем все обработчики в приложение ---
    application.add_handler(CommandHandler("start", navigation_handlers.start_command))
    application.add_handler(MessageHandler(filters_map['main'], navigation_handlers.main_menu_command))
    application.add_handler(MessageHandler(filters_map['settings'], settings_handlers.show_settings))

    application.add_handler(reg_conv)
    application.add_handler(form_conv)
    application.add_handler(search_conv)

    # Обработчики колбэков для меню настроек и пагинации
    application.add_handler(CallbackQueryHandler(settings_handlers.my_cards_command, "^settings_my_cards$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.help_callback, "^help_show$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.stats_callback, "^stats_show$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.export_csv_callback, "^export_csv$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.back_to_settings_callback, "^back_to_settings$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.handle_pagination, r"^paginate_"))
    application.add_handler(CallbackQueryHandler(settings_handlers.noop_callback, r"^noop$"))

    # --- Запускаем бота ---
    logger.info("Бот запускается в модульной структуре (v5)...")
    application.run_polling()


if __name__ == "__main__":
    main()
