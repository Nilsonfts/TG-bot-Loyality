#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки функции update_cell_by_row
"""

import logging
import os

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_update_function():
    """Тестирует функцию обновления ячеек"""
    
    # Проверяем наличие переменных окружения
    google_creds = os.getenv("GOOGLE_CREDS_JSON")
    google_sheet_key = os.getenv("GOOGLE_SHEET_KEY")
    
    if not google_creds:
        print("❌ GOOGLE_CREDS_JSON не найдена")
        return False
    
    if not google_sheet_key:
        print("❌ GOOGLE_SHEET_KEY не найдена")
        return False
    
    print("✅ Переменные окружения найдены")
    
    try:
        import g_sheets
        from constants import SheetCols
        
        print("\n=== ТЕСТИРОВАНИЕ ОТЛАДОЧНОЙ ФУНКЦИИ ===")
        headers = g_sheets.debug_sheet_headers()
        
        if headers:
            print(f"✅ Получено {len(headers)} заголовков")
        else:
            print("❌ Не удалось получить заголовки")
            return False
        
        print("\n=== ТЕСТИРОВАНИЕ ОБНОВЛЕНИЯ ЯЧЕЙКИ ===")
        # Пробуем обновить ячейку STATUS_COL для строки 1 (тестовое значение)
        test_row = 1  # Вторая строка данных (первая - заголовки)
        test_column = SheetCols.STATUS_COL
        test_value = "ТЕСТ"
        
        print(f"Пробуем обновить строку {test_row}, столбец '{test_column}', значение '{test_value}'")
        
        result = g_sheets.update_cell_by_row(test_row, test_column, test_value)
        
        if result:
            print("✅ Обновление прошло успешно")
        else:
            print("❌ Обновление не удалось")
        
        return result
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_update_function()
    exit(0 if success else 1)
