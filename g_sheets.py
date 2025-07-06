# -*- coding: utf-8 -*-

import os
import json
import logging
import datetime
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import GSpreadException
from constants import SheetCols

logger = logging.getLogger(__name__)

# Кэширование
INITIATOR_DATA_CACHE = {}
REGISTRATION_STATUS_CACHE = {}
CACHE_EXPIRATION_SECONDS = 300

def get_gspread_client():
    GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
    if not GOOGLE_CREDS_JSON:
        logger.critical("КРИТИЧЕСКАЯ ОШИБКА: Переменная GOOGLE_CREDS_JSON не найдена!")
        return None
    try:
        creds_info = json.loads(GOOGLE_CREDS_JSON)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.Client(auth=creds)
        client.list_spreadsheet_files()
        logger.info("Клиент Google Sheets успешно инициализирован.")
        return client
    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА на этапе авторизации в Google: {e}", exc_info=True)
        return None

def get_sheet_by_gid(client, gid=None):
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
                return worksheet
        logger.error(f"ОШИБКА: Лист с GID '{gid}' не найден в таблице.")
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при открытии листа: {e}", exc_info=True)
        return None

# --- ИЗМЕНЕНИЕ ---
# Функция полностью переписана, чтобы записывать данные последовательно,
# не обращая внимания на заголовки в таблице.
def write_row(data: dict) -> bool:
    """
    Записывает данные в новую строку в строго определенном порядке.
    Эта функция НЕ зависит от названий столбцов в Google Sheets.
    
    ВАЖНО: Порядок столбцов в вашей таблице должен строго соответствовать
    порядку в списке `COLUMN_ORDER` ниже.
    """
    client = get_gspread_client()
    if not client: return False
    sheet = get_sheet_by_gid(client)
    if not sheet: return False

    try:
        # Этот список определяет, в каком порядке данные будут записаны в строку.
        # Если вы поменяете столбцы местами в Google-таблице,
        # вам нужно будет поменять их местами и в этом списке.
        COLUMN_ORDER = [
            data.get('submission_time'),       # Отметка времени
            data.get('tg_user_id'),             # ID Инициатора
            data.get('initiator_username'),     # ТТ Инициатора
            data.get('initiator_email'),        # Адрес электронной почты
            data.get('initiator_fio'),          # ФИО Инициатора
            data.get('initiator_job_title'),    # Должность
            data.get('initiator_phone'),        # Телефон Инициатора
            data.get('owner_first_name'),       # Имя владельца карты
            data.get('owner_last_name'),        # Фамилия Владельца
            data.get('reason'),                 # Причина выдачи бартера/скидки
            data.get('card_type'),              # Какую карту регистрируем?
            data.get('card_number'),            # Номер карты
            data.get('category'),               # Статья пополнения карт
            data.get('amount'),                 # Сумма бартера или % скидки
            data.get('frequency'),              # Периодичность наполнения бартера
            data.get('issue_location'),         # БАР
            data.get('status'),                 # Статус Согласования
            # Если у вас есть столбец для причины отказа, добавьте его сюда
            # data.get('reject_reason'),
        ]

        final_row = COLUMN_ORDER
        
        api_response = sheet.append_row(final_row, value_input_option='USER_ENTERED')
        
        if api_response.get('updates', {}).get('updatedRows', 0) > 0:
            logger.info(f"Успешно записана строка для пользователя {data.get('tg_user_id')}")
            return True
        else:
            logger.error("API Google не подтвердил запись строки.")
            return False

    except Exception as e:
        logger.error(f"Ошибка при записи в таблицу: {e}", exc_info=True)
        return False


# Остальные функции (get_sheet_data, is_user_registered и т.д.) остаются без изменений.
# Они используют названия столбцов только для ЧТЕНИЯ, что безопасно.
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
        return True
    
    all_records = get_sheet_data()
    for row in all_records:
        if str(row.get(SheetCols.TG_ID)) == user_id and row.get(SheetCols.FIO_INITIATOR):
            REGISTRATION_STATUS_CACHE[user_id] = {'timestamp': datetime.datetime.now()}
            return True
    return False

def find_initiator_in_sheet_from_api(user_id: str):
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
    return user_data

def get_initiator_data(user_id: str):
    if user_id in INITIATOR_DATA_CACHE:
        cached_entry = INITIATOR_DATA_CACHE[user_id]
        if (datetime.datetime.now() - cached_entry['timestamp']).total_seconds() < CACHE_EXPIRATION_SECONDS:
            return cached_entry['data']
        else:
            del INITIATOR_DATA_CACHE[user_id]
    
    user_data = find_initiator_in_sheet_from_api(user_id)
    if user_data:
        INITIATOR_DATA_CACHE[user_id] = {'data': user_data.copy(), 'timestamp': datetime.datetime.now()}
    return user_data

def get_cards_from_sheet(user_id: str = None) -> list:
    all_records = get_sheet_data()
    valid_records = [r for r in all_records if r.get(SheetCols.OWNER_LAST_NAME_COL)]
    if user_id:
        user_cards = [r for r in valid_records if str(r.get(SheetCols.TG_ID)) == user_id]
    else:
        user_cards = valid_records
    return list(reversed(user_cards))
