# -*- coding: utf-8 -*-

import logging
import os
import re
import json
from datetime import datetime
import asyncio
import io
import csv
from collections import Counter

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputFile
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

# --- НАСТРОЙКИ И ПЕРЕМЕННЫЕ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOSS_ID = os.getenv("BOSS_ID") # ID администратора
CARDS_PER_PAGE = 7

# --- Настройка логирования ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Состояния для диалога ---
(
    # Регистрация
    REGISTER_CONTACT, REGISTER_FIO, REGISTER_EMAIL, REGISTER_JOB_TITLE,
    # Анкета
    OWNER_LAST_NAME, OWNER_FIRST_NAME,
    REASON, CARD_TYPE, CARD_NUMBER, CATEGORY, AMOUNT,
    FREQUENCY, COMMENT, CONFIRMATION,
    # Поиск
    SEARCH_CHOOSE_FIELD, AWAIT_SEARCH_QUERY,
    # Черновик
    AWAIT_DRAFT_CHOICE
) = range(17)


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С GOOGLE SHEETS ---
def get_gspread_client():
    try:
        creds_json_str = os.getenv("GOOGLE_CREDS_JSON")
        if creds_json_str:
            creds_info = json.loads(creds_json_str)
            scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
            return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Ошибка аутентификации в Google Sheets: {e}")
    return None

def get_cards_from_sheet(user_id: str = None) -> list:
    """Получает карты из таблицы. Если user_id указан, фильтрует по нему."""
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_KEY")).sheet1
        all_records = sheet.get_all_records() 
        
        if user_id:
            user_cards = [record for record in all_records if str(record.get('ТГ Заполняющего')) == user_id]
        else:
            user_cards = all_records

        return list(reversed(user_cards))
    except Exception as e:
        logger.error(f"Ошибка при поиске карт пользователя: {e}")
    return []

