# -*- coding: utf-8 -*-

import logging
import os
import re
import json
from datetime import datetime

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
CARDS_PER_PAGE = 5 # Количество записей на одной странице

# --- Настройка логирования ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Состояния для диалога ---
(
    # Основная анкета
    REUSE_DATA, EMAIL, FIO_INITIATOR, JOB_TITLE, OWNER_LAST_NAME, OWNER_FIRST_NAME,
    REASON, CARD_TYPE, CARD_NUMBER, CATEGORY, AMOUNT,
    FREQUENCY, COMMENT, CONFIRMATION,
    # Поиск
    AWAIT_SEARCH_QUERY
) = range(15)


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
    """Находит ВСЕ записи пользователя в таблице и возвращает их списком."""
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_KEY")).sheet1
        cell_list = sheet.findall(user_id, in_column=2)
        cards = []
        for cell in cell_list:
            row = sheet.row_values(cell.row)
            if len(row) >= 19:
                card_info = {
                    "date": row[0], "tg_id": row[1], "initiator_email": row[2],
                    "initiator_fio": row[3], "initiator_job": row[4],
                    "owner_last_name": row[5], "owner_first_name": row[6],
                    "reason": row[7], "card_type": row[8], "card_number": row[9],
                    "category": row[10], "amount": row[11], "frequency": row[12],
                    "comment": row[13], "status_q": row[16] or "–", "status_s": row[18] or "–"
                }
                cards.append(card_info)
        return list(reversed(cards)) # Новые сверху
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
            data.get('comment', ''), '', '', '', '', '', '' # Добавляем пустые ячейки до S
        ]
        sheet.append_row(row_to_insert)
        return True
    except Exception as e:
        logger.error(f"Не удалось записать данные в таблицу: {e}")
    return False

