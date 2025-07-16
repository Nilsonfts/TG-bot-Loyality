#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест реальной записи в Google Sheets с исправленной логикой
"""

import logging
from datetime import datetime, timezone, timedelta
from g_sheets import write_row
from constants import SheetCols

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_real_google_export():
    print("🔍 ТЕСТИРОВАНИЕ РЕАЛЬНОЙ ЗАПИСИ В GOOGLE SHEETS")
    print("=" * 60)
    
    # Подготавливаем тестовые данные с Moscow timezone
    moscow_tz = timezone(timedelta(hours=3))
    current_time = datetime.now(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    # Тестовые данные для записи (используем правильные константы)
    test_data = {
        SheetCols.TIMESTAMP: current_time,
        SheetCols.TG_ID: "123456789",
        SheetCols.TG_TAG: "@testuser",
        SheetCols.EMAIL: "test@example.com",
        SheetCols.FIO_INITIATOR: "Иванов Иван Иванович",
        SheetCols.JOB_TITLE: "Менеджер",
        SheetCols.PHONE_INITIATOR: "+7 900 123-45-67",
        SheetCols.OWNER_FIRST_NAME_COL: "Тест",
        SheetCols.OWNER_LAST_NAME_COL: "Тестов",
        SheetCols.REASON_COL: "Скидка постоянному клиенту",
        SheetCols.CARD_TYPE_COL: "Дисконтная",
        SheetCols.CARD_NUMBER_COL: "1234567890",
        SheetCols.CATEGORY_COL: "Бартер",
        SheetCols.AMOUNT_COL: "10%",
        SheetCols.FREQUENCY_COL: "Еженедельно",
        SheetCols.ISSUE_LOCATION_COL: "Тест Бар",
        SheetCols.STATUS_COL: "На рассмотрении"
    }
    
    print(f"📝 Тестовые данные подготовлены:")
    for key, value in test_data.items():
        print(f"  {key}: {value}")
    
    print(f"\n📊 Всего полей: {len(test_data)}")
    
    # Пытаемся записать в Google Sheets
    print("\n🚀 Попытка записи в Google Sheets...")
    try:
        result = write_row(test_data)
        if result:
            print("✅ УСПЕХ! Данные записаны в Google Sheets")
        else:
            print("❌ ОШИБКА! Запись не удалась")
        return result
    except Exception as e:
        print(f"💥 ИСКЛЮЧЕНИЕ при записи: {e}")
        return False

if __name__ == "__main__":
    test_real_google_export()
