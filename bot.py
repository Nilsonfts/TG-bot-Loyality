# -*- coding: utf-8 -*-

"""
This is a Telegram bot for managing loyalty card applications.
V3: Refactored registration flow and main menu logic based on user feedback.
"""

import logging
import os
import re
import json
from datetime import datetime
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
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOSS_ID = os.getenv("BOSS_ID")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

# --- Bot UI Constants ---
MENU_TEXT_REGISTER = "✍️ Регистрация"
MENU_TEXT_SUBMIT = "✍️ Подать заявку"
MENU_TEXT_SEARCH = "🔍 Поиск"
MENU_TEXT_SETTINGS = "⚙️ Настройки"
MENU_TEXT_MAIN_MENU = "🏠 Главное меню"
CARDS_PER_PAGE = 7

# --- State Constants ---
(
    REGISTER_CONTACT, REGISTER_FIO, REGISTER_EMAIL, REGISTER_JOB_TITLE,
    OWNER_LAST_NAME, OWNER_FIRST_NAME, REASON, CARD_TYPE, CARD_NUMBER,
    CATEGORY, AMOUNT, FREQUENCY, ISSUE_LOCATION, CONFIRMATION,
    SEARCH_CHOOSE_FIELD, AWAIT_SEARCH_QUERY
) = range(16)

# --- LOGGING SETUP ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- GOOGLE SHEETS INTEGRATION ---
def get_gspread_client():
    try:
        if GOOGLE_CREDS_JSON:
            creds_info = json.loads(GOOGLE_CREDS_JSON)
            scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
            return gspread.authorize(creds)
        else:
            logger.error("GOOGLE_CREDS_JSON environment variable not set.")
            return None
    except Exception as e:
        logger.error(f"Error authenticating with Google Sheets: {e}")
        return None

def get_sheet_data(sheet_name="sheet1"):
    client = get_gspread_client()
    if not client or not GOOGLE_SHEET_KEY: return []
    try:
        sheet = client.open_by_key(GOOGLE_SHEET_KEY).worksheet(sheet_name)
        return sheet.get_all_records()
    except Exception as e:
        logger.error(f"Error fetching data from Google Sheet: {e}")
    return []

def is_user_registered(user_id: str) -> bool:
    all_records = get_sheet_data()
    for row in all_records:
        if str(row.get('ТГ Заполняющего')) == user_id:
            # A non-empty FIO field indicates a completed registration
            if row.get('ФИО Инициатора'):
                return True
    return False

def find_initiator_in_sheet(user_id: str):
    all_records = get_sheet_data()
    for row in reversed(all_records):
        if str(row.get('ТГ Заполняющего')) == user_id:
            return {
                "initiator_username": row.get('Тег Telegram'), "initiator_email": row.get('Адрес электронной почты'),
                "initiator_fio": row.get('ФИО Инициатора'), "initiator_job_title": row.get('Должность'),
                "initiator_phone": row.get('Телефон инициатора'),
            }
    return None

def get_cards_from_sheet(user_id: str = None) -> list:
    all_records = get_sheet_data()
    # Filter out empty rows or registration-only rows
    valid_records = [r for r in all_records if r.get('Фамилия Владельца')]
    if user_id:
        user_cards = [r for r in valid_records if str(r.get('ТГ Заполняющего')) == user_id]
    else:
        user_cards = valid_records
    return list(reversed(user_cards))

def write_to_sheet(data: dict, submission_time: str, tg_user_id: str) -> bool:
    client = get_gspread_client()
    if not client or not GOOGLE_SHEET_KEY: return False
    try:
        sheet = client.open_by_key(GOOGLE_SHEET_KEY).sheet1
        final_row = [
            submission_time, tg_user_id,
            data.get('initiator_username', '–'), data.get('initiator_email', ''),
            data.get('initiator_fio', ''), data.get('initiator_job_title', ''),
            data.get('initiator_phone', ''), data.get('owner_last_name', ''),
            data.get('owner_first_name', ''), data.get('reason', ''),
            data.get('card_type', ''), data.get('card_number', ''),
            data.get('category', ''), data.get('amount', ''),
            data.get('frequency', ''), data.get('issue_location', ''),
            'Заявка' if data.get('owner_last_name') else 'Регистрация'
        ]
        sheet.append_row(final_row, value_input_option='USER_ENTERED')
        logger.info(f"Successfully wrote a row for user {tg_user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to write data to sheet for user {tg_user_id}: {e}")
        return False

