#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Комплексный автоматический тест Telegram-бота "Лояльность"
Проверяет все ключевые функции системы без необходимости в Telegram API
"""

import sys
import os
import json
import logging
from datetime import datetime
from unittest.mock import Mock, patch

# Добавляем текущую директорию в Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка логгирования для тестов
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BotTester:
    """Класс для автоматического тестирования бота"""
    
    def __init__(self):
        self.test_results = []
        self.passed_tests = 0
        self.failed_tests = 0
        
    def run_test(self, test_name, test_func):
        """Запускает отдельный тест и записывает результат"""
        print(f"\n🧪 Запуск теста: {test_name}")
        try:
            test_func()
            print(f"✅ ПРОЙДЕН: {test_name}")
            self.test_results.append(f"✅ {test_name}")
            self.passed_tests += 1
        except Exception as e:
            print(f"❌ ПРОВАЛЕН: {test_name} - {str(e)}")
            self.test_results.append(f"❌ {test_name} - {str(e)}")
            self.failed_tests += 1
    
    def test_imports(self):
        """Тест импорта всех модулей"""
        import constants
        import g_sheets
        import utils
        import admin_handlers
        import form_handlers
        import registration_handlers
        import keyboards
        import navigation_handlers
        import search_handlers
        import settings_handlers
        import reports
        assert hasattr(constants, 'SheetCols'), "SheetCols не найден в constants"
        assert hasattr(g_sheets, 'write_row'), "write_row не найден в g_sheets"
        assert hasattr(utils, 'validate_email'), "validate_email не найден в utils"
    
    def test_constants(self):
        """Тест констант"""
        from constants import SheetCols
        required_cols = [
            'TIMESTAMP', 'TG_ID', 'EMAIL', 'FIO_INITIATOR', 
            'OWNER_LAST_NAME_COL', 'CARD_TYPE_COL', 'STATUS_COL'
        ]
        for col in required_cols:
            assert hasattr(SheetCols, col), f"Константа {col} отсутствует"
    
    def test_validation_functions(self):
        """Тест функций валидации"""
        import utils
        
        # Тест валидации телефона
        assert utils.validate_phone_number("89991234567") == True
        assert utils.validate_phone_number("79991234567") == False
        assert utils.validate_phone_number("8999123456") == False
        
        # Тест валидации email
        assert utils.validate_email("test@company.com") == True
        assert utils.validate_email("invalid-email") == False
        assert utils.validate_email("test@") == False
        
        # Тест валидации ФИО
        assert utils.validate_fio("Иванов Иван Иванович") == True
        assert utils.validate_fio("И") == False
        
        # Тест валидации суммы
        is_valid, _ = utils.validate_amount("50", "Скидка")
        assert is_valid == True
        
        is_valid, _ = utils.validate_amount("150", "Скидка")
        assert is_valid == False
        
        is_valid, _ = utils.validate_amount("5000", "Бартер")
        assert is_valid == True
    
    def test_admin_notification_formatting(self):
        """Тест форматирования уведомлений админа"""
        import admin_handlers
        
        # Тестовые данные из context.user_data
        test_data = {
            'initiator_fio': 'Тестов Тест Тестович',
            'initiator_username': '@testuser',
            'owner_first_name': 'Иван',
            'owner_last_name': 'Иванов',
            'card_number': '89991234567',
            'card_type': 'Бартер',
            'amount': '5000',
            'category': 'АРТ',
            'issue_location': 'Москва'
        }
        
        result = admin_handlers.format_admin_notification(test_data, 1)
        
        assert 'text' in result, "Нет ключа 'text' в результате"
        assert 'reply_markup' in result, "Нет ключа 'reply_markup' в результате"
        assert 'Тестов Тест Тестович' in result['text'], "ФИО не найдено в тексте"
        assert 'Иван Иванов' in result['text'], "Имя владельца не найдено"
        assert '5000 ₽' in result['text'], "Сумма не найдена"
        assert 'АРТ' in result['text'], "Категория не найдена"
    
    def test_sanitization(self):
        """Тест очистки данных"""
        import utils
        
        # Тест очистки опасных символов
        dirty_input = "Тест<script>alert('hack')</script>"
        clean_output = utils.sanitize_input(dirty_input)
        assert '<script>' not in clean_output, "Опасные символы не удалены"
        
        # Тест ограничения длины
        long_input = "a" * 300
        limited_output = utils.sanitize_input(long_input, 100)
        assert len(limited_output) <= 100, "Длина не ограничена"
    
    def test_database_initialization(self):
        """Тест инициализации локальной базы данных"""
        import utils
        
        # Создаем тестовую БД
        result = utils.init_local_db()
        assert result == True, "Не удалось инициализировать локальную БД"
        
        # Проверяем, что файл БД создался
        db_path = os.path.join(os.getcwd(), 'bot_data.db')
        assert os.path.exists(db_path), "Файл базы данных не создался"
    
    def test_user_data_operations(self):
        """Тест операций с пользовательскими данными"""
        import utils
        
        # Инициализируем БД
        utils.init_local_db()
        
        # Тестовые данные пользователя
        test_user = {
            'tg_user_id': 'test_123',
            'initiator_fio': 'Тестов Тест',
            'initiator_email': 'test@test.com',
            'initiator_job_title': 'Тестер',
            'initiator_phone': '89991234567',
            'initiator_username': '@tester'
        }
        
        # Сохраняем пользователя
        result = utils.save_user_to_local_db(test_user)
        assert result == True, "Не удалось сохранить пользователя"
        
        # Получаем пользователя
        saved_user = utils.get_user_from_local_db('test_123')
        assert saved_user is not None, "Не удалось получить пользователя"
        assert saved_user['fio'] == 'Тестов Тест', "ФИО не совпадает"
    
    def test_application_operations(self):
        """Тест операций с заявками"""
        import utils
        
        # Инициализируем БД
        utils.init_local_db()
        
        # Тестовые данные заявки
        test_app = {
            'tg_user_id': 'test_123',
            'owner_last_name': 'Иванов',
            'owner_first_name': 'Иван',
            'card_number': '89991234567',
            'card_type': 'Бартер',
            'amount': '5000',
            'category': 'АРТ',
            'issue_location': 'Москва',
            'status': 'На согласовании'
        }
        
        # Сохраняем заявку
        app_id = utils.save_application_to_local_db(test_app)
        assert app_id is not None, "Не удалось сохранить заявку"
        assert isinstance(app_id, int), "ID заявки должен быть числом"
        
        # Тестируем поиск
        search_results = utils.search_applications_local('Иван', 'name')
        assert len(search_results) > 0, "Поиск не нашел заявку"
        assert search_results[0]['owner_first_name'] == 'Иван', "Неверные результаты поиска"
    
    def test_keyboard_generation(self):
        """Тест генерации клавиатур"""
        import keyboards
        
        # Тест главного меню для зарегистрированного пользователя
        keyboard_registered = keyboards.get_main_menu_keyboard(True)
        assert keyboard_registered is not None, "Клавиатура для зарегистрированного пользователя не создалась"
        
        # Тест главного меню для незарегистрированного пользователя
        keyboard_unregistered = keyboards.get_main_menu_keyboard(False)
        assert keyboard_unregistered is not None, "Клавиатура для незарегистрированного пользователя не создалась"
        
        # Тест клавиатуры настроек
        settings_keyboard = keyboards.get_settings_keyboard(True)
        assert settings_keyboard is not None, "Клавиатура настроек не создалась"
    
    def test_statistics_function(self):
        """Тест функции статистики"""
        import utils
        
        # Инициализируем БД и добавляем тестовые данные
        utils.init_local_db()
        
        # Добавляем несколько тестовых заявок
        test_apps = [
            {
                'tg_user_id': 'test_1', 'card_type': 'Бартер', 'status': 'Одобрено',
                'owner_first_name': 'Тест1', 'owner_last_name': 'Тестов1',
                'card_number': '89991111111', 'amount': '1000', 'category': 'АРТ',
                'issue_location': 'Москва'
            },
            {
                'tg_user_id': 'test_2', 'card_type': 'Скидка', 'status': 'На согласовании',
                'owner_first_name': 'Тест2', 'owner_last_name': 'Тестов2',
                'card_number': '89992222222', 'amount': '15', 'category': 'МАРКЕТ',
                'issue_location': 'СПб'
            }
        ]
        
        for app in test_apps:
            utils.save_application_to_local_db(app)
        
        # Получаем статистику
        stats = utils.get_statistics()
        
        # Проверяем структуру статистики
        assert 'total' in stats, "Отсутствует общее количество"
        assert 'by_status' in stats, "Отсутствует статистика по статусам"
        assert 'by_card_type' in stats, "Отсутствует статистика по типам карт"
    
    def test_data_integrity(self):
        """Тест целостности данных между модулями"""
        from constants import SheetCols
        import g_sheets
        
        # Проверяем, что все константы столбцов существуют
        required_columns = [
            SheetCols.TIMESTAMP, SheetCols.TG_ID, SheetCols.EMAIL,
            SheetCols.FIO_INITIATOR, SheetCols.OWNER_LAST_NAME_COL,
            SheetCols.CARD_TYPE_COL, SheetCols.STATUS_COL
        ]
        
        for col in required_columns:
            assert col is not None, f"Константа столбца {col} не определена"
            assert isinstance(col, str), f"Константа столбца {col} должна быть строкой"
    
    def run_all_tests(self):
        """Запускает все тесты"""
        print("🤖 ЗАПУСК АВТОМАТИЧЕСКОГО ТЕСТИРОВАНИЯ TELEGRAM-БОТА")
        print("=" * 60)
        
        # Список всех тестов
        tests = [
            ("Импорт модулей", self.test_imports),
            ("Проверка констант", self.test_constants),
            ("Функции валидации", self.test_validation_functions),
            ("Форматирование уведомлений админа", self.test_admin_notification_formatting),
            ("Очистка данных", self.test_sanitization),
            ("Инициализация БД", self.test_database_initialization),
            ("Операции с пользователями", self.test_user_data_operations),
            ("Операции с заявками", self.test_application_operations),
            ("Генерация клавиатур", self.test_keyboard_generation),
            ("Функция статистики", self.test_statistics_function),
            ("Целостность данных", self.test_data_integrity),
        ]
        
        # Запускаем все тесты
        for test_name, test_func in tests:
            self.run_test(test_name, test_func)
        
        # Выводим итоговый отчет
        print("\n" + "=" * 60)
        print("📊 ИТОГОВЫЙ ОТЧЕТ ТЕСТИРОВАНИЯ")
        print("=" * 60)
        
        for result in self.test_results:
            print(result)
        
        print(f"\n📈 СТАТИСТИКА:")
        print(f"✅ Пройдено тестов: {self.passed_tests}")
        print(f"❌ Провалено тестов: {self.failed_tests}")
        print(f"📊 Общий процент успеха: {(self.passed_tests / (self.passed_tests + self.failed_tests) * 100):.1f}%")
        
        if self.failed_tests == 0:
            print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО! СИСТЕМА ГОТОВА К ПРОДАКШЕНУ!")
            return True
        else:
            print(f"\n⚠️ ОБНАРУЖЕНЫ ПРОБЛЕМЫ. НЕОБХОДИМО ИСПРАВИТЬ {self.failed_tests} ОШИБОК.")
            return False

def cleanup_test_database():
    """Очищает тестовую базу данных"""
    db_path = os.path.join(os.getcwd(), 'bot_data.db')
    if os.path.exists(db_path):
        os.remove(db_path)
        print("🧹 Тестовая база данных очищена")

if __name__ == "__main__":
    # Устанавливаем тестовые переменные окружения
    os.environ['GOOGLE_CREDS_JSON'] = json.dumps({
        "type": "service_account",
        "project_id": "test_project"
    })
    os.environ['GOOGLE_SHEET_KEY'] = "test_sheet_key"
    os.environ['SHEET_GID'] = "0"
    os.environ['BOSS_ID'] = "123456789"
    
    try:
        # Очищаем предыдущие тестовые данные
        cleanup_test_database()
        
        # Запускаем тесты
        tester = BotTester()
        success = tester.run_all_tests()
        
        # Очищаем после тестов
        cleanup_test_database()
        
        # Возвращаем код выхода
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА ПРИ ТЕСТИРОВАНИИ: {e}")
        import traceback
        traceback.print_exc()
        cleanup_test_database()
        sys.exit(1)
