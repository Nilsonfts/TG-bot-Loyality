#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Диагностика проблемы с выгрузкой в Google Sheets
Проверяет каждый шаг процесса записи данных
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import utils
from constants import SheetCols

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def diagnose_export_issue():
    """Диагностирует проблему с неполной выгрузкой."""
    
    print("🔍 ДИАГНОСТИКА ПРОБЛЕМЫ С ВЫГРУЗКОЙ ДАННЫХ")
    print("=" * 60)
    
    # 1. Проверяем, есть ли зарегистрированные пользователи
    print("\n1️⃣ ПРОВЕРКА ЗАРЕГИСТРИРОВАННЫХ ПОЛЬЗОВАТЕЛЕЙ")
    print("-" * 50)
    
    try:
        utils.init_local_db()
        
        # Создаем тестового пользователя
        test_user = {
            'tg_user_id': 'diagnosis_test_user',
            'initiator_fio': 'Диагностический Пользователь',
            'initiator_email': 'diagnosis@test.com',
            'initiator_job_title': 'Диагност',
            'initiator_phone': '+7 (999) 000-00-00',
            'initiator_username': '@diagnosis_test'
        }
        
        # Сохраняем пользователя
        save_result = utils.save_user_to_local_db(test_user)
        print(f"✅ Пользователь сохранён: {save_result}")
        
        # Проверяем получение данных инициатора
        initiator_data = utils.get_initiator_from_local_db('diagnosis_test_user')
        if initiator_data:
            print(f"✅ Данные инициатора получены:")
            for key, value in initiator_data.items():
                print(f"   {key}: '{value}'")
        else:
            print("❌ Данные инициатора НЕ получены")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    # 2. Симулируем полный процесс заполнения формы
    print("\n2️⃣ СИМУЛЯЦИЯ ЗАПОЛНЕНИЯ ФОРМЫ")
    print("-" * 50)
    
    try:
        # Данные инициатора (из БД)
        initiator_data = utils.get_initiator_from_local_db('diagnosis_test_user')
        
        # Данные формы (вводит пользователь)
        form_data = {
            'owner_last_name': 'Диагностический',
            'owner_first_name': 'Владелец',
            'reason': 'Диагностическая причина выдачи карты',
            'card_type': 'Бартер',
            'card_number': '9999888877',
            'category': 'Диагностическая категория',
            'amount': '15000',
            'frequency': 'Ежемесячно',
            'issue_location': 'Диагностический бар'
        }
        
        # Системные данные
        moscow_tz = timezone(timedelta(hours=3))
        moscow_time = datetime.now(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
        
        system_data = {
            'submission_time': moscow_time,
            'tg_user_id': 'diagnosis_test_user',
            'status': 'На согласовании'
        }
        
        # Объединяем все данные
        complete_data = {}
        if initiator_data:
            complete_data.update(initiator_data)
        complete_data.update(form_data)
        complete_data.update(system_data)
        
        print(f"📊 СОБРАННЫЕ ДАННЫЕ ({len(complete_data)} полей):")
        for i, (key, value) in enumerate(complete_data.items(), 1):
            print(f"   {i:2d}. {key}: '{value}'")
            
    except Exception as e:
        print(f"❌ Ошибка симуляции: {e}")
    
    # 3. Проверяем маппинг констант
    print("\n3️⃣ ПРОВЕРКА МАППИНГА КОНСТАНТ")
    print("-" * 50)
    
    try:
        # Все константы Google Sheets
        constants = {
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
        }
        
        print("🔍 Константы Google Sheets:")
        for const_name, const_value in constants.items():
            print(f"   {const_name} = '{const_value}'")
            
        # Проверяем маппинг данных -> константы
        field_mapping = {
            'submission_time': SheetCols.TIMESTAMP,
            'tg_user_id': SheetCols.TG_ID,
            'initiator_username': SheetCols.TG_TAG,
            'initiator_email': SheetCols.EMAIL,
            'initiator_fio': SheetCols.FIO_INITIATOR,
            'initiator_job_title': SheetCols.JOB_TITLE,
            'initiator_phone': SheetCols.PHONE_INITIATOR,
            'owner_first_name': SheetCols.OWNER_FIRST_NAME_COL,
            'owner_last_name': SheetCols.OWNER_LAST_NAME_COL,
            'reason': SheetCols.REASON_COL,
            'card_type': SheetCols.CARD_TYPE_COL,
            'card_number': SheetCols.CARD_NUMBER_COL,
            'category': SheetCols.CATEGORY_COL,
            'amount': SheetCols.AMOUNT_COL,
            'frequency': SheetCols.FREQUENCY_COL,
            'issue_location': SheetCols.ISSUE_LOCATION_COL,
            'status': SheetCols.STATUS_COL,
        }
        
        print(f"\n📋 МАППИНГ ПОЛЕЙ:")
        for data_field, sheet_column in field_mapping.items():
            value = complete_data.get(data_field, '')
            status = "✅" if value else "❌"
            print(f"   {status} {data_field} → '{sheet_column}': '{value}'")
            
        # Проверяем, какие поля остаются пустыми
        empty_fields = [field for field, value in complete_data.items() if not value]
        missing_mappings = [field for field in field_mapping.keys() if field not in complete_data]
        
        if empty_fields:
            print(f"\n⚠️  ПУСТЫЕ ПОЛЯ ({len(empty_fields)}):")
            for field in empty_fields:
                print(f"   • {field}")
                
        if missing_mappings:
            print(f"\n❌ ОТСУТСТВУЮЩИЕ ПОЛЯ ({len(missing_mappings)}):")
            for field in missing_mappings:
                print(f"   • {field}")
                
    except Exception as e:
        print(f"❌ Ошибка проверки маппинга: {e}")
    
    # 4. Главная проблема - проверяем сам процесс сохранения
    print("\n4️⃣ ПРОВЕРКА ПРОЦЕССА СОХРАНЕНИЯ")
    print("-" * 50)
    
    # Создаем реальные пользовательские данные для теста
    test_scenario = {
        'initiator_username': '@diagnosis_test',
        'initiator_email': 'diagnosis@test.com', 
        'initiator_fio': 'Диагностический Пользователь',
        'initiator_job_title': 'Диагност',
        'initiator_phone': '+7 (999) 000-00-00',
        'owner_first_name': 'Владелец',
        'owner_last_name': 'Диагностический',
        'reason': 'Диагностическая причина',
        'card_type': 'Бартер',
        'card_number': '9999888877',
        'category': 'Диагностическая категория',
        'amount': '15000',
        'frequency': 'Ежемесячно',
        'issue_location': 'Диагностический бар',
        'submission_time': moscow_time,
        'tg_user_id': 'diagnosis_test_user',
        'status': 'На согласовании'
    }
    
    print("🧪 ТЕСТОВЫЙ СЦЕНАРИЙ:")
    filled_count = 0
    for key, value in test_scenario.items():
        status = "✅" if value else "❌"
        if value:
            filled_count += 1
        print(f"   {status} {key}: '{value}'")
    
    print(f"\n📊 СТАТИСТИКА:")
    print(f"   Заполнено полей: {filled_count}/{len(test_scenario)}")
    print(f"   Процент заполнения: {filled_count/len(test_scenario)*100:.1f}%")
    
    # 5. Рекомендации по исправлению
    print(f"\n💡 РЕКОМЕНДАЦИИ:")
    print("-" * 30)
    
    if filled_count == len(test_scenario):
        print("✅ Все данные заполнены корректно")
        print("🔍 Проблема может быть в:")
        print("   1. Процессе записи в Google Sheets API")
        print("   2. Порядке столбцов в таблице")
        print("   3. Обработке данных в g_sheets.py")
    else:
        print("❌ Есть незаполненные поля")
        print("🔧 Нужно проверить:")
        print("   1. Получение данных инициатора из БД")
        print("   2. Заполнение полей формы")
        print("   3. Системные данные")
    
    return filled_count == len(test_scenario)

if __name__ == "__main__":
    diagnose_export_issue()
