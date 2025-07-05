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
REGISTRATION_CACHE = {}
CACHE_EXPIRATION_SECONDS = 300  # 5 minutes

def cache_user_data(user_id: str, data: dict):
    """Caches user data locally after a successful registration."""
    REGISTRATION_CACHE[user_id] = {
        'data': data.copy(),
        'timestamp': datetime.datetime.now()
    }
    logger.info(f"User {user_id} data cached for {CACHE_EXPIRATION_SECONDS} seconds.")

def get_initiator_data(user_id: str):
    """
    Finds initiator data, checking the local cache first, then Google Sheets.
    """
    if user_id in REGISTRATION_CACHE:
        cached_entry = REGISTRATION_CACHE[user_id]
        if (datetime.datetime.now() - cached_entry['timestamp']).total_seconds() < CACHE_EXPIRATION_SECONDS:
            logger.info(f"Found user {user_id} data in local cache.")
            return cached_entry['data']
        else:
            del REGISTRATION_CACHE[user_id]
            logger.info(f"Removed expired cache for user {user_id}.")

    logger.info(f"User {user_id} not in cache, fetching from Google Sheet.")
    return find_initiator_in_sheet_from_api(user_id)

def get_gspread_client():
    """Authenticates and returns a gspread client."""
    try:
        if GOOGLE_CREDS_JSON:
            creds_info = json.loads(GOOGLE_CREDS_JSON)
            scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
            return gspread.authorize(creds)
        return None
    except Exception as e:
        logger.error(f"Error authenticating with Google Sheets: {e}")
        return None

def get_sheet_by_gid(client, gid=SHEET_GID):
    """Opens a worksheet by its GID."""
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
    """Fetches all records from the specified worksheet using GID."""
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
    """Checks if a user has a completed registration record in the sheet."""
    all_records = get_sheet_data()
    for row in all_records:
        if str(row.get('ТГ Заполняющего')) == user_id and row.get('ФИО Инициатора'):
            return True
    return False

def find_initiator_in_sheet_from_api(user_id: str):
    """Finds the most recent data for a given user directly from the sheet."""
    all_records = get_sheet_data()
    for row in reversed(all_records):
        if str(row.get('ТГ Заполняющего')) == user_id:
            return {
                "initiator_username": row.get('Тег Telegram'),
                "initiator_email": row.get('Адрес электронной почты'),
                "initiator_fio": row.get('ФИО Инициатора'),
                "initiator_job_title": row.get('Должность'),
                "initiator_phone": row.get('Телефон инициатора'),
            }
    return None

def get_cards_from_sheet(user_id: str = None) -> list:
    """Retrieves card applications, filtering out registration-only rows."""
    all_records = get_sheet_data()
    valid_records = [r for r in all_records if r.get('Фамилия Владельца')]
    if user_id:
        user_cards = [r for r in valid_records if str(r.get('ТГ Заполняющего')) == user_id]
    else:
        user_cards = valid_records
    return list(reversed(user_cards))

def write_to_sheet(data: dict, submission_time: str, tg_user_id: str) -> bool:
    """
    Writes a new row to the sheet and verifies the API response.
    """
    client = get_gspread_client()
    if not client: return False
    
    sheet = get_sheet_by_gid(client)
    if not sheet: return False

    try:
        status = 'Заявка' if data.get('owner_last_name') else 'Регистрация'
        final_row = [
            submission_time, tg_user_id,
            data.get('initiator_username', '–'), data.get('initiator_email', ''),
            data.get('initiator_fio', ''), data.get('initiator_job_title', ''),
            data.get('initiator_phone', ''), data.get('owner_last_name', ''),
            data.get('owner_first_name', ''), data.get('reason', ''),
            data.get('card_type', ''), data.get('card_number', ''),
            data.get('category', ''), data.get('amount', ''),
            data.get('frequency', ''), data.get('issue_location', ''),
            status
        ]
        
        api_response = sheet.append_row(final_row, value_input_option='USER_ENTERED')
        logger.info(f"Google Sheets API response: {api_response}")

        if api_response.get('updates', {}).get('updatedRows', 0) > 0:
            logger.info(f"SUCCESS: API confirmed {api_response['updates']['updatedRows']} row(s) were written for user {tg_user_id}.")
            return True
        else:
            logger.error(f"FAILURE: API call succeeded but 0 rows were written for user {tg_user_id}. Possible permissions or sheet protection issue.")
            return False

    except Exception as e:
        logger.error(f"Failed to write data to sheet for user {tg_user_id}: {e}", exc_info=True)
        return False
