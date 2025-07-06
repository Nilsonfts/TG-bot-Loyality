# -*- coding: utf-8 -*-

import logging
import re
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

import g_sheets
import navigation_handlers
from constants import (
    REGISTER_CONTACT, REGISTER_FIO, REGISTER_EMAIL, REGISTER_JOB_TITLE,
    OWNER_LAST_NAME, OWNER_FIRST_NAME, REASON, CARD_TYPE, CARD_NUMBER, CATEGORY,
    AMOUNT, FREQUENCY, ISSUE_LOCATION, CONFIRMATION
)

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

async def start_form_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начинает диалог подачи заявки.
    Если пользователь не зарегистрирован, сначала запускает флоу регистрации.
    """
    context.user_data.clear()
    user_id = str(update.effective_user.id)

    # Проверяем, зарегистрирован ли пользователь
    is_registered = g_sheets.is_user_registered(user_id)

    if is_registered:
        # Если зарегистрирован, получаем его данные и начинаем подачу заявки
        initiator_data = g_sheets.get_initiator_data(user_id)
        if not initiator_data:
            await update.message.reply_text("Ошибка: не удалось найти ваши данные.\nПожалуйста, перезапустите бота командой /start.")
            return await navigation_handlers.cancel(update, context)

        context.user_data.update(initiator_data)
        await update.message.reply_text(
            f"Начинаем подачу новой заявки.\nВведите <b>Фамилию</b> владельца карты.",
            parse_mode=ParseMode.HTML
            # Убрали ReplyKeyboardRemove, чтобы клавиатура осталась
        )
        return OWNER_LAST_NAME
    else:
        # Если не зарегистрирован, начинаем с запроса контакта
        keyboard = [[KeyboardButton("📱 Поделиться контактом", request_contact=True)]]
        await update.message.reply_text(
            "Здравствуйте! Похоже, вы у нас впервые.\n"
            "Для подачи заявки нужно сначала пройти быструю регистрацию.\n\n"
            "Пожалуйста, поделитесь своим контактом.",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
        return REGISTER_CONTACT

# --- НОВЫЕ ОБРАБОТЧИКИ РЕГИСТРАЦИИ (ПЕРЕНЕСЕНЫ СЮДА) ---

async def handle_contact_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact, user = update.message.contact, update.effective_user
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

async def get_registration_job_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['initiator_job_title'] = update.message.text
    await update.message.reply_text(
        "🎉 <b>Регистрация завершена!</b>\n\nТеперь продолжим с заявкой.\nВведите <b>Фамилию</b> владельца карты.",
        parse_mode=ParseMode.HTML
    )
    return OWNER_LAST_NAME


# --- СТАРЫЕ ОБРАБОТЧИКИ ПОДАЧИ ЗАЯВКИ (ОСТАЮТСЯ ЗДЕСЬ) ---

async def get_owner_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['owner_last_name'] = update.message.text
    await update.message.reply_text("<b>Имя</b> владельца карты.", parse_mode=ParseMode.HTML)
    return OWNER_FIRST_NAME

# ... (все остальные get_... функции остаются без изменений) ...
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

async def get_issue_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['issue_location'] = update.message.text
    summary = format_summary(context.user_data)
    keyboard = [[InlineKeyboardButton("✅ Да, все верно", callback_data="submit"), InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финализирует и отправляет единую заявку в Google Sheets."""
    query = update.callback_query
    await query.answer(text="Отправляю заявку...", show_alert=False)
    
    user_id = str(query.from_user.id)
    # Теперь мы пишем "Заявка" в любом случае, так как отдельной регистрации нет
    context.user_data['status'] = 'Заявка'
    
    success = g_sheets.write_to_sheet(
        data=context.user_data,
        submission_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        tg_user_id=user_id
    )

    status_text = "\n\n<b>Статус:</b> ✅ Заявка успешно отправлена." if success else "\n\n<b>Статус:</b> ❌ Ошибка! Не удалось сохранить заявку."
    await query.edit_message_text(text=query.message.text_html + status_text, parse_mode=ParseMode.HTML, reply_markup=None)
    
    # Если запись успешна, кэшируем статус регистрации пользователя
    if success:
        g_sheets.cache_user_registration_status(user_id)

    context.user_data.clear()
    
    # Отправляем сообщение о возврате в главное меню, не удаляя старое
    await navigation_handlers.main_menu_command(update, context)

    return ConversationHandler.END

async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Перезапускает диалог подачи заявки с самого начала."""
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    # Заново вызываем главный обработчик, который проверит регистрацию
    return await start_form_conversation(update, context)
