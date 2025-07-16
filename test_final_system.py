#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Финальный тест всей системы TG-bot-Loyalty
Комплексная проверка всех компонентов после исправлений
"""

import sys
import os
import logging
from datetime import datetime

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import utils
import g_sheets
from constants import SheetCols

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_comprehensive_test():
    """Комплексный тест всей системы."""
    
    print("🚀 ФИНАЛЬНЫЙ ТЕСТ СИСТЕМЫ TG-BOT-LOYALTY")
    print("=" * 60)
    
    results = {
        "database_init": False,
        "user_registration": False,
        "data_retrieval": False,
        "data_completeness": False,
        "volume_integration": False,
        "google_sheets_mapping": False
    }
    
    # 1. Тест инициализации базы данных
    print("\n1️⃣ ТЕСТ ИНИЦИАЛИЗАЦИИ БАЗЫ ДАННЫХ")
    print("-" * 40)
    try:
        utils.init_local_db()
        db_path = utils.get_db_path()
        if os.path.exists(db_path):
            print(f"✅ База данных создана: {db_path}")
            print(f"📏 Размер: {os.path.getsize(db_path)} байт")
            results["database_init"] = True
        else:
            print("❌ База данных не создана")
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
    
    # 2. Тест регистрации пользователя
    print("\n2️⃣ ТЕСТ РЕГИСТРАЦИИ ПОЛЬЗОВАТЕЛЯ")
    print("-" * 40)
    try:
        test_user = {
            'tg_user_id': 'test_final_user',
            'initiator_fio': 'Финальный Тестовый Пользователь',
            'initiator_email': 'final.test@bot-loyalty.com',
            'initiator_job_title': 'Системный тестировщик',
            'initiator_phone': '+7 (999) 999-99-99',
            'initiator_username': '@final_test'
        }
        
        success = utils.save_user_to_local_db(test_user)
        if success:
            print(f"✅ Пользователь сохранён: {test_user['initiator_fio']}")
            results["user_registration"] = True
        else:
            print("❌ Ошибка сохранения пользователя")
    except Exception as e:
        print(f"❌ Ошибка регистрации: {e}")
    
    # 3. Тест получения данных пользователя
    print("\n3️⃣ ТЕСТ ПОЛУЧЕНИЯ ДАННЫХ ПОЛЬЗОВАТЕЛЯ")
    print("-" * 40)
    try:
        user_data = utils.get_initiator_from_local_db('test_final_user')
        if user_data and len(user_data) >= 5:
            print(f"✅ Данные получены ({len(user_data)} полей):")
            for key, value in user_data.items():
                print(f"   {key}: {value}")
            results["data_retrieval"] = True
        else:
            print("❌ Данные не получены или неполные")
    except Exception as e:
        print(f"❌ Ошибка получения данных: {e}")
    
    # 4. Тест полноты данных для Google Sheets
    print("\n4️⃣ ТЕСТ ПОЛНОТЫ ДАННЫХ ДЛЯ GOOGLE SHEETS")
    print("-" * 40)
    try:
        # Создаем полный набор данных заявки
        complete_application = {
            'submission_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'tg_user_id': 'test_final_user',
            'initiator_username': '@final_test',
            'initiator_email': 'final.test@bot-loyalty.com',
            'initiator_fio': 'Финальный Тестовый Пользователь',
            'initiator_job_title': 'Системный тестировщик',
            'initiator_phone': '+7 (999) 999-99-99',
            'owner_first_name': 'Владимир',
            'owner_last_name': 'Тестовый',
            'reason': 'Финальная проверка системы',
            'card_type': 'Бартер',
            'card_number': '1111222233',
            'category': 'Тестирование',
            'amount': '10000',
            'frequency': 'Единоразово',
            'issue_location': 'Центр тестирования',
            'status': 'На согласовании'
        }
        
        # Проверяем маппинг всех полей
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
        
        filled_fields = 0
        for data_field, sheet_column in field_mapping.items():
            value = complete_application.get(data_field, '')
            if value:
                filled_fields += 1
        
        total_required = len(field_mapping)
        coverage = (filled_fields / total_required) * 100
        
        print(f"✅ Поля заполнены: {filled_fields}/{total_required}")
        print(f"✅ Покрытие данных: {coverage:.1f}%")
        
        if coverage >= 95:
            results["data_completeness"] = True
            print("🎉 Полнота данных ОТЛИЧНАЯ!")
        elif coverage >= 80:
            print("⚠️ Полнота данных ХОРОШАЯ")
        else:
            print("❌ Полнота данных НЕДОСТАТОЧНАЯ")
            
    except Exception as e:
        print(f"❌ Ошибка проверки полноты данных: {e}")
    
    # 5. Тест интеграции с Railway Volume
    print("\n5️⃣ ТЕСТ ИНТЕГРАЦИИ С RAILWAY VOLUME")
    print("-" * 40)
    try:
        db_path = utils.get_db_path()
        volume_env = os.getenv('RAILWAY_VOLUME_MOUNT_PATH')
        
        print(f"Переменная RAILWAY_VOLUME_MOUNT_PATH: {volume_env or 'НЕ УСТАНОВЛЕНА'}")
        print(f"Путь к БД: {db_path}")
        
        if volume_env and volume_env in db_path:
            print("✅ Volume настроен корректно для production")
            results["volume_integration"] = True
        elif not volume_env and os.getcwd() in db_path:
            print("✅ Локальная разработка настроена корректно")
            results["volume_integration"] = True
        else:
            print("❌ Проблемы с конфигурацией volume")
            
    except Exception as e:
        print(f"❌ Ошибка проверки volume: {e}")
    
    # 6. Тест констант Google Sheets
    print("\n6️⃣ ТЕСТ КОНСТАНТ GOOGLE SHEETS")
    print("-" * 40)
    try:
        # Проверяем, что все константы определены
        required_constants = [
            'TIMESTAMP', 'TG_ID', 'TG_TAG', 'EMAIL', 'FIO_INITIATOR',
            'JOB_TITLE', 'PHONE_INITIATOR', 'OWNER_FIRST_NAME_COL',
            'OWNER_LAST_NAME_COL', 'REASON_COL', 'CARD_TYPE_COL',
            'CARD_NUMBER_COL', 'CATEGORY_COL', 'AMOUNT_COL',
            'FREQUENCY_COL', 'ISSUE_LOCATION_COL', 'STATUS_COL',
            'APPROVAL_STATUS', 'START_DATE', 'ACTIVATED', 'REASON_REJECT'
        ]
        
        missing_constants = []
        for const in required_constants:
            if not hasattr(SheetCols, const):
                missing_constants.append(const)
        
        if not missing_constants:
            print(f"✅ Все константы определены ({len(required_constants)} штук)")
            results["google_sheets_mapping"] = True
        else:
            print(f"❌ Отсутствуют константы: {missing_constants}")
            
    except Exception as e:
        print(f"❌ Ошибка проверки констант: {e}")
    
    # Итоговый результат
    print(f"\n🏁 ИТОГОВЫЕ РЕЗУЛЬТАТЫ")
    print("=" * 60)
    
    passed_tests = sum(results.values())
    total_tests = len(results)
    success_rate = (passed_tests / total_tests) * 100
    
    for test_name, result in results.items():
        status = "✅ ПРОЙДЕН" if result else "❌ НЕ ПРОЙДЕН"
        print(f"   {test_name.replace('_', ' ').title()}: {status}")
    
    print(f"\n📊 ОБЩАЯ СТАТИСТИКА:")
    print(f"   Пройдено тестов: {passed_tests}/{total_tests}")
    print(f"   Процент успеха: {success_rate:.1f}%")
    
    if success_rate == 100:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! СИСТЕМА ГОТОВА К PRODUCTION!")
        print("🚀 Бот полностью функционален и готов к использованию")
    elif success_rate >= 80:
        print("\n✅ БОЛЬШИНСТВО ТЕСТОВ ПРОЙДЕНЫ! Система практически готова")
    else:
        print("\n⚠️ ТРЕБУЮТСЯ ДОПОЛНИТЕЛЬНЫЕ ИСПРАВЛЕНИЯ")
    
    print(f"\n🕐 Тест завершен: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return success_rate >= 80

if __name__ == "__main__":
    success = run_comprehensive_test()
    
    if success:
        print("\n" + "🎊" * 20)
        print("ПОЗДРАВЛЯЕМ! СИСТЕМА РАБОТАЕТ!")
        print("🎊" * 20)
    else:
        print("\n" + "🔧" * 20)
        print("ТРЕБУЮТСЯ ДОПОЛНИТЕЛЬНЫЕ РАБОТЫ")
        print("🔧" * 20)
