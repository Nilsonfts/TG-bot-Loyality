# -*- coding: utf-8 -*-

"""
Утилиты для валидации данных, безопасности и работы с внутренней базой данных.
"""

import re
import logging
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# === ВАЛИДАЦИЯ ДАННЫХ ===

def validate_phone_number(phone: str) -> bool:
    """Валидация номера телефона (должен начинаться с 8 и содержать 11 цифр)."""
    return bool(re.match(r'^8\d{10}$', phone))

def validate_email(email: str) -> bool:
    """Расширенная валидация email."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_fio(fio: str) -> bool:
    """Валидация ФИО (минимум 2 слова, только буквы, пробелы и дефисы)."""
    pattern = r'^[а-яёА-ЯЁa-zA-Z\s\-]{2,}\s+[а-яёА-ЯЁa-zA-Z\s\-]{2,}.*$'
    return bool(re.match(pattern, fio.strip()))

def sanitize_input(text: str, max_length: int = 255) -> str:
    """Очистка пользовательского ввода от потенциально опасных символов."""
    if not text:
        return ""
    
    # Убираем опасные символы
    sanitized = re.sub(r'[<>"\';\\]', '', text.strip())
    
    # Ограничиваем длину
    return sanitized[:max_length]

def validate_amount(amount: str, card_type: str) -> tuple[bool, str]:
    """
    Валидация суммы/процента в зависимости от типа карты.
    Возвращает (is_valid, error_message)
    """
    try:
        amount_val = float(amount)
        
        if card_type == "Скидка":
            if 0 < amount_val <= 100:
                return True, ""
            else:
                return False, "Скидка должна быть от 1% до 100%"
        else:  # Бартер
            if amount_val > 0:
                return True, ""
            else:
                return False, "Сумма бартера должна быть больше 0"
                
    except ValueError:
        return False, "Введите корректное число"

# === ВНУТРЕННЯЯ БАЗА ДАННЫХ (SQLite) ===

def get_db_path():
    """Возвращает путь к базе данных, используя volume если доступен."""
    volume_path = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', os.getcwd())
    return os.path.join(volume_path, 'bot_data.db')

def init_local_db():
    """Инициализация локальной SQLite базы для быстрого доступа к данным."""
    # Используем volume для постоянного хранения данных
    db_path = get_db_path()
    
    # Создаём директорию если её нет
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    logger.info(f"Инициализация БД по пути: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Создаем таблицу пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                tg_id TEXT PRIMARY KEY,
                fio TEXT NOT NULL,
                email TEXT NOT NULL,
                job_title TEXT,
                phone TEXT,
                username TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Создаем таблицу заявок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_user_id TEXT NOT NULL,
                owner_last_name TEXT,
                owner_first_name TEXT,
                card_number TEXT,
                card_type TEXT,
                amount REAL,
                category TEXT,
                frequency TEXT,
                issue_location TEXT,
                reason TEXT,
                status TEXT DEFAULT 'На согласовании',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                google_sheets_synced BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (tg_user_id) REFERENCES users (tg_id)
            )
        ''')
        
        # Создаем индексы для быстрого поиска
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_tg_id ON users(tg_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_applications_tg_user_id ON applications(tg_user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_applications_card_number ON applications(card_number)')
        
        conn.commit()
        conn.close()
        
        logger.info("Локальная база данных успешно инициализирована")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при инициализации локальной БД: {e}")
        return False

def save_user_to_local_db(user_data: Dict) -> bool:
    """Сохранение данных пользователя в локальную БД."""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (tg_id, fio, email, job_title, phone, username, last_activity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_data.get('tg_user_id'),
            user_data.get('initiator_fio'),
            user_data.get('initiator_email'),
            user_data.get('initiator_job_title'),
            user_data.get('initiator_phone'),
            user_data.get('initiator_username'),
            datetime.now()
        ))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении пользователя в локальную БД: {e}")
        return False

def save_application_to_local_db(app_data: Dict) -> Optional[int]:
    """Сохранение заявки в локальную БД. Возвращает ID записи."""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO applications 
            (tg_user_id, owner_last_name, owner_first_name, card_number, 
             card_type, amount, category, frequency, issue_location, reason, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            app_data.get('tg_user_id'),
            app_data.get('owner_last_name'),
            app_data.get('owner_first_name'),
            app_data.get('card_number'),
            app_data.get('card_type'),
            app_data.get('amount'),
            app_data.get('category'),
            app_data.get('frequency'),
            app_data.get('issue_location'),
            app_data.get('reason'),
            app_data.get('status', 'На согласовании')
        ))
        
        app_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return app_id
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении заявки в локальную БД: {e}")
        return None

def get_user_from_local_db(tg_id: str) -> Optional[Dict]:
    """Получение данных пользователя из локальной БД."""
    logger.info(f"🔍 Ищем пользователя в локальной БД: tg_id={tg_id}")
    
    try:
        db_path = get_db_path()
        logger.info(f"📂 Путь к БД: {db_path}")
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Сначала проверим, сколько пользователей в таблице
        cursor.execute('SELECT COUNT(*) as count FROM users')
        count_result = cursor.fetchone()
        logger.info(f"📊 Всего пользователей в БД: {count_result['count']}")
        
        # Теперь ищем конкретного пользователя
        cursor.execute('SELECT * FROM users WHERE tg_id = ?', (tg_id,))
        row = cursor.fetchone()
        
        if row:
            result = dict(row)
            logger.info(f"✅ Пользователь найден в локальной БД: {result}")
            conn.close()
            return result
        else:
            logger.warning(f"❌ Пользователь с tg_id={tg_id} не найден в локальной БД")
            
            # Покажем несколько записей для отладки
            cursor.execute('SELECT tg_id, fio FROM users LIMIT 5')
            sample_users = cursor.fetchall()
            logger.info(f"🔍 Примеры пользователей в БД: {[dict(u) for u in sample_users]}")
            
        conn.close()
        return None
        
    except Exception as e:
        logger.error(f"💥 Ошибка при получении пользователя из локальной БД: {e}")
        return None

def get_initiator_from_local_db(tg_id: str) -> Optional[Dict]:
    """Получение данных инициатора из локальной БД в нужном формате для формы."""
    logger.info(f"🔍 Получаем данные инициатора из локальной БД для tg_id: {tg_id}")
    
    user_data = get_user_from_local_db(tg_id)
    if not user_data:
        logger.warning(f"❌ Данные для tg_id {tg_id} не найдены в локальной БД")
        return None
    
    logger.info(f"✅ Найдены данные в локальной БД: {user_data}")
    
    # Преобразуем данные в формат, который ожидает форма
    result = {
        "initiator_username": user_data.get('username', ''),
        "initiator_email": user_data.get('email', ''),
        "initiator_fio": user_data.get('fio', ''),
        "initiator_job_title": user_data.get('job_title', ''),
        "initiator_phone": user_data.get('phone', ''),
    }
    
    logger.info(f"📋 Возвращаем преобразованные данные: {result}")
    return result

def search_applications_local(query: str, search_type: str = 'name', user_id: str = None) -> List[Dict]:
    """Быстрый поиск заявок в локальной БД."""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if search_type == 'name':
            sql = '''
                SELECT * FROM applications 
                WHERE (owner_first_name LIKE ? OR owner_last_name LIKE ?)
            '''
            params = [f'%{query}%', f'%{query}%']
        else:  # phone
            sql = 'SELECT * FROM applications WHERE card_number LIKE ?'
            params = [f'%{query}%']
        
        if user_id:
            sql += ' AND tg_user_id = ?'
            params.append(user_id)
            
        sql += ' ORDER BY created_at DESC'
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
        
    except Exception as e:
        logger.error(f"Ошибка при поиске в локальной БД: {e}")
        return []

def sync_with_google_sheets():
    """Синхронизация локальной БД с Google Sheets (фоновая задача)."""
    # Эта функция может выполняться периодически для обеспечения консистентности данных
    pass

# === СИСТЕМА УВЕДОМЛЕНИЙ ===

def should_send_reminder(last_activity: datetime) -> bool:
    """Проверяет, нужно ли отправить напоминание пользователю."""
    days_inactive = (datetime.now() - last_activity).days
    return days_inactive >= 7  # Напоминание через неделю неактивности

def get_users_for_reminder() -> List[Dict]:
    """Получает пользователей, которым нужно отправить напоминание."""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        week_ago = datetime.now() - timedelta(days=7)
        
        cursor.execute('''
            SELECT * FROM users 
            WHERE last_activity < ? 
            ORDER BY last_activity ASC
        ''', (week_ago,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
        
    except Exception as e:
        logger.error(f"Ошибка при получении пользователей для напоминания: {e}")
        return []

def update_user_activity(tg_id: str) -> bool:
    """Обновляет время последней активности пользователя."""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET last_activity = ? 
            WHERE tg_id = ?
        ''', (datetime.now(), tg_id))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении активности пользователя {tg_id}: {e}")
        return False

def cleanup_old_cache() -> None:
    """Очищает устаревший кэш из памяти."""
    try:
        import g_sheets
        current_time = datetime.now()
        
        # Очищаем устаревшие записи из кэша пользователей
        expired_users = []
        for user_id, cache_entry in g_sheets.INITIATOR_DATA_CACHE.items():
            if (current_time - cache_entry['timestamp']).total_seconds() > g_sheets.CACHE_EXPIRATION_SECONDS:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del g_sheets.INITIATOR_DATA_CACHE[user_id]
        
        # Очищаем устаревшие записи из кэша регистрации
        expired_reg = []
        for user_id, cache_entry in g_sheets.REGISTRATION_STATUS_CACHE.items():
            if (current_time - cache_entry['timestamp']).total_seconds() > g_sheets.CACHE_EXPIRATION_SECONDS:
                expired_reg.append(user_id)
        
        for user_id in expired_reg:
            del g_sheets.REGISTRATION_STATUS_CACHE[user_id]
        
        logger.info(f"Очищен кэш: {len(expired_users)} пользователей, {len(expired_reg)} записей регистрации")
        
    except Exception as e:
        logger.error(f"Ошибка при очистке кэша: {e}")

def backup_local_db() -> bool:
    """Создает резервную копию локальной базы данных."""
    try:
        db_path = get_db_path()
        backup_path = os.path.join(os.getcwd(), f'bot_data_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
        
        if os.path.exists(db_path):
            import shutil
            shutil.copy2(db_path, backup_path)
            logger.info(f"Создана резервная копия БД: {backup_path}")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии БД: {e}")
        return False

def get_statistics() -> dict:
    """
    Возвращает статистику по заявкам из локальной базы данных.
    """
    try:
        db_path = get_db_path()
        
        if not os.path.exists(db_path):
            return {"error": "База данных не найдена"}
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Общее количество заявок
        cursor.execute("SELECT COUNT(*) FROM applications")
        total = cursor.fetchone()[0]
        
        # Статистика по статусам
        cursor.execute("SELECT status, COUNT(*) FROM applications GROUP BY status")
        status_stats = dict(cursor.fetchall())
        
        # Статистика по типам карт
        cursor.execute("SELECT card_type, COUNT(*) FROM applications GROUP BY card_type")
        card_type_stats = dict(cursor.fetchall())
        
        # Статистика по категориям
        cursor.execute("SELECT category, COUNT(*) FROM applications GROUP BY category")
        category_stats = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            'total': total,
            'by_status': status_stats,
            'by_card_type': card_type_stats,
            'by_category': category_stats
        }
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        return {"error": str(e)}
