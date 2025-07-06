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
from constants import SheetCols # Импортируем константы

# --- Environment Variables & Constants ---
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
# Делаем GID настраиваемым через переменные окружения
SHEET_GID = int(os.getenv("SHEET_GID", 0))

logger = logging.getLogger(__name__)

# --- In-memory cache ---
INITIATOR_DATA_CACHE = {}
REGISTRATION_STATUS_CACHE = {}
CACHE_EXPIRATION_SECONDS = 300  # 5 minutes

def cache_user_registration_status(user_id: str, status: bool):
    """Кэширует статус регистрации пользователя (True или False)."""
    REGISTRATION_STATUS_CACHE[user_id] = {
        'status': status,
        'timestamp': datetime.datetime.now()
    }
    logger.info(f"User {user_id} registration status cached as {status}.")

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
        logger.error("GOOGLE_CREDS_JSON environment variable not set.")
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
    Сначала проверяет кэш. Кэширует и положительный, и отрицательный результат.
    """
    if user_id in REGISTRATION_STATUS_CACHE:
        cached_entry = REGISTRATION_STATUS_CACHE[user_id]
        # Кэш на 1 час для зарегистрированных, на 5 минут для незарегистрированных
        expiration = 3600 if cached_entry['status'] else 300
        if (datetime.datetime.now() - cached_entry['timestamp']).total_seconds() < expiration:
            logger.info(f"User {user_id} found in REGISTRATION_STATUS_CACHE with status: {cached_entry['status']}.")
            return cached_entry['status']
        else:
            del REGISTRATION_STATUS_CACHE[user_id]

    logger.info(f"User {user_id} not in status cache or cache expired, checking sheet.")
    all_records = get_sheet_data()
    for row in all_records:
        # Используем константы для надежности
        if str(row.get(SheetCols.TG_ID)) == user_id and row.get(SheetCols.FIO_INITIATOR):
            cache_user_registration_status(user_id, True)
            return True

    # Если цикл завершился и пользователь не найден, кэшируем отрицательный результат
    cache_user_registration_status(user_id, False)
    return False

def find_initiator_in_sheet_from_api(user_id: str):
    """Находит самые свежие данные для пользователя прямо из таблицы."""
    all_records = get_sheet_data()
    user_data = None
    for row in reversed(all_records):
        # Используем константы
        if str(row.get(SheetCols.TG_ID)) == user_id and row.get(SheetCols.FIO_INITIATOR):
            user_data = {
                "initiator_username": row.get(SheetCols.TG_TAG),
                "initiator_email": row.get(SheetCols.EMAIL),
                "initiator_fio": row.get(SheetCols.FIO_INITIATOR),
                "initiator_job_title": row.get(SheetCols.JOB_TITLE),
                "initiator_phone": row.get(SheetCols.PHONE_INITIATOR),
            }
            break 
    
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
    valid_records = [r for r in all_records if r.get(SheetCols.OWNER_LAST_NAME_COL)]
    if user_id:
        user_cards = [r for r in valid_records if str(r.get(SheetCols.TG_ID)) == user_id]
    else:
        user_cards = valid_records
    return list(reversed(user_cards))

def write_to_sheet(data: dict, submission_time: str, tg_user_id: str) -> bool:
    """Записывает одну строку со всеми данными в таблицу, устойчиво к порядку столбцов."""
    client = get_gspread_client()
    if not client: return False
    
    sheet = get_sheet_by_gid(client)
    if not sheet: return False

    try:
        headers = sheet.row_values(1)
        if not headers:
            logger.error(f"Could not retrieve headers from sheet with GID {SHEET_GID}.")
            return False

        row_data = {
            SheetCols.TIMESTAMP: submission_time,
            SheetCols.TG_ID: tg_user_id,
            SheetCols.TG_TAG: data.get('initiator_username', '–'),
            SheetCols.EMAIL: data.get('initiator_email', ''),
            SheetCols.FIO_INITIATOR: data.get('initiator_fio', ''),
            SheetCols.JOB_TITLE: data.get('initiator_job_title', ''),
            SheetCols.PHONE_INITIATOR: data.get('initiator_phone', ''),
            SheetCols.OWNER_LAST_NAME_COL: data.get('owner_last_name', ''),
            SheetCols.OWNER_FIRST_NAME_COL: data.get('owner_first_name', ''),
            SheetCols.REASON_COL: data.get('reason', ''),
            SheetCols.CARD_TYPE_COL: data.get('card_type', ''),
            SheetCols.CARD_NUMBER_COL: data.get('card_number', ''),
            SheetCols.CATEGORY_COL: data.get('category', ''),
            SheetCols.AMOUNT_COL: data.get('amount', ''),
            SheetCols.FREQUENCY_COL: data.get('frequency', ''),
            SheetCols.ISSUE_LOCATION_COL: data.get('issue_location', ''),
            SheetCols.STATUS_COL: data.get('status', 'Заявка')
        }

        final_row = [row_data.get(header, '') for header in headers]
        
        logger.info(f"Attempting to write row for user {tg_user_id}")

        api_response = sheet.append_row(final_row, value_input_option='USER_ENTERED')
        logger.info(f"Google Sheets API response: {api_response}")

        if api_response.get('updates', {}).get('updatedRows', 0) > 0:
            logger.info(f"SUCCESS: API confirmed {api_response['updates']['updatedRows']} row(s) were written for user {tg_user_id}.")
            if str(tg_user_id) not in REGISTRATION_STATUS_CACHE or not REGISTRATION_STATUS_CACHE[str(tg_user_id)]['status']:
                 cache_user_registration_status(str(tg_user_id), True)
            return True
        else:
            logger.error(f"FAILURE: API call succeeded but 0 rows were written for user {tg_user_id}. Data: {final_row}")
            return False

    except Exception as e:
        logger.error(f"Failed to write data to sheet for user {tg_user_id}: {e}", exc_info=True)
        return False
