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
    REGISTER_CONTACT, REGISTER_FIO, REGISTER_EMAIL, REGISTER_JOB_TITLE,
    OWNER_LAST_NAME, OWNER_FIRST_NAME,
    REASON, CARD_TYPE, CARD_NUMBER, CATEGORY, AMOUNT,
    FREQUENCY, COMMENT, CONFIRMATION,
    SEARCH_CHOOSE_FIELD, AWAIT_SEARCH_QUERY
) = range(16)


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
    """ИСПРАВЛЕНО: Корректно сопоставляет все данные со столбцами."""
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

# --- УТИЛИТАРНЫЕ ФУНКЦИИ ОЧИСТКИ ЧАТА ---
def add_message_to_delete(context: ContextTypes.DEFAULT_TYPE, message_id: int):
    context.user_data.setdefault('messages_to_delete', []).append(message_id)

async def delete_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    message_ids = context.user_data.pop('messages_to_delete', [])
    logger.info(f"Удаление {len(message_ids)} сообщений...")
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение {msg_id}: {e}")

# --- ГЛАВНОЕ МЕНЮ И СИСТЕМА НАВИГАЦИИ ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [["✍️ Подать заявку"], ["🔍 Поиск", "⚙️ Настройки"], ["🏠 Главное меню"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы в главном меню. Выберите действие:", reply_markup=reply_markup)

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    cards_button_text = "🗂️ Все заявки" if user_id == BOSS_ID else "🗂️ Мои Карты"
    
    keyboard = [
        [InlineKeyboardButton(cards_button_text, callback_data="settings_my_cards")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats_show")],
        [InlineKeyboardButton("📄 Экспорт в CSV", callback_data="export_csv")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_show")]
    ]
    await update.message.reply_text("Меню настроек:", reply_markup=InlineKeyboardMarkup(keyboard))

async def settings_my_cards_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает кнопку 'Мои Карты' из меню настроек."""
    query = update.callback_query
    await query.answer()
    await query.message.delete() # Удаляем меню настроек
    # Создаем фейковый объект message, чтобы передать его в my_cards_command
    await my_cards_command(query, context)

# ... (остальные колбэки меню настроек)
async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    help_text = ("<b>Справка по боту</b>\n\n"
                 "▫️ <b>Подать заявку</b> - запуск анкеты.\n"
                 "▫️ <b>Все карты / Мои Карты</b> - просмотр заявок.\n"
                 "▫️ <b>Поиск</b> - поиск по заявкам.\n"
                 "▫️ <b>Настройки</b> - это меню.\n\n"
                 "Нажатие на любую кнопку главного меню во время заполнения анкеты отменит ее.")
    keyboard = [[InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]
    await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
async def back_to_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    cards_button_text = "🗂️ Все заявки" if user_id == BOSS_ID else "🗂️ Мои Карты"
    keyboard = [
        [InlineKeyboardButton(cards_button_text, callback_data="settings_my_cards")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats_show")],
        [InlineKeyboardButton("📄 Экспорт в CSV", callback_data="export_csv")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_show")]
    ]
    await query.edit_message_text("Меню настроек:", reply_markup=InlineKeyboardMarkup(keyboard))

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = str(query.from_user.id)
    is_boss = (user_id == BOSS_ID)
    await query.edit_message_text("📊 Собираю статистику...")
    all_cards = get_cards_from_sheet() if is_boss else get_cards_from_sheet(user_id)
    if not all_cards: await query.edit_message_text("Нет данных для статистики."); return
    total_cards = len(all_cards)
    barter_count = sum(1 for card in all_cards if card.get('Какую карту регистрируем?') == 'Бартер')
    discount_count = total_cards - barter_count
    try:
        category_counter = Counter(card.get('Статья пополнения карт') for card in all_cards if card.get('Статья пополнения карт'))
        most_common_category = category_counter.most_common(1)[0][0] if category_counter else "–"
    except Exception: most_common_category = "Не удалось посчитать"
    text = f"<b>Статистика</b>\n\n"
    if is_boss: text += f"🗂️ Всего заявок в системе: <b>{total_cards}</b>\n"
    else: text += f"🗂️ Подано вами заявок: <b>{total_cards}</b>\n"
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
    if not cards_to_export: await query.edit_message_text("Нет данных для экспорта."); return
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=cards_to_export[0].keys())
    writer.writeheader()
    writer.writerows(cards_to_export)
    output.seek(0)
    file_to_send = InputFile(output.getvalue().encode('utf-8-sig'), filename=f"export_{datetime.now().strftime('%Y-%m-%d')}.csv")
    await context.bot.send_document(chat_id=query.message.chat_id, document=file_to_send)
    await query.message.delete()


# --- ПАГИНАЦИЯ И ПОИСК ---
# (Этот код без изменений)
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
                 f"<b>Согласование:</b> <code>{card.get('Статус Согласования', '–')}</code> | <b>Активность:</b> <code>{card.get('Статус активности', '–')}</code>\n"
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


# --- ДИАЛОГ ПОДАЧИ ЗАЯВКИ С АВТОРИЗАЦИЕЙ ---
# ... (Этот блок кода остается без изменений, он стабилен)
async def start_form_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    #... (код без изменений)
    await show_main_menu(update, context) # Возвращаемся в главное меню в конце
    return ConversationHandler.END

# ... (Остальные функции диалога остаются здесь)
# ...

# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА БОТА ---
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Фильтры для кнопок меню
    form_filter = filters.Regex("^(✍️ )?Подать заявку$")
    search_filter = filters.Regex("^(🔍 )?Поиск$")
    settings_filter = filters.Regex("^(⚙️ )?Настройки$")
    main_menu_filter = filters.Regex("^(🏠 )?Главное меню$")

    state_text_filter = filters.TEXT & ~filters.COMMAND & ~form_filter & ~search_filter & ~settings_filter & ~main_menu_filter
    
    cancel_handler = CommandHandler("cancel", cancel)
    fallback_handler = MessageHandler(search_filter | settings_filter | main_menu_filter, cancel)
    
    # Диалоги
    form_conv = ConversationHandler(
        entry_points=[MessageHandler(form_filter, start_form_conversation)],
        states={
            # ... (все состояния анкеты и регистрации)
        },
        fallbacks=[fallback_handler, cancel_handler],
    )
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(search_filter, search_command)],
        states={
            SEARCH_CHOOSE_FIELD: [CallbackQueryHandler(search_field_chosen)],
            AWAIT_SEARCH_QUERY: [MessageHandler(state_text_filter, perform_search)]
        },
        fallbacks=[MessageHandler(form_filter | settings_filter | main_menu_filter, cancel), cancel_handler],
    )

    # Регистрация всех хендлеров
    application.add_handler(CommandHandler("start", show_main_menu))
    application.add_handler(MessageHandler(main_menu_filter, show_main_menu))
    application.add_handler(form_conv)
    application.add_handler(search_conv)
    application.add_handler(MessageHandler(settings_filter, show_settings))
    
    # ... (регистрация всех CallbackQueryHandler'ов)
    
    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()
