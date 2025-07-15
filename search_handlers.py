# -*- coding: utf-8 -*-

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import g_sheets
import utils
# Импортируем утилиту для пагинации из модуля настроек
from settings_handlers import display_paginated_list
from constants import SEARCH_CHOOSE_FIELD, AWAIT_SEARCH_QUERY

logger = logging.getLogger(__name__)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог поиска."""
    keyboard = [
        [InlineKeyboardButton("По ФИО владельца", callback_data="search_by_name")],
        [InlineKeyboardButton("По номеру карты", callback_data="search_by_phone")]
    ]
    await update.message.reply_text("Выберите критерий поиска:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SEARCH_CHOOSE_FIELD


async def search_field_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор поля для поиска."""
    query = update.callback_query
    await query.answer()
    context.user_data['search_field'] = query.data
    await query.edit_message_text("Введите поисковый запрос:")
    return AWAIT_SEARCH_QUERY


async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выполняет поиск и отображает результаты."""
    user_id = str(update.effective_user.id)
    is_boss = (user_id == g_sheets.os.getenv("BOSS_ID"))
    search_query = utils.sanitize_input(update.message.text.lower().strip(), 100)
    
    if len(search_query) < 2:
        await update.message.reply_text("❌ Поисковый запрос слишком короткий. Введите минимум 2 символа.")
        return AWAIT_SEARCH_QUERY
    
    loading_msg = await update.message.reply_text("🔍 Выполняю поиск...")

    search_field = context.user_data.get('search_field')
    search_type = 'name' if search_field == 'search_by_name' else 'phone'
    
    # Сначала пытаемся искать в локальной БД (быстрее)
    local_results = utils.search_applications_local(
        query=search_query,
        search_type=search_type,
        user_id=None if is_boss else user_id
    )
    
    if local_results:
        # Преобразуем результаты из локальной БД в формат Google Sheets
        results = []
        for local_result in local_results:
            formatted_result = {
                'Имя владельца карты': local_result.get('owner_first_name', ''),
                'Фамилия Владельца': local_result.get('owner_last_name', ''),
                'Номер карты': local_result.get('card_number', ''),
                'Какую карту регистрируем?': local_result.get('card_type', ''),
                'Сумма бартера или % скидки': local_result.get('amount', ''),
                'Статья пополнения карт': local_result.get('category', ''),
                'Статус Согласования': local_result.get('status', ''),
                'Отметка времени': local_result.get('created_at', ''),
                'ТГ Заполняющего': local_result.get('tg_user_id', ''),
                'ФИО Инициатора': 'Данные из локальной БД',  # Можно доработать
                'Тег Telegram': '–'
            }
            results.append(formatted_result)
        
        logger.info(f"Найдено {len(results)} результатов в локальной БД")
    else:
        # Если в локальной БД ничего не найдено, ищем в Google Sheets
        all_cards = g_sheets.get_cards_from_sheet(user_id=None if is_boss else user_id)

        if search_field == 'search_by_name':
            results = [c for c in all_cards if search_query in c.get('Имя владельца карты', '').lower() or search_query in c.get('Фамилия Владельца', '').lower()]
        else:  # search_by_phone
            results = [c for c in all_cards if search_query in str(c.get('Номер карты', ''))]
        
        logger.info(f"Найдено {len(results)} результатов в Google Sheets")

    context.user_data['search_results'] = results
    await loading_msg.delete()

    # Используем утилиту для отображения с пагинацией
    # Поскольку мы не в callback_query, нам нужно отправить новое сообщение
    if results:
        search_summary = f"🔍 <b>Найдено результатов:</b> {len(results)}\n"
        search_summary += f"<b>Критерий поиска:</b> {'ФИО владельца' if search_type == 'name' else 'Номер карты'}\n"
        search_summary += f"<b>Запрос:</b> {search_query}\n\n"
    else:
        search_summary = f"🤷 По запросу '<b>{search_query}</b>' ничего не найдено.\n\n"

    paginated_message = await update.message.reply_text(search_summary, parse_mode='HTML')

    await display_paginated_list(
        update=update,
        context=context,
        message_to_edit=paginated_message,
        page=0,
        data_key='search_results',
        list_title="Результаты поиска"
    )
    return ConversationHandler.END