# --- UTILS ---
def add_message_to_delete(context: ContextTypes.DEFAULT_TYPE, message_id: int):
    if 'messages_to_delete' not in context.chat_data: context.chat_data['messages_to_delete'] = []
    context.chat_data['messages_to_delete'].append(message_id)

async def delete_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    for msg_id in context.chat_data.pop('messages_to_delete', []):
        try: await context.bot.delete_message(chat_id, msg_id)
        except Exception: pass

async def get_chat_id(update: Update) -> int | None:
    return update.effective_chat.id if update.effective_chat else None

# --- NAVIGATION & MENUS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    if is_user_registered(user_id):
        keyboard = [[MENU_TEXT_SUBMIT], [MENU_TEXT_SEARCH, MENU_TEXT_SETTINGS], [MENU_TEXT_MAIN_MENU]]
        await update.message.reply_text("Вы в главном меню:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    else:
        keyboard = [[MENU_TEXT_REGISTER]]
        await update.message.reply_text("Здравствуйте! Для начала работы, пройдите регистрацию.", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))

async def main_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_command(update, context)

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    cards_button_text = "🗂️ Все заявки" if user_id == BOSS_ID else "🗂️ Мои Заявки"
    keyboard = [
        [InlineKeyboardButton(cards_button_text, callback_data="settings_my_cards")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats_show")],
        [InlineKeyboardButton("📄 Экспорт в CSV", callback_data="export_csv")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_show")],
    ]
    await update.message.reply_text("Меню настроек:", reply_markup=InlineKeyboardMarkup(keyboard))

async def back_to_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    cards_button_text = "🗂️ Все заявки" if user_id == BOSS_ID else "🗂️ Мои Заявки"
    keyboard = [
        [InlineKeyboardButton(cards_button_text, callback_data="settings_my_cards")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats_show")],
        [InlineKeyboardButton("📄 Экспорт в CSV", callback_data="export_csv")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_show")],
    ]
    await query.edit_message_text("Меню настроек:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- REGISTRATION CONVERSATION ---
async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    msg = await update.message.reply_text("Начинаем регистрацию. Пожалуйста, поделитесь своим контактом.", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📱 Поделиться контактом", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True))
    return REGISTER_CONTACT

async def handle_contact_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact, user = update.message.contact, update.effective_user
    if contact.user_id != user.id:
        await update.message.reply_text("Пожалуйста, поделитесь своим собственным контактом.", reply_markup=ReplyKeyboardRemove())
        return await cancel(update, context)
    context.user_data['initiator_phone'] = contact.phone_number.replace('+', '')
    context.user_data['initiator_username'] = f"@{user.username}" if user.username else "–"
    await update.message.reply_text("✅ Контакт получен!\n\n👤 Введите ваше <b>полное ФИО</b>.", reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
    return REGISTER_FIO

async def get_registration_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['initiator_fio'] = update.message.text
    await update.message.reply_text("✅ ФИО принято.\n\n📧 Введите вашу <b>рабочую почту</b>.", parse_mode=ParseMode.HTML)
    return REGISTER_EMAIL

async def get_registration_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text("❌ Формат почты неверный. Попробуйте еще раз.")
        return REGISTER_EMAIL
    context.user_data['initiator_email'] = email
    await update.message.reply_text("✅ Почта принята.\n\n🏢 Введите вашу <b>должность</b>.", parse_mode=ParseMode.HTML)
    return REGISTER_JOB_TITLE

async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['initiator_job_title'] = update.message.text
    success = write_to_sheet(context.user_data, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), str(update.effective_user.id))
    if success:
        await update.message.reply_text("🎉 <b>Регистрация успешно завершена!</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ Ошибка при сохранении регистрации.")
    context.user_data.clear()
    await main_menu_command(update, context)
    return ConversationHandler.END

# --- All other handlers (form, search, settings features) are included below ---
# ... (The full code for help_callback, stats_callback, export_csv_callback, display_paginated_list, handle_pagination, noop_callback, my_cards_command, search_command, search_field_chosen, perform_search, start_form_conversation, get_owner_last_name, get_owner_first_name, get_reason, get_card_type, get_card_number, get_category, get_amount, get_frequency, get_issue_location, format_summary, submit, restart_conversation, cancel)
async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    is_boss = (user_id == BOSS_ID)
    await query.edit_message_text("📊 Собираю статистику...")
    cards_data = get_cards_from_sheet(user_id=None if is_boss else user_id)
    if not cards_data:
        await query.edit_message_text("Нет данных для статистики.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]))
        return
    total_cards, barter_count = len(cards_data), sum(1 for c in cards_data if c.get('Какую карту регистрируем?') == 'Бартер')
    category_counter = Counter(c.get('Статья пополнения карт') for c in cards_data if c.get('Статья пополнения карт'))
    most_common_category = category_counter.most_common(1)[0][0] if category_counter else "–"
    text = (f"<b>📊 Статистика</b>\n\n"
            f"🗂️ {'Всего заявок' if is_boss else 'Подано вами'}: <b>{total_cards}</b>\n"
            f"    - 'Бартер': <code>{barter_count}</code>\n"
            f"    - 'Скидка': <code>{total_cards - barter_count}</code>\n\n"
            f"📈 Частая статья: <b>{most_common_category}</b>")
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]), parse_mode=ParseMode.HTML)

async def export_csv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id, is_boss = str(query.from_user.id), (str(query.from_user.id) == BOSS_ID)
    await query.edit_message_text("📄 Формирую CSV файл...")
    cards_to_export = get_cards_from_sheet(user_id=None if is_boss else user_id)
    if not cards_to_export:
        await query.edit_message_text("Нет данных для экспорта.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]))
        return
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=cards_to_export[0].keys())
    writer.writeheader()
    writer.writerows(cards_to_export)
    output.seek(0)
    await context.bot.send_document(chat_id=query.message.chat_id, document=InputFile(output.getvalue().encode('utf-8-sig'), filename=f"export_{datetime.now().strftime('%Y-%m-%d')}.csv"))
    await query.message.delete()

async def display_paginated_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, data_key: str, list_title: str):
    query, message_to_edit = update.callback_query, update.callback_query.message
    all_items = context.user_data.get(data_key, [])
    if not all_items:
        await message_to_edit.edit_text("🤷 Ничего не найдено.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]))
        return
    start_index, end_index, total_pages = page * CARDS_PER_PAGE, (page + 1) * CARDS_PER_PAGE, (len(all_items) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    text = f"<b>{list_title} (Стр. {page + 1}/{total_pages}):</b>\n\n"
    for card in all_items[start_index:end_index]:
        owner_name = f"{card.get('Имя владельца карты','')} {card.get('Фамилия Владельца','-')}".strip()
        amount_text = ""
        if card.get('Сумма бартера или % скидки'):
            amount_text = f"💰 {'Скидка' if card.get('Какую карту регистрируем?') == 'Скидка' else 'Бартер'}: {card.get('Сумма бартера или % скидки')}{'%' if card.get('Какую карту регистрируем?') == 'Скидка' else ' ₽'}\n"
        text += (f"👤 <b>Владелец:</b> {owner_name}\n📞 Номер: {card.get('Номер карты', '-')}\n{amount_text}"
                 f"<b>Статус:</b> <code>{card.get('Статус Согласования', '–')}</code>\n📅 {card.get('Отметка времени', '-')}\n")
        if str(update.effective_user.id) == BOSS_ID:
            text += f"🤵‍♂️ <b>Инициатор:</b> {card.get('ФИО Инициатора', '-')} ({card.get('Тег Telegram', '-')})\n"
        text += "--------------------\n"
    row = []
    if page > 0: row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"paginate_{data_key}_{page - 1}"))
    row.append(InlineKeyboardButton(f" {page + 1}/{total_pages} ", callback_data="noop"))
    if end_index < len(all_items): row.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"paginate_{data_key}_{page + 1}"))
    await message_to_edit.edit_text(text, reply_markup=InlineKeyboardMarkup([row, [InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]), parse_mode=ParseMode.HTML)

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, data_key, page_str = query.data.split('_')
    list_title = "Все заявки" if data_key == "my_cards" and str(update.effective_user.id) == BOSS_ID else "Ваши поданные заявки"
    await display_paginated_list(update, context, page=int(page_str), data_key=data_key, list_title=list_title)

async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.callback_query.answer()

async def my_cards_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id, is_boss = str(query.from_user.id), (str(query.from_user.id) == BOSS_ID)
    await query.edit_message_text("👑 Загружаю ВСЕ заявки..." if is_boss else "🔍 Загружаю ваши заявки...")
    all_cards = get_cards_from_sheet(user_id=None if is_boss else user_id)
    if not all_cards:
        await query.edit_message_text("🤷 Заявок не найдено.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]))
        return
    context.user_data['my_cards'] = all_cards
    await display_paginated_list(update, context, page=0, data_key='my_cards', list_title="Все заявки" if is_boss else "Ваши заявки")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Выберите критерий поиска:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("По ФИО владельца", callback_data="search_by_name")], [InlineKeyboardButton("По номеру карты", callback_data="search_by_phone")]]))
    return SEARCH_CHOOSE_FIELD

