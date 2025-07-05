# -*- coding: utf-8 -*-

"""
This file contains all the logic for interacting with Google Sheets API.
"""

import os
import json
import logging
import gspread
from google.oauth2.service_account import Credentials

# --- Environment Variables ---
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")

logger = logging.getLogger(__name__)

def get_gspread_client():
    """Authenticates and returns a gspread client."""
    try:
        if GOOGLE_CREDS_JSON:
            creds_info = json.loads(GOOGLE_CREDS_JSON)
            scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
            return gspread.authorize(creds)
        else:
            logger.error("GOOGLE_CREDS_JSON environment variable not set.")
            return None
    except Exception as e:
        logger.error(f"Error authenticating with Google Sheets: {e}")
        return None

def get_sheet_data(sheet_name="sheet1"):
    """Fetches all records from the specified worksheet."""
    client = get_gspread_client()
    if not client or not GOOGLE_SHEET_KEY:
        return []
    try:
        sheet = client.open_by_key(GOOGLE_SHEET_KEY).worksheet(sheet_name)
        return sheet.get_all_records()
    except Exception as e:
        logger.error(f"Error fetching data from Google Sheet: {e}")
        return []

def is_user_registered(user_id: str) -> bool:
    """Checks if a user has a completed registration record."""
    all_records = get_sheet_data()
    for row in all_records:
        if str(row.get('ТГ Заполняющего')) == user_id and row.get('ФИО Инициатора'):
            return True
    return False

def find_initiator_in_sheet(user_id: str):
    """Finds the most recent data for a given user."""
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
    """Writes a new row to the sheet."""
    client = get_gspread_client()
    if not client or not GOOGLE_SHEET_KEY:
        return False
    try:
        sheet = client.open_by_key(GOOGLE_SHEET_KEY).sheet1
        # The status depends on whether it's a registration or a full application
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
        sheet.append_row(final_row, value_input_option='USER_ENTERED')
        logger.info(f"Successfully wrote a row for user {tg_user_id} with status '{status}'")
        return True
    except Exception as e:
        logger.error(f"Failed to write data to sheet for user {tg_user_id}: {e}")
        return False
