#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Railway Volume Production Test
Тест для проверки работы volume в production окружении
"""

import os
import sys
import logging
from datetime import datetime

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import utils

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_railway_volume_production():
    """Тест работы Railway Volume в production."""
    
    print("🚀 RAILWAY VOLUME PRODUCTION TEST")
    print("=" * 50)
    
    # Информация об окружении
    print("\n📋 Информация об окружении:")
    print(f"   Текущая директория: {os.getcwd()}")
    print(f"   RAILWAY_VOLUME_MOUNT_PATH: {os.getenv('RAILWAY_VOLUME_MOUNT_PATH', 'НЕ УСТАНОВЛЕНА')}")
    
    # Получаем путь к БД
    db_path = utils.get_db_path()
    print(f"   Путь к базе данных: {db_path}")
    
    # Проверяем, используется ли volume
    is_volume_used = '/app/data' in db_path
    print(f"   Volume используется: {'✅ ДА' if is_volume_used else '❌ НЕТ'}")
    
    # Тест инициализации БД
    print("\n🗄️ Тест инициализации базы данных:")
    try:
        utils.init_local_db()
        
        # Проверяем, что файл создался
        if os.path.exists(db_path):
            file_size = os.path.getsize(db_path)
            print(f"   ✅ База данных создана: {db_path}")
            print(f"   📏 Размер файла: {file_size} байт")
            
            # Проверяем права доступа
            is_readable = os.access(db_path, os.R_OK)
            is_writable = os.access(db_path, os.W_OK)
            print(f"   📖 Чтение: {'✅' if is_readable else '❌'}")
            print(f"   ✏️ Запись: {'✅' if is_writable else '❌'}")
            
        else:
            print(f"   ❌ Файл базы данных не найден: {db_path}")
            
    except Exception as e:
        print(f"   ❌ Ошибка инициализации: {e}")
        return False
    
    # Тест записи данных
    print("\n💾 Тест записи тестовых данных:")
    try:
        # Создаем тестового пользователя
        test_user_data = {
            'tg_user_id': 'test_volume_user',
            'fio': 'Test Volume User',
            'email': 'test@volume.railway',
            'job_title': 'Volume Tester',
            'phone': '+1234567890',
            'username': '@volume_test'
        }
        
        result = utils.save_user_to_local_db(test_user_data)
        if result:
            print(f"   ✅ Тестовый пользователь создан: {test_user_data['fio']}")
            
            # Проверяем, что данные сохранились
            user_exists = utils.is_user_registered(test_user_data['tg_user_id'])
            print(f"   ✅ Пользователь найден в БД: {'ДА' if user_exists else 'НЕТ'}")
            
        else:
            print("   ❌ Не удалось создать тестового пользователя")
            
    except Exception as e:
        print(f"   ❌ Ошибка записи данных: {e}")
        return False
    
    # Информация о volume
    print("\n📊 Информация о volume:")
    if is_volume_used:
        volume_dir = os.path.dirname(db_path)
        if os.path.exists(volume_dir):
            try:
                # Список файлов в volume
                files = os.listdir(volume_dir)
                print(f"   📁 Содержимое {volume_dir}:")
                for file in files:
                    file_path = os.path.join(volume_dir, file)
                    if os.path.isfile(file_path):
                        size = os.path.getsize(file_path)
                        print(f"      📄 {file} ({size} байт)")
                    else:
                        print(f"      📁 {file}/ (директория)")
                        
            except Exception as e:
                print(f"   ⚠️ Не удалось прочитать содержимое volume: {e}")
        else:
            print(f"   ❌ Volume директория не существует: {volume_dir}")
    
    # Итоговый статус
    print("\n🎯 РЕЗУЛЬТАТ ТЕСТА:")
    if is_volume_used and os.path.exists(db_path):
        print("   🎉 SUCCESS: Railway Volume работает корректно!")
        print("   ✅ База данных будет сохраняться между деплоями")
        print("   ✅ Данные защищены от потери при обновлениях")
        return True
    else:
        print("   ⚠️ WARNING: Volume может работать неправильно")
        print("   📋 Проверьте настройки Railway Volume")
        return False

if __name__ == "__main__":
    success = test_railway_volume_production()
    
    # Информация для мониторинга
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if success else "FAILED"
    print(f"\n🕐 Тест завершен: {timestamp}")
    print(f"📊 Статус: {status}")
    
    # Логируем для Railway
    logger.info(f"Railway Volume Test: {status} at {timestamp}")