async def search_field_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['search_field'] = query.data
    await query.edit_message_text("Введите поисковый запрос:")
    return AWAIT_SEARCH_QUERY

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id, is_boss, search_query = str(update.effective_user.id), (str(update.effective_user.id) == BOSS_ID), update.message.text.lower().strip()
    loading_msg = await update.message.reply_text("🔍 Выполняю поиск...")
    all_cards = get_cards_from_sheet(user_id=None if is_boss else user_id)
    search_field = context.user_data.get('search_field')
    if search_field == 'search_by_name':
        results = [c for c in all_cards if search_query in c.get('Имя владельца карты', '').lower() or search_query in c.get('Фамилия Владельца', '').lower()]
    else: # search_by_phone
        results = [c for c in all_cards if search_query in str(c.get('Номер карты', ''))]
    context.user_data['search_results'] = results
    await loading_msg.delete()
    class MockUpdate:
        def __init__(self, msg, user): self.callback_query, self.effective_user = type('MockCQ', (), {'message': msg})(), user
    await display_paginated_list(MockUpdate(update.message, update.effective_user), context, page=0, data_key='search_results', list_title="Результаты поиска")
    return ConversationHandler.END

async def start_form_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    initiator_data = find_initiator_in_sheet(str(update.effective_user.id))
    if not initiator_data:
        await update.message.reply_text("Ошибка: не удалось найти ваши регистрационные данные.")
        return await cancel(update, context)
    context.user_data.update(initiator_data)
    await update.message.reply_text(f"Начинаем подачу заявки.\nВведите <b>Фамилию</b> владельца карты.", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
    return OWNER_LAST_NAME

async def get_owner_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['owner_last_name'] = update.message.text
    await update.message.reply_text("<b>Имя</b> владельца карты.", parse_mode=ParseMode.HTML)
    return OWNER_FIRST_NAME

async def get_owner_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['owner_first_name'] = update.message.text
    await update.message.reply_text("Причина выдачи?")
    return REASON

async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['reason'] = update.message.text
    await update.message.reply_text("Тип карты?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Бартер", callback_data="Бартер"), InlineKeyboardButton("Скидка", callback_data="Скидка")]]))
    return CARD_TYPE

