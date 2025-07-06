# -*- coding: utf-8 -*-
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

import g_sheets
from constants import (
    SheetCols, AWAIT_REJECT_REASON, CALLBACK_APPROVE_PREFIX,
    CALLBACK_REJECT_PREFIX, CALLBACK_EDIT_PREFIX
)

logger = logging.getLogger(__name__)

def format_admin_notification(row_data: dict, row_index: int) -> dict:
    """Форматирует сообщение и клавиатуру для уведомления админа."""
    initiator_info = f"{row_data.get(SheetCols.FIO_INITIATOR, 'N/A')} ({row_data.get(SheetCols.TG_TAG, 'N/A')})"
    owner_info = f"{row_data.get(SheetCols.OWNER_FIRST_NAME_COL, '')} {row_data.get(SheetCols.OWNER_LAST_NAME_COL, '')}".strip()
    
    text = (
        f"🔔 <b>Новая заявка на согласование</b> 🔔\n\n"
        f"<b>Инициатор:</b> {initiator_info}\n"
        f"<b>Владелец карты:</b> {owner_info}\n"
        f"<b>Номер карты:</b> <code>{row_data.get(SheetCols.CARD_NUMBER_COL)}</code>\n"
        f"<b>Сумма/Скидка:</b> {row_data.get(SheetCols.AMOUNT_COL)}\n"
        f"<b>Статья:</b> {row_data.get(SheetCols.CATEGORY_COL)}\n\n"
        f"Требуется ваше действие."
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"{CALLBACK_APPROVE_PREFIX}{row_index}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"{CALLBACK_REJECT_PREFIX}{row_index}")
        ],
        # [InlineKeyboardButton("✏️ Редактировать", callback_data=f"{CALLBACK_EDIT_PREFIX}{row_index}")]
    ])
    
    return {"text": text, "reply_markup": keyboard}

async def approve_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает одобрение заявки."""
    query = update.callback_query
    await query.answer()
    
    row_index = int(query.data.split(':')[1])
    
    success = g_sheets.update_cell_by_row(row_index, SheetCols.STATUS_COL, "Одобрено")
    
    if success:
        await query.edit_message_text(query.message.text_html + "\n\n<b>Статус: ✅ ОДОБРЕНО</b>", parse_mode=ParseMode.HTML)
        
        # Уведомляем пользователя
        row_data = g_sheets.get_row_data(row_index)
        if row_data and row_data.get(SheetCols.TG_ID):
            owner_name = f"{row_data.get(SheetCols.OWNER_FIRST_NAME_COL)} {row_data.get(SheetCols.OWNER_LAST_NAME_COL)}"
            await context.bot.send_message(
                chat_id=row_data[SheetCols.TG_ID],
                text=f"🎉 Ваша заявка на карту для <b>{owner_name}</b> была <b>одобрена</b>.",
                parse_mode=ParseMode.HTML
            )

async def reject_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс отклонения, запрашивая причину."""
    query = update.callback_query
    await query.answer()
    
    row_index = int(query.data.split(':')[1])
    context.user_data['admin_action_row_index'] = row_index
    
    await query.edit_message_text(query.message.text_html + "\n\n⏳ Ожидание...", parse_mode=ParseMode.HTML)
    await query.message.reply_text("Пожалуйста, введите причину отказа для этой заявки.")
    
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
    
    await update.message.reply_text("Статус заявки обновлен на 'Отклонено'.")
    
    # Уведомляем пользователя
    row_data = g_sheets.get_row_data(row_index)
    if row_data and row_data.get(SheetCols.TG_ID):
        owner_name = f"{row_data.get(SheetCols.OWNER_FIRST_NAME_COL)} {row_data.get(SheetCols.OWNER_LAST_NAME_COL)}"
        await context.bot.send_message(
            chat_id=row_data[SheetCols.TG_ID],
            text=f"😔 Ваша заявка на карту для <b>{owner_name}</b> была <b>отклонена</b>.\n\n<i>Причина:</i> {reason}",
            parse_mode=ParseMode.HTML
        )
    
    context.user_data.clear()
    return ConversationHandler.END
