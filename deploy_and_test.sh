#!/bin/bash

# Скрипт автоматического тестирования и сохранения в GitHub
# Автор: GitHub Copilot
# Дата: $(date)

set -e  # Прекратить выполнение при любой ошибке

echo "🚀 АВТОМАТИЧЕСКОЕ ТЕСТИРОВАНИЕ И ДЕПЛОЙ В GITHUB"
echo "=================================================="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода с цветами
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверяем наличие Python
print_status "Проверка наличия Python..."
if ! command -v python3 &> /dev/null; then
    print_error "Python3 не найден!"
    exit 1
fi
print_success "Python3 найден: $(python3 --version)"

# Проверяем наличие Git
print_status "Проверка наличия Git..."
if ! command -v git &> /dev/null; then
    print_error "Git не найден!"
    exit 1
fi
print_success "Git найден: $(git --version)"

# Проверяем, что мы в git-репозитории
print_status "Проверка Git-репозитория..."
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    print_error "Текущая директория не является Git-репозиторием!"
    exit 1
fi
print_success "Git-репозиторий найден"

# Получаем информацию о репозитории
REPO_NAME=$(basename `git rev-parse --show-toplevel`)
CURRENT_BRANCH=$(git branch --show-current)
print_status "Репозиторий: $REPO_NAME"
print_status "Текущая ветка: $CURRENT_BRANCH"

# Запускаем полное тестирование
print_status "Запуск комплексного тестирования..."
echo "=================================================="

if python3 test_bot_complete.py; then
    print_success "🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!"
else
    print_error "❌ ТЕСТЫ НЕ ПРОЙДЕНЫ! Исправьте ошибки перед коммитом."
    exit 1
fi

echo "=================================================="

# Проверяем статус Git
print_status "Проверка статуса Git-репозитория..."
git status --porcelain

# Добавляем все изменения
print_status "Добавление всех изменений в Git..."
git add -A

# Проверяем, есть ли изменения для коммита
if git diff --cached --quiet; then
    print_warning "Нет изменений для коммита"
else
    # Создаем коммит с автоматическим сообщением
    COMMIT_MSG="🤖 Автоматическое тестирование и обновление ($(date '+%Y-%m-%d %H:%M:%S'))"
    print_status "Создание коммита: $COMMIT_MSG"
    git commit -m "$COMMIT_MSG"
    print_success "Коммит создан успешно"
    
    # Пушим изменения
    print_status "Отправка изменений на GitHub..."
    if git push origin $CURRENT_BRANCH; then
        print_success "🚀 Изменения успешно отправлены на GitHub!"
    else
        print_error "Ошибка при отправке на GitHub"
        exit 1
    fi
fi

# Выводим финальную статистику
echo "=================================================="
print_success "✅ АВТОМАТИЧЕСКОЕ ТЕСТИРОВАНИЕ И ДЕПЛОЙ ЗАВЕРШЕНЫ!"
echo "=================================================="

print_status "📊 ФИНАЛЬНАЯ СТАТИСТИКА:"
echo "• Репозиторий: $REPO_NAME"
echo "• Ветка: $CURRENT_BRANCH"
echo "• Последний коммит: $(git log -1 --pretty=format:'%h - %s (%cr)')"
echo "• Всего файлов в проекте: $(find . -name '*.py' | wc -l) Python файлов"
echo "• Размер репозитория: $(du -sh .git | cut -f1)"

# Показываем URL репозитория если возможно
REPO_URL=$(git config --get remote.origin.url 2>/dev/null || echo "URL не настроен")
if [[ $REPO_URL != "URL не настроен" ]]; then
    # Конвертируем SSH URL в HTTPS для отображения
    if [[ $REPO_URL == git@github.com:* ]]; then
        HTTPS_URL="https://github.com/${REPO_URL#git@github.com:}"
        HTTPS_URL="${HTTPS_URL%.git}"
        echo "• GitHub URL: $HTTPS_URL"
    else
        echo "• GitHub URL: $REPO_URL"
    fi
fi

print_success "🎯 Бот готов к использованию в продакшене!"
echo "=================================================="
