# -*- coding: utf-8 -*-

import logging
from datetime import datetime
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

import g_sheets
import navigation_handlers
from constants import States, SheetCols

logger = logging.getLogger(__name__)

def format_summary(data: dict) -> str:
    """Форматирует итоговое сообщение перед отправкой."""
    owner = f"{data.get('owner_first_name', '')} {data.get('owner_last_name', '')}".strip()
    card_type = data.get('card_type')
    amount_label = 'Скидка' if card_type == 'Скидка' else 'Сумма'
    amount_unit = '%' if card_type == 'Скидка' else ' ₽'
    return (f"<b>Пожалуйста, проверьте итоговую заявку:</b>\n\n"
            f"--- <b>Инициатор</b> ---\n"
            f"👤 ФИО: {data.get('initiator_fio', '-')}\n"
            f"📧 Почта: {data.get('initiator_email', '-')}\n"
            f"--- <b>Карта</b> ---\n"
            f"💳 Владелец: {owner}\n"
            f"📞 Номер: {data.get('card_number', '-')}\n"
            f"✨ Тип: {card_type}\n"
            f"💰 {amount_label}: {data.get('amount', '0')}{amount_unit}\n"
            f"📈 Статья: {data.get('category', '-')}\n"
            f"🔄 Периодичность: {data.get('frequency', '-')}\n"
            f"📍 Город/Бар: {data.get('issue_location', '-')}\n\n"
            "<i>Все верно?</i>")

async def start_form_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    """Начинает диалог подачи заявки для зарегистрированного пользователя."""
    context.user_data.clear()
    user_id = str(update.effective_user.id)

    initiator_data = g_sheets.get_initiator_data(user_id)
    if not initiator_data:
        await update.message.reply_text(
            "Ошибка: не удалось найти ваши данные. Возможно, вы не зарегистрированы.\n"
            "Пожалуйста, вернитесь в главное меню и выберите 'Регистрация'."
        )
        return await navigation_handlers.end_conversation_and_show_menu(update, context)

    context.user_data.update(initiator_data)
    await update.message.reply_text(
        "Начинаем подачу новой заявки.\nВведите <b>Фамилию</b> владельца карты.",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    return States.OWNER_LAST_NAME

async def get_owner_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    context.user_data['owner_last_name'] = update.message.text
    await update.message.reply_text("<b>Имя</b> владельца карты.", parse_mode=ParseMode.HTML)
    return States.OWNER_FIRST_NAME

async def get_owner_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    context.user_data['owner_first_name'] = update.message.text
    await update.message.reply_text("Причина выдачи?")
    return States.REASON

async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    context.user_data['reason'] = update.message.text
    keyboard = [[InlineKeyboardButton("Бартер", callback_data="Бартер"), InlineKeyboardButton("Скидка", callback_data="Скидка")]]
    await update.message.reply_text("Тип карты?", reply_markup=InlineKeyboardMarkup(keyboard))
    return States.CARD_TYPE

async def get_card_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    query = update.callback_query
    await query.answer()
    context.user_data['card_type'] = query.data
    await query.edit_message_text(f"Выбрано: {query.data}.\n\nНомер карты (телефон через 8)?")
    return States.CARD_NUMBER

async def get_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    number = update.message.text
    if not (number.startswith('8') and number.isdigit() and len(number) == 11):
        await update.message.reply_text("Неверный формат. Нужно 11 цифр, начиная с 8.")
        return States.CARD_NUMBER
    context.user_data['card_number'] = number
    keyboard = [[InlineKeyboardButton("АРТ", callback_data="АРТ"), InlineKeyboardButton("МАРКЕТ", callback_data="МАРКЕТ")], [InlineKeyboardButton("Операционный блок", callback_data="Операционный блок")], [InlineKeyboardButton("СКИДКА", callback_data="СКИДКА"), InlineKeyboardButton("Сертификат", callback_data="Сертификат")], [InlineKeyboardButton("Учредители", callback_data="Учредители")]]
    await update.message.reply_text("Статья пополнения?", reply_markup=InlineKeyboardMarkup(keyboard))
    return States.CATEGORY

async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    query = update.callback_query
    await query.answer()
    context.user_data['category'] = query.data
    prompt = "Сумма бартера (только число)?" if context.user_data['card_type'] == "Бартер" else "Процент скидки (только число)?"
    await query.edit_message_text(f"Статья: {query.data}.\n\n{prompt}")
    return States.AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    if not update.message.text.isdigit():
        await update.message.reply_text("Нужно ввести только число. Пожалуйста, попробуйте еще раз.")
        return States.AMOUNT
    context.user_data['amount'] = update.message.text
    keyboard = [[InlineKeyboardButton("Разовая", callback_data="Разовая")], [InlineKeyboardButton("Дополнить к балансу", callback_data="Дополнить к балансу")], [InlineKeyboardButton("Замена номера карты", callback_data="Замена номера карты")]]
    await update.message.reply_text("Периодичность?", reply_markup=InlineKeyboardMarkup(keyboard))
    return States.FREQUENCY

async def get_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    query = update.callback_query
    await query.answer()
    context.user_data['frequency'] = query.data
    await query.edit_message_text(f"Выбрано: {query.data}.\n\n<b>Город/Бар выдачи?</b>", parse_mode=ParseMode.HTML)
    return States.ISSUE_LOCATION

async def get_issue_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    context.user_data['issue_location'] = update.message.text
    summary = format_summary(context.user_data)
    keyboard = [[InlineKeyboardButton("✅ Да, все верно", callback_data="submit"), InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return States.CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финализирует и отправляет заявку, используя универсальную функцию записи."""
    query = update.callback_query
    await query.answer(text="Отправляю заявку...", show_alert=False)
    
    user_id = str(query.from_user.id)
    
    data_to_write = context.user_data.copy()
    data_to_write['submission_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data_to_write['tg_user_id'] = user_id
    data_to_write['status'] = 'Заявка'

    success = g_sheets.write_row(data_to_write)

    if success:
        status_text = "\n\n<b>Статус:</b> ✅ Заявка успешно отправлена."
    else:
        status_text = "\n\n<b>Статус:</b> ❌ Ошибка! Не удалось сохранить заявку. Обратитесь к администратору."
        
    await query.edit_message_text(text=query.message.text_html + status_text, parse_mode=ParseMode.HTML, reply_markup=None)
    
    context.user_data.clear()
    await navigation_handlers.main_menu_command(update, context)

    return ConversationHandler.END

# --- ИЗМЕНЕНИЕ ---
# Полностью переписанная функция для корректного перезапуска диалога
async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    """Корректно перезапускает диалог подачи заявки с самого начала."""
    query = update.callback_query
    await query.answer()
    
    # Редактируем сообщение, чтобы пользователь видел, что его действие принято
    await query.edit_message_text(text="Начинаем заполнение анкеты заново...")

    # Сохраняем данные об инициаторе, чтобы не запрашивать их снова
    initiator_keys = ['initiator_fio', 'initiator_email', 'initiator_phone', 'initiator_username', 'initiator_job_title']
    initiator_data = {key: context.user_data.get(key) for key in initiator_keys}
    
    # Очищаем все данные, которые вводились в анкете
    context.user_data.clear()
    # И возвращаем данные об инициаторе обратно
    context.user_data.update(initiator_data)

    # Отправляем первое сообщение анкеты как новое сообщение
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Начинаем подачу новой заявки.\nВведите <b>Фамилию</b> владельца карты.",
        parse_mode=ParseMode.HTML
    )
    
    # Возвращаемся в первое состояние анкеты
    return States.OWNER_LAST_NAME
