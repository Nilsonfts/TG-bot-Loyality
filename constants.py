# -*- coding: utf-8 -*-

"""
This file contains all the project constants, such as UI texts and conversation states.
"""

# --- Bot UI Constants ---
MENU_TEXT_REGISTER = "✍️ Регистрация"
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

    # Admin states
    AWAIT_REJECT_REASON,
) = range(17)


# --- Callback Data Prefixes ---
CALLBACK_APPROVE_PREFIX = "approve:"
CALLBACK_REJECT_PREFIX = "reject:"


# --- Google Sheet Column Names ---
class SheetCols:
    TIMESTAMP = 'Отметка времени'
    TG_ID = 'IDИнициатора'  # Изменено с 'ТГ Заполняющего'
    TG_TAG = 'ТГИнициатора'  # Изменено с 'Тег Telegram'
    EMAIL = 'Адрес электронной почты'
    FIO_INITIATOR = 'ФИО Инициатора'
    JOB_TITLE = 'Должность'
    PHONE_INITIATOR = 'Телефон Инициатора'  # Изменено с 'Телефон инициатора'
    OWNER_FIRST_NAME_COL = 'Имя владельца карты'  # Поменял местами с фамилией
    OWNER_LAST_NAME_COL = 'Фамилия Владельца карты'  # Изменено с 'Фамилия Владельца'
    REASON_COL = 'Причина выдачи бартера/скидки'  # Изменено с 'Причина выдачи'
    CARD_TYPE_COL = 'Какую карту регистрируем?'
    CARD_NUMBER_COL = 'Номер карты'
    CATEGORY_COL = 'Статья пополнения карт'
    AMOUNT_COL = 'Сумма бартера или % скидки'  # Изменено с 'Сумма бартера или % скидки'
    FREQUENCY_COL = 'Периодичность наполнения бартера'  # Изменено с 'Периодичность'
    ISSUE_LOCATION_COL = 'БАР'  # Изменено с 'Город/Бар выдачи'
    STATUS_COL = 'ЗАЯВКА'  # Изменено с 'Статус Согласования'
    APPROVAL_STATUS = 'Согласовано САД/Директором по рекламе'  # Новое поле
    START_DATE = 'STARTDATE (пополнение по четвергам после 22:00)'  # Новое поле
    ACTIVATED = 'Активировано'  # Новое поле
    REASON_REJECT = 'Причина отказа'  # Оставляем для обратной совместимости
