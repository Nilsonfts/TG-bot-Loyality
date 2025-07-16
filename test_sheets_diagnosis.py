#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Диагностика выгрузки данных в Google Sheets
Проверяет соответствие заголовков и данных
"""

import sys
import os
import logging

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import g_sheets
from constants import SheetCols

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def diagnose_sheets_export():
    """Диагностирует проблемы с выгрузкой в Google Sheets."""
    
    print("🔍 ДИАГНОСТИКА ВЫГРУЗКИ В GOOGLE SHEETS")
    print("=" * 60)
    
    # Получаем заголовки из Google Sheets
    try:
        client = g_sheets.get_gspread_client()
        if not client:
            print("❌ Ошибка: не удалось подключиться к Google Sheets")
            return False
            
        sheet = g_sheets.get_sheet_by_gid(client)
        if not sheet:
            print("❌ Ошибка: не удалось получить таблицу")
            return False
            
        actual_headers = sheet.row_values(1)
        print(f"\n📋 Заголовки в Google Sheets ({len(actual_headers)} столбцов):")
        for i, header in enumerate(actual_headers, 1):
            print(f"   {i:2d}. {header}")
            
    except Exception as e:
        print(f"❌ Ошибка получения заголовков: {e}")
        return False
    
    # Получаем константы из кода
    constants_dict = {}
    for attr_name in dir(SheetCols):
        if not attr_name.startswith('_'):
            constants_dict[attr_name] = getattr(SheetCols, attr_name)
    
    print(f"\n🔧 Константы в коде ({len(constants_dict)} штук):")
    for i, (const_name, const_value) in enumerate(constants_dict.items(), 1):
        print(f"   {i:2d}. {const_name} = '{const_value}'")
    
    # Проверяем соответствие
    print(f"\n🔍 АНАЛИЗ СООТВЕТСТВИЯ:")
    print("-" * 40)
    
    missing_in_sheets = []
    missing_in_constants = []
    
    # Проверяем, какие константы отсутствуют в таблице
    for const_name, const_value in constants_dict.items():
        if const_value not in actual_headers:
            missing_in_sheets.append(f"{const_name} = '{const_value}'")
    
    # Проверяем, какие заголовки отсутствуют в константах
    for header in actual_headers:
        if header not in constants_dict.values():
            missing_in_constants.append(header)
    
    if missing_in_sheets:
        print(f"\n❌ Константы НЕ НАЙДЕНЫ в таблице ({len(missing_in_sheets)}):")
        for missing in missing_in_sheets:
            print(f"   • {missing}")
    
    if missing_in_constants:
        print(f"\n❌ Заголовки НЕ НАЙДЕНЫ в константах ({len(missing_in_constants)}):")
        for missing in missing_in_constants:
            print(f"   • '{missing}'")
    
    if not missing_in_sheets and not missing_in_constants:
        print("✅ Все заголовки соответствуют константам!")
    
    # Тестируем тестовую запись
    print(f"\n🧪 ТЕСТИРОВАНИЕ ЗАПИСИ:")
    print("-" * 30)
    
    test_data = {
        'submission_time': '2025-07-16 15:30:00',
        'tg_user_id': '123456789',
        'initiator_username': '@testuser',
        'initiator_email': 'test@example.com',
        'initiator_fio': 'Тестовый Пользователь',
        'initiator_job_title': 'Тестировщик',
        'initiator_phone': '+7 999 123-45-67',
        'owner_first_name': 'Владимир',
        'owner_last_name': 'Владимирович',
        'reason': 'Тестовая причина',
        'card_type': 'Бартер',
        'card_number': '1234567890',
        'category': 'Тестовая категория',
        'amount': '1000',
        'frequency': 'Ежемесячно',
        'issue_location': 'Тестовый бар',
        'status': 'На рассмотрении'
    }
    
    print("📝 Тестовые данные:")
    for key, value in test_data.items():
        print(f"   {key}: {value}")
    
    # Показываем, как будет выглядеть строка
    row_mapping = {}
    for header in actual_headers:
        # Находим соответствующую константу
        const_found = None
        for const_name, const_value in constants_dict.items():
            if const_value == header:
                const_found = const_name
                break
        
        if const_found:
            # Ищем в тестовых данных соответствующее поле
            field_mapping = {
                'TIMESTAMP': 'submission_time',
                'TG_ID': 'tg_user_id',
                'TG_TAG': 'initiator_username',
                'EMAIL': 'initiator_email',
                'FIO_INITIATOR': 'initiator_fio',
                'JOB_TITLE': 'initiator_job_title',
                'PHONE_INITIATOR': 'initiator_phone',
                'OWNER_FIRST_NAME_COL': 'owner_first_name',
                'OWNER_LAST_NAME_COL': 'owner_last_name',
                'REASON_COL': 'reason',
                'CARD_TYPE_COL': 'card_type',
                'CARD_NUMBER_COL': 'card_number',
                'CATEGORY_COL': 'category',
                'AMOUNT_COL': 'amount',
                'FREQUENCY_COL': 'frequency',
                'ISSUE_LOCATION_COL': 'issue_location',
                'STATUS_COL': 'status',
                'APPROVAL_STATUS': '',
                'START_DATE': '',
                'ACTIVATED': '',
                'REASON_REJECT': ''
            }
            
            data_field = field_mapping.get(const_found, '')
            value = test_data.get(data_field, '') if data_field else ''
            row_mapping[header] = value
        else:
            row_mapping[header] = ''
    
    print(f"\n📊 ИТОГОВАЯ СТРОКА ДЛЯ ЗАПИСИ:")
    for i, (header, value) in enumerate(row_mapping.items(), 1):
        status = "✅" if value else "❌"
        print(f"   {i:2d}. {status} {header}: '{value}'")
    
    empty_fields = [header for header, value in row_mapping.items() if not value]
    if empty_fields:
        print(f"\n⚠️  ПУСТЫЕ ПОЛЯ ({len(empty_fields)}):")
        for field in empty_fields:
            print(f"   • {field}")
    
    return len(empty_fields) == 0

if __name__ == "__main__":
    diagnose_sheets_export()
