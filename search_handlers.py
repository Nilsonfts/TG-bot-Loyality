# -*- coding: utf-8 -*-

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import g_sheets
# Импортируем утилиту для пагинации из модуля настроек
from settings_handlers import display_paginated_list
# --- ИЗМЕНЕНИЕ ---
from constants import States, SheetCols

logger = logging.getLogger(__name__)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    """Начинает диалог поиска."""
    keyboard = [
        [InlineKeyboardButton("По ФИО владельца", callback_data="search_by_name")],
        [InlineKeyboardButton("По номеру карты", callback_data="search_by_phone")]
    ]
    await update.message.reply_text("Выберите критерий поиска:", reply_markup=InlineKeyboardMarkup(keyboard))
    # --- ИЗМЕНЕНИЕ ---
    return States.SEARCH_CHOOSE_FIELD


async def search_field_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> States:
    """Обрабатывает выбор поля для поиска."""
    query = update.callback_query
    await query.answer()
    context.user_data['search_field'] = query.data
    await query.edit_message_text("Введите поисковый запрос:")
    # --- ИЗМЕНЕНИЕ ---
    return States.AWAIT_SEARCH_QUERY


async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выполняет поиск и отображает результаты."""
    user_id = str(update.effective_user.id)
    is_boss = (user_id == g_sheets.os.getenv("BOSS_ID"))
    search_query = update.message.text.lower().strip()
    loading_msg = await update.message.reply_text("🔍 Выполняю поиск...")

    all_cards = g_sheets.get_cards_from_sheet(user_id=None if is_boss else user_id)
    search_field = context.user_data.get('search_field')

    if search_field == 'search_by_name':
        results = [
            c for c in all_cards 
            if search_query in c.get(SheetCols.OWNER_FIRST_NAME_COL, '').lower() or \
               search_query in c.get(SheetCols.OWNER_LAST_NAME_COL, '').lower()
        ]
    else:  # search_by_phone
        results = [c for c in all_cards if search_query in str(c.get(SheetCols.CARD_NUMBER_COL, ''))]

    context.user_data['search_results'] = results
    await loading_msg.delete()

    # Отправляем новое сообщение, которое затем будет редактироваться пагинатором
    paginated_message = await update.message.reply_text("Загрузка результатов...")

    await display_paginated_list(
        update=update,
        context=context,
        message_to_edit=paginated_message,
        page=0,
        data_key='search_results',
        list_title="Результаты поиска"
    )
    return ConversationHandler.END
