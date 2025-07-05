# -*- coding: utf-8 -*-

"""
This file contains all the logic for interacting with Google Sheets API,
including a local cache to mitigate API propagation delays.
including a local cache and enhanced debugging for write operations.
It uses GID for worksheet identification to be robust against renames.
"""

import os
@@ -15,45 +16,38 @@
# --- Environment Variables & Constants ---
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
SHEET_NAME = "РЕГИСТРАЦИЯ КАРТ ЕВГЕНИЧ"
SHEET_GID = 0  # <<< ИСПОЛЬЗУЕМ GID ВМЕСТО ИМЕНИ >>>

logger = logging.getLogger(__name__)

# --- NEW: In-memory cache to handle Google API delays ---
# --- In-memory cache to handle Google API delays ---
REGISTRATION_CACHE = {}
CACHE_EXPIRATION_SECONDS = 300  # 5 minutes

def cache_user_data(user_id: str, data: dict):
    """Caches user data locally after a successful registration."""
    REGISTRATION_CACHE[user_id] = {
        'data': data.copy(),  # Store a copy of the data
        'data': data.copy(),
        'timestamp': datetime.datetime.now()
    }
    logger.info(f"User {user_id} data cached for {CACHE_EXPIRATION_SECONDS} seconds.")

def get_initiator_data(user_id: str):
    """
    Finds initiator data, checking the local cache first, then Google Sheets.
    This is the new primary function to get user data.
    """
    # 1. Check cache first
    if user_id in REGISTRATION_CACHE:
        cached_entry = REGISTRATION_CACHE[user_id]
        # Check if the cache entry is still valid
        if (datetime.datetime.now() - cached_entry['timestamp']).total_seconds() < CACHE_EXPIRATION_SECONDS:
            logger.info(f"Found user {user_id} data in local cache.")
            return cached_entry['data']
        else:
            # Clean up expired cache entry
            del REGISTRATION_CACHE[user_id]
            logger.info(f"Removed expired cache for user {user_id}.")

    # 2. If not in cache or expired, fetch from the sheet
    logger.info(f"User {user_id} not in cache, fetching from Google Sheet.")
    return find_initiator_in_sheet_from_api(user_id)

# ---------------------------------------------------------

def get_gspread_client():
    """Authenticates and returns a gspread client."""
    try:
@@ -67,23 +61,36 @@
        logger.error(f"Error authenticating with Google Sheets: {e}")
        return None

def get_sheet_data(sheet_name=SHEET_NAME):
    """Fetches all records from the specified worksheet."""
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
    if not client or not GOOGLE_SHEET_KEY: return []
    if not client: return []
    
    sheet = get_sheet_by_gid(client)
    if not sheet: return []
    
    try:
        sheet = client.open_by_key(GOOGLE_SHEET_KEY).worksheet(sheet_name)
        return sheet.get_all_records()
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet '{sheet_name}' not found.")
        return []
    except Exception as e:
        logger.error(f"Error fetching data from Google Sheet: {e}")
        logger.error(f"An unexpected error occurred while fetching data from GID {SHEET_GID}: {e}")
        return []

def is_user_registered(user_id: str) -> bool:
    """Checks if a user has a completed registration record in the sheet."""
    # This check can still rely on the sheet, as it's not as time-sensitive.
    all_records = get_sheet_data()
    for row in all_records:
        if str(row.get('ТГ Заполняющего')) == user_id and row.get('ФИО Инициатора'):
@@ -115,11 +122,16 @@
    return list(reversed(user_cards))

def write_to_sheet(data: dict, submission_time: str, tg_user_id: str) -> bool:
    """Writes a new row to the sheet."""
    """
    Writes a new row to the sheet and verifies the API response.
    """
    client = get_gspread_client()
    if not client or not GOOGLE_SHEET_KEY: return False
    if not client: return False
    
    sheet = get_sheet_by_gid(client)
    if not sheet: return False

    try:
        sheet = client.open_by_key(GOOGLE_SHEET_KEY).worksheet(SHEET_NAME)
        status = 'Заявка' if data.get('owner_last_name') else 'Регистрация'
        final_row = [
            submission_time, tg_user_id,
@@ -132,9 +144,17 @@
            data.get('frequency', ''), data.get('issue_location', ''),
            status
        ]
        sheet.append_row(final_row, value_input_option='USER_ENTERED')
        logger.info(f"Successfully wrote a row for user {tg_user_id} with status '{status}'")
        return True
        
        api_response = sheet.append_row(final_row, value_input_option='USER_ENTERED')
        logger.info(f"Google Sheets API response: {api_response}")

        if api_response.get('updates', {}).get('updatedRows', 0) > 0:
            logger.info(f"SUCCESS: API confirmed {api_response['updates']['updatedRows']} row(s) were written for user {tg_user_id}.")
            return True
        else:
            logger.error(f"FAILURE: API call succeeded but 0 rows were written for user {tg_user_id}. Possible permissions or sheet protection issue.")
            return False

    except Exception as e:
        logger.error(f"Failed to write data to sheet for user {tg_user_id}: {e}")
        logger.error(f"Failed to write data to sheet for user {tg_user_id}: {e}", exc_info=True)
        return False
