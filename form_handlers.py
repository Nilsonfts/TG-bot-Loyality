# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timezone, timedelta
import re
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

import g_sheets
import navigation_handlers
import admin_handlers
import utils
from constants import (
    OWNER_LAST_NAME, OWNER_FIRST_NAME, REASON, CARD_TYPE, CARD_NUMBER, CATEGORY,
    AMOUNT, FREQUENCY, ISSUE_LOCATION, CONFIRMATION
)

logger = logging.getLogger(__name__)

def format_summary(data: dict) -> str:
    """Форматирует итоговое сообщение перед отправкой."""
    owner = f"{data.get('owner_first_name', '')} {data.get('owner_last_name', '')}".strip()
    card_type = data.get('card_type')
    amount_label = 'Скидка' if card_type == 'Скидка' else 'Сумма'
    amount_unit = '%' if card_type == 'Скидка' else ' ₽'
    return (f"<b>Пожалуйста, проверьте итоговую заявку:</b>\n\n"
            f"--- <b>Инициатор</b> ---\n"
            f"👤 ФИО: {data.get('initiator_fio', '-')}\n"
            f"📧 Почта: {data.get('initiator_email', '-')}\n"
            f"--- <b>Карта</b> ---\n"
            f"💳 Владелец: {owner}\n"
            f"📞 Номер: {data.get('card_number', '-')}\n"
            f"✨ Тип: {card_type}\n"
            f"💰 {amount_label}: {data.get('amount', '0')}{amount_unit}\n"
            f"📈 Статья: {data.get('category', '-')}\n"
            f"🔄 Периодичность: {data.get('frequency', '-')}\n"
            f"📍 Город/Бар: {data.get('issue_location', '-')}\n\n"
            "<i>Все верно?</i>")

