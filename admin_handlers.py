# -*- coding: utf-8 -*-
import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

import g_sheets
from constants import (
    SheetCols, AWAIT_REJECT_REASON, CALLBACK_APPROVE_PREFIX,
    CALLBACK_REJECT_PREFIX
)

logger = logging.getLogger(__name__)

def format_admin_notification(row_data: dict, row_index: int, action_id: str = None) -> dict:
    """Форматирует сообщение и клавиатуру для уведомления админа.

    action_id — короткий идентификатор, который используется в callback_data
    кнопок. Если не передан, fallback на row_index (старое поведение).
    """
    logger.info(f"format_admin_notification: row_index={row_index}, action_id={action_id}")
    
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
        reason = row_data.get('reason', 'Не указана')  # Добавляем причину выдачи
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
        reason = row_data.get(SheetCols.REASON_COL, 'Не указана')  # Добавляем причину выдачи
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

    if isinstance(row_index, int) and row_index >= 0:
        title = f"🔔 <b>Новая заявка на согласование (№{row_index + 1})</b> 🔔"
    else:
        title = "🔔 <b>Новая заявка на согласование</b> 🔔"

    text = (
        f"{title}\n\n"
        f"<b>Инициатор:</b> {initiator_info}\n"
        f"<b>Владелец карты:</b> {owner_info}\n"
        f"<b>Номер карты:</b> <code>{card_number}</code>\n"
        f"<b>Причина выдачи:</b> {reason}\n"
        f"<b>Сумма/Скидка:</b> {amount_text}\n"
        f"<b>Статья:</b> {category}\n"
        f"<b>Город/Бар:</b> {issue_location}\n\n"
        "Требуется ваше действие."
    )
    
    logger.info(f"Сформированное уведомление: {text}")

    if action_id:
        callback_token = action_id
    elif isinstance(row_index, int) and row_index >= 0:
        callback_token = str(row_index)
    else:
        callback_token = None

    if callback_token is not None:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"{CALLBACK_APPROVE_PREFIX}{callback_token}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"{CALLBACK_REJECT_PREFIX}{callback_token}")
            ]
        ])
    else:
        keyboard = None

    return {"text": text, "reply_markup": keyboard}

async def _resolve_action(query) -> tuple:
    """Извлекает row_index и row_data по callback_data.
    Поддерживает и новый формат (action_id), и старый (числовой row_index).
    Возвращает (row_index, row_data) или (None, None) при ошибке.
    """
    try:
        token = query.data.split(':', 1)[1]
    except (IndexError, ValueError):
        return None, None

    # Новый формат: action_id
    row_index, row_data = await asyncio.to_thread(g_sheets.resolve_pending_action, token)
    if row_index is not None:
        return row_index, row_data

    # Fallback: старый формат row_index числом
    if token.isdigit():
        idx = int(token)
        row_data = await asyncio.to_thread(g_sheets.get_row_data, idx)
        if row_data:
            return idx, row_data
    return None, None


