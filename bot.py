# -*- coding: utf-8 -*-

import logging
import os
import re
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# --- Настройка логирования для отладки ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Состояния для диалога (шаги анкеты) ---
(
    EMAIL, FIO_INITIATOR, JOB_TITLE, OWNER_LAST_NAME, OWNER_FIRST_NAME,
    REASON, CARD_TYPE, CARD_NUMBER, CATEGORY, AMOUNT,
    FREQUENCY, COMMENT, CONFIRMATION
) = range(13)


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
        else:
            logger.error("Переменная окружения GOOGLE_CREDS_JSON не найдена.")
            return None
    except Exception as e:
        logger.error(f"Ошибка аутентификации в Google Sheets: {e}")
        return None

def write_to_sheet(data: dict):
    """Записывает данные в Google Таблицу, используя ключ (ID) из переменных окружения."""
    client = get_gspread_client()
    if not client:
        logger.error("Не удалось получить gspread client.")
        return False

    sheet_key = os.getenv("GOOGLE_SHEET_KEY")
    if not sheet_key:
        logger.error("Переменная окружения GOOGLE_SHEET_KEY не найдена!")
        return False

    try:
        sheet = client.open_by_key(sheet_key).sheet1
        row_to_insert = [
            data.get('email', ''),
            data.get('fio_initiator', ''),
            data.get('job_title', ''),
            data.get('owner_last_name', ''),
            data.get('owner_first_name', ''),
            data.get('reason', ''),
            data.get('card_type', ''),
            data.get('card_number', ''),
            data.get('category', ''),
            data.get('amount', ''),
            data.get('frequency', ''),
            data.get('comment', ''),
        ]
        sheet.append_row(row_to_insert)
        return True
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"Таблица с ключом '{sheet_key}' не найдена. Проверьте ID и права доступа.")
        return False
    except Exception as e:
        logger.error(f"Не удалось записать данные в таблицу: {e}")
        return False


# --- ФУНКЦИИ-ШАГИ ДИАЛОГА ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог и запрашивает email."""
    context.user_data.clear()
    await update.message.reply_text(
        "Здравствуйте! Начинаем процесс регистрации карты лояльности.\n\n"
        "Пожалуйста, введите вашу рабочую электронную почту."
    )
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет email и запрашивает ФИО."""
    email = update.message.text
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text("Формат почты неверный. Пожалуйста, попробуйте еще раз.")
        return EMAIL

    context.user_data['email'] = email
    await update.message.reply_text("Отлично! Теперь введите ваше ФИО (полностью).")
    return FIO_INITIATOR

async def get_fio_initiator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет ФИО и запрашивает должность."""
    context.user_data['fio_initiator'] = update.message.text
    await update.message.reply_text("Принято. Введите вашу должность в компании (можно сокращенно).")
    return JOB_TITLE

async def get_job_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет должность и запрашивает фамилию владельца."""
    context.user_data['job_title'] = update.message.text
    await update.message.reply_text("Спасибо. Теперь введите Фамилию владельца карты.")
    return OWNER_LAST_NAME

async def get_owner_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет фамилию и запрашивает имя владельца."""
    context.user_data['owner_last_name'] = update.message.text
    await update.message.reply_text("А теперь Имя владельца карты.")
    return OWNER_FIRST_NAME

