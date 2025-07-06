# -*- coding: utf-8 -*-

"""
This file contains functions for generating keyboards for the bot.
"""

from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, KeyboardButton, InlineKeyboardButton
from constants import (
    MENU_TEXT_SUBMIT, MENU_TEXT_SEARCH,
    MENU_TEXT_SETTINGS, MENU_TEXT_MAIN_MENU
)

def get_main_menu_keyboard(is_registered: bool) -> ReplyKeyboardMarkup:
    """Returns the main menu keyboard based on user's registration status."""
    if is_registered:
        keyboard = [
            [MENU_TEXT_SUBMIT],
            [MENU_TEXT_SEARCH, MENU_TEXT_SETTINGS]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    else:
        # Убрали кнопку регистрации, т.к. она встроена в подачу заявки
        keyboard = [[MENU_TEXT_SUBMIT]]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_settings_keyboard(is_boss: bool) -> InlineKeyboardMarkup:
    """Returns the settings inline keyboard."""
    cards_button_text = "🗂️ Все заявки" if is_boss else "🗂️ Мои Заявки"
    keyboard = [
        [InlineKeyboardButton("👤 Мой профиль", callback_data="settings_my_profile")],
        [InlineKeyboardButton(cards_button_text, callback_data="settings_my_cards")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats_show")],
        [InlineKeyboardButton("📄 Экспорт в CSV", callback_data="export_csv")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_show")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_to_settings_keyboard() -> InlineKeyboardMarkup:
    """Returns a keyboard with a single 'Back to settings' button."""
    keyboard = [[InlineKeyboardButton("⬅️ Назад в настройки", callback_data="back_to_settings")]]
    return InlineKeyboardMarkup(keyboard)
