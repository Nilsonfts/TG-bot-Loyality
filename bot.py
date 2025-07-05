# -*- coding: utf-8 -*-

import logging
import os
import re
import json
from datetime import datetime
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
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
CARDS_PER_PAGE = 5

# --- Настройка логирования ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Состояния для диалога ---
(
    EMAIL, FIO_INITIATOR, JOB_TITLE, OWNER_LAST_NAME, OWNER_FIRST_NAME,
    REASON, CARD_TYPE, CARD_NUMBER, CATEGORY, AMOUNT,
    FREQUENCY, COMMENT, CONFIRMATION,
    AWAIT_SEARCH_QUERY
) = range(14)


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

def get_all_user_cards_from_sheet(user_id: str) -> list:
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_KEY")).sheet1
        all_rows = sheet.get_all_values()
        data_rows = all_rows[1:]
        user_cards = []
        for row in data_rows:
            if len(row) > 1 and str(row[1]) == user_id:
                if len(row) >= 19:
                    card_info = {
                        "date": row[0], "owner_first_name": row[6], "owner_last_name": row[5],
                        "card_number": row[9], "status_q": row[16] or "–", "status_s": row[18] or "–"
                    }
                    cards.append(card_info)
        return list(reversed(user_cards))
    except Exception as e:
        logger.error(f"Ошибка при поиске карт пользователя: {e}")
    return []

def write_to_sheet(data: dict, submission_time: str, tg_user_id: str):
    client = get_gspread_client()
    if not client: return False
    try:
        sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_KEY")).sheet1
        row_to_insert = [
            submission_time, tg_user_id, data.get('email', ''), data.get('fio_initiator', ''),
            data.get('job_title', ''), data.get('owner_last_name', ''), data.get('owner_first_name', ''),
            data.get('reason', ''), data.get('card_type', ''), data.get('card_number', ''),
            data.get('category', ''), data.get('amount', ''), data.get('frequency', ''),
            data.get('comment', ''), '', '', '', '', ''
        ]
        sheet.append_row(row_to_insert, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        logger.error(f"Не удалось записать данные в таблицу: {e}")
    return False

# --- ГЛАВНОЕ МЕНЮ И ДРУГИЕ КОМАНДЫ ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [["✍️ Подать заявку"], ["🗂️ Мои Карты", "🔍 Поиск", "❓ Помощь"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы в главном меню. Выберите действие:", reply_markup=reply_markup)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = ("<b>Справка по боту</b>\n\n"
                 "▫️ <b>Подать заявку</b> - запуск пошаговой анкеты.\n"
                 "▫️ <b>Мои Карты</b> - просмотр всех поданных вами заявок.\n"
                 "▫️ <b>Поиск</b> - поиск по вашим заявкам.\n\n"
                 "Нажатие на любую кнопку меню во время заполнения анкеты отменит текущее действие.")
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

# ... (Пагинация и Поиск остаются без изменений)
async def display_paginated_list(message_to_edit, context: ContextTypes.DEFAULT_TYPE, page: int, data_key: str, list_title: str):
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
        owner_name = f"{card.get('owner_first_name','')} {card.get('owner_last_name','-')}".strip()
        text += (f"👤 <b>Владелец:</b> {owner_name}\n"
                 f"📞 Номер: {card['card_number']}\n"
                 f"<b>Согласование:</b> <code>{card['status_q']}</code> | <b>Активность:</b> <code>{card['status_s']}</code>\n"
                 f"📅 Дата: {card['date']}\n"
                 f"--------------------\n")
    keyboard = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"paginate_{data_key}_{page - 1}"))
    row.append(InlineKeyboardButton(f" стр. {page + 1}/{total_pages} ", callback_data="noop"))
    if end_index < len(all_items):
        row.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"paginate_{data_key}_{page + 1}"))
    keyboard.append(row)
    await message_to_edit.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, data_key, page_str = query.data.split('_')
    page = int(page_str)
    list_title = "Ваши поданные заявки" if data_key == "mycards" else "Результаты поиска"
    await display_paginated_list(query.message, context, page=page, data_key=data_key, list_title=list_title)