async def get_card_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['card_type'] = query.data
    await query.edit_message_text(f"Выбрано: {query.data}.\n\nНомер карты (телефон через 8)?")
    return CARD_NUMBER

async def get_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    number = update.message.text
    if not (number.startswith('8') and number.isdigit() and len(number) == 11):
        await update.message.reply_text("Неверный формат. Нужно 11 цифр, начиная с 8.")
        return CARD_NUMBER
    context.user_data['card_number'] = number
    keyboard = [[InlineKeyboardButton("АРТ", callback_data="АРТ"), InlineKeyboardButton("МАРКЕТ", callback_data="МАРКЕТ")], [InlineKeyboardButton("Операционный блок", callback_data="Операционный блок")], [InlineKeyboardButton("СКИДКА", callback_data="СКИДКА"), InlineKeyboardButton("Сертификат", callback_data="Сертификат")], [InlineKeyboardButton("Учредители", callback_data="Учредители")]]
    await update.message.reply_text("Статья пополнения?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CATEGORY

async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['category'] = query.data
    prompt = "Сумма бартера?" if context.user_data['card_type'] == "Бартер" else "Процент скидки?"
    await query.edit_message_text(f"Статья: {query.data}.\n\n{prompt}")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.text.isdigit():
        await update.message.reply_text("Нужно ввести только число.")
        return AMOUNT
    context.user_data['amount'] = update.message.text
    keyboard = [[InlineKeyboardButton("Разовая", callback_data="Разовая")], [InlineKeyboardButton("Дополнить к балансу", callback_data="Дополнить к балансу")], [InlineKeyboardButton("Замена номера карты", callback_data="Замена номера карты")]]
    await update.message.reply_text("Периодичность?", reply_markup=InlineKeyboardMarkup(keyboard))
    return FREQUENCY

async def get_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['frequency'] = query.data
    await query.edit_message_text(f"Выбрано: {query.data}.\n\n<b>Город_БАР выдачи?</b>", parse_mode=ParseMode.HTML)
    return ISSUE_LOCATION

def format_summary(data: dict) -> str:
    owner = f"{data.get('owner_first_name', '')} {data.get('owner_last_name', '')}".strip()
    amt_lbl, amt_unit = ('Скидка', '%') if data.get('card_type') == 'Скидка' else ('Сумма', ' ₽')
    return (f"<b>Проверьте итоговую заявку:</b>\n\n"
            f"--- <b>Инициатор</b> ---\n"
            f"👤 ФИО: {data.get('initiator_fio', '-')}\n"
            f"--- <b>Карта</b> ---\n"
            f"💳 Владелец: {owner}\n"
            f"📞 Номер: {data.get('card_number', '-')}\n"
            f"✨ Тип: {data.get('card_type', '-')}\n"
            f"💰 {amt_lbl}: {data.get('amount', '0')}{amt_unit}\n"
            f"📈 Статья: {data.get('category', '-')}\n"
            f"🔄 Периодичность: {data.get('frequency', '-')}\n"
            f"📍 Город/Бар: {data.get('issue_location', '-')}\n\n"
            "<i>Все верно?</i>")

async def get_issue_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['issue_location'] = update.message.text
    summary = format_summary(context.user_data)
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Да, все верно", callback_data="submit"), InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")]]), parse_mode=ParseMode.HTML)
    return CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer(text="Отправляю заявку...", show_alert=False)
    success = write_to_sheet(context.user_data, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), str(query.from_user.id))
    status_text = "\n\n<b>Статус:</b> ✅ Заявка отправлена." if success else "\n\n<b>Статус:</b> ❌ Ошибка сохранения."
    await query.edit_message_text(text=query.message.text_html + status_text, parse_mode=ParseMode.HTML)
    context.user_data.clear()
    await main_menu_command(update.callback_query, context)
    return ConversationHandler.END