async def start_form_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог подачи заявки для УЖЕ ЗАРЕГИСТРИРОВАННОГО пользователя."""
    context.user_data.clear()
    user_id = str(update.effective_user.id)
    
    logger.info(f"🔄 Начинаем подачу заявки для пользователя {user_id}")

    initiator_data = g_sheets.get_initiator_data(user_id)
    logger.info(f"📊 Результат get_initiator_data: {initiator_data}")
    
    # Если данных нет в Google Sheets, пробуем получить из локальной БД
    if not initiator_data:
        logger.info(f"📋 Данные инициатора не найдены в Google Sheets для пользователя {user_id}, проверяем локальную БД")
        try:
            utils.init_local_db()  # Убеждаемся что БД инициализирована
            initiator_data = utils.get_initiator_from_local_db(user_id)
            if initiator_data:
                logger.info(f"✅ Данные инициатора найдены в локальной БД: {initiator_data}")
            else:
                logger.warning(f"❌ Данные инициатора НЕ найдены в локальной БД")
        except Exception as e:
            logger.error(f"💥 Ошибка получения данных из локальной БД: {e}")
    
    if not initiator_data:
        logger.error(f"🚫 Данные пользователя {user_id} не найдены ни в Google Sheets, ни в локальной БД")
        await update.message.reply_text(
            "❌ <b>Ошибка:</b> не удалось найти ваши данные.\n\n"
            "🔄 Пожалуйста, пройдите регистрацию заново через главное меню.",
            parse_mode=ParseMode.HTML
        )
        return await navigation_handlers.end_conversation_and_show_menu(update, context)

    logger.info(f"✅ Данные инициатора найдены, добавляем в context.user_data")
    context.user_data.update(initiator_data)
    
    await update.message.reply_text(
        "📝 <b>Начинаем подачу новой заявки</b>\n\n"
        "Введите <b>Фамилию</b> владельца карты:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    logger.info(f"📤 Сообщение отправлено, переходим к состоянию OWNER_LAST_NAME")
    return OWNER_LAST_NAME

async def get_owner_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    last_name = utils.sanitize_input(update.message.text, 50)
    if len(last_name) < 2:
        await update.message.reply_text("❌ Фамилия слишком короткая. Введите корректную фамилию.")
        return OWNER_LAST_NAME
    
    context.user_data['owner_last_name'] = last_name
    await update.message.reply_text("<b>Имя</b> владельца карты.", parse_mode=ParseMode.HTML)
    return OWNER_FIRST_NAME

async def get_owner_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    first_name = utils.sanitize_input(update.message.text, 50)
    if len(first_name) < 2:
        await update.message.reply_text("❌ Имя слишком короткое. Введите корректное имя.")
        return OWNER_FIRST_NAME
    
    context.user_data['owner_first_name'] = first_name
    await update.message.reply_text("Причина выдачи?")
    return REASON

async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['reason'] = update.message.text
    keyboard = [[InlineKeyboardButton("Бартер", callback_data="Бартер"), InlineKeyboardButton("Скидка", callback_data="Скидка")]]
    await update.message.reply_text("Тип карты?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CARD_TYPE

async def get_card_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['card_type'] = query.data
    await query.edit_message_text(f"Выбрано: {query.data}.\n\nНомер карты (телефон через 8)?")
    return CARD_NUMBER

async def get_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    number = update.message.text.strip()
    
    if not utils.validate_phone_number(number):
        await update.message.reply_text("❌ Неверный формат номера карты. Требуется 11 цифр, начиная с 8.\n\nПример: 89991234567")
        return CARD_NUMBER
    
    context.user_data['card_number'] = number
    keyboard = [[InlineKeyboardButton("АРТ", callback_data="АРТ"), InlineKeyboardButton("МАРКЕТ", callback_data="МАРКЕТ")], [InlineKeyboardButton("Операционный блок", callback_data="Операционный блок")], [InlineKeyboardButton("СКИДКА", callback_data="СКИДКА"), InlineKeyboardButton("Сертификат", callback_data="Сертификат")], [InlineKeyboardButton("Учредители", callback_data="Учредители")]]
    await update.message.reply_text("Статья пополнения?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CATEGORY

async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['category'] = query.data
    prompt = "Сумма бартера?" if context.user_data['card_type'] == "Бартер" else "Процент скидки?"
    await query.edit_message_text(f"Статья: {query.data}.\n\n{prompt}")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount_text = update.message.text.strip()
    card_type = context.user_data.get('card_type', '')
    
    is_valid, error_msg = utils.validate_amount(amount_text, card_type)
    if not is_valid:
        await update.message.reply_text(f"❌ {error_msg}\n\nПопробуйте еще раз:")
        return AMOUNT
    
    context.user_data['amount'] = amount_text
    keyboard = [[InlineKeyboardButton("Разовая", callback_data="Разовая")], [InlineKeyboardButton("Дополнить к балансу", callback_data="Дополнить к балансу")], [InlineKeyboardButton("Замена номера карты", callback_data="Замена номера карты")]]
    await update.message.reply_text("Периодичность?", reply_markup=InlineKeyboardMarkup(keyboard))
    return FREQUENCY

async def get_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['frequency'] = query.data
    await query.edit_message_text(f"Выбрано: {query.data}.\n\n<b>Город/Бар выдачи?</b>", parse_mode=ParseMode.HTML)
    return ISSUE_LOCATION

async def get_issue_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['issue_location'] = update.message.text
    summary = format_summary(context.user_data)
    keyboard = [[InlineKeyboardButton("✅ Да, все верно", callback_data="submit"), InlineKeyboardButton("❌ Нет, заполнить заново", callback_data="restart")]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRMATION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финализирует и отправляет заявку, используя новую функцию write_row."""
    query = update.callback_query
    await query.answer(text="Отправляю заявку...", show_alert=False)
    
    user_id = str(query.from_user.id)
    
    # --- ИЗМЕНЕНИЕ ЗДЕСЬ ---
    # Собираем данные в единый словарь для новой функции write_row
    data_to_write = context.user_data.copy() # Копируем все, что уже есть
    
    # Московское время (+3 часа от UTC)
    moscow_tz = timezone(timedelta(hours=3))
    moscow_time = datetime.now(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
    data_to_write['submission_time'] = moscow_time
    
    data_to_write['tg_user_id'] = user_id
    data_to_write['status'] = 'На согласовании'  # Изменено с 'Заявка' на более понятный статус
    
    # Убеждаемся, что username указан корректно
    if not data_to_write.get('initiator_username'):
        data_to_write['initiator_username'] = f"@{query.from_user.username}" if query.from_user.username else '–'

    # Детальное логирование данных перед записью
    logger.info(f"=== ДАННЫЕ ДЛЯ ЗАПИСИ В GOOGLE SHEETS ===")
    logger.info(f"Пользователь: {user_id}")
    for key, value in data_to_write.items():
        logger.info(f"  {key}: '{value}'")
    logger.info(f"==========================================")

    # Инициализируем локальную БД если еще не создана
    utils.init_local_db()
    
    # Сохраняем в локальную БД
    local_app_id = utils.save_application_to_local_db(data_to_write)
    
    # Вызываем новую, "умную" функцию записи в Google Sheets
    google_success = g_sheets.write_row(data_to_write)

    if google_success or local_app_id:
        if google_success:
            status_text = "\n\n<b>Статус:</b> ✅ Заявка успешно отправлена на согласование.\n\n" \
                         "📋 <i>Мы уведомим вас, как только заявка будет рассмотрена!</i>"
        else:
            status_text = "\n\n<b>Статус:</b> ✅ Заявка сохранена локально и будет отправлена на согласование после синхронизации.\n\n" \
                         "📋 <i>Мы уведомим вас, как только заявка будет рассмотрена!</i>"
        
        # Уведомляем админа о новой заявке только если удалось сохранить в Google Sheets
        if google_success:
            boss_id = os.getenv("BOSS_ID")
            if boss_id:
                try:
                    # ИСПРАВЛЕНИЕ: Получаем данные ПОСЛЕ добавления новой записи
                    all_records = g_sheets.get_sheet_data()
                    if all_records:
                        # Новая запись - это последняя запись в массиве
                        row_index = len(all_records) - 1  # Индекс последней записи (для get_row_data)
                        logger.info(f"📊 Всего записей после добавления: {len(all_records)}, row_index для админа: {row_index}")
                        
                        notification = admin_handlers.format_admin_notification(data_to_write, row_index)
                        
                        await context.bot.send_message(
                            chat_id=boss_id,
                            text=notification["text"],
                            reply_markup=notification["reply_markup"],
                            parse_mode=ParseMode.HTML
                        )
                        logger.info(f"Админ уведомлен о новой заявке от пользователя {user_id}")
                    else:
                        logger.error("❌ Не удалось получить обновленные данные таблицы")
                except Exception as e:
                    logger.error(f"Не удалось уведомить админа о новой заявке: {e}")
                    # Логируем детали для отладки
                    logger.error(f"data_to_write содержит: {data_to_write}")
                    import traceback
                    logger.error(f"Трейсбек ошибки: {traceback.format_exc()}")
    else:
        status_text = "\n\n<b>Статус:</b> ❌ Ошибка! Не удалось сохранить заявку. Попробуйте позже."
    
    await query.edit_message_text(text=query.message.text_html + status_text, parse_mode=ParseMode.HTML, reply_markup=None)
    
    context.user_data.clear()
    await navigation_handlers.main_menu_command(update, context)

    return ConversationHandler.END

async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Перезапускает диалог подачи заявки с самого начала."""
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    return await start_form_conversation(update, context)