async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
async def my_cards_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    loading_message = await update.message.reply_text("🔍 Загружаю ваши заявки...")
    all_cards = get_all_user_cards_from_sheet(user_id)
    if not all_cards:
        await loading_message.edit_text("🤷 Вы еще не подали ни одной заявки.")
        return
    context.user_data['mycards'] = all_cards
    await display_paginated_list(loading_message, context, page=0, data_key='mycards', list_title="Ваши поданные заявки")
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите, что вы хотите найти (имя, фамилию или номер телефона):")
    return AWAIT_SEARCH_QUERY
async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    search_query = update.message.text.lower()
    loading_message = await update.message.reply_text("🔍 Выполняю поиск...")
    all_cards = get_all_user_cards_from_sheet(user_id)
    if not all_cards:
        await loading_message.edit_text("🤷 У вас нет заявок для поиска.")
        return ConversationHandler.END
    search_results = [card for card in all_cards if search_query in card['owner_first_name'].lower() or search_query in card['owner_last_name'].lower() or search_query in card['card_number']]
    context.user_data['search'] = search_results
    await display_paginated_list(loading_message, context, page=0, data_key='search', list_title="Результаты поиска")
    return ConversationHandler.END

# --- НОВЫЙ ДИАЛОГ ПОДАЧИ ЗАЯВКИ С "ЖИВЫМ" ЧЕК-ЛИСТОМ ---

def format_live_summary(data: dict) -> str:
    """Форматирует 'живую' карточку-заявку с галочками."""
    # Вспомогательная функция для красивого вывода полей
    def field(emoji, label, value_key, default="..."):
        return f"{emoji} <b>{label}:</b> {data[value_key]}\n" if value_key in data else f"⏳ <b>{label}:</b> {default}\n"

    text = "<b>Заявка в процессе заполнения:</b>\n\n"
    text += "--- <b>Инициатор</b> ---\n"
    text += field("👤", "ФИО", 'fio_initiator')
    text += field("📧", "Почта", 'email')
    text += field("🏢", "Должность", 'job_title')
    text += "\n--- <b>Карта лояльности</b> ---\n"
    text += field("💳", "Владелец", 'owner_full_name')
    text += field("📞", "Номер", 'card_number')
    text += field("✨", "Тип", 'card_type')
    text += field("💰", "Сумма/%", 'amount_display')
    text += field("📈", "Статья", 'category')
    text += field("🔄", "Периодичность", 'frequency')
    text += field("💬", "Комментарий", 'comment')
    return text

