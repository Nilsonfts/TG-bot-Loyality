# -*- coding: utf-8 -*-

import logging
import io
import csv
import os
import asyncio
from datetime import datetime
from collections import Counter

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import g_sheets
import keyboards
from constants import (
    MENU_TEXT_SUBMIT, MENU_TEXT_SEARCH, MENU_TEXT_SETTINGS, 
    MENU_TEXT_MAIN_MENU, CARDS_PER_PAGE, SheetCols
)

logger = logging.getLogger(__name__)


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает меню настроек."""
    is_boss = (str(update.effective_user.id) == os.getenv("BOSS_ID"))
    keyboard = keyboards.get_settings_keyboard(is_boss)
    await update.message.reply_text("Меню настроек:", reply_markup=keyboard)


async def back_to_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Возвращает пользователя в меню настроек из подменю."""
    query = update.callback_query
    await query.answer()
    is_boss = (str(query.from_user.id) == os.getenv("BOSS_ID"))
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

async def my_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает регистрационные данные пользователя."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    user_data = await asyncio.to_thread(g_sheets.get_initiator_data, user_id)
    
    if not user_data:
        await query.edit_message_text("Не удалось найти ваши данные.", reply_markup=keyboards.get_back_to_settings_keyboard())
        return

    profile_text = (
        "<b>👤 Ваш профиль</b>\n\n"
        f"<b>ФИО:</b> {user_data.get('initiator_fio', '-')}\n"
        f"<b>Должность:</b> {user_data.get('initiator_job_title', '-')}\n"
        f"<b>Почта:</b> {user_data.get('initiator_email', '-')}\n"
        f"<b>Телефон:</b> {user_data.get('initiator_phone', '-')}\n\n"
        "<i>Эти данные используются при подаче заявок. Для их изменения обратитесь к администратору.</i>"
    )
    
    await query.edit_message_text(profile_text, parse_mode=ParseMode.HTML, reply_markup=keyboards.get_back_to_settings_keyboard())


async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Собирает и отображает статистику."""
    query = update.callback_query
    user_id = str(query.from_user.id)
    is_boss = (user_id == os.getenv("BOSS_ID"))
    await query.edit_message_text("📊 Собираю статистику...")
    cards_data = await asyncio.to_thread(g_sheets.get_cards_from_sheet, user_id=None if is_boss else user_id)

    if not cards_data:
        await query.edit_message_text("Нет данных для статистики.", reply_markup=keyboards.get_back_to_settings_keyboard())
        return

    total_cards = len(cards_data)
    barter_count = sum(1 for c in cards_data if c.get(SheetCols.CARD_TYPE_COL) == 'Бартер')
    category_counter = Counter(c.get(SheetCols.CATEGORY_COL) for c in cards_data if c.get(SheetCols.CATEGORY_COL))
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
    is_boss = (user_id == os.getenv("BOSS_ID"))
    await query.edit_message_text("📄 Формирую CSV файл...")
    cards_to_export = await asyncio.to_thread(g_sheets.get_cards_from_sheet, user_id=None if is_boss else user_id)

    if not cards_to_export:
        await query.edit_message_text("Нет данных для экспорта.", reply_markup=keyboards.get_back_to_settings_keyboard())
        return

    output = io.StringIO()
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
        owner_name = f"{card.get(SheetCols.OWNER_FIRST_NAME_COL,'')} {card.get(SheetCols.OWNER_LAST_NAME_COL,'-')}".strip()
        amount_text = ""
        if card.get(SheetCols.AMOUNT_COL):
            card_type_str = card.get(SheetCols.CARD_TYPE_COL)
            amount_val = card.get(SheetCols.AMOUNT_COL)
            amount_text = f"💰 {'Скидка' if card_type_str == 'Скидка' else 'Бартер'}: {amount_val}{'%' if card_type_str == 'Скидка' else ' ₽'}\n"

        text += (f"👤 <b>Владелец:</b> {owner_name}\n📞 Номер: {card.get(SheetCols.CARD_NUMBER_COL, '-')}\n{amount_text}"
                 f"<b>Статус:</b> <code>{card.get(SheetCols.STATUS_COL, '–')}</code>\n📅 {card.get(SheetCols.TIMESTAMP, '-')}\n")

        if str(update.effective_user.id) == os.getenv("BOSS_ID"):
            text += f"🤵‍♂️ <b>Инициатор:</b> {card.get(SheetCols.FIO_INITIATOR, '-')} ({card.get(SheetCols.TG_TAG, '-')})\n"
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
    payload = query.data.replace("paginate_", "", 1)
    data_key, page_str = payload.rsplit('_', 1)
    is_boss = (str(update.effective_user.id) == os.getenv("BOSS_ID"))
    
    if data_key == 'my_cards':
        list_title = "Все заявки" if is_boss else "Ваши поданные заявки"
    else: # search_results
        list_title = "Результаты поиска"

    await display_paginated_list(update, context, message_to_edit=query.message, page=int(page_str), data_key=data_key, list_title=list_title)


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пустой колбэк для кнопок, которые не должны ничего делать."""
    await update.callback_query.answer()


