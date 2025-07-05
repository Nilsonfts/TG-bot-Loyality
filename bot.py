# -*- coding: utf-8 -*-

"""
This is a Telegram bot for managing loyalty card applications.
It allows users to register, submit applications for new cards, view their existing applications,
and perform searches. All data is stored in a Google Sheet.
An admin user (BOSS_ID) has extended privileges to view all applications and statistics.
"""

import logging
import os
import re
import json
from datetime import datetime
import asyncio
import io
import csv
from collections import Counter

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InputFile,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURATION & CONSTANTS ---

# Load from environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOSS_ID = os.getenv("BOSS_ID")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

# --- Bot UI Constants ---
# Main Menu
MENU_TEXT_SUBMIT = "✍️ Подать заявку"
MENU_TEXT_SEARCH = "🔍 Поиск"
MENU_TEXT_SETTINGS = "⚙️ Настройки"
MENU_TEXT_MAIN_MENU = "🏠 Главное меню"

# Pagination
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
    ISSUE_LOCATION, # Formerly COMMENT
    CONFIRMATION,
    # Search States
    SEARCH_CHOOSE_FIELD,
    AWAIT_SEARCH_QUERY,
) = range(16)


# --- LOGGING SETUP ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- GOOGLE SHEETS INTEGRATION ---
def get_gspread_client():
    """
    Authenticates with Google Sheets API using credentials from environment variables.
    
    Returns:
        gspread.Client: An authorized gspread client object or None if authentication fails.
    """
    try:
        if GOOGLE_CREDS_JSON:
            creds_info = json.loads(GOOGLE_CREDS_JSON)
            scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
            return gspread.authorize(creds)
        else:
            logger.error("GOOGLE_CREDS_JSON environment variable not set.")
            return None
    except json.JSONDecodeError:
        logger.error("Failed to parse GOOGLE_CREDS_JSON. Check if it's valid JSON.")
        return None
    except Exception as e:
        logger.error(f"Error authenticating with Google Sheets: {e}")
        return None

def get_sheet_data(sheet_name="sheet1"):
    """
    Fetches all data records from the specified Google Sheet.

    Args:
        sheet_name (str): The name of the worksheet to access. Defaults to "sheet1".

    Returns:
        list: A list of dictionaries representing all rows, or an empty list on error.
    """
    client = get_gspread_client()
    if not client or not GOOGLE_SHEET_KEY:
        logger.error("Google client or Sheet Key is not available.")
        return []
    try:
        sheet = client.open_by_key(GOOGLE_SHEET_KEY).worksheet(sheet_name)
        return sheet.get_all_records()
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"Spreadsheet with key {GOOGLE_SHEET_KEY} not found.")
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet '{sheet_name}' not found in the spreadsheet.")
    except Exception as e:
        logger.error(f"Error fetching data from Google Sheet: {e}")
    return []


def find_initiator_in_sheet(user_id: str):
    """
    Finds the most recent registration data for a given user ID in the sheet.

    Args:
        user_id (str): The Telegram user ID to search for.

    Returns:
        dict: A dictionary with user data if found, otherwise None.
    """
    all_records = get_sheet_data()
    for row in reversed(all_records):
        if str(row.get('ТГ Заполняющего')) == user_id:
            return {
                "initiator_username": row.get('Тег Telegram'),
                "initiator_email": row.get('Адрес электронной почты'),
                "initiator_fio": row.get('ФИО Инициатора'),
                "initiator_job_title": row.get('Должность'),
                "initiator_phone": row.get('Телефон инициатора'),
            }
    return None

def get_cards_from_sheet(user_id: str = None) -> list:
    """
    Retrieves card application records, either for a specific user or all users.
    
    Args:
        user_id (str, optional): The Telegram user ID to filter by. If None, returns all cards.
    
    Returns:
        list: A reversed list of card records.
    """
    all_records = get_sheet_data()
    if user_id:
        user_cards = [record for record in all_records if str(record.get('ТГ Заполняющего')) == user_id]
    else:
        user_cards = all_records
    return list(reversed(user_cards))