# --- ОБЩАЯ СИСТЕМА ПАГИНАЦИИ ---
async def display_paginated_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, data_key: str, list_title: str, message_to_edit):
    """Универсальная функция для отображения любого списка с пагинацией."""
    all_items = context.user_data.get(data_key, [])
    if not all_items:
        await message_to_edit.edit_text("🤷 Ничего не найдено.")
        return

    start_index = page * CARDS_PER_PAGE
    end_index = start_index + CARDS_PER_PAGE
    items_on_page = all_items[start_index:end_index]
    total_pages = (len(all_items) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE

    text = f"<b>{list_title} (Страница {page + 1} из {total_pages}):</b>\n\n"
    for card in items_on_page:
        owner_name = f"{card.get('owner_first_name','')} {card.get('owner_last_name','-')}".strip()
        text += (
            f"👤 <b>Владелец:</b> {owner_name}\n"
            f"📞 Номер: {card['card_number']}\n"
            f"<b>Согласование:</b> <code>{card['status_q']}</code>\n"
            f"<b>Активность:</b> <code>{card['status_s']}</code>\n"
            f"📅 Дата подачи: {card['date']}\n"
            f"--------------------\n"
        )

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
    """Обрабатывает нажатия на любые кнопки пагинации."""
    query = update.callback_query
    await query.answer()
    _, data_key, page_str = query.data.split('_')
    page = int(page_str)
    
    list_title = "Ваши поданные заявки" if data_key == "mycards" else "Результаты поиска"
    await display_paginated_list(update, context, page=page, data_key=data_key, list_title=list_title, message_to_edit=query.message)

async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()

# --- КОМАНДА /mycards ---
async def show_my_cards(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    loading_message = await update.message.reply_text("🔍 Загружаю ваши заявки из таблицы...")
    all_cards = get_all_user_cards_from_sheet(user_id)
    if not all_cards:
        await loading_message.edit_text("🤷 Вы еще не подали ни одной заявки.")
        return
    context.user_data['mycards'] = all_cards
    await display_paginated_list(update, context, page=0, data_key='mycards', list_title="Ваши поданные заявки", message_to_edit=loading_message)

# --- НОВЫЙ ДИАЛОГ ПОИСКА: /search ---
async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог поиска."""
    await update.message.reply_text("Введите, что вы хотите найти (имя, фамилию или номер телефона):")
    return AWAIT_SEARCH_QUERY

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выполняет поиск по картам пользователя."""
    user_id = str(update.effective_user.id)
    search_query = update.message.text.lower()
    loading_message = await update.message.reply_text("🔍 Выполняю поиск...")

    all_cards = get_all_user_cards_from_sheet(user_id)
    if not all_cards:
        await loading_message.edit_text("🤷 У вас нет заявок для поиска.")
        return ConversationHandler.END

    search_results = [
        card for card in all_cards
        if search_query in card['owner_first_name'].lower()
        or search_query in card['owner_last_name'].lower()
        or search_query in card['card_number']
    ]

    context.user_data['search'] = search_results
    await display_paginated_list(update, context, page=0, data_key='search', list_title="Результаты поиска", message_to_edit=loading_message)
    return ConversationHandler.END

# --- ОСНОВНОЙ ДИАЛОГ ПОДАЧИ ЗАЯВКИ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (код этой функции и всех шагов анкеты остается таким же, как в прошлый раз)
    # Я его включу в финальный блок для полноты
    user_id = str(update.effective_user.id)
    chat = update.effective_chat
    if context.user_data.get('initiator_fio'):
        initiator_data = {
            "fio": context.user_data['initiator_fio'],
            "email": context.user_data['initiator_email'],
            "job_title": context.user_data['initiator_job_title']
        }
    else:
        initiator_data = None # Будет None, если это первый запуск
    #... и так далее
    # Для краткости здесь опускаю, но в финальном коде он будет полностью.
    # ... (весь остальной код анкеты)

# --- Полный код всех функций анкеты для копирования ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    chat = update.effective_chat
    
    initiator_data = context.user_data.get('initiator_fio') and {
        "fio": context.user_data.get('initiator_fio'),
        "email": context.user_data.get('initiator_email'),
        "job_title": context.user_data.get('initiator_job_title')
    }
    
    form_keys_to_clear = [
        'owner_last_name', 'owner_first_name', 'reason', 'card_type', 'card_number',
        'category', 'amount', 'frequency', 'comment', 'email', 'fio_initiator', 'job_title'
    ]
    for key in form_keys_to_clear:
        if key in context.user_data:
            del context.user_data[key]

    if initiator_data:
        text = (
            f"Здравствуйте! Используем сохраненные данные инициатора:\n\n"
            f"👤 <b>ФИО:</b> {initiator_data['fio']}\n"
            f"📧 <b>Почта:</b> {initiator_data['email']}\n"
            f"🏢 <b>Должность:</b> {initiator_data['job_title']}\n\n"
            f"Продолжить с этими данными?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Да, продолжить", callback_data="reuse_data")],
            [InlineKeyboardButton("✏️ Ввести заново", callback_data="enter_new_data")],
        ]
        await chat.send_message(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return REUSE_DATA
    else:
        await chat.send_message("Здравствуйте! Начинаем процесс регистрации.\n\nВведите вашу рабочую почту.")
        return EMAIL

async def handle_reuse_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == 'reuse_data':
        context.user_data['email'] = context.user_data['initiator_email']
        context.user_data['fio_initiator'] = context.user_data['initiator_fio']
        context.user_data['job_title'] = context.user_data['initiator_job_title']
        await query.edit_message_text("Данные инициатора заполнены.")
        await query.message.reply_text("Введите <b>Фамилию</b> владельца карты.", parse_mode=ParseMode.HTML)
        return OWNER_LAST_NAME
    else:
        await query.edit_message_text("Хорошо, введите данные заново.")
        await query.message.reply_text("Ваша рабочая почта?")
        return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['email'] = update.message.text
    context.user_data['initiator_email'] = update.message.text
    await update.message.reply_text("Ваше ФИО (полностью)?")
    return FIO_INITIATOR

async def get_fio_initiator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['fio_initiator'] = update.message.text
    context.user_data['initiator_fio'] = update.message.text
    await update.message.reply_text("Ваша должность?")
    return JOB_TITLE

async def get_job_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['job_title'] = update.message.text
    context.user_data['initiator_job_title'] = update.message.text
    await update.message.reply_text("Спасибо. Теперь введите <b>Фамилию</b> владельца карты.", parse_mode=ParseMode.HTML)
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
    keyboard = [[InlineKeyboardButton("Бартер", callback_data="Бартер"), InlineKeyboardButton("Скидка", callback_data="Скидка")]]
    await update.message.reply_text("Тип карты?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CARD_TYPE

async def get_card_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['card_type'] = query.data
    await query.edit_message_text(f"Выбрано: {query.data}.\n\nНомер карты (телефон через 8)?")
    return CARD_NUMBER

async def get_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    number = update.message.text
    if not (number.startswith('8') and number[1:].isdigit() and len(number) == 11):
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
    prompt = "Сумма бартера?" if context.user_data.get('card_type') == "Бартер" else "Процент скидки?"
    await query.edit_message_text(f"Статья: {query.data}.\n\n{prompt}")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if not text.isdigit():
        await update.message.reply_text("Нужно только число.")
        return AMOUNT
    context.user_data['amount'] = text
    keyboard = [[InlineKeyboardButton("Разовая", callback_data="Разовая")], [InlineKeyboardButton("Дополнить к балансу", callback_data="Дополнить к балансу")], [InlineKeyboardButton("Замена номера карты", callback_data="Замена номера карты")]]
    await update.message.reply_text("Периодичность?", reply_markup=InlineKeyboardMarkup(keyboard))
    return FREQUENCY

async def get_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['frequency'] = query.data
    await query.edit_message_text(f"Выбрано: {query.data}.\n\nКомментарий?")
    return COMMENT

def format_summary(data: dict) -> str:
    owner_full_name = f"{data.get('owner_first_name', '')} {data.get('owner_last_name', '')}".strip()
    card_type = data.get('card_type')
    amount_label = "Скидка" if card_type == 'Скидка' else "Сумма"
    amount_value = f"{data.get('amount', '0')}{'%' if card_type == 'Скидка' else ' ₽'}"
    return (
        "<b>Проверьте заявку:</b>\n\n"
        "<b>Инициатор:</b> {fio}, {job}, {email}\n"
        "<b>Владелец:</b> {owner}\n"
        "<b>Карта:</b> {num}, {type}\n"
        "<b>Начисление:</b> {amount} ({label})\n"
        "<b>Комментарий:</b> {comm}".format(
            fio=data.get('fio_initiator', '-'), job=data.get('job_title', '-'), email=data.get('email', '-'),
            owner=owner_full_name, num=data.get('card_number', '-'), type=card_type,
            amount=amount_value, label=data.get('frequency', '-'), comm=data.get('comment', '-')
        )
    )

async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['comment'] = update.message.text
    summary = format_summary(context.user_data)
    keyboard = [[InlineKeyboardButton("✅ Да, все верно", callback_data="submit"), InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Сохраняю...")
    user_id = str(query.from_user.id)
    success = write_to_sheet(context.user_data, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id)
    if success:
        await query.edit_message_text("✅ Готово! Заявка записана.")
    else:
        await query.edit_message_text("❌ Ошибка при записи в таблицу.")
    keyboard = [["Подать новую заявку"]]
    await context.bot.send_message(query.message.chat_id, "Нажмите кнопку, чтобы начать заново 👇", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))
    context.user_data.clear()
    return ConversationHandler.END

async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Начинаем заново...")
    return await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено.")
    if 'search' in context.user_data: del context.user_data['search']
    if 'mycards' in context.user_data: del context.user_data['mycards']
    return ConversationHandler.END

# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА БОТА ---
def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Не найден токен TELEGRAM_BOT_TOKEN.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Диалог для подачи заявки
    form_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.Regex("^Подать новую заявку$"), start)],
        states={
            REUSE_DATA: [CallbackQueryHandler(handle_reuse_choice)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            FIO_INITIATOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fio_initiator)],
            JOB_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_job_title)],
            OWNER_LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_owner_last_name)],
            OWNER_FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_owner_first_name)],
            REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reason)],
            CARD_TYPE: [CallbackQueryHandler(get_card_type)],
            CARD_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_card_number)],
            CATEGORY: [CallbackQueryHandler(get_category)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            FREQUENCY: [CallbackQueryHandler(get_frequency)],
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_comment)],
            CONFIRMATION: [
                CallbackQueryHandler(submit, pattern="^submit$"),
                CallbackQueryHandler(restart_conversation, pattern="^restart$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Диалог для поиска
    search_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("search", start_search)],
        states={
            AWAIT_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, perform_search)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(form_conv_handler)
    application.add_handler(search_conv_handler)
    application.add_handler(CommandHandler("mycards", show_my_cards))
    application.add_handler(CallbackQueryHandler(handle_pagination, pattern=r"^paginate_"))
    application.add_handler(CallbackQueryHandler(noop_callback, pattern=r"^noop$"))
    
    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()
