# -*- coding: utf-8 -*-
import logging
import os
from datetime import datetime, timedelta
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import g_sheets
import utils
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
            timestamp_str = card.get(SheetCols.TIMESTAMP)
            card_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            if card_time > yesterday:
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

    await context.bot.send_message(chat_id=boss_id, text=report_text, parse_mode=ParseMode.HTML)

async def send_user_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет напоминания неактивным пользователям."""
    logger.info("Checking for users to send reminders...")
    
    users_for_reminder = utils.get_users_for_reminder()
    
    if not users_for_reminder:
        logger.info("No users need reminders at this time.")
        return
    
    for user in users_for_reminder:
        try:
            reminder_text = (
                f"👋 Привет, {user.get('fio', 'пользователь')}!\n\n"
                "Давно не виделись! 🤔\n\n"
                "Напоминаем, что вы можете:\n"
                "• 📝 Подать новую заявку на карту\n"
                "• 🔍 Найти свои предыдущие заявки\n"
                "• 📊 Посмотреть статистику\n\n"
                "Есть вопросы? Я всегда готов помочь! 🤖"
            )
            
            await context.bot.send_message(
                chat_id=user['tg_id'],
                text=reminder_text
            )
            
            # Обновляем время последней активности, чтобы не спамить
            utils.update_user_activity(user['tg_id'])
            
            logger.info(f"Sent reminder to user {user['tg_id']}")
            
        except Exception as e:
            logger.error(f"Failed to send reminder to user {user['tg_id']}: {e}")
    
    logger.info(f"Sent {len(users_for_reminder)} reminder(s)")

async def send_weekly_analytics(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет еженедельную аналитику админу."""
    boss_id = os.getenv("BOSS_ID")
    if not boss_id:
        logger.warning("BOSS_ID not set, skipping weekly analytics.")
        return

    logger.info("Generating weekly analytics...")
    
    # Получаем статистику из локальной БД (быстрее)
    stats = utils.get_statistics()
    
    if not stats:
        await context.bot.send_message(
            chat_id=boss_id,
            text="📊 Еженедельная аналитика: Недостаточно данных для анализа."
        )
        return
    
    # Получаем данные за неделю
    week_ago = datetime.now() - timedelta(days=7)
    all_cards = g_sheets.get_cards_from_sheet(user_id=None)
    weekly_cards = []
    
    for card in all_cards:
        try:
            timestamp_str = card.get(SheetCols.TIMESTAMP)
            card_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            if card_time > week_ago:
                weekly_cards.append(card)
        except (TypeError, ValueError):
            continue
    
    weekly_new = len(weekly_cards)
    weekly_approved = sum(1 for card in weekly_cards if card.get(SheetCols.STATUS_COL) == 'Одобрено')
    weekly_rejected = sum(1 for card in weekly_cards if card.get(SheetCols.STATUS_COL) == 'Отклонено')
    
    approval_rate = (weekly_approved / weekly_new * 100) if weekly_new > 0 else 0
    
    analytics_text = (
        f"<b>📊 Еженедельная аналитика | {datetime.now():%d-%m-%Y}</b>\n\n"
        f"<b>За последнюю неделю:</b>\n"
        f"  - Новых заявок: <b>{weekly_new}</b>\n"
        f"  - Одобрено: <b>{weekly_approved}</b>\n"
        f"  - Отклонено: <b>{weekly_rejected}</b>\n"
        f"  - Процент одобрения: <b>{approval_rate:.1f}%</b>\n\n"
        f"<b>Общая статистика:</b>\n"
        f"  - Всего заявок: <b>{stats.get('total', 0)}</b>\n"
    )
    
    # Добавляем статистику по статусам
    by_status = stats.get('by_status', {})
    if by_status:
        analytics_text += "\n<b>По статусам:</b>\n"
        for status, count in by_status.items():
            analytics_text += f"  - {status}: <b>{count}</b>\n"
    
    # Добавляем статистику по типам карт
    by_card_type = stats.get('by_card_type', {})
    if by_card_type:
        analytics_text += "\n<b>По типам карт:</b>\n"
        for card_type, count in by_card_type.items():
            analytics_text += f"  - {card_type}: <b>{count}</b>\n"

    await context.bot.send_message(chat_id=boss_id, text=analytics_text, parse_mode=ParseMode.HTML)
