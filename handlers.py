# -*- coding: utf-8 -*-

"""
This file contains all the handlers for commands, messages, and callbacks.
"""

import logging
import re
import io
import csv
from datetime import datetime
from collections import Counter

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
    KeyboardButton, ReplyKeyboardRemove, InputFile
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

import g_sheets
import keyboards
from constants import (
    MENU_TEXT_SUBMIT, MENU_TEXT_SEARCH, MENU_TEXT_SETTINGS, MENU_TEXT_MAIN_MENU,
    CARDS_PER_PAGE, REGISTER_CONTACT, REGISTER_FIO, REGISTER_EMAIL,
    REGISTER_JOB_TITLE, OWNER_LAST_NAME, OWNER_FIRST_NAME, REASON, CARD_TYPE,
    CARD_NUMBER, CATEGORY, AMOUNT, FREQUENCY, ISSUE_LOCATION, CONFIRMATION,
    SEARCH_CHOOSE_FIELD, AWAIT_SEARCH_QUERY
)

logger = logging.getLogger(__name__)

# --- UTILITY HANDLERS ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels any active conversation and shows the main menu."""
    await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
    await start_command(update, context)
    return ConversationHandler.END


# --- NAVIGATION HANDLERS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point. Checks registration and shows the correct main menu."""
    is_registered = g_sheets.is_user_registered(str(update.effective_user.id))
    keyboard = keyboards.get_main_menu_keyboard(is_registered)
    if is_registered:
        await update.message.reply_text("Вы в главном меню:", reply_markup=keyboard)
    else:
        await update.message.reply_text("Здравствуйте! Для начала работы, пройдите регистрацию.", reply_markup=keyboard)

async def main_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /start to show the main menu."""
    await start_command(update, context)

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the settings menu."""
    is_boss = (str(update.effective_user.id) == g_sheets.os.getenv("BOSS_ID"))
    keyboard = keyboards.get_settings_keyboard(is_boss)
    await update.message.reply_text("Меню настроек:", reply_markup=keyboard)


# --- REGISTRATION CONVERSATION HANDLERS ---
async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the registration flow."""
    context.user_data.clear()
    keyboard = [[KeyboardButton("📱 Поделиться контактом", request_contact=True)]]
    await update.message.reply_text(
        "Начинаем регистрацию. Пожалуйста, поделитесь своим контактом.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return REGISTER_CONTACT

async def handle_contact_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles receiving the user's contact."""
    contact, user = update.message.contact, update.effective_user
    if contact.user_id != user.id:
        await update.message.reply_text("Пожалуйста, поделитесь своим собственным контактом.", reply_markup=ReplyKeyboardRemove())
        return await cancel(update, context)

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

