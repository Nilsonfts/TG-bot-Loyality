# check_google.py
import gspread
import os
import json
from google.oauth2.service_account import Credentials
import datetime

print(f"[{datetime.datetime.now()}] --- Starting Google Connection Test ---")

try:
    GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
    GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")

    if not GOOGLE_CREDS_JSON or not GOOGLE_SHEET_KEY:
        print("ОШИБКА: Убедитесь, что переменные GOOGLE_CREDS_JSON и GOOGLE_SHEET_KEY установлены.")
        exit()

    print("Шаг 1: Загрузка учетных данных из JSON...")
    creds_info = json.loads(GOOGLE_CREDS_JSON)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    print("Шаг 1: OK")

    print("Шаг 2: Авторизация в gspread...")
    client = gspread.authorize(creds)
    print("Шаг 2: OK")

    print(f"Шаг 3: Открытие таблицы по ключу: {GOOGLE_SHEET_KEY}...")
    spreadsheet = client.open_by_key(GOOGLE_SHEET_KEY)
    print("Шаг 3: OK")

    print("Шаг 4: Получение списка листов...")
    worksheet_list = spreadsheet.worksheets()
    print(f"Шаг 4: OK. Найдено {len(worksheet_list)} листов.")
    for ws in worksheet_list:
        print(f"  - Название листа: '{ws.title}', ID (GID): {ws.id}")
    
    print("\nУСПЕХ! Соединение с Google Sheets работает корректно.")

except gspread.exceptions.GSpreadException as e:
    print(f"\nОШИБКА gspread: {e}")
except Exception as e:
    print(f"\nКРИТИЧЕСКАЯ ОШИБКА: Произошла непредвиденная ошибка: {e}")

print(f"[{datetime.datetime.now()}] --- Тест завершен ---")
