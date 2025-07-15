# -*- coding: utf-8 -*-

import os
import json
import logging
import datetime
import gspread
from google.oauth2.service_account import Credentials
from constants import SheetCols # Убедимся, что импортируем константы

logger = logging.getLogger(__name__)

INITIATOR_DATA_CACHE = {}
REGISTRATION_STATUS_CACHE = {}
CACHE_EXPIRATION_SECONDS = 300

# get_gspread_client, get_sheet_by_gid остаются такими же "пуленепробиваемыми", как в прошлый раз

def get_gspread_client():
    # ... (код без изменений)
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
        client = gspread.Client(auth=creds)
        logger.info("get_gspread_client: Шаг 4/5: Клиент gspread.Client инициализирован.")
        client.list_spreadsheet_files()
        logger.info("get_gspread_client: Шаг 5/5: Проверочный запрос к Google API прошел успешно. Клиент готов к работе.")
        return client
    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА на этапе авторизации в Google: {e}", exc_info=True)
        return None


def get_sheet_by_gid(client, gid=None):
    # ... (код без изменений)
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

# === НОВАЯ УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ЗАПИСИ ===
def write_row(data: dict) -> bool:
    """
    Универсальная функция, которая записывает данные в строку,
    ориентируясь на заголовки столбцов.
    """
    logger.info(f"write_row вызвана с данными: {data}")
    
    client = get_gspread_client()
    if not client: return False
    sheet = get_sheet_by_gid(client)
    if not sheet: return False
    
    try:
        headers = sheet.row_values(1)
        if not headers:
            logger.error("Не удалось прочитать заголовки из таблицы.")
            return False

        logger.info(f"Заголовки таблицы: {headers}")

        # Собираем данные в словарь в соответствии с константами
        row_to_write = {
            SheetCols.TIMESTAMP: data.get('submission_time'),
            SheetCols.TG_ID: data.get('tg_user_id'),
            SheetCols.TG_TAG: data.get('initiator_username'),
            SheetCols.EMAIL: data.get('initiator_email'),
            SheetCols.FIO_INITIATOR: data.get('initiator_fio'),
            SheetCols.JOB_TITLE: data.get('initiator_job_title'),
            SheetCols.PHONE_INITIATOR: data.get('initiator_phone'),
            SheetCols.OWNER_LAST_NAME_COL: data.get('owner_last_name'),
            SheetCols.OWNER_FIRST_NAME_COL: data.get('owner_first_name'),
            SheetCols.REASON_COL: data.get('reason'),
            SheetCols.CARD_TYPE_COL: data.get('card_type'),
            SheetCols.CARD_NUMBER_COL: data.get('card_number'),
            SheetCols.CATEGORY_COL: data.get('category'),
            SheetCols.AMOUNT_COL: data.get('amount'),
            SheetCols.FREQUENCY_COL: data.get('frequency'),
            SheetCols.ISSUE_LOCATION_COL: data.get('issue_location'),
            SheetCols.STATUS_COL: data.get('status')
        }
        
        logger.info(f"Подготовленные данные для записи: {row_to_write}")
        
        # Собираем итоговый список в правильном порядке, ориентируясь на заголовки
        final_row = [row_to_write.get(header) for header in headers]
        
        logger.info(f"Финальная строка для записи: {final_row}")
        
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


# Остальные функции get_sheet_data, is_user_registered и т.д. остаются без изменений.
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

def update_cell_by_row(row_index: int, column_name: str, new_value: str) -> bool:
    """
    Обновляет конкретную ячейку в строке по индексу строки и названию столбца.
    row_index: номер строки (начиная с 1, где 1 - заголовки)
    column_name: название столбца из SheetCols
    new_value: новое значение для ячейки
    """
    client = get_gspread_client()
    if not client: 
        logger.error("Не удалось получить клиент Google Sheets")
        return False
    
    sheet = get_sheet_by_gid(client)
    if not sheet: 
        logger.error("Не удалось получить лист Google Sheets")
        return False
    
    try:
        # Получаем заголовки для определения номера столбца
        headers = sheet.row_values(1)
        if column_name not in headers:
            logger.error(f"Столбец '{column_name}' не найден в заголовках")
            return False
        
        column_index = headers.index(column_name) + 1  # +1 для gspread (1-based indexing)
        
        # Обновляем ячейку
        sheet.update_cell(row_index + 1, column_index, new_value)  # +1 т.к. row_index начинается с 0, а первая строка - заголовки
        logger.info(f"Успешно обновлена ячейка [{row_index + 1}, {column_index}] = '{new_value}'")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении ячейки: {e}", exc_info=True)
        return False

def get_row_data(row_index: int) -> dict:
    """
    Получает данные строки по индексу.
    row_index: номер строки (начиная с 0 для данных, не считая заголовки)
    """
    try:
        all_records = get_sheet_data()
        if 0 <= row_index < len(all_records):
            return all_records[row_index]
        else:
            logger.error(f"Индекс строки {row_index} выходит за границы данных")
            return {}
    except Exception as e:
        logger.error(f"Ошибка при получении данных строки {row_index}: {e}", exc_info=True)
        return {}

def search_applications_with_status(status: str) -> list:
    """
    Ищет заявки по статусу. Полезно для мониторинга.
    """
    all_records = get_sheet_data()
    return [record for record in all_records if record.get(SheetCols.STATUS_COL) == status]

def get_statistics() -> dict:
    """
    Возвращает базовую статистику по заявкам.
    """
    all_records = get_sheet_data()
    if not all_records:
        return {}
    
    total = len(all_records)
    by_status = {}
    by_card_type = {}
    
    for record in all_records:
        status = record.get(SheetCols.STATUS_COL, 'Неизвестно')
        card_type = record.get(SheetCols.CARD_TYPE_COL, 'Неизвестно')
        
        by_status[status] = by_status.get(status, 0) + 1
        by_card_type[card_type] = by_card_type.get(card_type, 0) + 1
    
    return {
        'total': total,
        'by_status': by_status,
        'by_card_type': by_card_type
    }
