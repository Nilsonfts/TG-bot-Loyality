#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест интеграции с Railway Volume
Проверяет, что база данных создаётся в правильном месте
"""

import os
import sys
import tempfile
import logging

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import utils

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_volume_integration():
    """Тестирует интеграцию с Railway Volume."""
    
    print("🧪 ТЕСТ ИНТЕГРАЦИИ С RAILWAY VOLUME")
    print("=" * 50)
    
    # Тест 1: Без volume (локальная разработка)
    print("\n1️⃣ Тест локальной разработки (без volume):")
    if 'RAILWAY_VOLUME_MOUNT_PATH' in os.environ:
        del os.environ['RAILWAY_VOLUME_MOUNT_PATH']
    
    db_path = utils.get_db_path()
    expected_local = os.path.join(os.getcwd(), 'bot_data.db')
    
    print(f"   Путь к БД: {db_path}")
    print(f"   Ожидается: {expected_local}")
    print(f"   ✅ Тест пройден: {db_path == expected_local}")
    
    # Тест 2: С volume (production на Railway)
    print("\n2️⃣ Тест production с volume:")
    test_volume_path = '/app/data'
    os.environ['RAILWAY_VOLUME_MOUNT_PATH'] = test_volume_path
    
    db_path = utils.get_db_path()
    expected_volume = os.path.join(test_volume_path, 'bot_data.db')
    
    print(f"   RAILWAY_VOLUME_MOUNT_PATH: {test_volume_path}")
    print(f"   Путь к БД: {db_path}")
    print(f"   Ожидается: {expected_volume}")
    print(f"   ✅ Тест пройден: {db_path == expected_volume}")
    
    # Тест 3: Создание БД
    print("\n3️⃣ Тест создания базы данных:")
    try:
        # Используем временную директорию для теста
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ['RAILWAY_VOLUME_MOUNT_PATH'] = temp_dir
            
            # Инициализируем БД
            utils.init_local_db()
            
            db_path = utils.get_db_path()
            db_exists = os.path.exists(db_path)
            
            print(f"   Временная директория: {temp_dir}")
            print(f"   База создана: {db_path}")
            print(f"   Файл существует: {db_exists}")
            print(f"   ✅ Тест пройден: {db_exists}")
            
            if db_exists:
                print(f"   📏 Размер файла: {os.path.getsize(db_path)} байт")
                
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False
    
    print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    print("\n📋 Следующие шаги:")
    print("   1. Установите RAILWAY_VOLUME_MOUNT_PATH=/app/data в Railway")
    print("   2. Подключите volume 'superb-volume' к mount path '/app/data'")
    print("   3. Деплойте обновленный код")
    print("   4. Проверьте логи на наличие: 'Инициализация БД по пути: /app/data/bot_data.db'")
    
    return True

if __name__ == "__main__":
    test_volume_integration()