def write_to_sheet(data: dict, submission_time: str, tg_user_id: str):
    client = get_gspread_client()
    if not client: return False
    try:
        sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_KEY")).sheet1
        header = sheet.row_values(1)
        row_map = {
            'Отметка времени': submission_time,
            'ТГ Заполняющего': tg_user_id,
            'Тег Telegram': data.get('initiator_username', '–'),
            'Адрес электронной почты': data.get('initiator_email', ''),
            'ФИО Инициатора': data.get('initiator_fio', ''),
            'Должность': data.get('initiator_job_title', ''),
            'Телефон инициатора': data.get('initiator_phone', ''),
            'Фамилия Владельца': data.get('owner_last_name', ''),
            'Имя владельца карты': data.get('owner_first_name', ''),
            'Причина выдачи бартера/скидки': data.get('reason', ''),
            'Какую карту регистрируем?': data.get('card_type', ''),
            'Номер карты': data.get('card_number', ''),
            'Статья пополнения карт': data.get('category', ''),
            'Сумма бартера или % скидки': data.get('amount', ''),
            'Периодичность наполнения бартера': data.get('frequency', ''),
            'Комментарий (привязка к какому бару)': data.get('comment', '')
        }
        final_row = [row_map.get(h, '') for h in header]
        sheet.append_row(final_row, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        logger.error(f"Не удалось записать данные в таблицу: {e}")
    return False

# --- ГЛАВНОЕ МЕНЮ И СИСТЕМА НАВИГАЦИИ ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    keyboard = [["✍️ Подать заявку"], ["🗂️ Мои Карты", "🔍 Поиск"], ["⚙️ Настройки"]]
    if user_id == BOSS_ID:
        keyboard[1][0] = "🗂️ Все заявки"
        
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы в главном меню. Выберите действие:", reply_markup=reply_markup)

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats_show")],
        [InlineKeyboardButton("📄 Экспорт в CSV", callback_data="export_csv")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_show")]
    ]
    await update.message.reply_text("Меню настроек:", reply_markup=InlineKeyboardMarkup(keyboard))

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    help_text = ("<b>Справка по боту</b>\n\n"
                 "▫️ <b>Подать заявку</b> - запуск анкеты.\n"
                 "▫️ <b>Мои Карты / Все карты</b> - просмотр заявок.\n"
                 "▫️ <b>Поиск</b> - поиск по заявкам.\n"
                 "▫️ <b>Настройки</b> - доступ к доп. функциям.\n\n"
                 "Отмена анкеты сохраняет черновик.")
    keyboard = [[InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]
    await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def back_to_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats_show")],
        [InlineKeyboardButton("📄 Экспорт в CSV", callback_data="export_csv")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_show")]
    ]
    await query.edit_message_text("Меню настроек:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- НОВЫЕ ФУНКЦИИ: СТАТИСТИКА И ЭКСПОРТ ---
async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    is_boss = (user_id == BOSS_ID)
    await query.edit_message_text("📊 Собираю статистику, пожалуйста, подождите...")

    all_cards = get_cards_from_sheet() if is_boss else get_cards_from_sheet(user_id)

    if not all_cards:
        await query.edit_message_text("Нет данных для статистики.")
        return

    total_cards = len(all_cards)
    barter_count = sum(1 for card in all_cards if card.get('Какую карту регистрируем?') == 'Бартер')
    discount_count = total_cards - barter_count
    
    try:
        category_counter = Counter(card.get('Статья пополнения карт') for card in all_cards if card.get('Статья пополнения карт'))
        most_common_category = category_counter.most_common(1)[0][0] if category_counter else "–"
    except Exception:
        most_common_category = "Не удалось посчитать"

    text = f"<b>Статистика</b>\n\n"
    if is_boss:
        text += f"🗂️ Всего заявок в системе: <b>{total_cards}</b>\n"
    else:
        text += f"🗂️ Подано вами заявок: <b>{total_cards}</b>\n"
    
    text += f"    - Карт 'Бартер': <code>{barter_count}</code>\n"
    text += f"    - Карт 'Скидка': <code>{discount_count}</code>\n\n"
    text += f"📈 Самая частая статья: <b>{most_common_category}</b>"

    keyboard = [[InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def export_csv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    is_boss = (user_id == BOSS_ID)
    
    await query.edit_message_text("📄 Формирую CSV файл...")
    
    cards_to_export = get_cards_from_sheet() if is_boss else get_cards_from_sheet(user_id)

    if not cards_to_export:
        await query.edit_message_text("Нет данных для экспорта.")
        return
        
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=cards_to_export[0].keys())
    writer.writeheader()
    writer.writerows(cards_to_export)
        
    output.seek(0)
    
    file_to_send = InputFile(output, filename=f"export_{datetime.now().strftime('%Y-%m-%d')}.csv")
    
    await context.bot.send_document(chat_id=query.message.chat_id, document=file_to_send)
    await query.message.delete()


# --- ПАГИНАЦИЯ, ПОИСК И ОСТАЛЬНЫЕ КОМАНДЫ ---
async def display_paginated_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, data_key: str, list_title: str):
    message_to_edit = update.callback_query.message if update.callback_query else update.message
    all_items = context.user_data.get(data_key, [])
    if not all_items: await message_to_edit.edit_text("🤷 Ничего не найдено."); return
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
            if card.get('Какую карту регистрируем?') == 'Скидка': amount_text = f"💰 Скидка: {amount}%\n"
            else: amount_text = f"💰 Бартер: {amount} ₽\n"
        text += (f"👤 <b>Владелец:</b> {owner_name}\n📞 Номер: {card.get('Номер карты', '-')}\n{amount_text}"
                 f"<b>Согласование:</b> <code>{card.get('Статус Согласования', '–')}</code>\n"
                 f"<b>Активность:</b> <code>{card.get('Статус активности', '–')}</code>\n"
                 f"📅 Дата: {card.get('Отметка времени', '-')}\n")
        if str(update.effective_user.id) == BOSS_ID:
            text += f"🤵‍♂️ <b>Инициатор:</b> {card.get('ФИО Инициатора', '-')} ({card.get('Тег Telegram', '-')})\n"
        text += "--------------------\n"
    keyboard = []
    row = []
    if page > 0: row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"paginate_{data_key}_{page - 1}"))
    row.append(InlineKeyboardButton(f" стр. {page + 1}/{total_pages} ", callback_data="noop"))
    if end_index < len(all_items): row.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"paginate_{data_key}_{page + 1}"))
    keyboard.append(row)
    await message_to_edit.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, data_key, page_str = query.data.split('_')
    page = int(page_str)
    list_title = "Все заявки" if data_key == "mycards" and str(update.effective_user.id) == BOSS_ID else "Ваши поданные заявки"
    await display_paginated_list(update, context, page=page, data_key=data_key, list_title=list_title)