async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finishes registration, saves data, and shows the main menu."""
    context.user_data['initiator_job_title'] = update.message.text
    success = g_sheets.write_to_sheet(
        data=context.user_data,
        submission_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        tg_user_id=str(update.effective_user.id)
    )
    if success:
        await update.message.reply_text("🎉 <b>Регистрация успешно завершена!</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ Произошла ошибка при сохранении регистрации. Пожалуйста, попробуйте снова или свяжитесь с администратором.")
    context.user_data.clear()
    await main_menu_command(update, context)
    return ConversationHandler.END


# --- SETTINGS & FEATURES CALLBACK HANDLERS ---
async def back_to_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    is_boss = (str(query.from_user.id) == g_sheets.os.getenv("BOSS_ID"))
    keyboard = keyboards.get_settings_keyboard(is_boss)
    await query.edit_message_text("Меню настроек:", reply_markup=keyboard)

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    help_text = (
        "<b>Справка по боту</b>\n\n"
        f"▫️ <b>{MENU_TEXT_SUBMIT}</b> - запуск анкеты для новой карты.\n"
        f"▫️ <b>{MENU_TEXT_SETTINGS}</b> - доступ к заявкам, статистике и экспорту.\n"
        f"▫️ <b>{MENU_TEXT_SEARCH}</b> - поиск по существующим заявкам.\n"
        f"▫️ <b>{MENU_TEXT_MAIN_MENU}</b> - возврат в главное меню и отмена любого действия."
    )
    await query.edit_message_text(help_text, reply_markup=keyboards.get_back_to_settings_keyboard(), parse_mode=ParseMode.HTML)

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    is_boss = (user_id == g_sheets.os.getenv("BOSS_ID"))
    await query.edit_message_text("📊 Собираю статистику...")
    cards_data = g_sheets.get_cards_from_sheet(user_id=None if is_boss else user_id)
    
    if not cards_data:
        await query.edit_message_text("Нет данных для статистики.", reply_markup=keyboards.get_back_to_settings_keyboard())
        return

    total_cards = len(cards_data)
    barter_count = sum(1 for c in cards_data if c.get('Какую карту регистрируем?') == 'Бартер')
    category_counter = Counter(c.get('Статья пополнения карт') for c in cards_data if c.get('Статья пополнения карт'))
    most_common_category = category_counter.most_common(1)[0][0] if category_counter else "–"
    
    text = (f"<b>📊 Статистика</b>\n\n"
            f"🗂️ {'Всего заявок в системе' if is_boss else 'Подано вами заявок'}: <b>{total_cards}</b>\n"
            f"    - Карт 'Бартер': <code>{barter_count}</code>\n"
            f"    - Карт 'Скидка': <code>{total_cards - barter_count}</code>\n\n"
            f"📈 Самая частая статья: <b>{most_common_category}</b>")
    await query.edit_message_text(text, reply_markup=keyboards.get_back_to_settings_keyboard(), parse_mode=ParseMode.HTML)

async def export_csv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    is_boss = (user_id == g_sheets.os.getenv("BOSS_ID"))
    await query.edit_message_text("📄 Формирую CSV файл...")
    cards_to_export = g_sheets.get_cards_from_sheet(user_id=None if is_boss else user_id)

    if not cards_to_export:
        await query.edit_message_text("Нет данных для экспорта.", reply_markup=keyboards.get_back_to_settings_keyboard())
        return

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=cards_to_export[0].keys())
    writer.writeheader()
    writer.writerows(cards_to_export)
    output.seek(0)
    
    file_to_send = InputFile(output.getvalue().encode('utf-8-sig'), filename=f"export_{datetime.now().strftime('%Y-%m-%d')}.csv")
    await context.bot.send_document(chat_id=query.message.chat_id, document=file_to_send)
    await query.message.delete()

# --- PAGINATION & SEARCH HANDLERS ---

async def display_paginated_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, data_key: str, list_title: str):
    """Generic function to display a paginated list of items."""
    message_to_edit = update.callback_query.message
    all_items = context.user_data.get(data_key, [])
    
    if not all_items:
        await message_to_edit.edit_text("🤷 Ничего не найдено.", reply_markup=keyboards.get_back_to_settings_keyboard())
        return

    start_index = page * CARDS_PER_PAGE
    end_index = start_index + CARDS_PER_PAGE
    items_on_page = all_items[start_index:end_index]
    total_pages = (len(all_items) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE

    text = f"<b>{list_title} (Стр. {page + 1}/{total_pages}):</b>\n\n"
    for card in items_on_page:
        owner_name = f"{card.get('Имя владельца карты','')} {card.get('Фамилия Владельца','-')}".strip()
        amount_text = ""
        if card.get('Сумма бартера или % скидки'):
            card_type_str = card.get('Какую карту регистрируем?')
            amount_text = f"💰 {'Скидка' if card_type_str == 'Скидка' else 'Бартер'}: {card.get('Сумма бартера или % скидки')}{'%' if card_type_str == 'Скидка' else ' ₽'}\n"
        
        text += (f"👤 <b>Владелец:</b> {owner_name}\n📞 Номер: {card.get('Номер карты', '-')}\n{amount_text}"
                 f"<b>Статус:</b> <code>{card.get('Статус Согласования', '–')}</code>\n📅 {card.get('Отметка времени', '-')}\n")
        
        if str(update.effective_user.id) == g_sheets.os.getenv("BOSS_ID"):
            text += f"🤵‍♂️ <b>Инициатор:</b> {card.get('ФИО Инициатора', '-')} ({card.get('Тег Telegram', '-')})\n"
        text += "--------------------\n"

    row = []
    if page > 0: row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"paginate_{data_key}_{page - 1}"))
    row.append(InlineKeyboardButton(f" {page + 1}/{total_pages} ", callback_data="noop"))
    if end_index < len(all_items): row.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"paginate_{data_key}_{page + 1}"))
    
    await message_to_edit.edit_text(text, reply_markup=InlineKeyboardMarkup([row, [InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]), parse_mode=ParseMode.HTML)

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, data_key, page_str = query.data.split('_')
    is_boss = (str(update.effective_user.id) == g_sheets.os.getenv("BOSS_ID"))
    list_title = "Все заявки" if is_boss else "Ваши поданные заявки"
    await display_paginated_list(update, context, page=int(page_str), data_key=data_key, list_title=list_title)

async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

async def my_cards_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    is_boss = (user_id == g_sheets.os.getenv("BOSS_ID"))
    await query.edit_message_text("👑 Загружаю ВСЕ заявки..." if is_boss else "🔍 Загружаю ваши заявки...")
    
    all_cards = g_sheets.get_cards_from_sheet(user_id=None if is_boss else user_id)
    if not all_cards:
        await query.edit_message_text("🤷 Заявок не найдено.", reply_markup=keyboards.get_back_to_settings_keyboard())
        return

    context.user_data['my_cards'] = all_cards
    list_title = "Все заявки" if is_boss else "Ваши поданные заявки"
    await display_paginated_list(update, context, page=0, data_key='my_cards', list_title=list_title)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("По ФИО владельца", callback_data="search_by_name")],
        [InlineKeyboardButton("По номеру карты", callback_data="search_by_phone")]
    ]
    await update.message.reply_text("Выберите критерий поиска:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SEARCH_CHOOSE_FIELD

async def search_field_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['search_field'] = query.data
    await query.edit_message_text("Введите поисковый запрос:")
    return AWAIT_SEARCH_QUERY

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    is_boss = (user_id == g_sheets.os.getenv("BOSS_ID"))
    search_query = update.message.text.lower().strip()
    loading_msg = await update.message.reply_text("🔍 Выполняю поиск...")

    all_cards = g_sheets.get_cards_from_sheet(user_id=None if is_boss else user_id)
    search_field = context.user_data.get('search_field')
    
    if search_field == 'search_by_name':
        results = [c for c in all_cards if search_query in c.get('Имя владельца карты', '').lower() or search_query in c.get('Фамилия Владельца', '').lower()]
    else: # search_by_phone
        results = [c for c in all_cards if search_query in str(c.get('Номер карты', ''))]
    
    context.user_data['search_results'] = results
    await loading_msg.delete()
    
    # Mock an update to reuse the display function
    class MockUpdate:
        def __init__(self, msg, user):
            self.callback_query = type('MockCQ', (), {'message': msg})()
            self.effective_user = user
            
    await display_paginated_list(MockUpdate(update.message, update.effective_user), context, page=0, data_key='search_results', list_title="Результаты поиска")
    return ConversationHandler.END


# --- APPLICATION FORM CONVERSATION HANDLERS ---
async def start_form_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the application form for a registered user."""
    context.user_data.clear()
    initiator_data = g_sheets.find_initiator_in_sheet(str(update.effective_user.id))
    if not initiator_data:
        await update.message.reply_text("Ошибка: не удалось найти ваши регистрационные данные. Пожалуйста, перезапустите бота командой /start.")
        return await cancel(update, context)

    context.user_data.update(initiator_data)
    await update.message.reply_text(
        f"Начинаем подачу новой заявки.\nВведите <b>Фамилию</b> владельца карты.",
        parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove()
    )
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