async def approve_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает одобрение заявки."""
    query = update.callback_query
    await query.answer()

    row_index, row_data = await _resolve_action(query)
    if row_index is None:
        logger.error(f"Не удалось сопоставить callback_data: {query.data}")
        await query.edit_message_text(
            (query.message.text_html or "") + "\n\n<b>❌ Заявка не найдена в таблице.</b>\nВозможно, она была удалена или сдвинута.",
            parse_mode=ParseMode.HTML, reply_markup=None,
        )
        return
    logger.info(f"Одобрение заявки №{row_index + 1} (row_index={row_index})")

    # Обновляем статус в Google Sheets
    success = await asyncio.to_thread(g_sheets.update_cell_by_row, row_index, SheetCols.STATUS_COL, "Одобрено")

    if not success:
        logger.error(f"Не удалось обновить статус заявки №{row_index}")
        await query.edit_message_text(
            query.message.text_html + "\n\n<b>❌ ОШИБКА: Не удалось обновить статус</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=None
        )
        return

    logger.info(f"Статус заявки №{row_index} успешно обновлен на 'Одобрено'")

    # Также обновляем поле одобрения
    approval_success = await asyncio.to_thread(g_sheets.update_cell_by_row, row_index, SheetCols.APPROVAL_STATUS, "Одобрено")
    if approval_success:
        logger.info(f"Поле одобрения для заявки №{row_index} обновлено")
    else:
        logger.warning(f"Не удалось обновить поле одобрения для заявки №{row_index}")

    if not row_data:
        row_data = await asyncio.to_thread(g_sheets.get_row_data, row_index)
    tg_id = row_data.get(SheetCols.TG_ID) if row_data else None
    if not row_data:
        logger.error(f"Не найдены данные для строки {row_index} (row_data is None)")
        return
    if not tg_id:
        logger.error(f"TG_ID отсутствует для строки {row_index}")
        return

    try:
        owner_name = f"{row_data.get(SheetCols.OWNER_FIRST_NAME_COL, '')} {row_data.get(SheetCols.OWNER_LAST_NAME_COL, '')}".strip() or "Не указано"
        card_number = row_data.get(SheetCols.CARD_NUMBER_COL, "Не указан")
        amount = row_data.get(SheetCols.AMOUNT_COL, "Не указана")
        
        # Вычисляем ближайший четверг для активации
        from datetime import datetime, timedelta
        
        # Получаем данные администратора, который одобрил
        admin_user = query.from_user
        admin_name = f"{admin_user.first_name} {admin_user.last_name or ''}".strip()
        if not admin_name:
            admin_name = admin_user.username or "Руководитель"
        
        # Вычисляем ближайший четверг
        today = datetime.now()
        days_until_thursday = (3 - today.weekday()) % 7  # 3 = четверг (понедельник = 0)
        if days_until_thursday == 0 and today.hour >= 22:  # Если сегодня четверг после 22:00
            days_until_thursday = 7  # Следующий четверг
        elif days_until_thursday == 0:  # Если сегодня четверг до 22:00
            days_until_thursday = 0  # Сегодня вечером
        
        next_thursday = today + timedelta(days=days_until_thursday)
        thursday_date = next_thursday.strftime("%d.%m.%Y")
        
        # Отправляем уведомление пользователю
        await context.bot.send_message(
            chat_id=tg_id,
            text=(
                f"🎉 <b>Заявка одобрена руководителем!</b>\n\n"
                f"📋 <b>Детали заявки:</b>\n"
                f"👤 Владелец карты: <b>{owner_name}</b>\n"
                f"💳 Номер карты: <code>{card_number}</code>\n"
                f"💰 Сумма/Скидка: <b>{amount}</b>\n\n"
                f"✅ <b>Согласовано:</b> {admin_name}\n"
                f"📅 <b>Активация:</b> {thursday_date} (четверг) после 22:00\n\n"
                f"ℹ️ <i>Карта будет активирована автоматически в указанную дату.\n"
                f"До этого времени средства недоступны для использования.</i>"
            ),
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Уведомление об одобрении отправлено пользователю {tg_id}")
        
        # Подтверждение админу о доставке
        user_tag = row_data.get(SheetCols.TG_TAG, "неизвестно")
        await query.edit_message_text(
            query.message.text_html + f"\n\n<b>Статус: ✅ ОДОБРЕНО</b>\n📬 <i>Уведомление доставлено пользователю {user_tag}</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=None
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {tg_id}: {e}")
        boss_id = os.getenv("BOSS_ID")
        if boss_id:
            await context.bot.send_message(
                boss_id,
                f"⚠️ Не удалось уведомить пользователя {row_data.get(SheetCols.TG_TAG, 'неизвестно')} об одобрении заявки №{row_index}.\n\nОшибка: {str(e)}"
            )

async def reject_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс отклонения, запрашивая причину."""
    query = update.callback_query
    await query.answer()

    row_index, _row_data = await _resolve_action(query)
    if row_index is None:
        logger.error(f"Не удалось сопоставить callback_data: {query.data}")
        await query.edit_message_text(
            (query.message.text_html or "") + "\n\n<b>❌ Заявка не найдена в таблице.</b>",
            parse_mode=ParseMode.HTML, reply_markup=None,
        )
        return ConversationHandler.END
    logger.info(f"Начинаем отклонение заявки №{row_index + 1} (row_index={row_index})")

    context.user_data['admin_action_row_index'] = row_index
    
    # Обновляем исходное сообщение
    await query.edit_message_text(
        query.message.text_html + "\n\n⏳ Ожидание причины отклонения...", 
        parse_mode=ParseMode.HTML, 
        reply_markup=None
    )
    
    # Отправляем запрос причины
    await query.message.reply_text(
        f"📝 Пожалуйста, введите причину отказа для заявки №{row_index + 1}:\n\n"
        "💡 <i>Укажите конкретную причину, которая поможет заявителю исправить ошибки в будущем.</i>",
        parse_mode=ParseMode.HTML
    )
    
    return AWAIT_REJECT_REASON