async def get_owner_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет имя и запрашивает причину выдачи."""
    context.user_data['owner_first_name'] = update.message.text
    await update.message.reply_text("Укажите причину выдачи карты (бартер/скидка).")
    return REASON

async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет причину и предлагает выбрать тип карты."""
    context.user_data['reason'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Бартер", callback_data="Бартер")],
        [InlineKeyboardButton("Скидка", callback_data="Скидка")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Какую карту регистрируем?", reply_markup=reply_markup)
    return CARD_TYPE

async def get_card_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет тип карты и запрашивает номер."""
    query = update.callback_query
    await query.answer()
    context.user_data['card_type'] = query.data
    await query.edit_message_text(text=f"Выбрано: {query.data}.\n\n"
                                        "Теперь введите номер карты (он же номер телефона, через 8).")
    return CARD_NUMBER

async def get_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет и сохраняет номер, запрашивает статью пополнения."""
    number = update.message.text
    if not (number.startswith('8') and number[1:].isdigit() and len(number) == 11):
        await update.message.reply_text("Неверный формат номера. Номер должен начинаться с 8 и содержать 11 цифр. Например: 89991234567")
        return CARD_NUMBER

    context.user_data['card_number'] = number
    keyboard = [
        [InlineKeyboardButton("АРТ", callback_data="АРТ"), InlineKeyboardButton("МАРКЕТ", callback_data="МАРКЕТ")],
        [InlineKeyboardButton("Операционный блок", callback_data="Операционный блок")],
        [InlineKeyboardButton("СКИДКА", callback_data="СКИДКА"), InlineKeyboardButton("Сертификат", callback_data="Сертификат")],
        [InlineKeyboardButton("Учредители", callback_data="Учредители")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите статью пополнения карты:", reply_markup=reply_markup)
    return CATEGORY

async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет категорию и запрашивает сумму/процент."""
    query = update.callback_query
    await query.answer()
    context.user_data['category'] = query.data

    card_type = context.user_data.get('card_type')
    if card_type == "Бартер":
        prompt = "Введите сумму бартера (только цифры):"
    elif card_type == "Скидка":
        prompt = "Введите процент скидки (только цифры, например, 15):"
    else:
        prompt = "Введите сумму или процент:"

    await query.edit_message_text(text=f"Выбрана статья: {query.data}.\n\n{prompt}")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет сумму и запрашивает периодичность."""
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
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите периодичность:", reply_markup=reply_markup)
    return FREQUENCY

async def get_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет периодичность и запрашивает комментарий."""
    query = update.callback_query
    await query.answer()
    context.user_data['frequency'] = query.data
    await query.edit_message_text(text=f"Выбрано: {query.data}.\n\n"
                                        "Последний шаг: введите комментарий (например, к какому бару привязка).")
    return COMMENT

def format_summary(data: dict) -> str:
    """Форматирует собранные данные для проверки (используя HTML для надежности)."""
    owner_full_name = f"{data.get('owner_last_name', '')} {data.get('owner_first_name', '')}".strip()

    card_type = data.get('card_type')
    amount_label = "Скидка" if card_type == 'Скидка' else "Сумма"
    amount_value = f"{data.get('amount', '0')}{'%' if card_type == 'Скидка' else ' ₽'}"

    # Используем HTML-теги <b>...</b> для надежного форматирования
    summary = (
        "Пожалуйста, проверьте данные перед сохранением.\n\n"
        "--- \n"
        "<b>Инициатор</b>\n"
        f"👤 ФИО: {data.get('fio_initiator', '-')}\n"
        f"📧 Почта: {data.get('email', '-')}\n"
        f"🏢 Должность: {data.get('job_title', '-')}\n"
        "--- \n"
        "<b>Карта лояльности</b>\n"
        f"💳 Владелец: {owner_full_name}\n"
        f"📞 Номер: {data.get('card_number', '-')}\n"
        f"✨ Тип: {card_type}\n"
        f"💰 <b>{amount_label}:</b> {amount_value}\n"
        f"📈 Статья: {data.get('category', '-')}\n"
        f"🔄 Периодичность: {data.get('frequency', '-')}\n"
        f"💬 Комментарий: {data.get('comment', '-')}\n"
        "--- \n\n"
        "Все верно?"
    )
    return summary

async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет комментарий и показывает все данные для подтверждения."""
    context.user_data['comment'] = update.message.text

    summary = format_summary(context.user_data)

    keyboard = [
        [InlineKeyboardButton("✅ Да, все верно", callback_data="submit")],
        [InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Используем ParseMode.HTML для отправки сообщения
    await update.message.reply_text(summary, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Записывает данные в таблицу и завершает диалог."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(text="Сохраняю данные...")

    success = write_to_sheet(context.user_data)

    if success:
        await query.edit_message_text(text="✅ Готово! Данные успешно записаны в таблицу.")
    else:
        await query.edit_message_text(text="❌ Произошла ошибка при записи в таблицу. Пожалуйста, свяжитесь с администратором.")

    context.user_data.clear()
    return ConversationHandler.END

async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает 'Нет' на шаге подтверждения и начинает диалог заново."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Хорошо, давайте начнем сначала.")
    return await start(query.message, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет и завершает диалог."""
    await update.message.reply_text(
        "Действие отменено. Для начала заново введите /start."
    )
    context.user_data.clear()
    return ConversationHandler.END


# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА БОТА ---

def main() -> None:
    """Основная функция для запуска бота."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Не найден токен TELEGRAM_BOT_TOKEN. Проверьте переменные окружения.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
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