def write_to_sheet(data: dict, submission_time: str, tg_user_id: str) -> bool:
    """
    Writes a new application row to the Google Sheet.

    IMPORTANT: This function assumes a fixed column order in the Google Sheet.
    The order must be:
    'Отметка времени', 'ТГ Заполняющего', 'Тег Telegram', 'Адрес электронной почты',
    'ФИО Инициатора', 'Должность', 'Телефон инициатора', 'Фамилия Владельца',
    'Имя владельца карты', 'Причина выдачи бартера/скидки', 'Какую карту регистрируем?',
    'Номер карты', 'Статья пополнения карт', 'Сумма бартера или % скидки',
    'Периодичность наполнения бартера', 'Комментарий (привязка к какому бару)', 'Статус Согласования'
    """
    client = get_gspread_client()
    if not client or not GOOGLE_SHEET_KEY:
        return False
    try:
        sheet = client.open_by_key(GOOGLE_SHEET_KEY).sheet1
        
        # This is the new, robust way. We define the order and don't rely on header names.
        final_row = [
            submission_time,
            tg_user_id,
            data.get('initiator_username', '–'),
            data.get('initiator_email', ''),
            data.get('initiator_fio', ''),
            data.get('initiator_job_title', ''),
            data.get('initiator_phone', ''),
            data.get('owner_last_name', ''),
            data.get('owner_first_name', ''),
            data.get('reason', ''),
            data.get('card_type', ''),
            data.get('card_number', ''),
            data.get('category', ''),
            data.get('amount', ''),
            data.get('frequency', ''),
            data.get('issue_location', ''), # Note the key change from 'comment'
            'Заявка' # Default status
        ]
        
        sheet.append_row(final_row, value_input_option='USER_ENTERED')
        logger.info(f"Successfully wrote a row for user {tg_user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to write data to sheet for user {tg_user_id}: {e}")
        return False

# --- MESSAGE CLEANUP UTILITIES ---
def add_message_to_delete(context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Adds a message ID to a list in chat_data for later deletion."""
    if 'messages_to_delete' not in context.chat_data:
        context.chat_data['messages_to_delete'] = []
    context.chat_data['messages_to_delete'].append(message_id)

async def delete_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Deletes all messages stored in the deletion list for a given chat."""
    message_ids = context.chat_data.pop('messages_to_delete', [])
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id, msg_id)
        except Exception as e:
            # Ignore errors if message is already deleted or not found
            logger.warning(f"Could not delete message {msg_id}: {e}")
            pass

