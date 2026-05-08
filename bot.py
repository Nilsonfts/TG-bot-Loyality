# -*- coding: utf-8 -*-

"""
Главный файл бота.
Инициализирует бота, настраивает обработчики из модулей
и запускает цикл опроса.
"""

import logging
import os
import html
import traceback
import datetime
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)

import constants
# --- ОБНОВЛЕННЫЕ ИМПОРТЫ ---
import navigation_handlers
import registration_handlers # Новый обработчик
import form_handlers
import search_handlers
import settings_handlers
import admin_handlers
import reports  # Новый импорт для отчетов
import utils
import g_sheets

# --- НАСТРОЙКА СРЕДЫ И ЛОГГИРОВАНИЯ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
# Снижаем шум от HTTP-клиента в PTB
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


async def global_error_handler(update: object, context) -> None:
    """Глобальный обработчик исключений: логирует и сообщает админу."""
    logger.error("Необработанное исключение:", exc_info=context.error)
    boss_id = os.getenv("BOSS_ID")
    if not boss_id:
        return
    try:
        tb = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))[-3000:]
        upd_repr = ""
        if isinstance(update, Update):
            who = update.effective_user.id if update.effective_user else "?"
            upd_repr = f"\nСобытие от пользователя <code>{who}</code>"
        msg = (
            f"⚠️ <b>Сбой в боте</b>{upd_repr}\n\n"
            f"<pre>{html.escape(tb)}</pre>"
        )
        await context.bot.send_message(chat_id=boss_id, text=msg, parse_mode=ParseMode.HTML)
    except Exception as notify_exc:  # noqa: BLE001
        logger.error(f"Не удалось уведомить админа об ошибке: {notify_exc}")


