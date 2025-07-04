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
# Убедитесь, что эти переменные установлены на вашем хостинге (Railway)
# 1. TELEGRAM_BOT_TOKEN: Секретный токен вашего бота от BotFather.
# 2. GOOGLE_CREDS_JSON: Полное содержимое вашего JSON-файла с учетными данными.
# 3. GOOGLE_SHEET_KEY: ID (ключ) вашей Google Таблицы из ее URL-адреса.

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --- Настройка логирования ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Состояния для диалога ---
(
    REUSE_DATA, EMAIL, FIO_INITIATOR, JOB_TITLE, OWNER_LAST_NAME, OWNER_FIRST_NAME,
    REASON, CARD_TYPE, CARD_NUMBER, CATEGORY, AMOUNT,
    FREQUENCY, COMMENT, CONFIRMATION
) = range(14)


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С GOOGLE SHEETS ---
def get_gspread_client():
    """Настраивает и возвращает клиент для работы с Google Sheets."""
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

def find_last_entry_in_sheet(user_id: str):
    """Ищет последнюю запись пользователя в таблице и возвращает его данные."""
    client = get_gspread_client()
    if not client:
        return None
    try:
        sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_KEY")).sheet1
        # Ищем ID пользователя во втором столбце (B)
        cell_list = sheet.findall(user_id, in_column=2)
        if cell_list:
            # Берем самую последнюю найденную запись
            last_cell = cell_list[-1]
            row_data = sheet.row_values(last_cell.row)
            # Предполагаем порядок столбцов: A:Дата, B:ТГ, C:Почта, D:ФИО, E:Должность
            if len(row_data) >= 5:
                return {
                    "email": row_data[2],
                    "fio": row_data[3],
                    "job_title": row_data[4]
                }
    except Exception as e:
        logger.error(f"Ошибка при поиске данных в таблице: {e}")
    return None

def write_to_sheet(data: dict, submission_time: str, tg_user_id: str):
    """Записывает данные в Google Таблицу."""
    client = get_gspread_client()
    if not client:
        return False
    try:
        sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_KEY")).sheet1
        row_to_insert = [
            submission_time, tg_user_id, data.get('email', ''), data.get('fio_initiator', ''),
            data.get('job_title', ''), data.get('owner_last_name', ''), data.get('owner_first_name', ''),
            data.get('reason', ''), data.get('card_type', ''), data.get('card_number', ''),
            data.get('category', ''), data.get('amount', ''), data.get('frequency', ''),
            data.get('comment', ''),
        ]
        sheet.append_row(row_to_insert)
        return True
    except Exception as e:
        logger.error(f"Не удалось записать данные в таблицу: {e}")
    return False