async def my_cards_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Загружает и отображает список заявок."""
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    is_boss = (user_id == os.getenv("BOSS_ID"))
    await query.edit_message_text("👑 Загружаю ВСЕ заявки..." if is_boss else "🔍 Загружаю ваши заявки...")

    all_cards = await asyncio.to_thread(g_sheets.get_cards_from_sheet, user_id=None if is_boss else user_id)
    
    data_key = 'my_cards'
    context.user_data[data_key] = all_cards
    list_title = "Все заявки" if is_boss else "Ваши поданные заявки"
    await display_paginated_list(update, context, message_to_edit=query.message, page=0, data_key=data_key, list_title=list_title)


async def last_application_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /last — показать последнюю заявку пользователя и её статус."""
    user_id = str(update.effective_user.id)
    cards = await asyncio.to_thread(g_sheets.get_cards_from_sheet, user_id=user_id)
    if not cards:
        await update.message.reply_text(
            "🤷 У вас ещё нет поданных заявок.\nНажмите «✍️ Подать заявку», чтобы создать первую."
        )
        return
    # get_cards_from_sheet возвращает в обратном порядке — самая свежая первой
    last = cards[0]
    owner = (
        f"{last.get(SheetCols.OWNER_FIRST_NAME_COL, '')} "
        f"{last.get(SheetCols.OWNER_LAST_NAME_COL, '')}"
    ).strip() or "—"
    card_type = last.get(SheetCols.CARD_TYPE_COL, "—")
    amount = last.get(SheetCols.AMOUNT_COL, "—")
    unit = "%" if card_type == "Скидка" else " ₽"
    status = last.get(SheetCols.STATUS_COL, "—")
    ts = last.get(SheetCols.TIMESTAMP, "—")
    text = (
        "<b>📋 Последняя заявка</b>\n\n"
        f"👤 Владелец: <b>{owner}</b>\n"
        f"💳 Карта: <code>{last.get(SheetCols.CARD_NUMBER_COL, '—')}</code>\n"
        f"✨ Тип: {card_type}\n"
        f"💰 Сумма/Скидка: {amount}{unit}\n"
        f"📍 Город/Бар: {last.get(SheetCols.ISSUE_LOCATION_COL, '—')}\n"
        f"📅 Подана: {ts}\n"
        f"<b>Статус:</b> <code>{status}</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def ack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка кнопки «✅ Понятно» под уведомлением заявителю.
    Убирает кнопку и (опционально) сообщает админу, что заявитель прочитал.
    """
    query = update.callback_query
    await query.answer("Спасибо за подтверждение!", show_alert=False)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Уведомить админа (если указан ADMIN_CONTACT_USERNAME — то есть «главного»)
    boss_id = os.getenv("BOSS_ID")
    if not boss_id:
        return
    try:
        # callback_data: ack:<row_index>:<status>
        parts = query.data.split(":", 2)
        info = ""
        if len(parts) == 3:
            _, row_idx, status = parts
            info = f" по заявке №{int(row_idx) + 1} (статус: {status})"
        user = query.from_user
        tag = f"@{user.username}" if user.username else f"id={user.id}"
        await context.bot.send_message(
            chat_id=boss_id,
            text=f"📬 Заявитель {tag} подтвердил прочтение уведомления{info}.",
        )
    except Exception as e:
        logger.warning(f"ack_callback notify boss failed: {e}")


# Отмечаем успешный импорт модуля для продовой диагностики
try:
    logger.info("settings_handlers imported successfully")
except Exception:
    pass
