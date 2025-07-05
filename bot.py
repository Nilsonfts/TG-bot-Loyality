# -*- coding: utf-8 -*-

"""
Main bot file.
This file initializes the bot, sets up handlers from the 'handlers' module,
and starts the polling loop.
"""

import logging
import os
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)

import constants
import handlers

# --- ENVIRONMENT & LOGGING SETUP ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Initializes and runs the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("CRITICAL ERROR: TELEGRAM_BOT_TOKEN is not set.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Filters for menu buttons ---
    filters_map = {
        'reg': filters.Regex(f"^{constants.MENU_TEXT_REGISTER}$"),
        'submit': filters.Regex(f"^{constants.MENU_TEXT_SUBMIT}$"),
        'search': filters.Regex(f"^{constants.MENU_TEXT_SEARCH}$"),
        'settings': filters.Regex(f"^{constants.MENU_TEXT_SETTINGS}$"),
        'main': filters.Regex(f"^{constants.MENU_TEXT_MAIN_MENU}$")
    }

    # <<< ИЗМЕНЕНИЕ ЗДЕСЬ >>>
    # Правильный способ объединить фильтры, чтобы исключить их из обработки в диалогах.
    # Вместо неработающего .join() мы используем оператор | (ИЛИ) для самих фильтров.
    combined_menu_filter = (
        filters_map['reg'] | filters_map['submit'] | filters_map['search'] |
        filters_map['settings'] | filters_map['main']
    )
    # Фильтр для текста, который не является ни командой, ни кнопкой меню.
    text_filter = filters.TEXT & ~filters.COMMAND & ~combined_menu_filter
    
    # --- Fallback and cancel handlers ---
    fallback_handler = MessageHandler(filters_map['main'], handlers.main_menu_command)
    cancel_handler = CommandHandler("cancel", handlers.cancel)

    # --- Conversation Handlers ---
    reg_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['reg'], handlers.start_registration)],
        states={
            constants.REGISTER_CONTACT: [MessageHandler(filters.CONTACT, handlers.handle_contact_registration)],
            constants.REGISTER_FIO: [MessageHandler(text_filter, handlers.get_registration_fio)],
            constants.REGISTER_EMAIL: [MessageHandler(text_filter, handlers.get_registration_email)],
            constants.REGISTER_JOB_TITLE: [MessageHandler(text_filter, handlers.finish_registration)],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    form_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['submit'], handlers.start_form_conversation)],
        states={
            constants.OWNER_LAST_NAME: [MessageHandler(text_filter, handlers.get_owner_last_name)],
            constants.OWNER_FIRST_NAME: [MessageHandler(text_filter, handlers.get_owner_first_name)],
            constants.REASON: [MessageHandler(text_filter, handlers.get_reason)],
            constants.CARD_TYPE: [CallbackQueryHandler(handlers.get_card_type)],
            constants.CARD_NUMBER: [MessageHandler(text_filter, handlers.get_card_number)],
            constants.CATEGORY: [CallbackQueryHandler(handlers.get_category)],
            constants.AMOUNT: [MessageHandler(text_filter, handlers.get_amount)],
            constants.FREQUENCY: [CallbackQueryHandler(handlers.get_frequency)],
            constants.ISSUE_LOCATION: [MessageHandler(text_filter, handlers.get_issue_location)],
            constants.CONFIRMATION: [
                CallbackQueryHandler(handlers.submit, "^submit$"),
                CallbackQueryHandler(handlers.restart_conversation, "^restart$")
            ],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['search'], handlers.search_command)],
        states={
            constants.SEARCH_CHOOSE_FIELD: [CallbackQueryHandler(handlers.search_field_chosen)],
            constants.AWAIT_SEARCH_QUERY: [MessageHandler(text_filter, handlers.perform_search)]
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    # --- Add all handlers to the application ---
    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(MessageHandler(filters_map['main'], handlers.main_menu_command))
    application.add_handler(MessageHandler(filters_map['settings'], handlers.show_settings))
    
    application.add_handler(reg_conv)
    application.add_handler(form_conv)
    application.add_handler(search_conv)
    
    # Callback handlers for settings menu and pagination
    application.add_handler(CallbackQueryHandler(handlers.my_cards_command, "^settings_my_cards$"))
    application.add_handler(CallbackQueryHandler(handlers.help_callback, "^help_show$"))
    application.add_handler(CallbackQueryHandler(handlers.stats_callback, "^stats_show$"))
    application.add_handler(CallbackQueryHandler(handlers.export_csv_callback, "^export_csv$"))
    application.add_handler(CallbackQueryHandler(handlers.back_to_settings_callback, "^back_to_settings$"))
    application.add_handler(CallbackQueryHandler(handlers.handle_pagination, r"^paginate_"))
    application.add_handler(CallbackQueryHandler(handlers.noop_callback, r"^noop$"))

    # --- Start the bot ---
    logger.info("Bot is starting in modular structure (v4)...")
    application.run_polling()


if __name__ == "__main__":
    main()
