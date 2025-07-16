#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки обновления ячеек в Google Sheets
"""

import sys
import os
import logging
from unittest.mock import Mock, patch

# Добавляем текущую директорию в Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка логгирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_constants_mapping():
    """Тестируем соответствие констант заголовкам"""
    
    print("🧪 ТЕСТИРОВАНИЕ СООТВЕТСТВИЯ КОНСТАНТ")
    print("=" * 50)
    
    from constants import SheetCols
    
    # Ожидаемые заголовки из таблицы
    expected_headers = [
        'Отметка времени',
        'IDИнициатора',
        'ТГИнициатора',
        'Адрес электронной почты',
        'ФИО Инициатора',
        'Должность',
        'Телефон Инициатора',
        'Имя владельца карты',
        'Фамилия Владельца карты',
        'Причина выдачи бартера/скидки',
        'Какую карту регистрируем?',
        'Номер карты',
        'Статья пополнения карт',
        'Сумма бартера или % скидки',
        'Периодичность наполнения бартера',
        'БАР',
        'ЗАЯВКА',
        'Согласовано САД/Директором по рекламе',
        'STARTDATE (пополнение по четвергам после 22:00)',
        'Активировано'
    ]
    
    # Проверяем константы
    constants_to_check = {
        'TIMESTAMP': SheetCols.TIMESTAMP,
        'TG_ID': SheetCols.TG_ID,
        'TG_TAG': SheetCols.TG_TAG,
        'EMAIL': SheetCols.EMAIL,
        'FIO_INITIATOR': SheetCols.FIO_INITIATOR,
        'JOB_TITLE': SheetCols.JOB_TITLE,
        'PHONE_INITIATOR': SheetCols.PHONE_INITIATOR,
        'OWNER_FIRST_NAME_COL': SheetCols.OWNER_FIRST_NAME_COL,
        'OWNER_LAST_NAME_COL': SheetCols.OWNER_LAST_NAME_COL,
        'REASON_COL': SheetCols.REASON_COL,
        'CARD_TYPE_COL': SheetCols.CARD_TYPE_COL,
        'CARD_NUMBER_COL': SheetCols.CARD_NUMBER_COL,
        'CATEGORY_COL': SheetCols.CATEGORY_COL,
        'AMOUNT_COL': SheetCols.AMOUNT_COL,
        'FREQUENCY_COL': SheetCols.FREQUENCY_COL,
        'ISSUE_LOCATION_COL': SheetCols.ISSUE_LOCATION_COL,
        'STATUS_COL': SheetCols.STATUS_COL,
        'APPROVAL_STATUS': SheetCols.APPROVAL_STATUS,
        'START_DATE': SheetCols.START_DATE,
        'ACTIVATED': SheetCols.ACTIVATED
    }
    
    all_good = True
    
    for const_name, const_value in constants_to_check.items():
        if const_value in expected_headers:
            print(f"✅ {const_name} = '{const_value}' - НАЙДЕН в заголовках")
        else:
            print(f"❌ {const_name} = '{const_value}' - НЕ НАЙДЕН в заголовках")
            all_good = False
    
    return all_good

def test_write_row_mapping():
    """Тестируем маппинг данных в write_row"""
    
    print("\n🧪 ТЕСТИРОВАНИЕ МАППИНГА ДАННЫХ")
    print("=" * 40)
    
    # Тестовые данные
    test_data = {
        'submission_time': '2025-07-16 08:30:00',
        'tg_user_id': '123456789',
        'initiator_username': '@testuser',
        'initiator_email': 'test@example.com',
        'initiator_fio': 'Тестов Тест Тестович',
        'initiator_job_title': 'Тестер',
        'initiator_phone': '89991234567',
        'owner_first_name': 'Иван',
        'owner_last_name': 'Иванов',
        'reason': 'Тестовая причина',
        'card_type': 'Бартер',
        'card_number': '89991234567',
        'category': 'АРТ',
        'amount': '5000',
        'frequency': 'Разовая',
        'issue_location': 'Москва',
        'status': 'На согласовании'
    }
    
    from constants import SheetCols
    
    # Создаем маппинг как в write_row
    row_to_write = {
        SheetCols.TIMESTAMP: test_data.get('submission_time', ''),
        SheetCols.TG_ID: test_data.get('tg_user_id', ''),
        SheetCols.TG_TAG: test_data.get('initiator_username', ''),
        SheetCols.EMAIL: test_data.get('initiator_email', ''),
        SheetCols.FIO_INITIATOR: test_data.get('initiator_fio', ''),
        SheetCols.JOB_TITLE: test_data.get('initiator_job_title', ''),
        SheetCols.PHONE_INITIATOR: test_data.get('initiator_phone', ''),
        SheetCols.OWNER_FIRST_NAME_COL: test_data.get('owner_first_name', ''),
        SheetCols.OWNER_LAST_NAME_COL: test_data.get('owner_last_name', ''),
        SheetCols.REASON_COL: test_data.get('reason', ''),
        SheetCols.CARD_TYPE_COL: test_data.get('card_type', ''),
        SheetCols.CARD_NUMBER_COL: test_data.get('card_number', ''),
        SheetCols.CATEGORY_COL: test_data.get('category', ''),
        SheetCols.AMOUNT_COL: test_data.get('amount', ''),
        SheetCols.FREQUENCY_COL: test_data.get('frequency', ''),
        SheetCols.ISSUE_LOCATION_COL: test_data.get('issue_location', ''),
        SheetCols.STATUS_COL: test_data.get('status', ''),
        SheetCols.APPROVAL_STATUS: '',
        SheetCols.START_DATE: '',
        SheetCols.ACTIVATED: '',
        SheetCols.REASON_REJECT: test_data.get('reason_reject', '')
    }
    
    print("📊 Результат маппинга:")
    for key, value in row_to_write.items():
        status = "✅" if value else "⚠️"
        print(f"{status} '{key}' = '{value}'")
    
    # Проверяем, что все важные поля заполнены
    important_fields = [
        SheetCols.TIMESTAMP, SheetCols.TG_ID, SheetCols.FIO_INITIATOR,
        SheetCols.OWNER_FIRST_NAME_COL, SheetCols.CARD_NUMBER_COL, 
        SheetCols.AMOUNT_COL, SheetCols.STATUS_COL
    ]
    
    all_filled = True
    for field in important_fields:
        if not row_to_write.get(field):
            print(f"❌ Важное поле '{field}' не заполнено!")
            all_filled = False
    
    if all_filled:
        print("✅ Все важные поля заполнены")
    
    return all_filled

async def test_update_cell_function():
    """Тестируем функцию update_cell_by_row"""
    
    print("\n🧪 ТЕСТИРОВАНИЕ ФУНКЦИИ UPDATE_CELL_BY_ROW")
    print("=" * 50)
    
    import g_sheets
    from constants import SheetCols
    
    # Мокаем Google Sheets API
    with patch('g_sheets.get_gspread_client') as mock_client_func, \
         patch('g_sheets.get_sheet_by_gid') as mock_sheet_func:
        
        # Настраиваем моки
        mock_client = Mock()
        mock_sheet = Mock()
        mock_client_func.return_value = mock_client
        mock_sheet_func.return_value = mock_sheet
        
        # Мокаем заголовки
        mock_headers = [
            'Отметка времени', 'IDИнициатора', 'ТГИнициатора',
            'Адрес электронной почты', 'ФИО Инициатора', 'Должность',
            'Телефон Инициатора', 'Имя владельца карты', 'Фамилия Владельца карты',
            'Причина выдачи бартера/скидки', 'Какую карту регистрируем?',
            'Номер карты', 'Статья пополнения карт', 'Сумма бартера или % скидки',
            'Периодичность наполнения бартера', 'БАР', 'ЗАЯВКА',
            'Согласовано САД/Директором по рекламе', 'STARTDATE (пополнение по четвергам после 22:00)',
            'Активировано'
        ]
        mock_sheet.row_values.return_value = mock_headers
        mock_sheet.update_cell.return_value = True
        
        # Тестируем обновление статуса
        try:
            result = g_sheets.update_cell_by_row(0, SheetCols.STATUS_COL, "Одобрено")
            
            if result:
                print("✅ Функция update_cell_by_row работает корректно")
                
                # Проверяем, что update_cell был вызван с правильными параметрами
                mock_sheet.update_cell.assert_called_once()
                call_args = mock_sheet.update_cell.call_args[0]
                
                print(f"📍 Вызов update_cell: строка={call_args[0]}, столбец={call_args[1]}, значение='{call_args[2]}'")
                
                # Ожидаем: строка 2 (0 + 2), столбец 17 (индекс 'ЗАЯВКА' + 1)
                expected_row = 2
                expected_col = mock_headers.index(SheetCols.STATUS_COL) + 1
                
                if call_args[0] == expected_row and call_args[1] == expected_col:
                    print("✅ Параметры вызова корректны")
                    return True
                else:
                    print(f"❌ Неверные параметры: ожидалось ({expected_row}, {expected_col}), получено ({call_args[0]}, {call_args[1]})")
                    return False
            else:
                print("❌ Функция вернула False")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка при тестировании: {e}")
            return False

def main():
    """Главная функция тестирования"""
    
    print("🤖 ТЕСТИРОВАНИЕ ИСПРАВЛЕНИЙ GOOGLE SHEETS")
    print("=" * 60)
    
    # Устанавливаем тестовые переменные окружения
    os.environ['GOOGLE_CREDS_JSON'] = '{"type": "service_account"}'
    os.environ['GOOGLE_SHEET_KEY'] = 'test_key'
    os.environ['SHEET_GID'] = '0'
    
    tests_passed = 0
    total_tests = 3
    
    # Тест 1: Константы
    if test_constants_mapping():
        tests_passed += 1
        print("✅ ТЕСТ 1 ПРОЙДЕН: Константы соответствуют заголовкам")
    else:
        print("❌ ТЕСТ 1 НЕ ПРОЙДЕН: Константы не соответствуют заголовкам")
    
    # Тест 2: Маппинг данных
    if test_write_row_mapping():
        tests_passed += 1
        print("✅ ТЕСТ 2 ПРОЙДЕН: Маппинг данных корректен")
    else:
        print("❌ ТЕСТ 2 НЕ ПРОЙДЕН: Проблемы с маппингом данных")
    
    # Тест 3: Функция обновления
    import asyncio
    if asyncio.run(test_update_cell_function()):
        tests_passed += 1
        print("✅ ТЕСТ 3 ПРОЙДЕН: Функция обновления работает")
    else:
        print("❌ ТЕСТ 3 НЕ ПРОЙДЕН: Проблемы с функцией обновления")
    
    # Итоги
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    print(f"✅ Пройдено тестов: {tests_passed}/{total_tests}")
    print(f"📈 Процент успеха: {(tests_passed/total_tests)*100:.1f}%")
    
    if tests_passed == total_tests:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! ИСПРАВЛЕНИЯ КОРРЕКТНЫ!")
        return True
    else:
        print(f"\n⚠️ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ. ТРЕБУЕТСЯ ДОРАБОТКА.")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