def _admin_only(func):
    async def wrapper(update, context, *args, **kwargs):
        boss_id = os.getenv("BOSS_ID")
        if not boss_id or str(update.effective_user.id) != boss_id:
            await update.message.reply_text("⛔️ Команда доступна только администратору.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


@_admin_only
async def admin_stats_command(update, context):
    import asyncio
    stats = await asyncio.to_thread(utils.get_statistics)
    if not stats or 'error' in stats:
        await update.message.reply_text("📊 Статистика недоступна.")
        return
    by_status = stats.get('by_status', {}) or {}
    by_type = stats.get('by_card_type', {}) or {}
    text = [f"<b>📊 Статистика</b>\nВсего заявок: <b>{stats.get('total', 0)}</b>"]
    if by_status:
        text.append("\n<b>По статусам:</b>")
        for k, v in by_status.items():
            text.append(f"• {k}: <b>{v}</b>")
    if by_type:
        text.append("\n<b>По типам карт:</b>")
        for k, v in by_type.items():
            text.append(f"• {k}: <b>{v}</b>")
    await update.message.reply_text("\n".join(text), parse_mode=ParseMode.HTML)


@_admin_only
async def admin_pending_command(update, context):
    import asyncio
    pending = await asyncio.to_thread(g_sheets.search_applications_with_status, "На согласовании")
    count = len(pending)
    if count == 0:
        await update.message.reply_text("✅ Ожидающих заявок нет.")
        return
    lines = [f"<b>🔥 Ожидает решения: {count}</b>\n"]
    from constants import SheetCols
    for r in pending[-15:]:
        owner = f"{r.get(SheetCols.OWNER_FIRST_NAME_COL,'')} {r.get(SheetCols.OWNER_LAST_NAME_COL,'')}".strip() or '-'
        lines.append(
            f"• <b>{owner}</b> | карта <code>{r.get(SheetCols.CARD_NUMBER_COL,'-')}</code> | "
            f"{r.get(SheetCols.AMOUNT_COL,'-')} | {r.get(SheetCols.TIMESTAMP,'-')}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@_admin_only
async def admin_diag_command(update, context):
    """Быстрая диагностика Google Sheets и окружения."""
    import asyncio
    headers = await asyncio.to_thread(g_sheets.debug_sheet_headers)
    db_path = utils.get_db_path()
    has_db = os.path.exists(db_path)
    text = (
        "<b>🔧 Диагностика</b>\n"
        f"• GOOGLE_CREDS_JSON: {'✅' if os.getenv('GOOGLE_CREDS_JSON') else '❌'}\n"
        f"• GOOGLE_SHEET_KEY: {'✅' if os.getenv('GOOGLE_SHEET_KEY') else '❌'}\n"
        f"• BOSS_ID: {'✅' if os.getenv('BOSS_ID') else '❌'}\n"
        f"• Заголовков Sheets: <b>{len(headers) if headers else 0}</b>\n"
        f"• SQLite файл: {'✅' if has_db else '❌'} (<code>{db_path}</code>)\n"
        f"• PENDING_ACTIONS в памяти: {len(g_sheets.PENDING_ACTIONS)}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


def main() -> None:
    """Инициализирует и запускает бота."""
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен.")
        return

    # Инициализируем локальную базу данных
    if utils.init_local_db():
        logger.info("Локальная база данных успешно инициализирована")
    else:
        logger.warning("Не удалось инициализировать локальную базу данных, работаем только с Google Sheets")

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # --- Фильтры для кнопок меню ---
    filters_map = {
        'reg': filters.Regex(f"^{constants.MENU_TEXT_REGISTER}$"),
        'submit': filters.Regex(f"^{constants.MENU_TEXT_SUBMIT}$"),
        'search': filters.Regex(f"^{constants.MENU_TEXT_SEARCH}$"),
        'settings': filters.Regex(f"^{constants.MENU_TEXT_SETTINGS}$"),
        'main': filters.Regex(f"^{constants.MENU_TEXT_MAIN_MENU}$"),
        'cancel_form': filters.Regex(f"^{constants.MENU_TEXT_CANCEL_FORM}$"),
    }

    combined_menu_filter = (
        filters_map['reg'] | filters_map['submit'] | filters_map['search'] |
        filters_map['settings'] | filters_map['main'] | filters_map['cancel_form']
    )
    text_filter = filters.TEXT & ~filters.COMMAND & ~combined_menu_filter

    # --- Обработчики отмены и возврата в меню ---
    fallback_handler = MessageHandler(filters_map['main'], navigation_handlers.end_conversation_and_show_menu)
    cancel_form_handler = MessageHandler(filters_map['cancel_form'], navigation_handlers.end_conversation_and_show_menu)
    cancel_handler = CommandHandler("cancel", navigation_handlers.cancel)

    # --- ДИАЛОГ РЕГИСТРАЦИИ ---
    reg_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['reg'], registration_handlers.start_registration)],
        states={
            constants.REGISTER_CONTACT: [MessageHandler(filters.CONTACT, registration_handlers.handle_contact)],
            constants.REGISTER_FIO: [MessageHandler(text_filter, registration_handlers.get_fio)],
            constants.REGISTER_EMAIL: [MessageHandler(text_filter, registration_handlers.get_email)],
            constants.REGISTER_JOB_TITLE: [MessageHandler(text_filter, registration_handlers.get_job_title_and_finish)],
        },
        fallbacks=[fallback_handler, cancel_form_handler, cancel_handler],
    )

    # --- ДИАЛОГ ПОДАЧИ ЗАЯВКИ ---
    form_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['submit'], form_handlers.start_form_conversation)],
        states={
            constants.OWNER_LAST_NAME: [MessageHandler(text_filter, form_handlers.get_owner_last_name)],
            constants.OWNER_FIRST_NAME: [MessageHandler(text_filter, form_handlers.get_owner_first_name)],
            constants.REASON: [MessageHandler(text_filter, form_handlers.get_reason)],
            constants.CARD_TYPE: [CallbackQueryHandler(form_handlers.get_card_type, pattern=r"^(Бартер сотрудники|Бартер маркетинг|Скидка)$")],
            constants.CARD_NUMBER: [MessageHandler(text_filter, form_handlers.get_card_number)],
            constants.CATEGORY: [CallbackQueryHandler(form_handlers.get_category, pattern=r"^(АРТ|МАРКЕТ|Операционный блок|СКИДКА|Сертификат|Учредители)$")],
            constants.AMOUNT: [MessageHandler(text_filter, form_handlers.get_amount)],
            constants.FREQUENCY: [CallbackQueryHandler(form_handlers.get_frequency, pattern=r"^(Разовая|Ежемесячная|Дополнить к балансу)$")],
            constants.ISSUE_LOCATION: [CallbackQueryHandler(form_handlers.get_issue_location, pattern=r"^city:")],
            constants.CONFIRMATION: [
                CallbackQueryHandler(form_handlers.submit, "^submit$"),
                CallbackQueryHandler(form_handlers.restart_conversation, "^restart$")
            ],
        },
        fallbacks=[fallback_handler, cancel_form_handler, cancel_handler],
    )

    # --- ДИАЛОГ ПОИСКА ---
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters_map['search'], search_handlers.search_command)],
        states={
            constants.SEARCH_CHOOSE_FIELD: [CallbackQueryHandler(search_handlers.search_field_chosen, pattern=r"^search_by_(name|phone)$")],
            constants.AWAIT_SEARCH_QUERY: [MessageHandler(text_filter, search_handlers.perform_search)]
        },
        fallbacks=[fallback_handler, cancel_form_handler, cancel_handler],
    )

    # --- ДИАЛОГ АДМИНСКИХ ДЕЙСТВИЙ ---
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_handlers.reject_request_start, f"^{constants.CALLBACK_REJECT_PREFIX}")],
        states={
            constants.AWAIT_REJECT_REASON: [MessageHandler(text_filter, admin_handlers.reject_request_reason)]
        },
        fallbacks=[cancel_handler],
    )

    # --- Добавляем все обработчики в приложение ---
    application.add_handler(CommandHandler("start", navigation_handlers.start_command))
    application.add_handler(CommandHandler("stats", admin_stats_command))
    application.add_handler(CommandHandler("pending", admin_pending_command))
    application.add_handler(CommandHandler("diag", admin_diag_command))
    application.add_handler(MessageHandler(filters_map['main'], navigation_handlers.main_menu_command))
    application.add_handler(MessageHandler(filters_map['cancel_form'], navigation_handlers.end_conversation_and_show_menu))
    application.add_handler(MessageHandler(filters_map['settings'], settings_handlers.show_settings))

    application.add_handler(reg_conv) # Новый диалог
    application.add_handler(form_conv)
    application.add_handler(search_conv)
    application.add_handler(admin_conv) # Админский диалог

    # Обработчики колбэков для меню настроек
    # ... (здесь ваш код для обработчиков кнопок из settings_handlers остается без изменений)
    application.add_handler(CallbackQueryHandler(settings_handlers.my_cards_command, "^settings_my_cards$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.help_callback, "^help_show$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.stats_callback, "^stats_show$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.export_csv_callback, "^export_csv$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.back_to_settings_callback, "^back_to_settings$"))
    application.add_handler(CallbackQueryHandler(settings_handlers.handle_pagination, r"^paginate_"))
    application.add_handler(CallbackQueryHandler(settings_handlers.noop_callback, r"^noop$"))

    # Обработчики админских колбэков (отдельно от ConversationHandler для корректной работы)
    application.add_handler(CallbackQueryHandler(admin_handlers.approve_request, f"^{constants.CALLBACK_APPROVE_PREFIX}"))
    
    # ВАЖНО: CallbackQueryHandler для reject должен быть в ConversationHandler выше!

    # Добавляем периодические задачи
    job_queue = application.job_queue
    if job_queue:
        # Ежедневные отчеты админу в 9:00
        job_queue.run_daily(reports.send_daily_summary, time=datetime.time(hour=9, minute=0), days=(0, 1, 2, 3, 4, 5, 6))
        
        # Еженедельная аналитика по понедельникам в 10:00
        job_queue.run_daily(reports.send_weekly_analytics, time=datetime.time(hour=10, minute=0), days=(0,))  # 0 = понедельник
        
        # Напоминания пользователям по средам в 14:00
        job_queue.run_daily(reports.send_user_reminders, time=datetime.time(hour=14, minute=0), days=(2,))  # 2 = среда
        
        # Очистка кэша каждые 6 часов (оборачиваем sync-функцию в async)
        async def _cleanup_cache_job(ctx):
            import asyncio as _a
            await _a.to_thread(utils.cleanup_old_cache)

        async def _backup_db_job(ctx):
            import asyncio as _a
            await _a.to_thread(utils.backup_local_db)

        job_queue.run_repeating(_cleanup_cache_job, interval=21600, first=10)  # 21600 сек = 6 часов

        # Резервное копирование БД каждый день в 02:00
        job_queue.run_daily(_backup_db_job, time=datetime.time(hour=2, minute=0), days=(0, 1, 2, 3, 4, 5, 6))
        
        logger.info("Все периодические задачи настроены")

    # Глобальный обработчик исключений
    application.add_error_handler(global_error_handler)

    # --- Запускаем бота ---
    logger.info("Бот запускается с разделенной логикой регистрации...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
