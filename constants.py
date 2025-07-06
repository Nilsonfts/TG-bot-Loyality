# -*- coding: utf-8 -*-

"""
This file contains all the project constants, such as UI texts and conversation states.
"""

from enum import Enum, auto

# --- Bot UI Constants ---
MENU_TEXT_REGISTER = "✍️ Регистрация"
MENU_TEXT_SUBMIT = "✍️ Подать заявку"
MENU_TEXT_SEARCH = "🔍 Поиск"
MENU_TEXT_SETTINGS = "⚙️ Настройки"
MENU_TEXT_MAIN_MENU = "🏠 Главное меню"
CARDS_PER_PAGE = 7

# --- State Constants for Conversation Handlers ---
class States(Enum):
    """
    Состояния для ConversationHandlers. Использование Enum делает код более читаемым.
    """
    # Registration States
    REGISTER_CONTACT = auto()
    REGISTER_FIO = auto()
    REGISTER_EMAIL = auto()
    REGISTER_JOB_TITLE = auto()
    
    # Form Submission States
    OWNER_LAST_NAME = auto()
    OWNER_FIRST_NAME = auto()
    REASON = auto()
    CARD_TYPE = auto()
    CARD_NUMBER = auto()
    CATEGORY = auto()
    AMOUNT = auto()
    FREQUENCY = auto()
    ISSUE_LOCATION = auto()
    CONFIRMATION = auto()
    
    # Search States
    SEARCH_CHOOSE_FIELD = auto()
    AWAIT_SEARCH_QUERY = auto()

    # Admin states
    AWAIT_REJECT_REASON = auto()


# --- Callback Data Prefixes ---
CALLBACK_APPROVE_PREFIX = "approve:"
CALLBACK_REJECT_PREFIX = "reject:"


# --- Google Sheet Column Names ---
class SheetCols:
    TIMESTAMP = 'Отметка времени'
    TG_ID = 'ТГ Заполняющего'
    TG_TAG = 'Тег Telegram'
    EMAIL = 'Адрес электронной почты'
    FIO_INITIATOR = 'ФИО Инициатора'
    JOB_TITLE = 'Должность'
    PHONE_INITIATOR = 'Телефон инициатора'
    OWNER_LAST_NAME_COL = 'Фамилия Владельца'
    OWNER_FIRST_NAME_COL = 'Имя владельца карты'
    REASON_COL = 'Причина выдачи'
    CARD_TYPE_COL = 'Какую карту регистрируем?'
    CARD_NUMBER_COL = 'Номер карты'
    CATEGORY_COL = 'Статья пополнения карт'
    AMOUNT_COL = 'Сумма бартера или % скидки'
    FREQUENCY_COL = 'Периодичность'
    ISSUE_LOCATION_COL = 'Город/Бар выдачи'
    STATUS_COL = 'Статус Согласования'
    REASON_REJECT = 'Причина отказа'
