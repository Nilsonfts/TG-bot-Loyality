#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки обработчиков админских кнопок
"""

import sys
import os
import logging
from unittest.mock import Mock, patch, AsyncMock

# Добавляем текущую директорию в Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка логгирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_admin_buttons():
    """Тестируем админские кнопки одобрения и отклонения"""
    
    print("🧪 ТЕСТИРОВАНИЕ АДМИНСКИХ КНОПОК")
    print("=" * 50)
    
    # Импортируем модули
    import admin_handlers
    from constants import CALLBACK_APPROVE_PREFIX, CALLBACK_REJECT_PREFIX
    
    # Мокаем объекты Telegram
    mock_update = Mock()
    mock_context = Mock()
    mock_query = Mock()
    
    # Настраиваем mock объекты
    mock_update.callback_query = mock_query
    mock_query.answer = AsyncMock()
    mock_query.edit_message_text = AsyncMock()
    mock_query.data = f"{CALLBACK_APPROVE_PREFIX}1"  # Тестируем одобрение заявки №1
    mock_query.from_user.id = 123456789
    mock_query.message.text_html = "Тестовое сообщение админа"
    
    mock_context.bot.send_message = AsyncMock()
    
    print("✅ Mock объекты созданы")
    
    # Мокаем функции g_sheets
    with patch('admin_handlers.g_sheets.update_cell_by_row', return_value=True) as mock_update_cell, \
         patch('admin_handlers.g_sheets.get_row_data', return_value={
             'ТГ Заполняющего': '987654321',
             'Тег Telegram': '@testuser',
             'Имя владельца карты': 'Тест',
             'Фамилия Владельца': 'Тестов'
         }) as mock_get_row, \
         patch.dict(os.environ, {'BOSS_ID': '123456789'}):
        
        print("📝 Тестируем approve_request...")
        
        try:
            # Вызываем функцию одобрения
            await admin_handlers.approve_request(mock_update, mock_context)
            
            # Проверяем, что функции были вызваны
            mock_query.answer.assert_called_once()
            mock_update_cell.assert_called_once_with(1, 'Статус Согласования', 'Одобрено')
            mock_query.edit_message_text.assert_called_once()
            mock_context.bot.send_message.assert_called_once()
            
            print("✅ approve_request работает корректно")
            
        except Exception as e:
            print(f"❌ Ошибка в approve_request: {e}")
            return False
    
    # Тестируем отклонение
    print("📝 Тестируем reject_request_start...")
    
    mock_query.data = f"{CALLBACK_REJECT_PREFIX}2"  # Тестируем отклонение заявки №2
    mock_context.user_data = {}
    mock_query.message.reply_text = AsyncMock()
    
    try:
        result = await admin_handlers.reject_request_start(mock_update, mock_context)
        
        # Проверяем, что возвращается правильное состояние
        from constants import AWAIT_REJECT_REASON
        assert result == AWAIT_REJECT_REASON, f"Ожидался {AWAIT_REJECT_REASON}, получен {result}"
        
        # Проверяем, что row_index сохранен
        assert mock_context.user_data.get('admin_action_row_index') == 2
        
        print("✅ reject_request_start работает корректно")
        
    except Exception as e:
        print(f"❌ Ошибка в reject_request_start: {e}")
        return False
    
    print("\n🎉 ВСЕ ТЕСТЫ АДМИНСКИХ КНОПОК ПРОЙДЕНЫ!")
    return True

async def test_callback_patterns():
    """Тестируем паттерны callback данных"""
    
    print("\n🧪 ТЕСТИРОВАНИЕ ПАТТЕРНОВ CALLBACK")
    print("=" * 50)
    
    from constants import CALLBACK_APPROVE_PREFIX, CALLBACK_REJECT_PREFIX
    
    # Тестовые данные
    test_callbacks = [
        f"{CALLBACK_APPROVE_PREFIX}1",
        f"{CALLBACK_APPROVE_PREFIX}25", 
        f"{CALLBACK_REJECT_PREFIX}3",
        f"{CALLBACK_REJECT_PREFIX}100"
    ]
    
    for callback_data in test_callbacks:
        try:
            # Извлекаем row_index
            row_index = int(callback_data.split(':')[1])
            prefix = callback_data.split(':')[0] + ':'
            
            if prefix == CALLBACK_APPROVE_PREFIX:
                action = "одобрение"
            elif prefix == CALLBACK_REJECT_PREFIX:
                action = "отклонение"
            else:
                action = "неизвестное"
            
            print(f"✅ {callback_data} -> {action} заявки №{row_index}")
            
        except Exception as e:
            print(f"❌ Ошибка обработки {callback_data}: {e}")
            return False
    
    print("✅ Все паттерны обрабатываются корректно")
    return True

def test_constants():
    """Проверяем константы"""
    
    print("\n🧪 ПРОВЕРКА КОНСТАНТ")
    print("=" * 30)
    
    try:
        from constants import (
            CALLBACK_APPROVE_PREFIX, CALLBACK_REJECT_PREFIX, 
            AWAIT_REJECT_REASON, SheetCols
        )
        
        print(f"✅ CALLBACK_APPROVE_PREFIX = '{CALLBACK_APPROVE_PREFIX}'")
        print(f"✅ CALLBACK_REJECT_PREFIX = '{CALLBACK_REJECT_PREFIX}'")
        print(f"✅ AWAIT_REJECT_REASON = {AWAIT_REJECT_REASON}")
        print(f"✅ SheetCols.STATUS_COL = '{SheetCols.STATUS_COL}'")
        print(f"✅ SheetCols.REASON_REJECT = '{SheetCols.REASON_REJECT}'")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка импорта констант: {e}")
        return False

async def main():
    """Главная функция тестирования"""
    
    print("🤖 ЗАПУСК ТЕСТИРОВАНИЯ АДМИНСКИХ ФУНКЦИЙ")
    print("=" * 60)
    
    # Устанавливаем тестовые переменные окружения
    os.environ['GOOGLE_CREDS_JSON'] = '{"type": "service_account"}'
    os.environ['GOOGLE_SHEET_KEY'] = 'test_key'
    os.environ['SHEET_GID'] = '0'
    os.environ['BOSS_ID'] = '123456789'
    
    tests_passed = 0
    total_tests = 3
    
    # Тест 1: Константы
    if test_constants():
        tests_passed += 1
    
    # Тест 2: Паттерны callback
    if await test_callback_patterns():
        tests_passed += 1
    
    # Тест 3: Админские кнопки
    if await test_admin_buttons():
        tests_passed += 1
    
    # Итоги
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    print(f"✅ Пройдено тестов: {tests_passed}/{total_tests}")
    print(f"📈 Процент успеха: {(tests_passed/total_tests)*100:.1f}%")
    
    if tests_passed == total_tests:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! АДМИНСКИЕ ФУНКЦИИ РАБОТАЮТ!")
        return True
    else:
        print(f"\n⚠️ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ. ТРЕБУЕТСЯ ДОРАБОТКА.")
        return False

if __name__ == "__main__":
    import asyncio
    
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
