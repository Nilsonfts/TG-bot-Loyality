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

# --- ОБНОВЛЕННЫЕ ИМПОРТЫ ---
from constants import (
    MENU_TEXT_REGISTER, MENU_TEXT_SUBMIT, MENU_TEXT_SEARCH,
    MENU_TEXT_SETTINGS, MENU_TEXT_MAIN_MENU, States
)
import navigation_handlers
import registration_handlers
import form_handlers
import search_handlers
import settings_handlers

# --- НАСТРОЙКА СРЕДЫ И ЛОГГИРОВАНИЯ ---
# Рекомендуется использовать python-dotenv для загрузки переменных из .env файла
# from dotenv import load_dotenv
# load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
# Уменьшаем "шум" от httpx, который использует python-telegram-bot
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> None:
    """Инициализирует и запускает бота."""
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Фильтры для кнопок меню ---
    # Использование set для быстрой проверки - хорошая практика при большом количестве кнопок
    menu_buttons = {
        MENU_TEXT_REGISTER, MENU_TEXT_SUBMIT, MENU_TEXT_SEARCH,
        MENU_TEXT_SETTINGS, MENU_TEXT_MAIN_MENU
    }
    filters_map = {
        'reg': filters.Regex(f"^{MENU_TEXT_REGISTER}$"),
        'submit': filters.Regex(f"^{MENU_TEXT_SUBMIT}$"),
        'search': filters.Regex(f"^{MENU_TEXT_SEARCH}$"),
        'settings': filters.Regex(f"^{MENU_TEXT_SETTINGS}$"),
        'main': filters.Regex(f"^{MENU_TEXT_MAIN_MENU}$")
    }

    # Универсальный фильтр для текста, который не является командой или кнопкой меню
    text_filter = filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^({'|'.join(menu_buttons)})$")

    # --- Обработчики отмены и возврата в меню ---
    fallback_handler = MessageHandler(filters_map['main'], navigation_handlers.end_conversation_and_show_menu)
    cancel_handler = CommandHandler("cancel", navigation_handlers.cancel)

    # --- ДИАЛОГ РЕГИСТРАЦИИ (с использованием States Enum) ---
    reg_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['reg'], registration_handlers.start_registration)],
        states={
            States.REGISTER_CONTACT: [MessageHandler(filters.CONTACT, registration_handlers.handle_contact)],
            States.REGISTER_FIO: [MessageHandler(text_filter, registration_handlers.get_fio)],
            States.REGISTER_EMAIL: [MessageHandler(text_filter, registration_handlers.get_email)],
            States.REGISTER_JOB_TITLE: [MessageHandler(text_filter, registration_handlers.get_job_title_and_finish)],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    # --- ДИАЛОГ ПОДАЧИ ЗАЯВКИ (с использованием States Enum) ---
    form_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['submit'], form_handlers.start_form_conversation)],
        states={
            States.OWNER_LAST_NAME: [MessageHandler(text_filter, form_handlers.get_owner_last_name)],
            States.OWNER_FIRST_NAME: [MessageHandler(text_filter, form_handlers.get_owner_first_name)],
            States.REASON: [MessageHandler(text_filter, form_handlers.get_reason)],
            States.CARD_TYPE: [CallbackQueryHandler(form_handlers.get_card_type)],
            States.CARD_NUMBER: [MessageHandler(text_filter, form_handlers.get_card_number)],
            States.CATEGORY: [CallbackQueryHandler(form_handlers.get_category)],
            States.AMOUNT: [MessageHandler(text_filter, form_handlers.get_amount)],
            States.FREQUENCY: [CallbackQueryHandler(form_handlers.get_frequency)],
            States.ISSUE_LOCATION: [MessageHandler(text_filter, form_handlers.get_issue_location)],
            States.CONFIRMATION: [
                CallbackQueryHandler(form_handlers.submit, "^submit$"),
                CallbackQueryHandler(form_handlers.restart_conversation, "^restart$")
            ],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    # --- ДИАЛОГ ПОИСКА (с использованием States Enum) ---
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['search'], search_handlers.search_command)],
        states={
            States.SEARCH_CHOOSE_FIELD: [CallbackQueryHandler(search_handlers.search_field_chosen)],
            States.AWAIT_SEARCH_QUERY: [MessageHandler(text_filter, search_handlers.perform_search)]
        },
        fallbacks=[fallback_handler, cancel_handler],
    )
    
    # Группировка обработчиков для лучшей читаемости
    # --- Основные команды и сообщения ---
    application.add_handler(CommandHandler("start", navigation_handlers.start_command))
    application.add_handler(MessageHandler(filters_map['main'], navigation_handlers.main_menu_command))
    application.add_handler(MessageHandler(filters_map['settings'], settings_handlers.show_settings))

    # --- Диалоги ---
    application.add_handler(reg_conv)
    application.add_handler(form_conv)
    application.add_handler(search_conv)

    # --- Обработчики колбэков из меню настроек ---
    settings_callbacks = {
        "settings_my_cards": settings_handlers.my_cards_command,
        "my_profile": settings_handlers.my_profile_callback, # Добавил обработчик для профиля
        "stats_show": settings_handlers.stats_callback,
        "export_csv": settings_handlers.export_csv_callback,
        "help_show": settings_handlers.help_callback,
        "back_to_settings": settings_handlers.back_to_settings_callback,
        "noop": settings_handlers.noop_callback
    }
    for pattern, handler in settings_callbacks.items():
        application.add_handler(CallbackQueryHandler(handler, f"^{pattern}$"))

    application.add_handler(CallbackQueryHandler(settings_handlers.handle_pagination, r"^paginate_"))


    # --- Запускаем бота ---
    logger.info("Бот запускается с обновленной структурой...")
    application.run_polling()


if __name__ == "__main__":
    main()
