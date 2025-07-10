# -*- coding: utf-8 -*-
import logging
import os
from datetime import datetime, timedelta
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import g_sheets
from constants import SheetCols

logger = logging.getLogger(__name__)

async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Формирует и отправляет ежедневный отчет админу."""
    # --- ИЗМЕНЕНИЕ: Используем REPORT_CHAT_ID вместо BOSS_ID ---
    report_chat_id = os.getenv("REPORT_CHAT_ID")
    if not report_chat_id:
        logger.warning("REPORT_CHAT_ID не установлен, ежедневный отчет пропущен.")
        return

    logger.info("Генерация ежедневного отчета...")
    all_cards = g_sheets.get_cards_from_sheet(user_id=None)
    
    if not all_cards:
        await context.bot.send_message(chat_id=report_chat_id, text="📄 Ежедневный отчет: За последние 24 часа не было активности.")
        return

    yesterday = datetime.now() - timedelta(days=1)
    recent_cards = []
    
    for card in all_cards:
        try:
            # Предполагаемый формат времени из Google Sheets
            # Если формат другой, его нужно будет поменять здесь
            timestamp_str = card.get(SheetCols.TIMESTAMP)
            # Примерные форматы, которые могут быть в таблице
            supported_formats = ["%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"]
            card_time = None
            for fmt in supported_formats:
                try:
                    card_time = datetime.strptime(timestamp_str, fmt)
                    break
                except (ValueError, TypeError):
                    continue
            
            if card_time and card_time > yesterday:
                recent_cards.append(card)
        except (TypeError, ValueError):
            continue 
            
    pending_count = sum(1 for card in all_cards if card.get(SheetCols.STATUS_COL) == 'На согласовании')
    new_in_24h = len(recent_cards)
    approved_in_24h = sum(1 for card in recent_cards if card.get(SheetCols.STATUS_COL) == 'Одобрено')
    rejected_in_24h = sum(1 for card in recent_cards if card.get(SheetCols.STATUS_COL) == 'Отклонено')

    report_text = (
        f"<b>📄 Ежедневная сводка | {datetime.now():%d-%m-%Y}</b>\n\n"
        f"<b>За последние 24 часа:</b>\n"
        f"  - Новых заявок: <b>{new_in_24h}</b>\n"
        f"  - Одобрено: <b>{approved_in_24h}</b>\n"
        f"  - Отклонено: <b>{rejected_in_24h}</b>\n\n"
        f"<b>Общий статус:</b>\n"
        f"  - 🔥 Ожидают решения: <b>{pending_count}</b>"
    )

    await context.bot.send_message(chat_id=report_chat_id, text=report_text, parse_mode=ParseMode.HTML)
