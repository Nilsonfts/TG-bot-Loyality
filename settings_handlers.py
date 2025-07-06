# -*- coding: utf-8 -*-

import logging
import io
import csv
from datetime import datetime
from collections import Counter

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import g_sheets
import keyboards
from constants import MENU_TEXT_SUBMIT, MENU_TEXT_SEARCH, MENU_TEXT_SETTINGS, MENU_TEXT_MAIN_MENU, CARDS_PER_PAGE

logger = logging.getLogger(__name__)


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает меню настроек."""
    is_boss = (str(update.effective_user.id) == g_sheets.os.getenv("BOSS_ID"))
    keyboard = keyboards.get_settings_keyboard(is_boss)
    await update.message.reply_text("Меню настроек:", reply_markup=keyboard)


async def back_to_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Возвращает пользователя в меню настроек из подменю."""
    query = update.callback_query
    await query.answer()
    is_boss = (str(query.from_user.id) == g_sheets.os.getenv("BOSS_ID"))
    keyboard = keyboards.get_settings_keyboard(is_boss)
    await query.edit_message_text("Меню настроек:", reply_markup=keyboard)


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает справочную информацию."""
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
    """Собирает и отображает статистику."""
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
    """Формирует и отправляет CSV файл с заявками."""
    query = update.callback_query
    user_id = str(query.from_user.id)
    is_boss = (user_id == g_sheets.os.getenv("BOSS_ID"))
    await query.edit_message_text("📄 Формирую CSV файл...")
    cards_to_export = g_sheets.get_cards_from_sheet(user_id=None if is_boss else user_id)

    if not cards_to_export:
        await query.edit_message_text("Нет данных для экспорта.", reply_markup=keyboards.get_back_to_settings_keyboard())
        return

    output = io.StringIO()
    # Убедимся, что заголовки берутся из первой записи, если она есть
    if cards_to_export:
        writer = csv.DictWriter(output, fieldnames=cards_to_export[0].keys())
        writer.writeheader()
        writer.writerows(cards_to_export)
        output.seek(0)
        file_to_send = InputFile(output.getvalue().encode('utf-8-sig'), filename=f"export_{datetime.now().strftime('%Y-%m-%d')}.csv")
        await context.bot.send_document(chat_id=query.message.chat_id, document=file_to_send)
        await query.message.delete()


async def display_paginated_list(update: Update, context: ContextTypes.DEFAULT_TYPE, message_to_edit, page: int, data_key: str, list_title: str):
    """Отображает список элементов с кнопками пагинации."""
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

    await message_to_edit.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([row, [InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]),
        parse_mode=ParseMode.HTML
    )


async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки пагинации."""
    query = update.callback_query
    await query.answer()
    _, data_key, page_str = query.data.split('_')
    is_boss = (str(update.effective_user.id) == g_sheets.os.getenv("BOSS_ID"))
    list_title = "Все заявки" if is_boss else "Ваши поданные заявки"
    await display_paginated_list(update, context, message_to_edit=query.message, page=int(page_str), data_key=data_key, list_title=list_title)


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пустой колбэк для кнопок, которые не должны ничего делать (например, счетчик страниц)."""
    await update.callback_query.answer()


async def my_cards_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Загружает и отображает список заявок."""
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    is_boss = (user_id == g_sheets.os.getenv("BOSS_ID"))
    await query.edit_message_text("👑 Загружаю ВСЕ заявки..." if is_boss else "🔍 Загружаю ваши заявки...")

    all_cards = g_sheets.get_cards_from_sheet(user_id=None if is_boss else user_id)
    if not all_cards:
        await query.edit_message_text("🤷 Заявок не найдено.", reply_markup=keyboards.get_back_to_settings_keyboard())
        return

    data_key = 'my_cards'
    context.user_data[data_key] = all_cards
    list_title = "Все заявки" if is_boss else "Ваши поданные заявки"
    await display_paginated_list(update, context, message_to_edit=query.message, page=0, data_key=data_key, list_title=list_title)