def format_summary(data: dict) -> str:
    """Formats the final summary of the application."""
    owner = f"{data.get('owner_first_name', '')} {data.get('owner_last_name', '')}".strip()
    card_type = data.get('card_type')
    amount_label = 'Скидка' if card_type == 'Скидка' else 'Сумма'
    amount_unit = '%' if card_type == 'Скидка' else ' ₽'
    return (f"<b>Пожалуйста, проверьте итоговую заявку:</b>\n\n"
            f"--- <b>Инициатор</b> ---\n"
            f"👤 ФИО: {data.get('initiator_fio', '-')}\n"
            f"--- <b>Карта</b> ---\n"
            f"💳 Владелец: {owner}\n"
            f"📞 Номер: {data.get('card_number', '-')}\n"
            f"✨ Тип: {card_type}\n"
            f"💰 {amount_label}: {data.get('amount', '0')}{amount_unit}\n"
            f"📈 Статья: {data.get('category', '-')}\n"
            f"🔄 Периодичность: {data.get('frequency', '-')}\n"
            f"📍 Город/Бар: {data.get('issue_location', '-')}\n\n"
            "<i>Все верно?</i>")

async def get_issue_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['issue_location'] = update.message.text
    summary = format_summary(context.user_data)
    keyboard = [[InlineKeyboardButton("✅ Да, все верно", callback_data="submit"), InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Final submission handler for an application."""
    query = update.callback_query
    await query.answer(text="Отправляю заявку...", show_alert=False)
    success = g_sheets.write_to_sheet(context.user_data, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), str(query.from_user.id))
    status_text = "\n\n<b>Статус:</b> ✅ Заявка успешно отправлена." if success else "\n\n<b>Статус:</b> ❌ Ошибка! Не удалось сохранить заявку."
    await query.edit_message_text(text=query.message.text_html + status_text, parse_mode=ParseMode.HTML, reply_markup=None)
    context.user_data.clear()
    await main_menu_command(query, context)
    return ConversationHandler.END

async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Restarts the application form from the beginning."""
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    return await start_form_conversation(query, context)