async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()

async def my_cards_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    is_boss = (user_id == BOSS_ID)
    loading_message = await update.message.reply_text("👑 Админ-режим: Загружаю ВСЕ заявки..." if is_boss else "🔍 Загружаю ваши заявки...")
    all_cards = get_cards_from_sheet() if is_boss else get_cards_from_sheet(user_id)
    if not all_cards: await loading_message.edit_text("🤷 Заявок не найдено."); return
    context.user_data['mycards'] = all_cards
    await display_paginated_list(update, context, page=0, data_key='mycards', list_title="Все заявки" if is_boss else "Ваши поданные заявки")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[InlineKeyboardButton("По ФИО владельца", callback_data="search_by_name")],[InlineKeyboardButton("По номеру карты", callback_data="search_by_phone")]]
    await update.message.reply_text("Выберите критерий поиска:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SEARCH_CHOOSE_FIELD

async def search_field_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['search_field'] = query.data
    await query.edit_message_text("Теперь введите ваш поисковый запрос:")
    return AWAIT_SEARCH_QUERY

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    is_boss = (user_id == BOSS_ID)
    search_query = update.message.text.lower()
    search_field = context.user_data.get('search_field')
    loading_message = await update.message.reply_text("🔍 Выполняю поиск...")
    all_cards = get_cards_from_sheet() if is_boss else get_cards_from_sheet(user_id)
    if not all_cards: await loading_message.edit_text("🤷 Заявок для поиска нет."); return ConversationHandler.END
    if search_field == 'search_by_name':
        search_results = [card for card in all_cards if search_query in card.get('Имя владельца карты', '').lower() or search_query in card.get('Фамилия Владельца', '').lower()]
    elif search_field == 'search_by_phone':
        search_results = [card for card in all_cards if search_query in card.get('Номер карты', '')]
    else: search_results = []
    context.user_data['search'] = search_results
    await display_paginated_list(update, context, page=0, data_key='search', list_title="Результаты поиска")
    return ConversationHandler.END


# --- ДИАЛОГ ПОДАЧИ ЗАЯВКИ ---
async def start_form_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data.get('is_draft'):
        keyboard = [[InlineKeyboardButton("Продолжить", callback_data="draft_continue"), InlineKeyboardButton("Начать заново", callback_data="draft_restart")]]
        await update.message.reply_text("Найден незаконченный черновик. Хотите продолжить?", reply_markup=InlineKeyboardMarkup(keyboard))
        return AWAIT_DRAFT_CHOICE
    
    await update.message.reply_text("Начинаем подачу новой заявки.\n\nВведите <b>Фамилию</b> владельца карты.", parse_mode=ParseMode.HTML)
    return OWNER_LAST_NAME

async def handle_draft_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == 'draft_continue':
        # Просто ничего не делаем, диалог продолжится с того же места
        await query.edit_message_text("Продолжаем с черновика...")
        # Нужно вернуть последнее состояние, но это сложно, проще попросить ввести последнее поле заново
        await query.message.reply_text("Пожалуйста, введите последнее поле заново, чтобы продолжить.")
        return context.user_data.get('last_form_state', OWNER_LAST_NAME)
    else: # draft_restart
        # Очищаем черновик
        form_keys = ['owner_last_name', 'owner_first_name', 'reason', 'card_type', 'card_number', 'category', 'amount', 'frequency', 'comment', 'is_draft', 'last_form_state']
        for key in form_keys:
            if key in context.user_data:
                del context.user_data[key]
        await query.edit_message_text("Черновик удален. Начинаем заново.")
        return await start_form_conversation(update.callback_query, context)

async def get_owner_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['owner_last_name'] = update.message.text
    context.user_data['last_form_state'] = OWNER_LAST_NAME
    await update.message.reply_text("<b>Имя</b> владельца карты.", parse_mode=ParseMode.HTML)
    return OWNER_FIRST_NAME

# ... (и так далее для всех шагов анкеты, добавляя last_form_state)

async def get_owner_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['owner_first_name'] = update.message.text
    context.user_data['last_form_state'] = OWNER_FIRST_NAME
    await update.message.reply_text("Причина выдачи?")
    return REASON

async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['reason'] = update.message.text
    context.user_data['last_form_state'] = REASON
    keyboard = [[InlineKeyboardButton("Бартер", callback_data="Бартер"), InlineKeyboardButton("Скидка", callback_data="Скидка")]]
    await update.message.reply_text("Тип карты?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CARD_TYPE

async def get_card_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['card_type'] = query.data
    context.user_data['last_form_state'] = CARD_TYPE
    await query.edit_message_text(f"Выбрано: {query.data}.\n\nНомер карты (телефон через 8)?")
    return CARD_NUMBER

async def get_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    number = update.message.text
    if not (number.startswith('8') and number[1:].isdigit() and len(number) == 11):
        await update.message.reply_text("Неверный формат. Нужно 11 цифр, начиная с 8.")
        return CARD_NUMBER
    context.user_data['card_number'] = number
    context.user_data['last_form_state'] = CARD_NUMBER
    keyboard = [[InlineKeyboardButton("АРТ", callback_data="АРТ"), InlineKeyboardButton("МАРКЕТ", callback_data="МАРКЕТ")], [InlineKeyboardButton("Операционный блок", callback_data="Операционный блок")], [InlineKeyboardButton("СКИДКА", callback_data="СКИДКА"), InlineKeyboardButton("Сертификат", callback_data="Сертификат")], [InlineKeyboardButton("Учредители", callback_data="Учредители")]]
    await update.message.reply_text("Статья пополнения?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CATEGORY

async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['category'] = query.data
    context.user_data['last_form_state'] = CATEGORY
    prompt = "Сумма бартера?" if context.user_data.get('card_type') == "Бартер" else "Процент скидки?"
    await query.edit_message_text(f"Статья: {query.data}.\n\n{prompt}")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if not text.isdigit():
        await update.message.reply_text("Нужно только число.")
        return AMOUNT
    context.user_data['amount'] = text
    context.user_data['last_form_state'] = AMOUNT
    keyboard = [[InlineKeyboardButton("Разовая", callback_data="Разовая")], [InlineKeyboardButton("Дополнить к балансу", callback_data="Дополнить к балансу")], [InlineKeyboardButton("Замена номера карты", callback_data="Замена номера карты")]]
    await update.message.reply_text("Периодичность?", reply_markup=InlineKeyboardMarkup(keyboard))
    return FREQUENCY

async def get_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['frequency'] = query.data
    context.user_data['last_form_state'] = FREQUENCY
    await query.edit_message_text(f"Выбрано: {query.data}.\n\nКомментарий?")
    return COMMENT

async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['comment'] = update.message.text
    summary = format_summary(context.user_data)
    keyboard = [[InlineKeyboardButton("✅ Да, все верно", callback_data="submit"), InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRMATION

def format_summary(data: dict) -> str:
    owner_full_name = f"{data.get('owner_first_name', '')} {data.get('owner_last_name', '')}".strip()
    return ("<b>Пожалуйста, проверьте итоговую заявку:</b>\n\n"
            "--- <b>Инициатор</b> ---\n"
            f"👤 <b>ФИО:</b> {data.get('initiator_fio', '-')}\n"
            f"📧 <b>Почта:</b> {data.get('initiator_email', '-')}\n"
            f"🏢 <b>Должность:</b> {data.get('initiator_job_title', '-')}\n\n"
            "--- <b>Карта лояльности</b> ---\n"
            f"💳 <b>Владелец:</b> {owner_full_name}\n"
            f"📞 <b>Номер:</b> {data.get('card_number', '-')}\n"
            f"   <i>(он же является номером телефона)</i>\n"
            f"✨ <b>Тип:</b> {data.get('card_type', '-')}\n"
            f"💰 <b>{ 'Скидка' if data.get('card_type') == 'Скидка' else 'Сумма' }:</b> {data.get('amount', '0')}{'%' if data.get('card_type') == 'Скидка' else ' ₽'}\n"
            f"📈 <b>Статья:</b> {data.get('category', '-')}\n"
            f"🔄 <b>Периодичность:</b> {data.get('frequency', '-')}\n"
            f"💬 <b>Комментарий:</b> {data.get('comment', '-')}\n\n"
            "<i>Все верно?</i>")

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    success = write_to_sheet(context.user_data, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id)
    original_text = query.message.text_html
    status_text = "\n\n<b>Статус:</b> ✅ Заявка успешно записана." if success else "\n\n<b>Статус:</b> ❌ Ошибка при записи в таблицу."
    await query.edit_message_text(text=original_text + status_text, parse_mode=ParseMode.HTML, reply_markup=None)
    await show_main_menu(update.callback_query, context)
    return ConversationHandler.END

async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Начинаем заявку заново...")
    return await start_form_conversation(update.callback_query, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    form_keys = ['owner_last_name', 'owner_first_name', 'reason', 'card_type', 'card_number', 'category', 'amount', 'frequency', 'comment']
    is_draft = any(key in context.user_data for key in form_keys)
    if is_draft:
        context.user_data['is_draft'] = True
        await update.message.reply_text("Действие отменено. Ваш прогресс сохранен как черновик.")
    else:
        await update.message.reply_text("Действие отменено.")
    await show_main_menu(update, context)
    return ConversationHandler.END


# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА БОТА ---
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Фильтры для кнопок меню
    form_filter = filters.Regex("^(✍️ )?Подать заявку$")
    cards_filter = filters.Regex("^(🗂️ )?(Мои Карты|Все заявки)$")
    search_filter = filters.Regex("^(🔍 )?Поиск$")
    settings_filter = filters.Regex("^(⚙️ )?Настройки$")
    
    cancel_handler = CommandHandler("cancel", cancel)
    
    # Диалоги
    form_conv = ConversationHandler(
        entry_points=[MessageHandler(form_filter, start_form_conversation)],
        states={
            AWAIT_DRAFT_CHOICE: [CallbackQueryHandler(handle_draft_choice)],
            OWNER_LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_owner_last_name)], 
            OWNER_FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_owner_first_name)],
            REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reason)], 
            CARD_TYPE: [CallbackQueryHandler(get_card_type)],
            CARD_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_card_number)], 
            CATEGORY: [CallbackQueryHandler(get_category)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)], 
            FREQUENCY: [CallbackQueryHandler(get_frequency)],
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_comment)],
            CONFIRMATION: [CallbackQueryHandler(submit, pattern="^submit$"), CallbackQueryHandler(restart_conversation, pattern="^restart$")],
        },
        fallbacks=[cancel_handler],
        block=False
    )
    
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(search_filter, search_command)],
        states={
            SEARCH_CHOOSE_FIELD: [CallbackQueryHandler(search_field_chosen)],
            AWAIT_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, perform_search)],
        },
        fallbacks=[cancel_handler],
        block=False
    )

    # Регистрируем хендлеры
    application.add_handler(CommandHandler("start", show_main_menu))
    
    application.add_handler(form_conv)
    application.add_handler(search_conv)
    
    application.add_handler(MessageHandler(cards_filter, my_cards_command))
    application.add_handler(MessageHandler(settings_filter, show_settings))
    
    # Хендлеры для инлайн-кнопок
    application.add_handler(CallbackQueryHandler(help_callback, pattern="^help_show$"))
    application.add_handler(CallbackQueryHandler(stats_callback, pattern="^stats_show$"))
    application.add_handler(CallbackQueryHandler(export_csv_callback, pattern="^export_csv$"))
    application.add_handler(CallbackQueryHandler(back_to_settings_callback, pattern="^back_to_settings$"))
    application.add_handler(CallbackQueryHandler(handle_pagination, pattern=r"^paginate_"))
    application.add_handler(CallbackQueryHandler(noop_callback, pattern=r"^noop$"))
    
    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()
