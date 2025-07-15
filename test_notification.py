#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки функции format_admin_notification
"""

import sys
import os

# Добавляем текущую директорию в Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from admin_handlers import format_admin_notification

def test_format_admin_notification():
    """Тестирует функцию форматирования уведомлений админа"""
    
    # Тестовые данные как из context.user_data
    test_data = {
        'submission_time': '2025-07-15 18:45:00',
        'tg_user_id': '123456789',
        'initiator_username': '@testuser',
        'initiator_email': 'test@company.com',
        'initiator_fio': 'Тестов Тест Тестович',
        'initiator_job_title': 'Менеджер',
        'initiator_phone': '89991234567',
        'owner_last_name': 'Иванов',
        'owner_first_name': 'Иван',
        'reason': 'Для партнера',
        'card_type': 'Бартер',
        'card_number': '89991234567',
        'category': 'АРТ',
        'amount': '5000',
        'frequency': 'Разовая',
        'issue_location': 'Москва',
        'status': 'На согласовании'
    }
    
    print("=== ТЕСТ ФУНКЦИИ format_admin_notification ===")
    print(f"Входные данные: {test_data}")
    print()
    
    try:
        result = format_admin_notification(test_data, 6)
        print("Результат функции:")
        print("TEXT:")
        print(result["text"])
        print()
        print("REPLY_MARKUP:")
        print(result["reply_markup"])
        print()
        print("✅ ТЕСТ УСПЕШЕН!")
        
    except Exception as e:
        print(f"❌ ОШИБКА В ТЕСТЕ: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_format_admin_notification()
