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
MENU_TEXT_CANCEL_FORM = "❌ Отменить заполнение"
CARDS_PER_PAGE = 7

# --- Доступные значения "Город/Бар" для шага ISSUE_LOCATION ---
CITY_OPTIONS = [
    "ЕВГ_СПБ_НЕВ",
    "ЕВГ_СПБ_РУБ",
    "ЕВГ_МСК_ПЯТ",
    "ЕВГ_МСК_ЦВЕТ",
    "ЕВГ_ЧЕХ",
    "ЕВГ_КЗН",
    "ЕВГ_САМ",
]

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
    TG_ID = 'ID\nИнициатора'  # Исправлено: добавлен перенос строки
    TG_TAG = 'ТГ\nИнициатора'  # Исправлено: добавлен перенос строки
    EMAIL = 'Адрес электронной почты'
    FIO_INITIATOR = 'ФИО \nИнициатора'  # Исправлено: добавлен пробел и перенос
    JOB_TITLE = 'Должность'
    PHONE_INITIATOR = 'Телефон\nИнициатора'  # Исправлено: добавлен перенос строки
    OWNER_FIRST_NAME_COL = 'Имя владельца карты '  # Исправлено: добавлен пробел в конце
    OWNER_LAST_NAME_COL = 'Фамилия Владельца карты '  # Исправлено: добавлен пробел в конце
    REASON_COL = 'Причина выдачи бартера/скидки '  # Исправлено: добавлен пробел в конце
    CARD_TYPE_COL = 'Какую карту регистрируем? '  # Исправлено: добавлен пробел в конце
    CARD_NUMBER_COL = 'Номер карты'
    CATEGORY_COL = 'Статья пополнения карт '  # Исправлено: добавлен пробел в конце
    AMOUNT_COL = 'Сумма бартера или  %  скидки '  # Исправлено: добавлены пробелы
    FREQUENCY_COL = 'Периодичность наполнения бартера'
    ISSUE_LOCATION_COL = 'БАР'
    STATUS_COL = 'ЗАЯВКА'
    APPROVAL_STATUS = 'Согласовано САД/Директором по рекламе '  # Исправлено: добавлен пробел в конце
    START_DATE = 'STARTDATE (пополнение по четвергам после 22:00)'
    ACTIVATED = 'Активировано'
    REASON_REJECT = 'Причина отказа'  # Оставляем для обратной совместимости
