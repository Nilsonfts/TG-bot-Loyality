# -*- coding: utf-8 -*-

import os
import json
import logging
import re
import datetime
import gspread
from google.oauth2.service_account import Credentials
from constants import SheetCols

# --- Environment Variables & Constants ---
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
SHEET_GID = int(os.getenv("SHEET_GID", 0))

logger = logging.getLogger(__name__)

# --- In-memory cache ---
INITIATOR_DATA_CACHE = {}
REGISTRATION_STATUS_CACHE = {}
CACHE_EXPIRATION_SECONDS = 300  # 5 minutes

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
    """Проверяет, есть ли у пользователя завершенная запись в таблице."""
    if user_id in REGISTRATION_STATUS_CACHE:
        cached_entry = REGISTRATION_STATUS_CACHE[user_id]
        if (datetime.datetime.now() - cached_entry['timestamp']).total_seconds() < 3600:
            return True
        else:
            del REGISTRATION_STATUS_CACHE[user_id]

    logger.info(f"User {user_id} not in status cache, checking sheet.")
    all_records = get_sheet_data()
    for row in all_records:
        if str(row.get(SheetCols.TG_ID)) == user_id and row.get(SheetCols.FIO_INITIATOR):
            REGISTRATION_STATUS_CACHE[user_id] = {'timestamp': datetime.datetime.now()}
            return True
    return False

def get_initiator_data(user_id: str):
    """Находит данные инициатора, проверяя кэш, затем Google Sheets."""
    if user_id in INITIATOR_DATA_CACHE:
        cached_entry = INITIATOR_DATA_CACHE[user_id]
        if (datetime.datetime.now() - cached_entry['timestamp']).total_seconds() < CACHE_EXPIRATION_SECONDS:
            return cached_entry['data']
        else:
            del INITIATOR_DATA_CACHE[user_id]

    all_records = get_sheet_data()
    user_data = None
    for row in reversed(all_records):
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
        INITIATOR_DATA_CACHE[user_id] = {'data': user_data.copy(), 'timestamp': datetime.datetime.now()}
    return user_data

def get_cards_from_sheet(user_id: str = None) -> list:
    """Получает заявки на карты."""
    all_records = get_sheet_data()
    valid_records = [r for r in all_records if r.get(SheetCols.OWNER_LAST_NAME_COL)]
    if user_id:
        user_cards = [r for r in valid_records if str(r.get(SheetCols.TG_ID)) == user_id]
    else:
        user_cards = valid_records
    return list(reversed(user_cards))

def find_card_by_number(card_number: str) -> gspread.cell.Cell | None:
    """Ищет карту по номеру телефона."""
    client = get_gspread_client()
    if not client: return None
    sheet = get_sheet_by_gid(client)
    if not sheet: return None
    try:
        headers = sheet.row_values(1)
        card_number_col_index = headers.index(SheetCols.CARD_NUMBER_COL) + 1
        cell = sheet.find(card_number, in_column=card_number_col_index)
        return cell
    except gspread.exceptions.CellNotFound:
        return None
    except (ValueError, Exception) as e:
        logger.error(f"Error finding card by number {card_number}: {e}")
        return None

def get_config_options(column_name: str) -> list[str]:
    """Получает список опций из справочника на листе 'Config'."""
    client = get_gspread_client()
    if not client: return []
    try:
        spreadsheet = client.open_by_key(GOOGLE_SHEET_KEY)
        config_sheet = spreadsheet.worksheet("Config")
        headers = config_sheet.row_values(1)
        if column_name not in headers:
            logger.warning(f"Column '{column_name}' not found in 'Config' sheet.")
            return []
        col_index = headers.index(column_name) + 1
        options = config_sheet.col_values(col_index)[1:]
        return [opt for opt in options if opt]
    except Exception as e:
        logger.error(f"Could not get config options for '{column_name}': {e}")
        return []

def update_cell_by_row(row_index: int, col_name: str, value: str) -> bool:
    """Обновляет одну ячейку в указанной строке."""
    client = get_gspread_client()
    if not client: return False
    sheet = get_sheet_by_gid(client)
    if not sheet: return False
    try:
        headers = sheet.row_values(1)
        col_index = headers.index(col_name) + 1
        sheet.update_cell(row_index, col_index, value)
        logger.info(f"Updated cell at row {row_index}, col '{col_name}' with value '{value}'.")
        return True
    except (ValueError, Exception) as e:
        logger.error(f"Failed to update cell at row {row_index}, col '{col_name}': {e}")
        return False

def get_row_data(row_index: int) -> dict | None:
    """Получает все данные из указанной строки."""
    client = get_gspread_client()
    if not client: return None
    sheet = get_sheet_by_gid(client)
    if not sheet: return None
    try:
        headers = sheet.row_values(1)
        values = sheet.row_values(row_index)
        return dict(zip(headers, values))
    except Exception as e:
        logger.error(f"Failed to get data for row {row_index}: {e}")
        return None

def write_to_sheet(data: dict, submission_time: str, tg_user_id: str) -> int | None:
    """Записывает одну строку и возвращает ИНДЕКС новой строки или None."""
    client = get_gspread_client()
    if not client: return None
    sheet = get_sheet_by_gid(client)
    if not sheet: return None
    try:
        headers = sheet.row_values(1)
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
            SheetCols.STATUS_COL: data.get('status', 'На согласовании')
        }
        final_row = [row_data.get(header, '') for header in headers]

        api_response = sheet.append_row(final_row, value_input_option='USER_ENTERED')
        
        if api_response.get('updates', {}).get('updatedRows', 0) > 0:
            updated_range = api_response['updates']['updatedRange']
            row_index = int(re.search(r'A(\d+)', updated_range).group(1))
            logger.info(f"SUCCESS: Row written at index {row_index} for user {tg_user_id}.")
            return row_index
        else:
            logger.error(f"FAILURE: API call succeeded but 0 rows were written for user {tg_user_id}.")
            return None
    except Exception as e:
        logger.error(f"Failed to write data to sheet for user {tg_user_id}: {e}", exc_info=True)
        return None