async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    return await start_form_conversation(query, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
    await main_menu_command(update, context)
    return ConversationHandler.END

def main() -> None:
    if not all([TELEGRAM_BOT_TOKEN, BOSS_ID, GOOGLE_SHEET_KEY, GOOGLE_CREDS_JSON]):
        logger.critical("CRITICAL ERROR: One or more environment variables are not set.")
        return
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Filters
    filters_map = {
        'reg': filters.Regex(f"^{MENU_TEXT_REGISTER}$"),
        'submit': filters.Regex(f"^{MENU_TEXT_SUBMIT}$"),
        'search': filters.Regex(f"^{MENU_TEXT_SEARCH}$"),
        'settings': filters.Regex(f"^{MENU_TEXT_SETTINGS}$"),
        'main': filters.Regex(f"^{MENU_TEXT_MAIN_MENU}$")
    }
    txt_filter = filters.TEXT & ~filters.COMMAND & ~filters.Regex_val_from_dict(filters_map)
    fallback_handler = MessageHandler(filters_map['main'], main_menu_command)
    cancel_handler = CommandHandler("cancel", cancel)
    
    # Conversations
    reg_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['reg'], start_registration)],
        states={
            REGISTER_CONTACT: [MessageHandler(filters.CONTACT, handle_contact_registration)],
            REGISTER_FIO: [MessageHandler(txt_filter, get_registration_fio)],
            REGISTER_EMAIL: [MessageHandler(txt_filter, get_registration_email)],
            REGISTER_JOB_TITLE: [MessageHandler(txt_filter, finish_registration)],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )
    form_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['submit'], start_form_conversation)],
        states={
            OWNER_LAST_NAME: [MessageHandler(txt_filter, get_owner_last_name)],
            OWNER_FIRST_NAME: [MessageHandler(txt_filter, get_owner_first_name)],
            REASON: [MessageHandler(txt_filter, get_reason)],
            CARD_TYPE: [CallbackQueryHandler(get_card_type)],
            CARD_NUMBER: [MessageHandler(txt_filter, get_card_number)],
            CATEGORY: [CallbackQueryHandler(get_category)],
            AMOUNT: [MessageHandler(txt_filter, get_amount)],
            FREQUENCY: [CallbackQueryHandler(get_frequency)],
            ISSUE_LOCATION: [MessageHandler(txt_filter, get_issue_location)],
            CONFIRMATION: [CallbackQueryHandler(submit, "^submit$"), CallbackQueryHandler(restart_conversation, "^restart$")],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['search'], search_command)],
        states={
            SEARCH_CHOOSE_FIELD: [CallbackQueryHandler(search_field_chosen)],
            AWAIT_SEARCH_QUERY: [MessageHandler(txt_filter, perform_search)]
        },
        fallbacks=[fallback_handler, cancel_handler],
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters_map['main'], main_menu_command))
    application.add_handler(MessageHandler(filters_map['settings'], show_settings))
    application.add_handler(reg_conv)
    application.add_handler(form_conv)
    application.add_handler(search_conv)
    application.add_handler(CallbackQueryHandler(my_cards_command, "^settings_my_cards$"))
    application.add_handler(CallbackQueryHandler(help_callback, "^help_show$"))
    application.add_handler(CallbackQueryHandler(stats_callback, "^stats_show$"))
    application.add_handler(CallbackQueryHandler(export_csv_callback, "^export_csv$"))
    application.add_handler(CallbackQueryHandler(back_to_settings_callback, "^back_to_settings$"))
    application.add_handler(CallbackQueryHandler(handle_pagination, r"^paginate_"))
    application.add_handler(CallbackQueryHandler(noop_callback, r"^noop$"))
    
    logger.info("Bot is starting (V3)...")
    application.run_polling()

if __name__ == "__main__":
    main()