async def update_live_summary(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Обновляет сообщение с 'живой' карточкой."""
    summary_message_id = context.user_data.get('summary_message_id')
    if summary_message_id:
        text = format_live_summary(context.user_data)
        try:
            await context.bot.edit_message_text(text, chat_id=chat_id, message_id=summary_message_id, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Не удалось обновить карточку: {e}")

async def ask_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str, reply_markup=None):
    """Удаляет сообщение пользователя, старый вопрос и задает новый."""
    chat_id = update.effective_chat.id
    
    # Удаляем сообщение пользователя с ответом
    try:
        await context.bot.delete_message(chat_id, update.message.message_id)
    except Exception: pass
    
    # Удаляем предыдущий вопрос бота
    if 'question_message_id' in context.user_data:
        try:
            await context.bot.delete_message(chat_id, context.user_data['question_message_id'])
        except Exception: pass
        
    # Задаем новый вопрос
    msg = await context.bot.send_message(chat_id, question, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    context.user_data['question_message_id'] = msg.message_id


async def start_form_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    chat = update.effective_chat
    summary_msg = await chat.send_message(format_live_summary(context.user_data), parse_mode=ParseMode.HTML)
    context.user_data['summary_message_id'] = summary_msg.message_id
    await ask_next_question(update, context, "📧 Введите вашу рабочую почту:")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['email'] = update.message.text
    context.user_data['fio_initiator'] = update.effective_user.full_name
    await update_live_summary(context, update.effective_chat.id)
    await ask_next_question(update, context, "👤 Введите вашу должность?")
    return JOB_TITLE

async def get_job_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['job_title'] = update.message.text
    await update_live_summary(context, update.effective_chat.id)
    await ask_next_question(update, context, "💳 Введите <b>Фамилию</b> владельца карты.")
    return OWNER_LAST_NAME

async def get_owner_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['owner_last_name'] = update.message.text
    await ask_next_question(context, update.effective_chat.id, "💳 Введите <b>Имя</b> владельца карты.")
    return OWNER_FIRST_NAME

async def get_owner_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['owner_first_name'] = update.message.text
    context.user_data['owner_full_name'] = f"{update.message.text} {context.user_data['owner_last_name']}"
    await update_live_summary(context, update.effective_chat.id)
    await ask_next_question(context, update.effective_chat.id, "🤔 Причина выдачи?")
    return REASON

async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['reason'] = update.message.text
    keyboard = [[InlineKeyboardButton("Бартер", callback_data="Бартер"), InlineKeyboardButton("Скидка", callback_data="Скидка")]]
    await ask_next_question(context, update.effective_chat.id, "✨ Тип карты?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CARD_TYPE

async def get_card_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['card_type'] = query.data
    await update_live_summary(context, query.message.chat_id)
    await ask_next_question(query, context, "📞 Номер карты (телефон через 8)?")
    return CARD_NUMBER

async def get_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    number = update.message.text
    if not (number.startswith('8') and number[1:].isdigit() and len(number) == 11):
        await ask_next_question(update, context, "❌ Неверный формат. Попробуйте еще раз (11 цифр, начиная с 8).")
        return CARD_NUMBER
    context.user_data['card_number'] = number
    await update_live_summary(context, update.effective_chat.id)
    keyboard = [[InlineKeyboardButton("АРТ", callback_data="АРТ"), InlineKeyboardButton("МАРКЕТ", callback_data="МАРКЕТ")], [InlineKeyboardButton("Операционный блок", callback_data="Операционный блок")], [InlineKeyboardButton("СКИДКА", callback_data="СКИДКА"), InlineKeyboardButton("Сертификат", callback_data="Сертификат")], [InlineKeyboardButton("Учредители", callback_data="Учредители")]]
    await ask_next_question(context, update.effective_chat.id, "📈 Статья пополнения?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CATEGORY

async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['category'] = query.data
    await update_live_summary(context, query.message.chat_id)
    prompt = "💰 Сумма бартера?" if context.user_data.get('card_type') == "Бартер" else "💰 Процент скидки?"
    await ask_next_question(query, context, prompt)
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if not text.isdigit():
        await ask_next_question(update, context, "❌ Нужно только число. Попробуйте еще раз.")
        return AMOUNT
    context.user_data['amount'] = text
    context.user_data['amount_display'] = f"{text}{'%' if context.user_data.get('card_type') == 'Скидка' else ' ₽'}"
    await update_live_summary(context, update.effective_chat.id)
    keyboard = [[InlineKeyboardButton("Разовая", callback_data="Разовая")], [InlineKeyboardButton("Дополнить к балансу", callback_data="Дополнить к балансу")], [InlineKeyboardButton("Замена номера карты", callback_data="Замена номера карты")]]
    await ask_next_question(context, update.effective_chat.id, "🔄 Периодичность?", reply_markup=InlineKeyboardMarkup(keyboard))
    return FREQUENCY

async def get_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['frequency'] = query.data
    await update_live_summary(context, query.message.chat_id)
    await ask_next_question(query, context, "💬 Последний шаг: Комментарий?")
    return COMMENT

async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['comment'] = update.message.text
    await update_live_summary(context, update.effective_chat.id)
    summary_message_id = context.user_data.get('summary_message_id')
    final_text = format_live_summary(context.user_data) + "\n\n<i><b>Все верно? Отправляем?</b></i>"
    keyboard = [[InlineKeyboardButton("✅ Да, отправить", callback_data="submit"), InlineKeyboardButton("❌ Отмена", callback_data="cancel_final")]]
    if 'question_message_id' in context.user_data:
        await context.bot.delete_message(update.effective_chat.id, context.user_data['question_message_id'])
    await context.bot.edit_message_text(final_text, chat_id=update.effective_chat.id, message_id=summary_message_id, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    await asyncio.sleep(1)
    success = write_to_sheet(context.user_data, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id)
    
    final_summary = format_live_summary(context.user_data)
    status_text = "✅ <b>Заявка успешно записана.</b>" if success else "❌ <b>Ошибка при записи в таблицу.</b>"
    final_summary_with_status = final_summary + f"\n<b>Статус:</b> {status_text}"
    
    await query.edit_message_text(text=final_summary_with_status, parse_mode=ParseMode.HTML, reply_markup=None)
    
    await show_main_menu(update, context)
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена на финальном шаге."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Заявка отменена.", parse_mode=ParseMode.HTML)
    await show_main_menu(update, context)
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Полностью отменяет любой диалог и возвращает в главное меню."""
    if context.user_data:
        await update.message.reply_text("Текущее действие отменено.")
        # Попытка удалить 'живую' карточку, если она была создана
        if 'summary_message_id' in context.user_data:
            try:
                await context.bot.delete_message(update.effective_chat.id, context.user_data['summary_message_id'])
            except Exception: pass
        context.user_data.clear()
    await show_main_menu(update, context)
    return ConversationHandler.END


# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА БОТА ---
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    form_filter = filters.Regex("^(✍️ )?Подать заявку$")
    cards_filter = filters.Regex("^(🗂️ )?Мои Карты$")
    search_filter = filters.Regex("^(🔍 )?Поиск$")
    help_filter = filters.Regex("^(❓ )?Помощь$")
    state_text_filter = filters.TEXT & ~filters.COMMAND & ~form_filter & ~cards_filter & ~search_filter & ~help_filter
    
    fallback_handler = MessageHandler(cards_filter | search_filter | help_filter, cancel_conversation)
    cancel_handler = CommandHandler("cancel", cancel_conversation)

    form_conv = ConversationHandler(
        entry_points=[MessageHandler(form_filter, start_form_conversation)],
        states={
            EMAIL: [MessageHandler(state_text_filter, get_email)],
            JOB_TITLE: [MessageHandler(state_text_filter, get_job_title)],
            OWNER_LAST_NAME: [MessageHandler(state_text_filter, get_owner_last_name)], 
            OWNER_FIRST_NAME: [MessageHandler(state_text_filter, get_owner_first_name)],
            REASON: [MessageHandler(state_text_filter, get_reason)], 
            CARD_TYPE: [CallbackQueryHandler(get_card_type)],
            CARD_NUMBER: [MessageHandler(state_text_filter, get_card_number)], 
            CATEGORY: [CallbackQueryHandler(get_category)],
            AMOUNT: [MessageHandler(state_text_filter, get_amount)], 
            FREQUENCY: [CallbackQueryHandler(get_frequency)],
            COMMENT: [MessageHandler(state_text_filter, get_comment)],
            CONFIRMATION: [
                CallbackQueryHandler(submit, pattern="^submit$"), 
                CallbackQueryHandler(cancel_final, pattern="^cancel_final$")
            ],
        },
        fallbacks=[fallback_handler, cancel_handler],
    )

    search_conv = ConversationHandler(
        entry_points=[MessageHandler(search_filter, search_command)],
        states={ AWAIT_SEARCH_QUERY: [MessageHandler(state_text_filter, perform_search)] },
        fallbacks=[MessageHandler(form_filter | cards_filter | help_filter, cancel_conversation), cancel_handler],
    )

    application.add_handler(CommandHandler("start", show_main_menu))
    application.add_handler(form_conv)
    application.add_handler(search_conv)
    application.add_handler(MessageHandler(cards_filter, my_cards_command))
    application.add_handler(MessageHandler(help_filter, show_help))
    application.add_handler(CallbackQueryHandler(handle_pagination, pattern=r"^paginate_"))
    application.add_handler(CallbackQueryHandler(noop_callback, pattern=r"^noop$"))
    
    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()
