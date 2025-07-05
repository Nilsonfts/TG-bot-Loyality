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
    REUSE_DATA, EMAIL, FIO_INITIATOR, JOB_TITLE, OWNER_LAST_NAME, OWNER_FIRST_NAME,
    REASON, CARD_TYPE, CARD_NUMBER, CATEGORY, AMOUNT,
    FREQUENCY, COMMENT, CONFIRMATION,
    AWAIT_SEARCH_QUERY, INTERRUPT_CONFIRMATION
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

def get_all_user_cards_from_sheet(user_id: str) -> list:
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
                    "date": row[0], "owner_first_name": row[6], "owner_last_name": row[5],
                    "card_number": row[9], "status_q": row[16] or "–", "status_s": row[18] or "–"
                }
                cards.append(card_info)
        return list(reversed(cards))
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

# --- УТИЛИТАРНЫЕ ФУНКЦИИ ---
def add_message_to_delete(context: ContextTypes.DEFAULT_TYPE, message_id: int):
    context.user_data.setdefault('messages_to_delete', []).append(message_id)

async def delete_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    for msg_id in context.user_data.get('messages_to_delete', []):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение {msg_id}: {e}")
    context.user_data['messages_to_delete'] = []

# --- ГЛАВНОЕ МЕНЮ И СИСТЕМА НАВИГАЦИИ ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [["✍️ Подать заявку"], ["🗂️ Мои Карты", "🔍 Поиск", "❓ Помощь"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы в главном меню. Выберите действие:", reply_markup=reply_markup)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = ("<b>Справка по боту</b>\n\n"
                 "▫️ <b>Подать заявку</b> - запуск пошаговой анкеты.\n"
                 "▫️ <b>Мои Карты</b> - просмотр всех поданных вами заявок.\n"
                 "▫️ <b>Поиск</b> - поиск по вашим заявкам.\n\n"
                 "Если вы начали заполнять заявку, но нажали другую кнопку меню, бот предложит подтвердить отмену.")
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


# --- СИСТЕМА ПАГИНАЦИИ ---
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


# --- ФУНКЦИИ КОМАНД МЕНЮ ---
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


