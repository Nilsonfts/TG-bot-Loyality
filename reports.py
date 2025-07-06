# -*- coding: utf-8 -*-
import logging
import os
from datetime import datetime, timedelta
from collections import Counter
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import g_sheets
from constants import SheetCols

logger = logging.getLogger(__name__)

async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Формирует и отправляет ежедневный отчет админу."""
    boss_id = os.getenv("BOSS_ID")
    if not boss_id:
        logger.warning("BOSS_ID not set, skipping daily report.")
        return

    logger.info("Generating daily summary...")
    all_cards = g_sheets.get_cards_from_sheet(user_id=None)
    
    if not all_cards:
        await context.bot.send_message(chat_id=boss_id, text="📄 Ежедневный отчет: За последние 24 часа не было активности.")
        return

    yesterday = datetime.now() - timedelta(days=1)
    recent_cards = []
    
    for card in all_cards:
        try:
            # Приводим строку времени к объекту datetime
            timestamp_str = card.get(SheetCols.TIMESTAMP)
            card_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            if card_time > yesterday:
                recent_cards.append(card)
        except (TypeError, ValueError):
            continue # Пропускаем строки с неверным форматом даты
            
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

    await context.bot.send_message(chat_id=boss_id, text=report_text, parse_mode=ParseMode.HTML)