# --- ЛОГИКА ДИАЛОГА ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начинает диалог. Сначала проверяет кэш, и только потом Google Таблицу.
    """
    user_id = str(update.effective_user.id)
    chat = update.effective_chat
    
    # Сначала проверяем "быструю память" (кэш в context.user_data)
    if context.user_data.get('initiator_fio'):
        logger.info(f"Найдены кэшированные данные для пользователя {user_id}")
        initiator_data = {
            "fio": context.user_data['initiator_fio'],
            "email": context.user_data['initiator_email'],
            "job_title": context.user_data['initiator_job_title']
        }
    else:
        # Если в кэше пусто, один раз обращаемся к медленной Google Таблице
        logger.info(f"Кэш пуст. Ищем данные для пользователя {user_id} в Google Таблице...")
        initiator_data = find_last_entry_in_sheet(user_id)
        # Если нашли, сохраняем в кэш для будущих запусков
        if initiator_data:
            logger.info("Данные найдены в таблице и сохранены в кэш.")
            context.user_data['initiator_fio'] = initiator_data['fio']
            context.user_data['initiator_email'] = initiator_data['email']
            context.user_data['initiator_job_title'] = initiator_data['job_title']

    # Очищаем только данные прошлой *заявки*, оставляя данные *инициатора*
    form_keys_to_clear = [
        'owner_last_name', 'owner_first_name', 'reason', 'card_type', 'card_number',
        'category', 'amount', 'frequency', 'comment', 'email', 'fio_initiator', 'job_title',
        'found_initiator_data'
    ]
    for key in form_keys_to_clear:
        if key in context.user_data:
            del context.user_data[key]

    if initiator_data:
        text = (
            f"Здравствуйте! Найдена ваша предыдущая запись:\n\n"
            f"👤 <b>ФИО:</b> {initiator_data['fio']}\n"
            f"📧 <b>Почта:</b> {initiator_data['email']}\n"
            f"🏢 <b>Должность:</b> {initiator_data['job_title']}\n\n"
            f"Использовать эти данные для новой заявки?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Да, использовать", callback_data="reuse_data")],
            [InlineKeyboardButton("✏️ Ввести заново", callback_data="enter_new_data")],
        ]
        await chat.send_message(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return REUSE_DATA
    else:
        await chat.send_message(
            "Здравствуйте! Начинаем процесс регистрации карты лояльности.\n\n"
            "Пожалуйста, введите вашу рабочую электронную почту."
        )
        return EMAIL

async def handle_reuse_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор пользователя: использовать старые данные или ввести новые."""
    query = update.callback_query
    await query.answer()

    if query.data == 'reuse_data':
        # Копируем данные из кэша в текущую форму
        context.user_data['email'] = context.user_data['initiator_email']
        context.user_data['fio_initiator'] = context.user_data['initiator_fio']
        context.user_data['job_title'] = context.user_data['initiator_job_title']

        await query.edit_message_text("Отлично! Данные инициатора заполнены.")
        await query.message.reply_text("Теперь введите <b>Фамилию</b> владельца карты.", parse_mode=ParseMode.HTML)
        return OWNER_LAST_NAME
    else: # enter_new_data
        await query.edit_message_text("Хорошо, давайте введем данные заново.")
        await query.message.reply_text("Пожалуйста, введите вашу рабочую электронную почту.")
        return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает и сохраняет email инициатора."""
    context.user_data['email'] = update.message.text
    context.user_data['initiator_email'] = update.message.text # Кэшируем
    await update.message.reply_text("Отлично! Теперь введите ваше ФИО (полностью).")
    return FIO_INITIATOR

async def get_fio_initiator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает и сохраняет ФИО инициатора."""
    context.user_data['fio_initiator'] = update.message.text
    context.user_data['initiator_fio'] = update.message.text # Кэшируем
    await update.message.reply_text("Принято. Введите вашу должность в компании (можно сокращенно).")
    return JOB_TITLE

