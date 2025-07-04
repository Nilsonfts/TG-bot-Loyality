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

def write_to_sheet(data: dict, submission_time: str, tg_handle: str):
    client = get_gspread_client()
    if not client:
        return False
    sheet_key = os.getenv("GOOGLE_SHEET_KEY")
    if not sheet_key:
        return False
    try:
        sheet = client.open_by_key(sheet_key).sheet1
        row_to_insert = [
            submission_time, tg_handle, data.get('email', ''), data.get('fio_initiator', ''),
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


# --- НОВАЯ ЛОГИКА ДИАЛОГА ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начинает диалог. Проверяет, есть ли сохраненные данные об инициаторе.
    """
    # Проверяем, есть ли сохраненные данные об инициаторе в user_data
    if context.user_data.get('initiator_fio'):
        fio = context.user_data['initiator_fio']
        email = context.user_data['initiator_email']
        job = context.user_data['initiator_job_title']

        text = (
            f"Здравствуйте! Найдена сохраненная информация о вас:\n\n"
            f"👤 **ФИО:** {fio}\n"
            f"📧 **Почта:** {email}\n"
            f"🏢 **Должность:** {job}\n\n"
            f"Использовать эти данные для новой заявки?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Да, использовать", callback_data="reuse_data")],
            [InlineKeyboardButton("✏️ Ввести заново", callback_data="enter_new_data")],
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return REUSE_DATA
    else:
        await update.message.reply_text(
            "Здравствуйте! Начинаем процесс регистрации карты лояльности.\n\n"
            "Пожалуйста, введите вашу рабочую электронную почту."
        )
        return EMAIL

async def handle_reuse_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор пользователя: использовать старые данные или ввести новые."""
    query = update.callback_query
    await query.answer()

    if query.data == 'reuse_data':
        # Копируем сохраненные данные в текущую форму
        context.user_data['email'] = context.user_data['initiator_email']
        context.user_data['fio_initiator'] = context.user_data['initiator_fio']
        context.user_data['job_title'] = context.user_data['initiator_job_title']

        await query.edit_message_text("Отлично! Данные инициатора заполнены.")
        await query.message.reply_text("Теперь введите **Фамилию** владельца карты.")
        return OWNER_LAST_NAME
    else: # enter_new_data
        await query.edit_message_text("Хорошо, давайте введем данные заново.")
        await query.message.reply_text("Пожалуйста, введите вашу рабочую электронную почту.")
        return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text("Формат почты неверный. Пожалуйста, попробуйте еще раз.")
        return EMAIL

    context.user_data['email'] = email
    context.user_data['initiator_email'] = email # Сохраняем для будущего использования
    await update.message.reply_text("Отлично! Теперь введите ваше ФИО (полностью).")
    return FIO_INITIATOR

async def get_fio_initiator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    fio = update.message.text
    context.user_data['fio_initiator'] = fio
    context.user_data['initiator_fio'] = fio # Сохраняем для будущего использования
    await update.message.reply_text("Принято. Введите вашу должность в компании (можно сокращенно).")
    return JOB_TITLE

async def get_job_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    job = update.message.text
    context.user_data['job_title'] = job
    context.user_data['initiator_job_title'] = job # Сохраняем для будущего использования
    await update.message.reply_text("Спасибо. Теперь введите **Фамилию** владельца карты.")
    return OWNER_LAST_NAME

# --- Остальные шаги диалога (без изменений) ---

async def get_owner_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['owner_last_name'] = update.message.text
    await update.message.reply_text("А теперь **Имя** владельца карты.")
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
        await update.message.reply_text("Неверный формат. Номер должен начинаться с 8 и содержать 11 цифр. Например: 89991234567")
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
    prompt = "Введите сумму бартера (только цифры):" if card_type == "Бартер" else "Введите процент скидки (только цифры, например, 15):"
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
    await query.edit_message_text(text=f"Выбрано: {query.data}.\n\nПоследний шаг: введите комментарий (например, к какому бару привязка).")
    return COMMENT

def format_summary(data: dict) -> str:
    owner_full_name = f"{data.get('owner_last_name', '')} {data.get('owner_first_name', '')}".strip()
    card_type = data.get('card_type')
    amount_label = "Скидка" if card_type == 'Скидка' else "Сумма"
    amount_value = f"{data.get('amount', '0')}{'%' if card_type == 'Скидка' else ' ₽'}"
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
    context.user_data['comment'] = update.message.text
    summary = format_summary(context.user_data)
    keyboard = [[InlineKeyboardButton("✅ Да, все верно", callback_data="submit"), InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Сохраняю данные...")
    user = query.from_user
    tg_handle = f"@{user.username}" if user.username else f"ID: {user.id}"
    submission_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    success = write_to_sheet(context.user_data, submission_time, tg_handle)
    if success:
        await query.edit_message_text(text="✅ Готово! Данные успешно записаны в таблицу.")
    else:
        await query.edit_message_text(text="❌ Произошла ошибка при записи в таблицу.")
    keyboard = [["Подать новую заявку"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await context.bot.send_message(chat_id=query.message.chat_id, text="Чтобы подать еще одну заявку, нажмите на кнопку ниже 👇", reply_markup=reply_markup)
    
    # Очищаем только данные формы, оставляя данные инициатора
    form_keys = ['owner_last_name', 'owner_first_name', 'reason', 'card_type', 'card_number', 
                 'category', 'amount', 'frequency', 'comment', 'email', 'fio_initiator', 'job_title']
    for key in form_keys:
        if key in context.user_data:
            del context.user_data[key]
            
    return ConversationHandler.END

async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Хорошо, давайте начнем сначала.")
    return await start(query.message, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено.")
    context.user_data.clear() # Полная очистка при отмене
    return ConversationHandler.END


# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА БОТА ---

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Не найден токен TELEGRAM_BOT_TOKEN.")
        return

    # Убрали PicklePersistence
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
        # Убрали persistent=True и name, так как они требуют PicklePersistence
    )

    application.add_handler(conv_handler)
    logger.info("Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()
