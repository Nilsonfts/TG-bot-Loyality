#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки соответствия заголовков
"""

# Заголовки из логов
real_headers = [
    'Отметка времени', 
    'ID\nИнициатора', 
    'ТГ\nИнициатора', 
    'Адрес электронной почты', 
    'ФИО \nИнициатора', 
    'Должность', 
    'Телефон\nИнициатора', 
    'Имя владельца карты ', 
    'Фамилия Владельца карты ', 
    'Причина выдачи бартера/скидки ', 
    'Какую карту регистрируем? ', 
    'Номер карты', 
    'Статья пополнения карт ', 
    'Сумма бартера или  %  скидки ', 
    'Периодичность наполнения бартера', 
    'БАР', 
    'ЗАЯВКА', 
    'Согласовано САД/Директором по рекламе ', 
    'STARTDATE (пополнение по четвергам после 22:00)', 
    'Активировано'
]

# Заголовки из констант
from constants import SheetCols

constants_headers = {
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
    'APPROVAL_STATUS': SheetCols.APPROVAL_STATUS,
    'START_DATE': SheetCols.START_DATE,
    'ACTIVATED': SheetCols.ACTIVATED,
}

print("=== СРАВНЕНИЕ ЗАГОЛОВКОВ ===")
print("\nЗаголовки из таблицы:")
for i, header in enumerate(real_headers):
    print(f"{i+1:2d}. '{header}' (len={len(header)})")

print("\nЗаголовки из констант:")
for name, header in constants_headers.items():
    print(f"    {name}: '{header}' (len={len(header)})")

print("\n=== ПОИСК СОВПАДЕНИЙ ===")
for name, const_header in constants_headers.items():
    found = False
    for i, real_header in enumerate(real_headers):
        if const_header == real_header:
            print(f"✅ {name}: ТОЧНОЕ СОВПАДЕНИЕ в позиции {i+1}")
            found = True
            break
    
    if not found:
        # Пробуем нормализованное сравнение
        normalized_const = const_header.strip().replace('\n', ' ')
        for i, real_header in enumerate(real_headers):
            normalized_real = real_header.strip().replace('\n', ' ')
            if normalized_const == normalized_real:
                print(f"🔄 {name}: НОРМАЛИЗОВАННОЕ СОВПАДЕНИЕ в позиции {i+1}")
                print(f"   Константа: '{const_header}'")
                print(f"   Реальный:  '{real_header}'")
                found = True
                break
    
    if not found:
        print(f"❌ {name}: НЕ НАЙДЕНО")
        print(f"   Ищем: '{const_header}'")
        # Покажем ближайшие совпадения
        for i, real_header in enumerate(real_headers):
            if const_header.replace('\n', '').replace(' ', '').lower() in real_header.replace('\n', '').replace(' ', '').lower():
                print(f"   Похоже на позицию {i+1}: '{real_header}'")

print("\n=== СПЕЦИАЛЬНАЯ ПРОВЕРКА ПРОБЛЕМНОГО ЗАГОЛОВКА ===")
problem_header = 'Согласовано САД/Директором по рекламе '
print(f"Ищем: '{problem_header}' (len={len(problem_header)})")
for i, real_header in enumerate(real_headers):
    if problem_header == real_header:
        print(f"✅ НАЙДЕНО на позиции {i+1}")
        break
else:
    print("❌ НЕ НАЙДЕНО")
    # Покажем символы проблемного заголовка
    print("Коды символов в константе:", [ord(c) for c in problem_header])
    # Найдем похожий
    for i, real_header in enumerate(real_headers):
        if 'Согласовано САД' in real_header:
            print(f"Похожий заголовок на позиции {i+1}: '{real_header}'")
            print("Коды символов в реальном заголовке:", [ord(c) for c in real_header])
