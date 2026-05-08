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

# Кэш карты "канонический заголовок -> реальный заголовок в таблице".
# Обновляется автоматически при первом обращении и инвалидируется по TTL.
_HEADER_MAP_CACHE: dict = {}
_HEADER_MAP_TS: float = 0.0
_HEADER_MAP_TTL = 600  # 10 минут


def _normalize_header(s: str) -> str:
    """Сводит заголовок к каноническому виду для нечёткого сравнения:
    убирает все пробельные символы (включая \n, табы, неразрывные), lower-case.
    """
    if s is None:
        return ""
    return "".join(ch for ch in str(s).lower() if not ch.isspace())


def _all_canonical_headers() -> list:
    """Список всех ожидаемых имён колонок (в SheetCols)."""
    return [
        getattr(SheetCols, name) for name in dir(SheetCols)
        if not name.startswith('_') and isinstance(getattr(SheetCols, name), str)
    ]


def _build_header_map(actual_headers: list) -> dict:
    """Строит {canonical_value_from_SheetCols -> actual_header_in_sheet} с учётом нормализации."""
    norm_to_actual = {_normalize_header(h): h for h in actual_headers if h}
    mapping = {}
    for canonical in _all_canonical_headers():
        actual = norm_to_actual.get(_normalize_header(canonical))
        if actual:
            mapping[canonical] = actual
    return mapping


def _get_header_map(sheet=None) -> dict:
    """Возвращает кэшированную карту заголовков. Если кэш протух — обновляет."""
    global _HEADER_MAP_CACHE, _HEADER_MAP_TS
    now = datetime.datetime.now().timestamp()
    if _HEADER_MAP_CACHE and (now - _HEADER_MAP_TS) < _HEADER_MAP_TTL:
        return _HEADER_MAP_CACHE
    if sheet is None:
        client = get_gspread_client()
        if not client:
            return {}
        sheet = get_sheet_by_gid(client)
        if not sheet:
            return {}
    try:
        headers = sheet.row_values(1)
        _HEADER_MAP_CACHE = _build_header_map(headers)
        _HEADER_MAP_TS = now
        logger.info(f"Header map обновлён: {len(_HEADER_MAP_CACHE)} соответствий")
    except Exception as e:
        logger.error(f"Не удалось обновить header map: {e}")
    return _HEADER_MAP_CACHE


def _normalize_row(row: dict, header_map: dict) -> dict:
    """Дополняет строку каноническими ключами на основе header_map.
    Не удаляет оригинальные ключи (для обратной совместимости),
    но добавляет канонические — чтобы код, использующий SheetCols.*, всегда находил данные.
    """
    if not header_map:
        return row
    out = dict(row)
    for canonical, actual in header_map.items():
        if canonical not in out and actual in row:
            out[canonical] = row[actual]
    return out


# === Реестр админских заявок на согласование ===
# Хранит соответствие краткого action_id -> {row_index, tg_user_id, submission_time}
# Используется для НАДЕЖНОГО сопоставления нажатия кнопки админом со строкой
# в Google Sheets, даже если порядок строк изменился между уведомлением и нажатием.
PENDING_ACTIONS: dict = {}
_PENDING_ACTIONS_COUNTER = 0


def register_pending_action(row_index: int, tg_user_id: str, submission_time: str) -> str:
    """Регистрирует ожидающее действие админа и возвращает короткий action_id."""
    global _PENDING_ACTIONS_COUNTER
    _PENDING_ACTIONS_COUNTER += 1
    action_id = f"{int(datetime.datetime.now().timestamp())}{_PENDING_ACTIONS_COUNTER % 1000:03d}"
    PENDING_ACTIONS[action_id] = {
        'row_index': row_index,
        'tg_user_id': str(tg_user_id),
        'submission_time': submission_time,
    }
    # Ограничиваем размер реестра, чтобы не рос бесконечно
    if len(PENDING_ACTIONS) > 500:
        for k in sorted(PENDING_ACTIONS.keys())[:100]:
            PENDING_ACTIONS.pop(k, None)
    return action_id