# --- CORE UI & NAVIGATION HANDLERS ---
async def get_chat_id(update: Update) -> int | None:
    """Safely gets chat_id from either a Message or a CallbackQuery."""
    if update.effective_chat:
        return update.effective_chat.id
    return None

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the main menu keyboard to the user."""
    chat_id = await get_chat_id(update)
    if not chat_id: return

    keyboard = [[MENU_TEXT_SUBMIT], [MENU_TEXT_SEARCH, MENU_TEXT_SETTINGS], [MENU_TEXT_MAIN_MENU]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    # Determine how to send the message based on the update type
    if update.message:
        await update.message.reply_text("Вы в главном меню. Выберите действие:", reply_markup=reply_markup)
    elif update.callback_query:
        # If coming from a callback, it's better to send a new message
        await context.bot.send_message(chat_id, "Вы в главном меню. Выберите действие:", reply_markup=reply_markup)


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the settings menu with inline buttons."""
    user_id = str(update.effective_user.id)
    is_boss = (user_id == BOSS_ID)
    
    cards_button_text = "🗂️ Все заявки" if is_boss else "🗂️ Мои Заявки"
    
    keyboard = [
        [InlineKeyboardButton(cards_button_text, callback_data="settings_my_cards")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats_show")],
        [InlineKeyboardButton("📄 Экспорт в CSV", callback_data="export_csv")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_show")],
    ]
    await update.message.reply_text("Меню настроек:", reply_markup=InlineKeyboardMarkup(keyboard))

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the help text when the help button is pressed."""
    query = update.callback_query
    await query.answer()
    help_text = (
        "<b>Справка по боту</b>\n\n"
        f"▫️ <b>{MENU_TEXT_SUBMIT}</b> - запуск анкеты для новой карты.\n"
        f"▫️ <b>{MENU_TEXT_SETTINGS}</b> - доступ к просмотру заявок, статистике и экспорту.\n"
        f"▫️ <b>{MENU_TEXT_SEARCH}</b> - поиск по существующим заявкам.\n"
        f"▫️ <b>{MENU_TEXT_MAIN_MENU}</b> - возврат в главное меню и отмена любого действия."
    )
    keyboard = [[InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]
    await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def back_to_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Back to Settings' button press."""
    query = update.callback_query
    await query.answer()
    
    # Re-create the settings menu to show it again
    user_id = str(query.from_user.id)
    is_boss = (user_id == BOSS_ID)
    cards_button_text = "🗂️ Все заявки" if is_boss else "🗂️ Мои Заявки"
    keyboard = [
        [InlineKeyboardButton(cards_button_text, callback_data="settings_my_cards")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats_show")],
        [InlineKeyboardButton("📄 Экспорт в CSV", callback_data="export_csv")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_show")],
    ]
    await query.edit_message_text("Меню настроек:", reply_markup=InlineKeyboardMarkup(keyboard))


# --- FEATURES (STATS, EXPORT, PAGINATION) ---

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generates and displays statistics based on user's cards."""
    query = update.callback_query
    user_id = str(query.from_user.id)
    is_boss = (user_id == BOSS_ID)
    await query.edit_message_text("📊 Собираю статистику...")

    cards_data = get_cards_from_sheet(user_id=None if is_boss else user_id)
    
    if not cards_data:
        await query.edit_message_text("Нет данных для отображения статистики.")
        return

    total_cards = len(cards_data)
    barter_count = sum(1 for card in cards_data if card.get('Какую карту регистрируем?') == 'Бартер')
    discount_count = total_cards - barter_count
    
    try:
        category_counter = Counter(card.get('Статья пополнения карт') for card in cards_data if card.get('Статья пополнения карт'))
        most_common_category = category_counter.most_common(1)[0][0] if category_counter else "–"
    except Exception:
        most_common_category = "Не удалось посчитать"

    text = f"<b>📊 Статистика</b>\n\n"
    text += f"🗂️ {'Всего заявок в системе' if is_boss else 'Подано вами заявок'}: <b>{total_cards}</b>\n"
    text += f"    - Карт 'Бартер': <code>{barter_count}</code>\n"
    text += f"    - Карт 'Скидка': <code>{discount_count}</code>\n\n"
    text += f"📈 Самая частая статья пополнения: <b>{most_common_category}</b>"

    keyboard = [[InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def export_csv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exports user's (or all) card data to a CSV file."""
    query = update.callback_query
    user_id = str(query.from_user.id)
    is_boss = (user_id == BOSS_ID)
    await query.edit_message_text("📄 Формирую CSV файл...")

    cards_to_export = get_cards_from_sheet(user_id=None if is_boss else user_id)
    
    if not cards_to_export:
        await query.edit_message_text("Нет данных для экспорта.")
        return

    output = io.StringIO()
    # Ensure we have headers even if the list is empty (though we checked)
    if cards_to_export:
        writer = csv.DictWriter(output, fieldnames=cards_to_export[0].keys())
        writer.writeheader()
        writer.writerows(cards_to_export)
        output.seek(0)
        
        file_name = f"export_{datetime.now().strftime('%Y-%m-%d')}.csv"
        file_to_send = InputFile(output.getvalue().encode('utf-8-sig'), filename=file_name)
        
        await context.bot.send_document(chat_id=query.message.chat_id, document=file_to_send)
        await query.message.delete() # Clean up the "Forming CSV..." message


async def display_paginated_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, data_key: str, list_title: str):
    """
    Generic function to display a paginated list of items from context.user_data.
    """
    query = update.callback_query
    message_to_edit = query.message
    
    all_items = context.user_data.get(data_key, [])
    if not all_items:
        await message_to_edit.edit_text("🤷 Ничего не найдено.")
        return

    start_index = page * CARDS_PER_PAGE
    end_index = start_index + CARDS_PER_PAGE
    items_on_page = all_items[start_index:end_index]
    total_pages = (len(all_items) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE

    text = f"<b>{list_title} (Стр. {page + 1}/{total_pages}):</b>\n\n"
    for card in items_on_page:
        owner_name = f"{card.get('Имя владельца карты','')} {card.get('Фамилия Владельца','-')}".strip()
        amount = card.get('Сумма бартера или % скидки', '')
        amount_text = ""
        if amount:
            if card.get('Какую карту регистрируем?') == 'Скидка':
                amount_text = f"💰 Скидка: {amount}%\n"
            else:
                amount_text = f"💰 Бартер: {amount} ₽\n"
        
        text += (f"👤 <b>Владелец:</b> {owner_name}\n"
                 f"📞 Номер: {card.get('Номер карты', '-')}\n"
                 f"{amount_text}"
                 f"<b>Согласование:</b> <code>{card.get('Статус Согласования', '–')}</code>\n"
                 f"📅 Дата: {card.get('Отметка времени', '-')}\n")
        
        if str(update.effective_user.id) == BOSS_ID:
            text += f"🤵‍♂️ <b>Инициатор:</b> {card.get('ФИО Инициатора', '-')} ({card.get('Тег Telegram', '-')})\n"
        text += "--------------------\n"

    # --- Pagination Buttons ---
    keyboard = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"paginate_{data_key}_{page - 1}"))
    row.append(InlineKeyboardButton(f" {page + 1}/{total_pages} ", callback_data="noop")) # noop = no operation
    if end_index < len(all_items):
        row.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"paginate_{data_key}_{page + 1}"))
    keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")])

    await message_to_edit.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback query handler for pagination buttons."""
    query = update.callback_query
    await query.answer()
    
    _, data_key, page_str = query.data.split('_')
    page = int(page_str)
    
    list_title = "Все заявки" if data_key == "my_cards" and str(update.effective_user.id) == BOSS_ID else "Ваши поданные заявки"
    await display_paginated_list(update, context, page=page, data_key=data_key, list_title=list_title)


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """An empty callback handler for buttons that shouldn't do anything (like page counters)."""
    await update.callback_query.answer()


async def my_cards_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays the user's cards, initiating pagination."""
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    is_boss = (user_id == BOSS_ID)

    await query.edit_message_text("👑 Админ-режим: Загружаю ВСЕ заявки..." if is_boss else "🔍 Загружаю ваши заявки...")

    all_cards = get_cards_from_sheet(user_id=None if is_boss else user_id)
    if not all_cards:
        await query.edit_message_text("🤷 Заявок не найдено.")
        return

    context.user_data['my_cards'] = all_cards # Use a more descriptive key
    list_title = "Все заявки" if is_boss else "Ваши поданные заявки"
    await display_paginated_list(update, context, page=0, data_key='my_cards', list_title=list_title)


# --- SEARCH CONVERSATION ---
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the search conversation by asking for the search criteria."""
    keyboard = [
        [InlineKeyboardButton("По ФИО владельца", callback_data="search_by_name")],
        [InlineKeyboardButton("По номеру карты", callback_data="search_by_phone")]
    ]
    await update.message.reply_text("Выберите критерий поиска:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SEARCH_CHOOSE_FIELD


async def search_field_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the user's choice of search field."""
    query = update.callback_query
    await query.answer()
    context.user_data['search_field'] = query.data
    await query.edit_message_text("Теперь введите ваш поисковый запрос:")
    return AWAIT_SEARCH_QUERY


async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Performs the search based on the query and field, then displays results."""
    user_id = str(update.effective_user.id)
    is_boss = (user_id == BOSS_ID)
    search_query = update.message.text.lower().strip()
    search_field = context.user_data.get('search_field')

    loading_message = await update.message.reply_text("🔍 Выполняю поиск...")
    
    all_cards = get_cards_from_sheet(user_id=None if is_boss else user_id)
    if not all_cards:
        await loading_message.edit_text("🤷 Заявок для поиска нет.")
        return ConversationHandler.END

    if search_field == 'search_by_name':
        search_results = [
            card for card in all_cards 
            if search_query in card.get('Имя владельца карты', '').lower() or 
               search_query in card.get('Фамилия Владельца', '').lower()
        ]
    elif search_field == 'search_by_phone':
        search_results = [card for card in all_cards if search_query in str(card.get('Номер карты', ''))]
    else:
        search_results = []
    
    context.user_data['search_results'] = search_results
    await loading_message.delete()
    
    # We need to simulate a CallbackQuery update to reuse the pagination function
    # This is a trick to unify the display logic.
    class MockCallbackQuery:
        def __init__(self, message):
            self.message = message
    class MockUpdate:
        def __init__(self, message, user):
            self.callback_query = MockCallbackQuery(message)
            self.effective_user = user

    mock_update = MockUpdate(update.message, update.effective_user)
    await display_paginated_list(mock_update, context, page=0, data_key='search_results', list_title="Результаты поиска")

    return ConversationHandler.END


# --- APPLICATION FORM CONVERSATION ---

async def start_form_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the application form, checking if the user is new or returning."""
    context.user_data.clear()
    context.chat_data.clear()
    add_message_to_delete(context, update.message.message_id)
    user_id = str(update.effective_user.id)

    # Check for existing registration data first
    if context.user_data.get('initiator_registered'):
        msg = await update.message.reply_text("Начинаем подачу новой заявки.\n\nВведите <b>Фамилию</b> владельца карты.", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
        add_message_to_delete(context, msg.message_id)
        return OWNER_LAST_NAME

    # If not in context, try finding in sheet (for returning users in a new session)
    initiator_data = find_initiator_in_sheet(user_id)
    if initiator_data:
        context.user_data.update(initiator_data)
        context.user_data['initiator_registered'] = True
        msg = await update.message.reply_text(f"С возвращением, {initiator_data['initiator_fio']}!\n\nВведите <b>Фамилию</b> владельца карты.", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
        add_message_to_delete(context, msg.message_id)
        return OWNER_LAST_NAME
    else:
        # New user registration
        keyboard = [[KeyboardButton("📱 Авторизоваться (поделиться контактом)", request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        msg = await update.message.reply_text("Здравствуйте! Похоже, вы здесь впервые. Для начала работы, пройдите быструю авторизацию.", reply_markup=reply_markup)
        add_message_to_delete(context, msg.message_id)
        return REGISTER_CONTACT

# ... (Registration steps: handle_contact_registration, get_registration_fio, etc.)
async def handle_contact_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    contact = update.message.contact
    user = update.effective_user
    if contact.user_id != user.id:
        await update.message.reply_text("Пожалуйста, поделитесь своим собственным контактом.", reply_markup=ReplyKeyboardRemove())
        return await cancel(update, context) 

    context.user_data['initiator_phone'] = contact.phone_number.replace('+', '')
    context.user_data['initiator_username'] = f"@{user.username}" if user.username else "–"
    msg = await update.message.reply_text("✅ Контакт получен!\n\n👤 Введите ваше <b>полное ФИО</b> для отчетности.", reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
    add_message_to_delete(context, msg.message_id)
    return REGISTER_FIO

async def get_registration_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    context.user_data['initiator_fio'] = update.message.text
    msg = await update.message.reply_text("✅ ФИО принято.\n\n📧 Введите вашу <b>рабочую почту</b>.", parse_mode=ParseMode.HTML)
    add_message_to_delete(context, msg.message_id)
    return REGISTER_EMAIL

async def get_registration_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    email = update.message.text
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        msg = await update.message.reply_text("❌ Формат почты неверный. Попробуйте еще раз.")
        add_message_to_delete(context, msg.message_id)
        return REGISTER_EMAIL

    context.user_data['initiator_email'] = email
    msg = await update.message.reply_text("✅ Почта принята.\n\n🏢 Введите вашу <b>должность</b>.", parse_mode=ParseMode.HTML)
    add_message_to_delete(context, msg.message_id)
    return REGISTER_JOB_TITLE

async def get_registration_job_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    context.user_data['initiator_job_title'] = update.message.text
    context.user_data['initiator_registered'] = True

    await delete_messages(context, update.effective_chat.id)
    await update.message.reply_text("🎉 <b>Регистрация успешно завершена!</b>", parse_mode=ParseMode.HTML)
    await show_main_menu(update, context) # Show main menu after registration
    return ConversationHandler.END

# --- Form Steps ---
async def get_owner_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    context.user_data['owner_last_name'] = update.message.text
    msg = await update.message.reply_text("<b>Имя</b> владельца карты.", parse_mode=ParseMode.HTML)
    add_message_to_delete(context, msg.message_id)
    return OWNER_FIRST_NAME

async def get_owner_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    context.user_data['owner_first_name'] = update.message.text
    msg = await update.message.reply_text("Причина выдачи?")
    add_message_to_delete(context, msg.message_id)
    return REASON

async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    context.user_data['reason'] = update.message.text
    keyboard = [[InlineKeyboardButton("Бартер", callback_data="Бартер"), InlineKeyboardButton("Скидка", callback_data="Скидка")]]
    msg = await update.message.reply_text("Тип карты?", reply_markup=InlineKeyboardMarkup(keyboard))
    add_message_to_delete(context, msg.message_id)
    return CARD_TYPE

async def get_card_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['card_type'] = query.data
    await query.message.delete()
    msg = await context.bot.send_message(chat_id=query.message.chat_id, text=f"Выбрано: {query.data}.\n\nНомер карты (телефон через 8)?")
    add_message_to_delete(context, msg.message_id)
    return CARD_NUMBER

async def get_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    number = update.message.text
    if not (number.startswith('8') and number[1:].isdigit() and len(number) == 11):
        msg = await update.message.reply_text("Неверный формат. Нужно 11 цифр, начиная с 8.")
        add_message_to_delete(context, msg.message_id)
        return CARD_NUMBER

    context.user_data['card_number'] = number
    keyboard = [[InlineKeyboardButton("АРТ", callback_data="АРТ"), InlineKeyboardButton("МАРКЕТ", callback_data="МАРКЕТ")], [InlineKeyboardButton("Операционный блок", callback_data="Операционный блок")], [InlineKeyboardButton("СКИДКА", callback_data="СКИДКА"), InlineKeyboardButton("Сертификат", callback_data="Сертификат")], [InlineKeyboardButton("Учредители", callback_data="Учредители")]]
    msg = await update.message.reply_text("Статья пополнения?", reply_markup=InlineKeyboardMarkup(keyboard))
    add_message_to_delete(context, msg.message_id)
    return CATEGORY

async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['category'] = query.data
    prompt = "Сумма бартера?" if context.user_data.get('card_type') == "Бартер" else "Процент скидки?"
    await query.message.delete()
    msg = await context.bot.send_message(chat_id=query.message.chat_id, text=f"Статья: {query.data}.\n\n{prompt}")
    add_message_to_delete(context, msg.message_id)
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    text = update.message.text
    if not text.isdigit():
        msg = await update.message.reply_text("Нужно ввести только число.")
        add_message_to_delete(context, msg.message_id)
        return AMOUNT

    context.user_data['amount'] = text
    keyboard = [[InlineKeyboardButton("Разовая", callback_data="Разовая")], [InlineKeyboardButton("Дополнить к балансу", callback_data="Дополнить к балансу")], [InlineKeyboardButton("Замена номера карты", callback_data="Замена номера карты")]]
    msg = await update.message.reply_text("Периодичность?", reply_markup=InlineKeyboardMarkup(keyboard))
    add_message_to_delete(context, msg.message_id)
    return FREQUENCY

async def get_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles frequency selection and asks for the issue location.
    THIS IS THE EDITED FUNCTION.
    """
    query = update.callback_query
    await query.answer()
    context.user_data['frequency'] = query.data
    await query.message.delete()
    # ** THE FIX IS HERE: Changed prompt from "Комментарий?" to "Город_БАР выдачи?" **
    msg = await context.bot.send_message(chat_id=query.message.chat_id, text=f"Выбрано: {query.data}.\n\n<b>Город_БАР выдачи?</b>", parse_mode=ParseMode.HTML)
    add_message_to_delete(context, msg.message_id)
    return ISSUE_LOCATION # Go to the newly named state

def format_summary(data: dict) -> str:
    """Formats the final summary of the application for user confirmation."""
    owner_full_name = f"{data.get('owner_first_name', '')} {data.get('owner_last_name', '')}".strip()
    amount_label = 'Скидка' if data.get('card_type') == 'Скидка' else 'Сумма'
    amount_unit = '%' if data.get('card_type') == 'Скидка' else ' ₽'
    
    return (
        "<b>Пожалуйста, проверьте итоговую заявку:</b>\n\n"
        "--- <b>Инициатор</b> ---\n"
        f"👤 <b>ФИО:</b> {data.get('initiator_fio', '-')}\n"
        f"📧 <b>Почта:</b> {data.get('initiator_email', '-')}\n"
        f"🏢 <b>Должность:</b> {data.get('initiator_job_title', '-')}\n\n"
        "--- <b>Карта лояльности</b> ---\n"
        f"💳 <b>Владелец:</b> {owner_full_name}\n"
        f"📞 <b>Номер:</b> {data.get('card_number', '-')}\n"
        f"✨ <b>Тип:</b> {data.get('card_type', '-')}\n"
        f"💰 <b>{amount_label}:</b> {data.get('amount', '0')}{amount_unit}\n"
        f"📈 <b>Статья:</b> {data.get('category', '-')}\n"
        f"🔄 <b>Периодичность:</b> {data.get('frequency', '-')}\n"
        f"📍 <b>Город/Бар выдачи:</b> {data.get('issue_location', '-')}\n\n" # ** THE FIX IS HERE **
        "<i>Все верно?</i>"
    )

async def get_issue_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Gets the issue location (formerly comment) and displays the final summary.
    THIS IS THE RENAMED FUNCTION.
    """
    add_message_to_delete(context, update.message.message_id)
    context.user_data['issue_location'] = update.message.text # ** THE FIX IS HERE **
    
    summary = format_summary(context.user_data)
    keyboard = [[InlineKeyboardButton("✅ Да, все верно", callback_data="submit"), InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")]]
    
    await delete_messages(context, update.effective_chat.id)
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Final submission handler. Writes data to sheet and ends conversation.
    This function is now safe to call from a CallbackQuery.
    """
    query = update.callback_query
    await query.answer(text="Отправляю заявку...", show_alert=False)
    
    user_id = str(query.from_user.id)
    submission_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    success = write_to_sheet(context.user_data, submission_time, user_id)
    
    original_text = query.message.text_html
    status_text = "\n\n<b>Статус:</b> ✅ Заявка успешно отправлена." if success else "\n\n<b>Статус:</b> ❌ Ошибка! Не удалось сохранить заявку. Обратитесь к администратору."
    
    # Edit the confirmation message with the final status and remove buttons
    await query.edit_message_text(text=original_text + status_text, parse_mode=ParseMode.HTML, reply_markup=None)

    context.user_data.clear()
    context.chat_data.clear()
    await show_main_menu(update, context) # Return to main menu
    return ConversationHandler.END


async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the 'restart' button, effectively starting the form over."""
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    # We need to simulate a message update to re-enter the conversation
    class MockMessage:
        def __init__(self, chat, message_id, user):
            self.chat = chat
            self.message_id = message_id
            self.from_user = user
    class MockUpdate:
         def __init__(self, query):
            self.message = MockMessage(query.message.chat, query.message.message_id, query.from_user)
            self.effective_user = query.from_user
    
    return await start_form_conversation(MockUpdate(query), context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels any active conversation and returns to the main menu."""
    chat_id = await get_chat_id(update)
    if chat_id:
        await delete_messages(context, chat_id)
        await context.bot.send_message(chat_id, "Действие отменено. Вы возвращены в главное меню.")
    
    await show_main_menu(update, context)
    return ConversationHandler.END

# --- MAIN BOT SETUP ---
def main() -> None:
    """Initializes and runs the Telegram bot."""
    if not all([TELEGRAM_BOT_TOKEN, BOSS_ID, GOOGLE_SHEET_KEY, GOOGLE_CREDS_JSON]):
        logger.critical("CRITICAL ERROR: One or more environment variables are not set. Bot cannot start.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Define filters for main menu buttons
    form_filter = filters.Regex(f"^{MENU_TEXT_SUBMIT}$")
    search_filter = filters.Regex(f"^{MENU_TEXT_SEARCH}$")
    settings_filter = filters.Regex(f"^{MENU_TEXT_SETTINGS}$")
    main_menu_filter = filters.Regex(f"^{MENU_TEXT_MAIN_MENU}$")

    # Filter for text messages that are not commands or menu buttons
    state_text_filter = filters.TEXT & ~filters.COMMAND & ~form_filter & ~search_filter & ~settings_filter & ~main_menu_filter

    # A generic cancel handler for the /cancel command
    cancel_handler = CommandHandler("cancel", cancel)
    # A fallback handler that catches main menu button presses to cancel conversations
    fallback_handler = MessageHandler(main_menu_filter, cancel)

    # Conversation handler for the application form
    form_conv = ConversationHandler(
        entry_points=[MessageHandler(form_filter, start_form_conversation)],
        states={
            REGISTER_CONTACT: [MessageHandler(filters.CONTACT, handle_contact_registration)],
            REGISTER_FIO: [MessageHandler(state_text_filter, get_registration_fio)],
            REGISTER_EMAIL: [MessageHandler(state_text_filter, get_registration_email)],
            REGISTER_JOB_TITLE: [MessageHandler(state_text_filter, get_registration_job_title)],
            OWNER_LAST_NAME: [MessageHandler(state_text_filter, get_owner_last_name)],
            OWNER_FIRST_NAME: [MessageHandler(state_text_filter, get_owner_first_name)],
            REASON: [MessageHandler(state_text_filter, get_reason)],
            CARD_TYPE: [CallbackQueryHandler(get_card_type)],
            CARD_NUMBER: [MessageHandler(state_text_filter, get_card_number)],
            CATEGORY: [CallbackQueryHandler(get_category)],
            AMOUNT: [MessageHandler(state_text_filter, get_amount)],
            FREQUENCY: [CallbackQueryHandler(get_frequency)],
            ISSUE_LOCATION: [MessageHandler(state_text_filter, get_issue_location)], # Renamed state
            CONFIRMATION: [
                CallbackQueryHandler(submit, pattern="^submit$"),
                CallbackQueryHandler(restart_conversation, pattern="^restart$"),
            ],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    # Conversation handler for the search functionality
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(search_filter, search_command)],
        states={
            SEARCH_CHOOSE_FIELD: [CallbackQueryHandler(search_field_chosen)],
            AWAIT_SEARCH_QUERY: [MessageHandler(state_text_filter, perform_search)],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    # Add handlers to the application
    application.add_handler(CommandHandler("start", show_main_menu))
    application.add_handler(MessageHandler(main_menu_filter, show_main_menu))
    application.add_handler(MessageHandler(settings_filter, show_settings))
    application.add_handler(form_conv)
    application.add_handler(search_conv)

    # Add callback query handlers for settings and other inline buttons
    application.add_handler(CallbackQueryHandler(my_cards_command, pattern="^settings_my_cards$"))
    application.add_handler(CallbackQueryHandler(help_callback, pattern="^help_show$"))
    application.add_handler(CallbackQueryHandler(stats_callback, pattern="^stats_show$"))
    application.add_handler(CallbackQueryHandler(export_csv_callback, pattern="^export_csv$"))
    application.add_handler(CallbackQueryHandler(back_to_settings_callback, pattern="^back_to_settings$"))
    application.add_handler(CallbackQueryHandler(handle_pagination, pattern=r"^paginate_"))
    application.add_handler(CallbackQueryHandler(noop_callback, pattern=r"^noop$"))

    logger.info("Bot is starting...")
    application.run_polling()


if __name__ == "__main__":
    main()
