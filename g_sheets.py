# -*- coding: utf-8 -*-

"""
This file contains all the logic for interacting with Google Sheets API,
including a local cache and enhanced debugging for write operations.
It uses GID for worksheet identification to be robust against renames.
"""

import os
import json
import logging
import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- Environment Variables & Constants ---
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
SHEET_GID = 0

logger = logging.getLogger(__name__)

# --- In-memory cache to handle Google API delays ---
# Этот кэш для данных инициатора
INITIATOR_DATA_CACHE = {}
# НОВЫЙ кэш для статуса регистрации, чтобы не дергать API постоянно
REGISTRATION_STATUS_CACHE = {}
CACHE_EXPIRATION_SECONDS = 300  # 5 minutes

def cache_user_registration_status(user_id: str):
    """Кэширует подтвержденный статус регистрации пользователя."""
    REGISTRATION_STATUS_CACHE[user_id] = {
        'timestamp': datetime.datetime.now()
    }
    logger.info(f"User {user_id} registration status cached.")

def get_initiator_data(user_id: str):
    """
    Находит данные инициатора, проверяя локальный кэш первым, затем Google Sheets.
    """
    if user_id in INITIATOR_DATA_CACHE:
        cached_entry = INITIATOR_DATA_CACHE[user_id]
        if (datetime.datetime.now() - cached_entry['timestamp']).total_seconds() < CACHE_EXPIRATION_SECONDS:
            logger.info(f"Found user {user_id} data in local cache.")
            return cached_entry['data']
        else:
            del INITIATOR_DATA_CACHE[user_id]
            logger.info(f"Removed expired cache for user {user_id}.")

    logger.info(f"User {user_id} not in cache, fetching from Google Sheet.")
    return find_initiator_in_sheet_from_api(user_id)

def get_gspread_client():
    """Аутентифицирует и возвращает gspread клиент."""
    try:
        if GOOGLE_CREDS_JSON:
            creds_info = json.loads(GOOGLE_CREDS_JSON)
            scopes = ["https.www.googleapis.com/auth/spreadsheets", "https.www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
            return gspread.authorize(creds)
        return None
    except Exception as e:
        logger.error(f"Error authenticating with Google Sheets: {e}")
        return None

def get_sheet_by_gid(client, gid=SHEET_GID):
    """Открывает рабочий лист по его GID."""
    try:
        spreadsheet = client.open_by_key(GOOGLE_SHEET_KEY)
        for worksheet in spreadsheet.worksheets():
            if worksheet.id == gid:
                return worksheet
        logger.error(f"Worksheet with GID '{gid}' not found.")
        return None
    except Exception as e:
        logger.error(f"Could not open worksheet by GID: {e}")
        return None

def get_sheet_data():
    """Получает все записи из указанного рабочего листа по GID."""
    client = get_gspread_client()
    if not client: return []
    
    sheet = get_sheet_by_gid(client)
    if not sheet: return []
    
    try:
        return sheet.get_all_records()
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching data from GID {SHEET_GID}: {e}")
        return []

def is_user_registered(user_id: str) -> bool:
    """
    Проверяет, есть ли у пользователя завершенная запись в таблице.
    СНАЧАЛА ПРОВЕРЯЕТ КЭШ.
    """
    # 1. Проверяем быстрый кэш статуса
    if user_id in REGISTRATION_STATUS_CACHE:
        cached_entry = REGISTRATION_STATUS_CACHE[user_id]
        if (datetime.datetime.now() - cached_entry['timestamp']).total_seconds() < 3600: # Кэш на час
            logger.info(f"User {user_id} found in REGISTRATION_STATUS_CACHE.")
            return True
        else:
            del REGISTRATION_STATUS_CACHE[user_id]

    # 2. Если в кэше нет, идем в таблицу
    logger.info(f"User {user_id} not in status cache, checking sheet.")
    all_records = get_sheet_data()
    for row in all_records:
        # Проверяем по ID и наличию ФИО, что это полноценная запись
        if str(row.get('ТГ Заполняющего')) == user_id and row.get('ФИО Инициатора'):
            # Если нашли, кэшируем, чтобы больше не искать
            cache_user_registration_status(user_id)
            return True
    return False

def find_initiator_in_sheet_from_api(user_id: str):
    """Находит самые свежие данные для пользователя прямо из таблицы."""
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
            break # Нашли самую последнюю, выходим
    
    # Кэшируем найденные данные
    if user_data:
        INITIATOR_DATA_CACHE[user_id] = {
            'data': user_data.copy(),
            'timestamp': datetime.datetime.now()
        }
    
    return user_data

def get_cards_from_sheet(user_id: str = None) -> list:
    """Получает заявки на карты, отфильтровывая строки только с регистрацией."""
    all_records = get_sheet_data()
    # Валидной записью теперь считается та, где есть Фамилия Владельца
    valid_records = [r for r in all_records if r.get('Фамилия Владельца')]
    if user_id:
        user_cards = [r for r in valid_records if str(r.get('ТГ Заполняющего')) == user_id]
    else:
        user_cards = valid_records
    return list(reversed(user_cards))

def write_to_sheet(data: dict, submission_time: str, tg_user_id: str) -> bool:
    """Записывает одну строку со всеми данными в таблицу."""
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
            data.get('status', 'Заявка') # Статус теперь берется из данных
        ]
        
        api_response = sheet.append_row(final_row, value_input_option='USER_ENTERED')
        logger.info(f"Google Sheets API response: {api_response}")

        if api_response.get('updates', {}).get('updatedRows', 0) > 0:
            logger.info(f"SUCCESS: API confirmed {api_response['updates']['updatedRows']} row(s) were written for user {tg_user_id}.")
            return True
        else:
            logger.error(f"FAILURE: API call succeeded but 0 rows were written for user {tg_user_id}.")
            return False

    except Exception as e:
        logger.error(f"Failed to write data to sheet for user {tg_user_id}: {e}", exc_info=True)
        return False