async def get_job_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает и сохраняет должность, переходит к данным владельца."""
    context.user_data['job_title'] = update.message.text
    context.user_data['initiator_job_title'] = update.message.text # Кэшируем
    await update.message.reply_text("Спасибо. Теперь введите <b>Фамилию</b> владельца карты.", parse_mode=ParseMode.HTML)
    return OWNER_LAST_NAME

async def get_owner_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['owner_last_name'] = update.message.text
    await update.message.reply_text("А теперь <b>Имя</b> владельца карты.", parse_mode=ParseMode.HTML)
    return OWNER_FIRST_NAME

async def get_owner_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['owner_first_name'] = update.message.text
    await update.message.reply_text("Укажите причину выдачи карты (бартер/скидка).")
    return REASON

async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['reason'] = update.message.text
    keyboard = [[InlineKeyboardButton("Бартер", callback_data="Бартер"), InlineKeyboardButton("Скидка", callback_data="Скидка")]]
    await update.message.reply_text("Какую карту регистрируем?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CARD_TYPE

async def get_card_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['card_type'] = query.data
    await query.edit_message_text(text=f"Выбрано: {query.data}.\n\nТеперь введите номер карты (он же номер телефона, через 8).")
    return CARD_NUMBER

async def get_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    number = update.message.text
    if not (number.startswith('8') and number[1:].isdigit() and len(number) == 11):
        await update.message.reply_text("Неверный формат. Номер должен начинаться с 8 и содержать 11 цифр.")
        return CARD_NUMBER
    context.user_data['card_number'] = number
    keyboard = [
        [InlineKeyboardButton("АРТ", callback_data="АРТ"), InlineKeyboardButton("МАРКЕТ", callback_data="МАРКЕТ")],
        [InlineKeyboardButton("Операционный блок", callback_data="Операционный блок")],
        [InlineKeyboardButton("СКИДКА", callback_data="СКИДКА"), InlineKeyboardButton("Сертификат", callback_data="Сертификат")],
        [InlineKeyboardButton("Учредители", callback_data="Учредители")]
    ]
    await update.message.reply_text("Выберите статью пополнения:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CATEGORY

async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['category'] = query.data
    card_type = context.user_data.get('card_type')
    prompt = "Введите сумму бартера:" if card_type == "Бартер" else "Введите процент скидки:"
    await query.edit_message_text(text=f"Выбрана статья: {query.data}.\n\n{prompt}")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount_text = update.message.text
    if not amount_text.isdigit():
        await update.message.reply_text("Пожалуйста, введите только число.")
        return AMOUNT
    context.user_data['amount'] = amount_text
    keyboard = [
        [InlineKeyboardButton("Разовая", callback_data="Разовая")],
        [InlineKeyboardButton("Дополнить к балансу", callback_data="Дополнить к балансу")],
        [InlineKeyboardButton("Замена номера карты", callback_data="Замена номера карты")],
    ]
    await update.message.reply_text("Выберите периодичность:", reply_markup=InlineKeyboardMarkup(keyboard))
    return FREQUENCY

async def get_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['frequency'] = query.data
    await query.edit_message_text(text=f"Выбрано: {query.data}.\n\nПоследний шаг: введите комментарий.")
    return COMMENT

def format_summary(data: dict) -> str:
    owner_full_name = f"{data.get('owner_last_name', '')} {data.get('owner_first_name', '')}".strip()
    card_type = data.get('card_type')
    amount_label = "Скидка" if card_type == 'Скидка' else "Сумма"
    amount_value = f"{data.get('amount', '0')}{'%' if card_type == 'Скидка' else ' ₽'}"
    summary = (
        "Пожалуйста, проверьте данные:\n\n"
        "<b>Инициатор</b>\n"
        f"👤 ФИО: {data.get('fio_initiator', '-')}\n"
        f"📧 Почта: {data.get('email', '-')}\n"
        f"🏢 Должность: {data.get('job_title', '-')}\n"
        "---\n"
        "<b>Карта лояльности</b>\n"
        f"💳 Владелец: {owner_full_name}\n"
        f"📞 Номер: {data.get('card_number', '-')}\n"
        f"✨ Тип: {card_type}\n"
        f"💰 <b>{amount_label}:</b> {amount_value}\n"
        f"📈 Статья: {data.get('category', '-')}\n"
        f"🔄 Периодичность: {data.get('frequency', '-')}\n"
        f"💬 Комментарий: {data.get('comment', '-')}\n"
        "---\n\n"
        "Все верно?"
    )
    return summary

async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['comment'] = update.message.text
    summary = format_summary(context.user_data)
    keyboard = [[InlineKeyboardButton("✅ Да, все верно", callback_data="submit"), InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Сохраняю данные...")
    user_id = str(query.from_user.id)
    success = write_to_sheet(context.user_data, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id)
    if success:
        await query.edit_message_text(text="✅ Готово! Данные успешно записаны в таблицу.")
    else:
        await query.edit_message_text(text="❌ Произошла ошибка при записи в таблицу.")
    keyboard = [["Подать новую заявку"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Чтобы подать еще одну заявку, нажмите на кнопку ниже 👇", reply_markup=reply_markup)
    
    # Очищаем только данные формы, оставляя данные инициатора в кэше
    form_keys = ['owner_last_name', 'owner_first_name', 'reason', 'card_type', 'card_number', 
                 'category', 'amount', 'frequency', 'comment', 'email', 'fio_initiator', 'job_title']
    for key in form_keys:
        if key in context.user_data:
            del context.user_data[key]
            
    return ConversationHandler.END

async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Корректно перезапускает диалог, вызывая start."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Начинаем заново...")
    return await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено.")
    context.user_data.clear() # Полная очистка при отмене
    return ConversationHandler.END


# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА БОТА ---

def main() -> None:
    """Собирает и запускает бота."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Не найден токен TELEGRAM_BOT_TOKEN.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^Подать новую заявку$"), start)
        ],
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

    application.add_handler(conv_handler)
    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()