# --- ДИАЛОГ ПОДАЧИ ЗАЯВКИ ---
async def start_form_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat = update.effective_chat
    context.user_data['messages_to_delete'] = []
    initiator_data = context.user_data.get('initiator_fio') and {"fio": context.user_data.get('initiator_fio'), "email": context.user_data.get('initiator_email'), "job_title": context.user_data.get('initiator_job_title')}
    if initiator_data:
        text = (f"Начинаем новую заявку. Используем сохраненные данные:\n\n"
                f"👤 <b>ФИО:</b> {initiator_data['fio']}\n\n"
                f"Продолжить?")
        keyboard = [[InlineKeyboardButton("✅ Да, продолжить", callback_data="reuse_data"), InlineKeyboardButton("✏️ Ввести заново", callback_data="enter_new_data")]]
        msg = await chat.send_message(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        add_message_to_delete(context, msg.message_id)
        return REUSE_DATA
    else:
        msg = await chat.send_message("Начинаем процесс регистрации.\n\nВведите вашу рабочую почту.")
        add_message_to_delete(context, msg.message_id)
        return EMAIL

async def handle_reuse_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    if query.data == 'reuse_data':
        context.user_data['email'] = context.user_data.get('initiator_email')
        context.user_data['fio_initiator'] = context.user_data.get('initiator_fio')
        context.user_data['job_title'] = context.user_data.get('initiator_job_title')
        msg = await query.message.reply_text("Данные инициатора заполнены.\n\nВведите <b>Фамилию</b> владельца карты.", parse_mode=ParseMode.HTML)
        add_message_to_delete(context, msg.message_id)
        return OWNER_LAST_NAME
    else: # enter_new_data
        msg = await query.message.reply_text("Хорошо, введите данные заново.\n\nВаша рабочая почта?")
        add_message_to_delete(context, msg.message_id)
        return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    context.user_data['email'] = update.message.text
    context.user_data['initiator_email'] = update.message.text
    msg = await update.message.reply_text("Ваше ФИО (полностью)?")
    add_message_to_delete(context, msg.message_id)
    return FIO_INITIATOR

# ... (и так далее для всех функций get_... )
async def get_fio_initiator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    context.user_data['fio_initiator'] = update.message.text
    context.user_data['initiator_fio'] = update.message.text
    msg = await update.message.reply_text("Ваша должность?")
    add_message_to_delete(context, msg.message_id)
    return JOB_TITLE

async def get_job_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    context.user_data['job_title'] = update.message.text
    context.user_data['initiator_job_title'] = update.message.text
    msg = await update.message.reply_text("Спасибо. Теперь введите <b>Фамилию</b> владельца карты.", parse_mode=ParseMode.HTML)
    add_message_to_delete(context, msg.message_id)
    return OWNER_LAST_NAME

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
    await query.message.edit_text(f"Выбрано: {query.data}.\n\nНомер карты (телефон через 8)?")
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
    await query.message.edit_text(f"Статья: {query.data}.\n\n{prompt}")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    text = update.message.text
    if not text.isdigit():
        msg = await update.message.reply_text("Нужно только число.")
        add_message_to_delete(context, msg.message_id)
        return AMOUNT
    context.user_data['amount'] = text
    keyboard = [[InlineKeyboardButton("Разовая", callback_data="Разовая")], [InlineKeyboardButton("Дополнить к балансу", callback_data="Дополнить к балансу")], [InlineKeyboardButton("Замена номера карты", callback_data="Замена номера карты")]]
    msg = await update.message.reply_text("Периодичность?", reply_markup=InlineKeyboardMarkup(keyboard))
    add_message_to_delete(context, msg.message_id)
    return FREQUENCY

async def get_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['frequency'] = query.data
    await query.message.edit_text(f"Выбрано: {query.data}.\n\nКомментарий?")
    return COMMENT

def format_summary(data: dict) -> str:
    owner_full_name = f"{data.get('owner_first_name', '')} {data.get('owner_last_name', '')}".strip()
    return (
        "<b>Пожалуйста, проверьте итоговую заявку:</b>\n\n"
        "--- <b>Инициатор</b> ---\n"
        f"👤 <b>ФИО:</b> {data.get('fio_initiator', '-')}\n"
        f"📧 <b>Почта:</b> {data.get('email', '-')}\n"
        f"🏢 <b>Должность:</b> {data.get('job_title', '-')}\n\n"
        "--- <b>Карта лояльности</b> ---\n"
        f"💳 <b>Владелец:</b> {owner_full_name}\n"
        f"📞 <b>Номер:</b> {data.get('card_number', '-')}\n"
        f"   <i>(он же является номером телефона)</i>\n"
        f"✨ <b>Тип:</b> {data.get('card_type', '-')}\n"
        f"💰 <b>{ 'Скидка' if data.get('card_type') == 'Скидка' else 'Сумма' }:</b> {data.get('amount', '0')}{'%' if data.get('card_type') == 'Скидка' else ' ₽'}\n"
        f"📈 <b>Статья:</b> {data.get('category', '-')}\n"
        f"🔄 <b>Периодичность:</b> {data.get('frequency', '-')}\n"
        f"💬 <b>Комментарий:</b> {data.get('comment', '-')}\n\n"
        "<i>Все верно?</i>"
    )

async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_message_to_delete(context, update.message.message_id)
    context.user_data['comment'] = update.message.text
    summary = format_summary(context.user_data)
    keyboard = [[InlineKeyboardButton("✅ Да, все верно", callback_data="submit"), InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")]]
    msg = await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    add_message_to_delete(context, msg.message_id)
    return CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await delete_messages(context, update.effective_chat.id)
    user_id = str(query.from_user.id)
    # Добавляем небольшую паузу для Google Sheets
    await asyncio.sleep(2)
    success = write_to_sheet(context.user_data, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id)
    final_text = "✅ Готово! Заявка успешно записана." if success else "❌ Ошибка при записи в таблицу."
    # Вместо редактирования, отправляем новую итоговую карточку
    final_summary = format_summary(context.user_data)
    final_summary += f"\n\n<b>Статус:</b> { '✅ Успешно' if success else '❌ Ошибка' }"
    await context.bot.send_message(update.effective_chat.id, text=final_summary, parse_mode=ParseMode.HTML)
    await show_main_menu(update, context)
    context.user_data.clear()
    return ConversationHandler.END

async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await delete_messages(context, update.effective_chat.id)
    return await start_form_conversation(update, context)

# --- Функции отмены и прерывания диалогов ---
async def fallback_interrupt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Спрашивает подтверждение на отмену текущего действия."""
    command_text = update.message.text.lstrip('✍️🗂️🔍❓ ').strip()
    context.user_data['interrupt_command'] = command_text
    keyboard = [[
        InlineKeyboardButton("Да, прервать", callback_data="interrupt_yes"),
        InlineKeyboardButton("Нет, продолжить", callback_data="interrupt_no")
    ]]
    msg = await update.message.reply_text(f"Вы не закончили подачу заявки. Прервать и перейти в «{command_text}»?", reply_markup=InlineKeyboardMarkup(keyboard))
    add_message_to_delete(context, msg.message_id)
    return INTERRUPT_CONFIRMATION

async def handle_interrupt_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ответ на подтверждение прерывания."""
    query = update.callback_query
    await query.answer()
    await query.message.delete() # Удаляем сообщение с вопросом

    if query.data == "interrupt_yes":
        command = context.user_data.pop('interrupt_command', None)
        await delete_messages(context, update.effective_chat.id) # Очищаем старые сообщения анкеты
        
        if command == "Подать заявку":
            return await start_form_conversation(update, context)
        elif command == "Мои Карты":
            await my_cards_command(update, context)
        elif command == "Поиск":
            return await search_command(update, context)
        elif command == "Помощь":
            await show_help(update, context)
        return ConversationHandler.END
    else: # interrupt_no
        # Просто остаемся в том же состоянии, пользователь может продолжать ввод
        current_state = context.user_data.get(ConversationHandler.STATE)
        await query.message.reply_text("Хорошо, продолжаем. Жду ваш ответ.")
        return current_state

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено.")
    await show_main_menu(update, context)
    return ConversationHandler.END

# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА БОТА ---
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    form_filter = filters.Regex("^(✍️ )?Подать заявку$")
    cards_filter = filters.Regex("^(🗂️ )?Мои Карты$")
    search_filter = filters.Regex("^(🔍 )?Поиск$")
    help_filter = filters.Regex("^(❓ )?Помощь$")
    menu_filters = form_filter | cards_filter | search_filter | help_filter
    state_text_filter = filters.TEXT & ~filters.COMMAND & ~menu_filters

    form_conv = ConversationHandler(
        entry_points=[MessageHandler(form_filter, start_form_conversation)],
        states={
            REUSE_DATA: [CallbackQueryHandler(handle_reuse_choice)], EMAIL: [MessageHandler(state_text_filter, get_email)],
            FIO_INITIATOR: [MessageHandler(state_text_filter, get_fio_initiator)], JOB_TITLE: [MessageHandler(state_text_filter, get_job_title)],
            OWNER_LAST_NAME: [MessageHandler(state_text_filter, get_owner_last_name)], OWNER_FIRST_NAME: [MessageHandler(state_text_filter, get_owner_first_name)],
            REASON: [MessageHandler(state_text_filter, get_reason)], CARD_TYPE: [CallbackQueryHandler(get_card_type)],
            CARD_NUMBER: [MessageHandler(state_text_filter, get_card_number)], CATEGORY: [CallbackQueryHandler(get_category)],
            AMOUNT: [MessageHandler(state_text_filter, get_amount)], FREQUENCY: [CallbackQueryHandler(get_frequency)],
            COMMENT: [MessageHandler(state_text_filter, get_comment)],
            CONFIRMATION: [CallbackQueryHandler(submit, pattern="^submit$"), CallbackQueryHandler(restart_conversation, pattern="^restart$")],
            INTERRUPT_CONFIRMATION: [CallbackQueryHandler(handle_interrupt_confirmation)],
        },
        fallbacks=[MessageHandler(menu_filters, fallback_interrupt), CommandHandler("start", cancel)],
    )

    search_conv = ConversationHandler(
        entry_points=[MessageHandler(search_filter, search_command)],
        states={ AWAIT_SEARCH_QUERY: [MessageHandler(state_text_filter, perform_search)] },
        fallbacks=[MessageHandler(menu_filters & ~search_filter, fallback_interrupt), CommandHandler("start", cancel)],
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
