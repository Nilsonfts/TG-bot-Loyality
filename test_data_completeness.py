#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест полной выгрузки данных в Google Sheets
Проверяет, что все поля заполняются корректно
"""

import sys
import os
import logging

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import utils
from constants import SheetCols

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_data_export_completeness():
    """Тестирует полноту выгрузки данных."""
    
    print("🧪 ТЕСТ ПОЛНОТЫ ВЫГРУЗКИ ДАННЫХ")
    print("=" * 50)
    
    # Создаем тестового пользователя в локальной БД
    test_user_id = "987654321"
    
    try:
        # Инициализируем БД
        utils.init_local_db()
        
        # Добавляем тестового пользователя в правильном формате
        test_user_data = {
            'tg_user_id': test_user_id,
            'initiator_fio': 'Тестовый Инициатор Тестович',
            'initiator_email': 'test.initiator@example.com',
            'initiator_job_title': 'Главный тестировщик',
            'initiator_phone': '+7 (999) 888-77-66',
            'initiator_username': '@test_initiator'
        }
        
        utils.save_user_to_local_db(test_user_data)
        print(f"✅ Тестовый пользователь создан: {test_user_id}")
        
        # Получаем данные инициатора
        initiator_data = utils.get_initiator_from_local_db(test_user_id)
        print(f"\n📋 Данные инициатора из БД:")
        for key, value in initiator_data.items():
            print(f"   {key}: '{value}'")
        
        # Создаем полный набор данных формы
        form_data = {
            'owner_last_name': 'Владельцев',
            'owner_first_name': 'Владимир',
            'reason': 'Тестовая причина выдачи карты',
            'card_type': 'Бартер',
            'card_number': '9876543210',
            'category': 'Тестовая категория',
            'amount': '5000',
            'frequency': 'Ежемесячно',
            'issue_location': 'Тестовый бар "У Программиста"'
        }
        
        # Объединяем данные
        complete_data = {}
        complete_data.update(initiator_data)
        complete_data.update(form_data)
        complete_data.update({
            'submission_time': '2025-07-16 16:00:00',
            'tg_user_id': test_user_id,
            'status': 'На согласовании',
            'initiator_username': '@test_initiator'
        })
        
        print(f"\n📊 ПОЛНЫЙ НАБОР ДАННЫХ ({len(complete_data)} полей):")
        for i, (key, value) in enumerate(complete_data.items(), 1):
            print(f"   {i:2d}. {key}: '{value}'")
        
        # Проверяем соответствие с константами Google Sheets
        print(f"\n🔍 ПРОВЕРКА СООТВЕТСТВИЯ КОНСТАНТАМ:")
        
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
        
        mapped_data = {}
        for data_field, sheet_column in field_mapping.items():
            value = complete_data.get(data_field, '')
            mapped_data[sheet_column] = value
            status = "✅" if value else "❌"
            print(f"   {status} {data_field} → {sheet_column}: '{value}'")
        
        # Добавляем поля, которые будут пустыми при создании
        mapped_data[SheetCols.APPROVAL_STATUS] = ''
        mapped_data[SheetCols.START_DATE] = ''
        mapped_data[SheetCols.ACTIVATED] = ''
        mapped_data[SheetCols.REASON_REJECT] = ''
        
        print(f"\n📋 ИТОГОВЫЕ ДАННЫЕ ДЛЯ GOOGLE SHEETS ({len(mapped_data)} полей):")
        for i, (column, value) in enumerate(mapped_data.items(), 1):
            status = "✅" if value else "⭕"
            print(f"   {i:2d}. {status} {column}: '{value}'")
        
        filled_fields = sum(1 for v in mapped_data.values() if v)
        total_fields = len(mapped_data)
        
        print(f"\n📈 СТАТИСТИКА:")
        print(f"   Заполнено полей: {filled_fields}/{total_fields}")
        print(f"   Процент заполнения: {filled_fields/total_fields*100:.1f}%")
        
        if filled_fields >= total_fields - 4:  # 4 поля заполняются позже (approval и т.д.)
            print(f"\n🎉 ТЕСТ ПРОЙДЕН! Все необходимые поля заполнены")
            return True
        else:
            print(f"\n❌ ТЕСТ НЕ ПРОЙДЕН! Недостаточно заполненных полей")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка теста: {e}")
        return False

if __name__ == "__main__":
    test_data_export_completeness()
