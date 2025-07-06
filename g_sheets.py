# -*- coding: utf-8 -*-

import os
import json
import logging
import datetime
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# Кэши остаются как есть
INITIATOR_DATA_CACHE = {}
REGISTRATION_STATUS_CACHE = {}
CACHE_EXPIRATION_SECONDS = 300

def get_gspread_client():
    """
    Аутентифицирует и возвращает gspread клиент.
    Финальная версия с прямой инициализацией и тестовым запросом.
    """
    GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
    
    if not GOOGLE_CREDS_JSON:
        logger.critical("КРИТИЧЕСКАЯ ОШИБКА: Переменная GOOGLE_CREDS_JSON не найдена или пуста!")
        return None
    
    logger.info("get_gspread_client: Шаг 1/5: Переменная GOOGLE_CREDS_JSON найдена.")

    try:
        creds_info = json.loads(GOOGLE_CREDS_JSON)
        logger.info("get_gspread_client: Шаг 2/5: JSON-ключ успешно распарсен.")
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        logger.info("get_gspread_client: Шаг 3/5: Объект credentials создан успешно.")
        
        # --- ИЗМЕНЕНИЕ ---
        # Вместо gspread.authorize() используем прямой конструктор gspread.Client
        # Это более современный и надежный способ
        client = gspread.Client(auth=creds)
        logger.info("get_gspread_client: Шаг 4/5: Клиент gspread.Client инициализирован.")

        # --- САМОЕ ГЛАВНОЕ: ПРОВЕРОЧНЫЙ ЗАПРОС ---
        # Пытаемся выполнить простой запрос, чтобы убедиться, что токен РАБОТАЕТ.
        # Если ошибка произойдет, она случится именно здесь.
        client.list_spreadsheet_files()
        logger.info("get_gspread_client: Шаг 5/5: Проверочный запрос к Google API прошел успешно. Клиент готов к работе.")
        
        return client

    except json.JSONDecodeError as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось распарсить GOOGLE_CREDS_JSON. Проверьте, что это валидный JSON. Ошибка: {e}")
        return None
    except Exception as e:
        # Если ошибка возникает здесь, это на 100% проблема с правами или самим проектом Google
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА на этапе авторизации или тестового запроса в Google: {e}", exc_info=True)
        return None

def get_sheet_by_gid(client, gid=None):
    """Открывает рабочий лист по его GID."""
    GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
    SHEET_GID = int(os.getenv("SHEET_GID", 0))
    
    if gid is None: gid = SHEET_GID

    if not GOOGLE_SHEET_KEY:
        logger.critical("КРИТИЧЕСКАЯ ОШИБКА: Переменная GOOGLE_SHEET_KEY не найдена!")
        return None

    try:
        spreadsheet = client.open_by_key(GOOGLE_SHEET_KEY)
        for worksheet in spreadsheet.worksheets():
            if worksheet.id == gid:
                logger.info(f"Успешно открыт лист '{worksheet.title}' с GID {gid}.")
                return worksheet
        logger.error(f"ОШИБКА: Лист с GID '{gid}' не найден в таблице.")
        return None
    except gspread.exceptions.APIError as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА API Google: Не удалось открыть таблицу. Проверьте, что вы поделились таблицей с email'ом бота ({client.auth.service_account_email}) и что ключ GOOGLE_SHEET_KEY верный. Детали: {e}")
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при открытии листа: {e}", exc_info=True)
        return None

# Остальные функции остаются без изменений, я привожу их для полноты файла

def cache_user_registration_status(user_id: str):
    REGISTRATION_STATUS_CACHE[user_id] = {'timestamp': datetime.datetime.now()}
    logger.info(f"User {user_id} registration status cached.")

def get_initiator_data(user_id: str):
    if user_id in INITIATOR_DATA_CACHE:
        cached_entry = INITIATOR_DATA_CACHE[user_id]
        if (datetime.datetime.now() - cached_entry['timestamp']).total_seconds() < CACHE_EXPIRATION_SECONDS:
            return cached_entry['data']
        else:
            del INITIATOR_DATA_CACHE[user_id]
    return find_initiator_in_sheet_from_api(user_id)

def get_sheet_data():
    client = get_gspread_client()
    if not client: return []
    sheet = get_sheet_by_gid(client)
    if not sheet: return []
    try:
        return sheet.get_all_records()
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching data: {e}")
        return []

def is_user_registered(user_id: str) -> bool:
    if user_id in REGISTRATION_STATUS_CACHE:
        cached_entry = REGISTRATION_STATUS_CACHE[user_id]
        if (datetime.datetime.now() - cached_entry['timestamp']).total_seconds() < 3600:
            return True
        else:
            del REGISTRATION_STATUS_CACHE[user_id]

    logger.info(f"User {user_id} not in status cache, checking sheet.")
    all_records = get_sheet_data()
    for row in all_records:
        if str(row.get('ТГ Заполняющего')) == user_id and row.get('ФИО Инициатора'):
            cache_user_registration_status(user_id)
            return True
    return False

def find_initiator_in_sheet_from_api(user_id: str):
    all_records = get_sheet_data()
    user_data = None
    for row in reversed(all_records):
        if str(row.get('ТГ Заполняющего')) == user_id and row.get('ФИО Инициатора'):
            user_data = {
                "initiator_username": row.get('Тег Telegram'),
                "initiator_email": row.get('Адрес электронной почты'),
                "initiator_fio": row.get('ФИО Инициатора'),
                "initiator_job_title": row.get('Должность'),
                "initiator_phone": row.get('Телефон инициатора'),
            }
            break
    if user_data:
        INITIATOR_DATA_CACHE[user_id] = {'data': user_data.copy(), 'timestamp': datetime.datetime.now()}
    return user_data

def get_cards_from_sheet(user_id: str = None) -> list:
    all_records = get_sheet_data()
    valid_records = [r for r in all_records if r.get('Фамилия Владельца')]
    if user_id:
        user_cards = [r for r in valid_records if str(r.get('ТГ Заполняющего')) == user_id]
    else:
        user_cards = valid_records
    return list(reversed(user_cards))

def write_to_sheet(data: dict, submission_time: str, tg_user_id: str) -> bool:
    client = get_gspread_client()
    if not client: return False
    sheet = get_sheet_by_gid(client)
    if not sheet: return False
    try:
        final_row = [
            submission_time, tg_user_id,
            data.get('initiator_username', '–'), data.get('initiator_email', ''),
            data.get('initiator_fio', ''), data.get('initiator_job_title', ''),
            data.get('initiator_phone', ''), data.get('owner_last_name', ''),
            data.get('owner_first_name', ''), data.get('reason', ''),
            data.get('card_type', ''), data.get('card_number', ''),
            data.get('category', ''), data.get('amount', ''),
            data.get('frequency', ''), data.get('issue_location', ''),
            data.get('status', 'Заявка')
        ]
        api_response = sheet.append_row(final_row, value_input_option='USER_ENTERED')
        if api_response.get('updates', {}).get('updatedRows', 0) > 0:
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"Failed to write data to sheet for user {tg_user_id}: {e}", exc_info=True)
        return False
