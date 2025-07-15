# -*- coding: utf-8 -*-
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

import g_sheets
from constants import (
    SheetCols, AWAIT_REJECT_REASON, CALLBACK_APPROVE_PREFIX,
    CALLBACK_REJECT_PREFIX
)

logger = logging.getLogger(__name__)

def format_admin_notification(row_data: dict, row_index: int) -> dict:
    """Форматирует сообщение и клавиатуру для уведомления админа."""
    # Логгируем входные данные для отладки
    logger.info(f"format_admin_notification вызвана с row_data: {row_data}")
    logger.info(f"format_admin_notification вызвана с row_index: {row_index}")
    
    # Проверяем, какой формат данных у нас: из Google Sheets или из context.user_data
    if 'initiator_fio' in row_data:
        # Данные из context.user_data (form_handlers)
        initiator_info = f"{row_data.get('initiator_fio', 'N/A')} ({row_data.get('initiator_username', 'N/A')})"
        owner_info = f"{row_data.get('owner_first_name', '')} {row_data.get('owner_last_name', '')}".strip()
        amount_val = row_data.get('amount', '-')
        card_type_str = row_data.get('card_type')
        card_number = row_data.get('card_number')
        category = row_data.get('category')
        issue_location = row_data.get('issue_location')
        logger.info("Используем формат данных из context.user_data")
    else:
        # Данные из Google Sheets (с константами SheetCols)
        initiator_info = f"{row_data.get(SheetCols.FIO_INITIATOR, 'N/A')} ({row_data.get(SheetCols.TG_TAG, 'N/A')})"
        owner_info = f"{row_data.get(SheetCols.OWNER_FIRST_NAME_COL, '')} {row_data.get(SheetCols.OWNER_LAST_NAME_COL, '')}".strip()
        amount_val = row_data.get(SheetCols.AMOUNT_COL, '-')
        card_type_str = row_data.get(SheetCols.CARD_TYPE_COL)
        card_number = row_data.get(SheetCols.CARD_NUMBER_COL)
        category = row_data.get(SheetCols.CATEGORY_COL)
        issue_location = row_data.get(SheetCols.ISSUE_LOCATION_COL)
        logger.info("Используем формат данных из Google Sheets")
    
    # Обрабатываем пустые значения
    if not owner_info.strip():
        owner_info = "Не указано"
    if not card_number:
        card_number = "Не указан"
    if not category:
        category = "Не указана"
    if not issue_location:
        issue_location = "Не указан"
    
    amount_text = f"{amount_val}{'%' if card_type_str == 'Скидка' else ' ₽'}"
    
    text = (
        f"🔔 <b>Новая заявка на согласование (№{row_index})</b> 🔔\n\n"
        f"<b>Инициатор:</b> {initiator_info}\n"
        f"<b>Владелец карты:</b> {owner_info}\n"
        f"<b>Номер карты:</b> <code>{card_number}</code>\n"
        f"<b>Сумма/Скидка:</b> {amount_text}\n"
        f"<b>Статья:</b> {category}\n"
        f"<b>Город/Бар:</b> {issue_location}\n\n"
        "Требуется ваше действие."
    )
    
    logger.info(f"Сформированное уведомление: {text}")
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"{CALLBACK_APPROVE_PREFIX}{row_index}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"{CALLBACK_REJECT_PREFIX}{row_index}")
        ]
    ])
    
    return {"text": text, "reply_markup": keyboard}
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"{CALLBACK_APPROVE_PREFIX}{row_index}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"{CALLBACK_REJECT_PREFIX}{row_index}")
        ]
    ])
    
    return {"text": text, "reply_markup": keyboard}

async def approve_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает одобрение заявки."""
    query = update.callback_query
    await query.answer()
    
    try:
        row_index = int(query.data.split(':')[1])
    except (IndexError, ValueError):
        await query.edit_message_text("Ошибка: неверный формат ID заявки.", reply_markup=None)
        return

    success = g_sheets.update_cell_by_row(row_index, SheetCols.STATUS_COL, "Одобрено")
    
    if success:
        await query.edit_message_text(query.message.text_html + "\n\n<b>Статус: ✅ ОДОБРЕНО</b>", parse_mode=ParseMode.HTML, reply_markup=None)
        
        row_data = g_sheets.get_row_data(row_index)
        if row_data and row_data.get(SheetCols.TG_ID):
            try:
                owner_name = f"{row_data.get(SheetCols.OWNER_FIRST_NAME_COL)} {row_data.get(SheetCols.OWNER_LAST_NAME_COL)}"
                await context.bot.send_message(
                    chat_id=row_data[SheetCols.TG_ID],
                    text=f"🎉 Ваша заявка на карту для <b>{owner_name}</b> была <b>одобрена</b>.",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Failed to send approval notification to user {row_data[SheetCols.TG_ID]}: {e}")
                boss_id = os.getenv("BOSS_ID")
                if boss_id:
                    await context.bot.send_message(boss_id, f"Не удалось уведомить пользователя {row_data[SheetCols.TG_TAG]} об одобрении заявки №{row_index}.")

async def reject_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс отклонения, запрашивая причину."""
    query = update.callback_query
    await query.answer()

    try:
        row_index = int(query.data.split(':')[1])
    except (IndexError, ValueError):
        await query.edit_message_text("Ошибка: неверный формат ID заявки.", reply_markup=None)
        return ConversationHandler.END
        
    context.user_data['admin_action_row_index'] = row_index
    
    await query.edit_message_text(query.message.text_html + "\n\n⏳ Ожидание...", parse_mode=ParseMode.HTML, reply_markup=None)
    await query.message.reply_text(f"Пожалуйста, введите причину отказа для заявки №{row_index}.")
    
    return AWAIT_REJECT_REASON

async def reject_request_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает причину, обновляет статус и уведомляет пользователя."""
    reason = update.message.text
    row_index = context.user_data.get('admin_action_row_index')
    
    if not row_index:
        await update.message.reply_text("Произошла ошибка, не найден ID заявки. Попробуйте снова.")
        return ConversationHandler.END
        
    g_sheets.update_cell_by_row(row_index, SheetCols.STATUS_COL, "Отклонено")
    g_sheets.update_cell_by_row(row_index, SheetCols.REASON_REJECT, reason)
    
    await update.message.reply_text(f"Статус заявки №{row_index} обновлен на 'Отклонено'.")
    
    row_data = g_sheets.get_row_data(row_index)
    if row_data and row_data.get(SheetCols.TG_ID):
        try:
            owner_name = f"{row_data.get(SheetCols.OWNER_FIRST_NAME_COL)} {row_data.get(SheetCols.OWNER_LAST_NAME_COL)}"
            await context.bot.send_message(
                chat_id=row_data[SheetCols.TG_ID],
                text=f"😔 Ваша заявка на карту для <b>{owner_name}</b> была <b>отклонена</b>.\n\n<i>Причина:</i> {reason}",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send rejection notification to user {row_data[SheetCols.TG_ID]}: {e}")
            boss_id = os.getenv("BOSS_ID")
            if boss_id:
                await context.bot.send_message(boss_id, f"Не удалось уведомить пользователя {row_data[SheetCols.TG_TAG]} об отклонении заявки №{row_index}.")

    context.user_data.clear()
    return ConversationHandler.END
