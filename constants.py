# -*- coding: utf-8 -*-

"""
This file contains all the project constants, such as UI texts and conversation states.
"""

# --- Bot UI Constants ---
MENU_TEXT_REGISTER = "✍️ Регистрация" # Новая кнопка
MENU_TEXT_SUBMIT = "✍️ Подать заявку"
MENU_TEXT_SEARCH = "🔍 Поиск"
MENU_TEXT_SETTINGS = "⚙️ Настройки"
MENU_TEXT_MAIN_MENU = "🏠 Главное меню"
CARDS_PER_PAGE = 7

# --- State Constants for Conversation Handlers ---
(
    # Registration States
    REGISTER_CONTACT,
    REGISTER_FIO,
    REGISTER_EMAIL,
    REGISTER_JOB_TITLE,
    
    # Form Submission States
    OWNER_LAST_NAME,
    OWNER_FIRST_NAME,
    REASON,
    CARD_TYPE,
    CARD_NUMBER,
    CATEGORY,
    AMOUNT,
    FREQUENCY,
    ISSUE_LOCATION,
    CONFIRMATION,
    
    # Search States
    SEARCH_CHOOSE_FIELD,
    AWAIT_SEARCH_QUERY,
) = range(16)