async def reject_request_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает причину, обновляет статус и уведомляет пользователя."""
    reason = update.message.text.strip()
    row_index = context.user_data.get('admin_action_row_index')
    
    if row_index is None:
        await update.message.reply_text("❌ Произошла ошибка: не найден ID заявки. Попробуйте снова.")
        return ConversationHandler.END
    
    if not reason:
        await update.message.reply_text("❌ Причина не может быть пустой. Введите причину отклонения:")
        return AWAIT_REJECT_REASON
        
    logger.info(f"Отклоняем заявку №{row_index} с причиной: {reason}")
    
    # Обновляем статус и причину в Google Sheets
    status_updated = await asyncio.to_thread(g_sheets.update_cell_by_row, row_index, SheetCols.STATUS_COL, "Отклонено")
    reason_updated = await asyncio.to_thread(g_sheets.update_cell_by_row, row_index, SheetCols.REASON_REJECT, reason)
    
    if status_updated and reason_updated:
        logger.info(f"Статус и причина для заявки №{row_index} успешно обновлены")
        await update.message.reply_text(
            f"✅ <b>Заявка №{row_index + 1} отклонена</b>\n\n"
            f"📝 <b>Причина:</b> {reason}\n\n"
            f"🔔 <i>Уведомление будет отправлено заявителю...</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Получаем данные для уведомления пользователя
        row_data = await asyncio.to_thread(g_sheets.get_row_data, row_index)
        if row_data and row_data.get(SheetCols.TG_ID):
            try:
                user_id = row_data[SheetCols.TG_ID]
                owner_name = f"{row_data.get(SheetCols.OWNER_FIRST_NAME_COL, '')} {row_data.get(SheetCols.OWNER_LAST_NAME_COL, '')}".strip()
                card_number = row_data.get(SheetCols.CARD_NUMBER_COL, "Не указан")
                
                # Отправляем уведомление пользователю
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"😔 <b>Заявка отклонена</b>\n\n"
                        f"📋 <b>Детали заявки:</b>\n"
                        f"👤 Владелец карты: <b>{owner_name}</b>\n"
                        f"💳 Номер карты: <code>{card_number}</code>\n\n"
                        f"❌ <b>К сожалению, ваша заявка была отклонена.</b>\n\n"
                        f"📝 <b>Причина отклонения:</b>\n"
                        f"<i>{reason}</i>\n\n"
                        f"ℹ️ <b>Что делать дальше?</b>\n"
                        f"• Изучите причину отклонения\n"
                        f"• Исправьте указанные замечания\n"
                        f"• Подайте новую заявку\n\n"
                        f"💡 <i>Мы всегда готовы помочь! Обращайтесь, если есть вопросы.</i>"
                    ),
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Уведомление об отклонении отправлено пользователю {user_id}")
                
                # Подтверждение админу о доставке
                user_tag = row_data.get(SheetCols.TG_TAG, "неизвестно")
                await update.message.reply_text(
                    f"📬 <b>Уведомление доставлено!</b>\n\n"
                    f"👤 Пользователь: {user_tag}\n"
                    f"✅ Уведомление об отклонении заявки №{row_index + 1} успешно отправлено",
                    parse_mode=ParseMode.HTML
                )
                
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
                
                # Уведомляем босса об ошибке
                boss_id = os.getenv("BOSS_ID")
                if boss_id:
                    await context.bot.send_message(
                        boss_id, 
                        f"⚠️ Не удалось уведомить пользователя {row_data.get(SheetCols.TG_TAG, 'неизвестно')} об отклонении заявки №{row_index}.\n\nОшибка: {str(e)}"
                    )
        else:
            logger.error(f"Не найдены данные для строки {row_index} или отсутствует TG_ID")
    else:
        logger.error(f"Ошибка обновления статуса/причины для заявки №{row_index}")
        await update.message.reply_text(f"❌ Ошибка: не удалось обновить статус заявки №{row_index}")

    # Очищаем данные
    if 'admin_action_row_index' in context.user_data:
        del context.user_data['admin_action_row_index']
    
    return ConversationHandler.END