def resolve_pending_action(action_id: str):
    """Возвращает (row_index, row_data) для action_id, перепроверяя строку в таблице.
    Если строка сместилась — ищет по уникальному ключу (TG_ID + submission_time).
    """
    record = PENDING_ACTIONS.get(action_id)
    if not record:
        return None, None

    rows = get_sheet_data()
    if not rows:
        return None, None

    idx = record['row_index']
    expected_tg = record['tg_user_id']
    expected_ts = record['submission_time']

    def _matches(row: dict) -> bool:
        return (
            str(row.get(SheetCols.TG_ID)) == expected_tg
            and str(row.get(SheetCols.TIMESTAMP)) == expected_ts
        )

    if 0 <= idx < len(rows) and _matches(rows[idx]):
        return idx, rows[idx]

    for i, row in enumerate(rows):
        if _matches(row):
            return i, row

    return None, None


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
    Дополнительно:
    - дублирует заявку в лист «Ежемесячные» (gid из MONTHLY_SHEET_GID),
      если frequency == 'Ежемесячная'.
    """
    logger.info(f"write_row вызвана с данными: {data}")

    client = get_gspread_client()
    if not client:
        return False
    sheet = get_sheet_by_gid(client)
    if not sheet:
        return False

    ok = _write_row_to_sheet(sheet, data)
    if not ok:
        return False

    # === Зеркалирование в лист «Ежемесячные» ===
    try:
        if str(data.get('frequency', '')).strip().lower() == 'ежемесячная':
            monthly_gid_raw = (os.getenv('MONTHLY_SHEET_GID') or '').strip()
            if monthly_gid_raw.isdigit():
                monthly_sheet = get_sheet_by_gid(client, gid=int(monthly_gid_raw))
                if monthly_sheet is not None:
                    mirror_ok = _write_row_to_sheet(monthly_sheet, data)
                    if mirror_ok:
                        logger.info("Зеркалирование в лист «Ежемесячные» выполнено.")
                    else:
                        logger.warning("Не удалось зеркалировать в «Ежемесячные».")
                else:
                    logger.warning(f"Лист «Ежемесячные» с gid={monthly_gid_raw} не найден.")
            else:
                logger.info("MONTHLY_SHEET_GID не задан — зеркалирование пропущено.")
    except Exception as e:
        logger.error(f"Ошибка зеркалирования в «Ежемесячные»: {e}", exc_info=True)

    return True


def _write_row_to_sheet(sheet, data: dict) -> bool:
    """Внутренний хелпер: пишет одну строку в указанный лист, ориентируясь на заголовки."""
    try:
        headers = sheet.row_values(1)
        if not headers:
            logger.error("Не удалось прочитать заголовки из таблицы.")
            return False

        row_to_write = {
            SheetCols.TIMESTAMP: data.get('submission_time', ''),
            SheetCols.TG_ID: data.get('tg_user_id', ''),
            SheetCols.TG_TAG: data.get('initiator_username', ''),
            SheetCols.EMAIL: data.get('initiator_email', ''),
            SheetCols.FIO_INITIATOR: data.get('initiator_fio', ''),
            SheetCols.JOB_TITLE: data.get('initiator_job_title', ''),
            SheetCols.PHONE_INITIATOR: data.get('initiator_phone', ''),
            SheetCols.OWNER_FIRST_NAME_COL: data.get('owner_first_name', ''),
            SheetCols.OWNER_LAST_NAME_COL: data.get('owner_last_name', ''),
            SheetCols.REASON_COL: data.get('reason', ''),
            SheetCols.CARD_TYPE_COL: data.get('card_type', ''),
            SheetCols.CARD_NUMBER_COL: data.get('card_number', ''),
            SheetCols.CATEGORY_COL: data.get('category', ''),
            SheetCols.AMOUNT_COL: data.get('amount', ''),
            SheetCols.FREQUENCY_COL: data.get('frequency', ''),
            SheetCols.ISSUE_LOCATION_COL: data.get('issue_location', ''),
            SheetCols.STATUS_COL: data.get('status', ''),
            SheetCols.APPROVAL_STATUS: '',
            SheetCols.START_DATE: '',
            SheetCols.ACTIVATED: '',
            SheetCols.REASON_REJECT: data.get('reason_reject', ''),
        }

        # Сопоставление заголовков с учётом нормализации
        norm_to_value = {_normalize_header(k): v for k, v in row_to_write.items()}
        final_row = []
        for header in headers:
            value = norm_to_value.get(_normalize_header(header), '')
            final_row.append(value if value is not None else '')

        if len(final_row) != len(headers):
            logger.error(
                f"_write_row_to_sheet: длина строки ({len(final_row)}) "
                f"!= количество заголовков ({len(headers)})"
            )
            return False

        api_response = sheet.append_row(final_row, value_input_option='USER_ENTERED')
        if api_response.get('updates', {}).get('updatedRows', 0) > 0:
            logger.info(f"Строка записана в лист «{sheet.title}».")
            return True
        logger.error("API Google не подтвердил запись строки.")
        return False
    except Exception as e:
        logger.error(f"_write_row_to_sheet ошибка: {e}", exc_info=True)
        return False


# Остальные функции get_sheet_data, is_user_registered и т.д. остаются без изменений.
def get_sheet_data():
    client = get_gspread_client()
    if not client: return []
    sheet = get_sheet_by_gid(client)
    if not sheet: return []
    try:
        records = sheet.get_all_records()
        header_map = _get_header_map(sheet)
        if header_map:
            records = [_normalize_row(r, header_map) for r in records]
        return records
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching data: {e}")
        return []


def repair_sheet_headers() -> dict:
    """Приводит заголовки в листе к каноническим именам из SheetCols.

    - Убирает висячие пробелы / двойные пробелы.
    - Меняет реальный заголовок на канонический, если они эквивалентны после нормализации.
    - Добавляет недостающие канонические колонки в конец.

    Возвращает отчёт {renamed: [...], added: [...], untouched: [...]}.
    """
    report = {"renamed": [], "added": [], "untouched": [], "error": None}
    client = get_gspread_client()
    if not client:
        report["error"] = "no_client"
        return report
    sheet = get_sheet_by_gid(client)
    if not sheet:
        report["error"] = "no_sheet"
        return report
    try:
        headers = sheet.row_values(1)
        norm_to_idx = {_normalize_header(h): i for i, h in enumerate(headers)}
        new_headers = list(headers)

        # 1. Переименование: для каждого канонического имени, если в таблице есть
        # «эквивалентный» заголовок но другим написанием — заменить.
        for canonical in _all_canonical_headers():
            idx = norm_to_idx.get(_normalize_header(canonical))
            if idx is None:
                continue
            actual = headers[idx]
            if actual != canonical:
                new_headers[idx] = canonical
                report["renamed"].append({"was": actual, "now": canonical})
            else:
                report["untouched"].append(canonical)

        # 2. Добавление недостающих
        present_norms = {_normalize_header(h) for h in new_headers}
        for canonical in _all_canonical_headers():
            if _normalize_header(canonical) not in present_norms:
                new_headers.append(canonical)
                report["added"].append(canonical)
                present_norms.add(_normalize_header(canonical))

        # 3. Записываем заголовки одной операцией, если что-то поменялось
        if new_headers != headers:
            # Расширяем количество колонок при необходимости
            if len(new_headers) > sheet.col_count:
                sheet.add_cols(len(new_headers) - sheet.col_count)
            sheet.update('A1', [new_headers], value_input_option='USER_ENTERED')

        # Сбрасываем кэш карты заголовков, чтобы пересчитался
        global _HEADER_MAP_CACHE, _HEADER_MAP_TS
        _HEADER_MAP_CACHE = {}
        _HEADER_MAP_TS = 0.0

        return report
    except Exception as e:
        logger.error(f"repair_sheet_headers: {e}", exc_info=True)
        report["error"] = str(e)
        return report

def is_user_registered(user_id: str) -> bool:
    if user_id in REGISTRATION_STATUS_CACHE:
        cached_entry = REGISTRATION_STATUS_CACHE[user_id]
        if (datetime.datetime.now() - cached_entry['timestamp']).total_seconds() < CACHE_EXPIRATION_SECONDS:
            return True
        del REGISTRATION_STATUS_CACHE[user_id]
    
    all_records = get_sheet_data()
    for row in all_records:
        if str(row.get(SheetCols.TG_ID)) == user_id and row.get(SheetCols.FIO_INITIATOR):
            REGISTRATION_STATUS_CACHE[user_id] = {'timestamp': datetime.datetime.now()}
            return True
    return False

def find_initiator_in_sheet_from_api(user_id: str):
    logger.info(f"🔍 Ищем инициатора с user_id: {user_id}")
    all_records = get_sheet_data()
    logger.info(f"📊 Получено {len(all_records)} записей из таблицы")
    
    user_data = None
    found_matching_ids = []
    
    for i, row in enumerate(reversed(all_records)):
        row_tg_id = str(row.get(SheetCols.TG_ID))
        row_fio = row.get(SheetCols.FIO_INITIATOR)
        
        # Логируем каждую запись для отладки
        if i < 5:  # Первые 5 записей для отладки
            logger.info(f"  Запись {i}: TG_ID='{row_tg_id}', FIO='{row_fio}'")
        
        if row_tg_id == user_id:
            found_matching_ids.append(f"Индекс {i}: TG_ID={row_tg_id}, FIO='{row_fio}'")
            
        if row_tg_id == user_id and row_fio:
            logger.info(f"✅ Найден инициатор: TG_ID={row_tg_id}, FIO={row_fio}")
            user_data = {
                "initiator_username": row.get(SheetCols.TG_TAG),
                "initiator_email": row.get(SheetCols.EMAIL),
                "initiator_fio": row.get(SheetCols.FIO_INITIATOR),
                "initiator_job_title": row.get(SheetCols.JOB_TITLE),
                "initiator_phone": row.get(SheetCols.PHONE_INITIATOR),
            }
            logger.info(f"📋 Возвращаем данные: {user_data}")
            break
    
    if not user_data:
        logger.warning(f"❌ Инициатор с user_id {user_id} не найден")
        if found_matching_ids:
            logger.info(f"🔍 Найдены записи с совпадающим TG_ID, но без FIO: {found_matching_ids}")
        else:
            logger.info(f"🔍 Записей с TG_ID {user_id} вообще не найдено")
    
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

def debug_sheet_headers():
    """
    Отладочная функция для просмотра заголовков таблицы
    """
    client = get_gspread_client()
    if not client:
        logger.error("Не удалось получить клиент Google Sheets")
        return []
    
    sheet = get_sheet_by_gid(client)
    if not sheet:
        logger.error("Не удалось получить лист Google Sheets")
        return []
    
    try:
        headers = sheet.row_values(1)
        logger.info("=== ОТЛАДКА ЗАГОЛОВКОВ ТАБЛИЦЫ ===")
        for i, header in enumerate(headers):
            logger.info(f"Столбец {i+1}: '{header}' (len={len(header)})")
            # Показываем символы, которые могут быть невидимыми
            char_codes = [ord(c) for c in header]
            logger.info(f"  Коды символов: {char_codes}")
        logger.info("=== КОНЕЦ ОТЛАДКИ ===")
        return headers
    except Exception as e:
        logger.error(f"Ошибка при получении заголовков: {e}")
        return []


def update_cell_by_row(row_index: int, column_name: str, new_value: str) -> bool:
    """
    Обновляет конкретную ячейку в строке по индексу строки и названию столбца.
    row_index: номер записи в данных (начиная с 0)
    column_name: название столбца из SheetCols
    new_value: новое значение для ячейки
    """
    logger.info(f"🔄 update_cell_by_row вызвана: row_index={row_index}, column_name='{column_name}', new_value='{new_value}'")
    
    client = get_gspread_client()
    if not client: 
        logger.error("❌ Не удалось получить клиент Google Sheets")
        return False
    
    sheet = get_sheet_by_gid(client)
    if not sheet: 
        logger.error("❌ Не удалось получить лист Google Sheets")
        return False
    
    try:
        # Сначала проверим, сколько строк в таблице
        all_data = sheet.get_all_values()
        total_rows = len(all_data)
        data_rows = total_rows - 1  # Исключаем заголовок
        
        logger.info(f"📊 Всего строк в таблице: {total_rows} (включая заголовок)")
        logger.info(f"📊 Строк с данными: {data_rows}")
        logger.info(f"📍 Запрашиваемый row_index: {row_index}")
        
        # Проверяем, что row_index валидный
        if row_index < 0 or row_index >= data_rows:
            logger.error(f"❌ Неверный row_index: {row_index}. Должен быть от 0 до {data_rows - 1}")
            return False
        
        # Получаем заголовки для определения номера столбца
        headers = sheet.row_values(1)
        logger.info(f"📋 Заголовки таблицы: {headers}")
        
        # Сначала пробуем точное совпадение
        column_index = None
        if column_name in headers:
            column_index = headers.index(column_name) + 1
            logger.info(f"✅ Найдено точное совпадение: '{column_name}' в позиции {column_index}")
        else:
            # Пробуем найти похожий заголовок (убираем лишние пробелы и переносы)
            normalized_column_name = column_name.strip().replace('\n', ' ')
            for i, header in enumerate(headers):
                normalized_header = header.strip().replace('\n', ' ')
                if normalized_header == normalized_column_name:
                    column_index = i + 1
                    logger.info(f"🔄 Найдено точное совпадение по нормализованному имени: '{header}' -> '{column_name}' в позиции {column_index}")
                    break
            
            # Если не найдено, пробуем частичное совпадение
            if column_index is None:
                for i, header in enumerate(headers):
                    if column_name.replace('\n', '').replace(' ', '') in header.replace('\n', '').replace(' ', ''):
                        column_index = i + 1
                        logger.info(f"⚠️ Найдено частичное совпадение: '{header}' -> '{column_name}' в позиции {column_index}")
                        break
        
        if column_index is None:
            logger.error(f"❌ Столбец '{column_name}' не найден в заголовках")
            logger.error(f"📋 Доступные заголовки: {headers}")
            # Покажем нормализованные версии для отладки
            normalized_headers = [h.strip().replace('\n', ' ') for h in headers]
            logger.error(f"📋 Нормализованные заголовки: {normalized_headers}")
            return False
        
        # Вычисляем номер строки в Google Sheets (row_index + 2, т.к. +1 для заголовка и +1 для 1-based indexing)
        sheet_row_number = row_index + 2
        
        logger.info(f"🎯 Обновляем ячейку: строка {sheet_row_number}, столбец {column_index} ('{column_name}')")
        logger.info(f"🎯 Формула: row_index({row_index}) + 2 = sheet_row_number({sheet_row_number})")
        
        # Проверяем, что не выходим за границы таблицы
        if sheet_row_number > total_rows:
            logger.error(f"❌ Попытка обновить строку {sheet_row_number}, но в таблице только {total_rows} строк")
            return False
        
        # Обновляем ячейку
        sheet.update_cell(sheet_row_number, column_index, new_value)
        logger.info(f"✅ Успешно обновлена ячейка [{sheet_row_number}, {column_index}] = '{new_value}'")
        return True
        
    except Exception as e:
        logger.error(f"💥 Ошибка при обновлении ячейки: {e}", exc_info=True)
        logger.error(f"📊 Параметры: row_index={row_index}, column_name='{column_name}', new_value='{new_value}'")
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


# === Подсветка и синхронизация статусов ===

# Цвета для статусов (в формате 0..1)
_STATUS_COLORS = {
    "одобрено": {"red": 0.83, "green": 0.94, "blue": 0.83},   # мягкий зелёный
    "approved": {"red": 0.83, "green": 0.94, "blue": 0.83},
    "отклонено": {"red": 0.99, "green": 0.85, "blue": 0.85},  # мягкий красный
    "rejected":  {"red": 0.99, "green": 0.85, "blue": 0.85},
}


def _color_row_in_sheet(sheet, row_index: int, color: dict) -> bool:
    """Подсвечивает строку (row_index — 0-based в данных, без заголовка)."""
    try:
        sheet_row_number = row_index + 2
        # Диапазон от A до последней колонки
        last_col_letter = gspread.utils.rowcol_to_a1(1, max(sheet.col_count, 1))
        # rowcol_to_a1 возвращает 'A1', нужно вытащить буквенную часть
        col_letters = ''.join(ch for ch in last_col_letter if ch.isalpha())
        cell_range = f"A{sheet_row_number}:{col_letters}{sheet_row_number}"
        sheet.format(cell_range, {"backgroundColor": color})
        return True
    except Exception as e:
        logger.error(f"_color_row_in_sheet failed: {e}", exc_info=True)
        return False


def _find_row_in_sheet_by_key(sheet, tg_id: str, submission_time: str):
    """Возвращает (row_index_0based, row_dict) в указанном листе по ключу TG_ID + TIMESTAMP.
    Использует нормализацию заголовков, чтобы не зависеть от точного имени колонки.
    """
    try:
        records = sheet.get_all_records()
    except Exception as e:
        logger.error(f"_find_row_in_sheet_by_key: get_all_records failed: {e}")
        return None, None

    if not records:
        return None, None

    # Карта норм-заголовков для текущего листа
    headers = sheet.row_values(1)
    norm_to_actual = {_normalize_header(h): h for h in headers if h}

    tg_actual = norm_to_actual.get(_normalize_header(SheetCols.TG_ID))
    ts_actual = norm_to_actual.get(_normalize_header(SheetCols.TIMESTAMP))
    if not tg_actual or not ts_actual:
        return None, None

    for i, row in enumerate(records):
        if str(row.get(tg_actual)) == str(tg_id) and str(row.get(ts_actual)) == str(submission_time):
            return i, row
    return None, None


def update_status_everywhere(tg_id: str, submission_time: str, new_status: str,
                              extra_updates: dict = None, paint: bool = True) -> dict:
    """Меняет статус заявки и (опционально) подсвечивает строку
    одновременно в основном листе и в листе «Ежемесячные» (если задан MONTHLY_SHEET_GID).

    extra_updates: словарь {канонический_заголовок: значение} — будут обновлены те же
    колонки в обоих листах (например, REASON_REJECT, APPROVAL_STATUS).

    Возвращает {'main': bool, 'monthly': bool|None}.
    """
    extra_updates = extra_updates or {}
    result = {'main': False, 'monthly': None}

    client = get_gspread_client()
    if not client:
        return result

    color = _STATUS_COLORS.get(str(new_status).strip().lower()) if paint else None

    def _apply(sheet) -> bool:
        idx, _ = _find_row_in_sheet_by_key(sheet, tg_id, submission_time)
        if idx is None:
            return False
        # Обновляем статус
        try:
            headers = sheet.row_values(1)
            norm_to_idx = {_normalize_header(h): (i + 1) for i, h in enumerate(headers)}

            def _col(canonical):
                return norm_to_idx.get(_normalize_header(canonical))

            status_col = _col(SheetCols.STATUS_COL)
            if status_col:
                sheet.update_cell(idx + 2, status_col, new_status)

            for canonical, value in extra_updates.items():
                col = _col(canonical)
                if col:
                    sheet.update_cell(idx + 2, col, value)

            if color:
                _color_row_in_sheet(sheet, idx, color)
            return True
        except Exception as e:
            logger.error(f"update_status_everywhere apply failed: {e}", exc_info=True)
            return False

    main_sheet = get_sheet_by_gid(client)
    if main_sheet is not None:
        result['main'] = _apply(main_sheet)

    monthly_gid_raw = (os.getenv('MONTHLY_SHEET_GID') or '').strip()
    if monthly_gid_raw.isdigit():
        monthly_sheet = get_sheet_by_gid(client, gid=int(monthly_gid_raw))
        if monthly_sheet is not None:
            result['monthly'] = _apply(monthly_sheet)
        else:
            result['monthly'] = False

    return result

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
