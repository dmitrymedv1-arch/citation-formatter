import os
import csv
import streamlit as st
import re
import json
from datetime import datetime
from crossref.restful import Works
from docx import Document
from docx.oxml.ns import qn
from docx.shared import RGBColor, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import io
from tqdm import tqdm
from docx.oxml import OxmlElement
import base64
import html
import concurrent.futures
from typing import List, Dict, Tuple, Set, Any, Optional
import hashlib
import time
from collections import Counter
import functools
import logging
from pathlib import Path
import sqlite3
from contextlib import contextmanager
import requests
import streamlit.components.v1 as components

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('citation_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
class Config:
    """Конфигурационные константы приложения"""
    # Пути к файлам
    DB_PATH = "doi_cache.db"
    LTWA_CSV_PATH = "ltwa.csv"
    USER_PREFS_DB = "user_preferences.db"
    
    # Настройки API
    CROSSREF_WORKERS = 3
    CROSSREF_RETRY_WORKERS = 2
    REQUEST_TIMEOUT = 30
    
    # Кэширование
    CACHE_TTL_HOURS = 24 * 7  # 1 неделя
    
    # Валидация
    MIN_REFERENCES_FOR_STATS = 5
    MAX_REFERENCES = 1000
    
    # Стили
    NUMBERING_STYLES = ["No numbering", "1", "1.", "1)", "(1)", "[1]"]
    AUTHOR_FORMATS = ["AA Smith", "A.A. Smith", "Smith AA", "Smith A.A", "Smith, A.A."]
    PAGE_FORMATS = ["122 - 128", "122-128", "122 – 128", "122–128", "122–8", "122"]
    DOI_FORMATS = ["10.10/xxx", "doi:10.10/xxx", "DOI:10.10/xxx", "https://dx.doi.org/10.10/xxx"]
    JOURNAL_STYLES = ["{Full Journal Name}", "{J. Abbr.}", "{J Abbr}"]
    AVAILABLE_ELEMENTS = ["", "Authors", "Title", "Journal", "Year", "Volume", "Issue", "Pages", "DOI"]
    
    # Цвета прогресс-бара
    PROGRESS_COLORS = {
        'start': '#FF6B6B',
        'middle': '#4ECDC4', 
        'end': '#45B7D1'
    }
    
    # Настройки тем (3 темы: светлая, темная, контрастная)
    THEMES = {
        'light': {
            'primary': '#3B82F6',
            'secondary': '#10B981',
            'accent': '#8B5CF6',
            'background': '#FFFFFF',
            'secondaryBackground': '#F9FAFB',
            'text': '#1F2937',
            'textSecondary': '#6B7280',
            'border': '#E5E7EB',
            'success': '#10B981',
            'warning': '#F59E0B',
            'error': '#EF4444',
            'font': 'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
            'cardBackground': '#FFFFFF',
            'shadow': '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
            'radius': '12px'
        },
        'dark': {
            'primary': '#8B5CF6',
            'secondary': '#10B981',
            'accent': '#3B82F6',
            'background': '#1F2937',
            'secondaryBackground': '#374151',
            'text': '#F9FAFB',
            'textSecondary': '#D1D5DB',
            'border': '#4B5563',
            'success': '#10B981',
            'warning': '#F59E0B',
            'error': '#EF4444',
            'font': 'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
            'cardBackground': '#111827',
            'shadow': '0 1px 3px 0 rgba(0, 0, 0, 0.3), 0 1px 2px 0 rgba(0, 0, 0, 0.2)',
            'radius': '12px'
        },
        'contrast': {
            'primary': '#000000',
            'secondary': '#0055FF',
            'accent': '#FF5500',
            'background': '#FFFF00',
            'secondaryBackground': '#FFFFFF',
            'text': '#000000',
            'textSecondary': '#333333',
            'border': '#000000',
            'success': '#008800',
            'warning': '#FF8800',
            'error': '#FF0000',
            'font': 'Arial, sans-serif',
            'cardBackground': '#FFFFFF',
            'shadow': '0 0 0 2px #000000',
            'radius': '4px'
        }
    }
    
    # Навигация
    MAX_UNDO_STEPS = 3
    STEPS = ["start", "style_select", "style_create", "input", "process", "output"]
    
    # Готовые стили
    PRESET_STYLES = {
        'gost': {
            'name': 'ГОСТ 7.0.5-2008',
            'description': 'Российский стандарт для научных публикаций',
            'language': 'ru'
        },
        'apa': {
            'name': 'APA 7th',
            'description': 'American Psychological Association (7th edition)',
            'language': 'en'
        },
        'vancouver': {
            'name': 'Vancouver',
            'description': 'Библиографический стиль для медицинских журналов',
            'language': 'en'
        },
        'ieee': {
            'name': 'IEEE',
            'description': 'Институт инженеров электротехники и электроники',
            'language': 'en'
        },
        'harvard': {
            'name': 'Harvard',
            'description': 'Стиль автора-даты, популярный в социальных науках',
            'language': 'en'
        },
        'acs': {
            'name': 'ACS (MDPI)',
            'description': 'American Chemical Society style',
            'language': 'en'
        },
        'rsc': {
            'name': 'RSC',
            'description': 'Royal Society of Chemistry style',
            'language': 'en'
        },
        'chicago': {
            'name': 'Chicago',
            'description': 'Chicago Manual of Style',
            'language': 'en'
        }
    }

# Инициализация Crossref
works = Works()

# Полный словарь переводов (только русский и английский)
TRANSLATIONS = {
    'en': {
        # Навигация и общее
        'app_title': '🎨 Citation Style Constructor',
        'back': '← Back',
        'next': 'Next →',
        'clear_all': '🔄 Clear All',
        'start_over': 'Start Over',
        'save': '💾 Save',
        'load': '📂 Load',
        'apply': 'Apply',
        'cancel': 'Cancel',
        'confirm': 'Confirm',
        
        # Шаги
        'step_start': 'Start',
        'step_style': 'Style',
        'step_input': 'Input',
        'step_process': 'Process',
        'step_output': 'Output',
        
        # Стартовый экран
        'welcome': 'Welcome to Citation Style Constructor',
        'create_new_style': '🎨 Create New Style',
        'create_new_desc': 'Customize all formatting parameters yourself',
        'choose_preset': '📚 Choose Preset Style',
        'choose_preset_desc': 'GOST, APA, Vancouver, IEEE, etc.',
        'load_saved': '📂 Load Saved Style',
        'language_select': 'Language:',
        'theme_select': 'Theme:',
        'theme_light': 'Light',
        'theme_dark': 'Dark',
        'theme_contrast': 'High Contrast',
        
        # Выбор готового стиля
        'select_preset_title': 'Select Citation Style',
        'select_preset_desc': 'Choose one of the popular citation styles',
        'style_description': 'Description:',
        'preview': 'Preview:',
        
        # Создание стиля
        'create_style_title': 'Create Custom Style',
        'create_style_desc': 'Drag elements to reorder, click to configure',
        'elements_title': 'Reference Elements',
        'drag_to_reorder': 'Drag to reorder',
        'element_settings': 'Element Settings:',
        'italic': 'Italic',
        'bold': 'Bold',
        'parentheses': 'Parentheses',
        'separator': 'Separator',
        'style_preview': 'Style Preview:',
        'save_style_as': 'Save style as:',
        'style_name': 'Style name',
        
        # Ввод данных
        'input_title': 'Input References',
        'input_desc': 'Choose how to provide your references',
        'upload_docx': '📎 Upload DOCX File',
        'paste_text': '📝 Paste Text',
        'enter_doi': '🔗 Enter DOI List',
        'text_area_placeholder': 'Paste references here (one per line)...',
        'doi_area_placeholder': 'Enter DOI list (one per line)...',
        'clear_input': '🗑️ Clear',
        'browse_files': 'Browse files',
        'or': 'or',
        
        # Обработка
        'process_title': 'Processing Options',
        'process_desc': 'Configure output settings',
        'output_format': 'Output Format:',
        'format_docx': 'DOCX (with formatting)',
        'format_txt': 'TXT (plain text)',
        'format_bibtex': 'BibTeX',
        'format_ris': 'RIS',
        'additional_options': 'Additional Options:',
        'number_references': 'Number references',
        'highlight_duplicates': 'Highlight duplicates',
        'add_statistics': 'Add statistics',
        'process_button': '🚀 Process References',
        'processing': '⏳ Processing...',
        'retry_processing': '🔄 Process Again',
        
        # Результаты
        'results_title': 'Results',
        'processed_count': 'Processed:',
        'doi_found': 'DOI found:',
        'needs_check': 'Need manual check:',
        'download_section': 'Download:',
        'download_formatted': 'Formatted references (.docx)',
        'download_statistics': 'Statistics report (.pdf)',
        'download_doi_list': 'DOI list (.txt)',
        'download_style': 'Save style (.json)',
        'new_document': '🔄 New Document',
        'edit_style': '✏️ Edit Style',
        
        # Статистика
        'statistics': 'Statistics',
        'total_references': 'Total references:',
        'unique_dois': 'Unique DOIs:',
        'most_common_journals': 'Most common journals:',
        'year_distribution': 'Year distribution:',
        'frequent_authors': 'Frequent authors:',
        
        # Сообщения
        'success': 'Success!',
        'error': 'Error!',
        'warning': 'Warning!',
        'info': 'Info',
        'no_references': 'No references provided',
        'no_style_selected': 'No style selected',
        'style_saved': 'Style saved successfully!',
        'style_loaded': 'Style loaded successfully!',
        'processing_complete': 'Processing complete!',
        'upload_file_first': 'Please upload a file first',
        'enter_text_first': 'Please enter text first',
        'select_output_format': 'Please select output format',
        
        # Подсказки
        'hint_drag_elements': 'Drag elements to change their order in the citation',
        'hint_click_configure': 'Click on an element to configure formatting options',
        'hint_multiple_formats': 'You can download results in multiple formats',
        'hint_save_style': 'Save your custom style for future use',
        
        # Кнопки действий
        'action_edit': 'Edit',
        'action_delete': 'Delete',
        'action_duplicate': 'Duplicate',
        'action_preview': 'Preview',
        'action_download': 'Download',
        'action_upload': 'Upload',
        
        # Элементы
        'element_authors': 'Authors',
        'element_title': 'Title',
        'element_journal': 'Journal',
        'element_year': 'Year',
        'element_volume': 'Volume',
        'element_issue': 'Issue',
        'element_pages': 'Pages',
        'element_doi': 'DOI',
        
        # Форматы
        'format_author_smith_aa': 'Smith AA',
        'format_author_aa_smith': 'AA Smith',
        'format_author_a_a_smith': 'A.A. Smith',
        'format_author_smith_a_a': 'Smith A.A',
        'format_author_smith_comma_a_a': 'Smith, A.A.',
    },
    'ru': {
        # Навигация и общее
        'app_title': '🎨 Конструктор стилей цитирования',
        'back': '← Назад',
        'next': 'Далее →',
        'clear_all': '🔄 Очистить все',
        'start_over': 'Начать заново',
        'save': '💾 Сохранить',
        'load': '📂 Загрузить',
        'apply': 'Применить',
        'cancel': 'Отмена',
        'confirm': 'Подтвердить',
        
        # Шаги
        'step_start': 'Старт',
        'step_style': 'Стиль',
        'step_input': 'Ввод',
        'step_process': 'Обработка',
        'step_output': 'Результат',
        
        # Стартовый экран
        'welcome': 'Добро пожаловать в Конструктор стилей цитирования',
        'create_new_style': '🎨 Создать новый стиль',
        'create_new_desc': 'Настроить все параметры форматирования самостоятельно',
        'choose_preset': '📚 Выбрать готовый стиль',
        'choose_preset_desc': 'ГОСТ, APA, Vancouver, IEEE и другие',
        'load_saved': '📂 Загрузить сохраненный стиль',
        'language_select': 'Язык:',
        'theme_select': 'Тема:',
        'theme_light': 'Светлая',
        'theme_dark': 'Темная',
        'theme_contrast': 'Высокая контрастность',
        
        # Выбор готового стиля
        'select_preset_title': 'Выберите стиль цитирования',
        'select_preset_desc': 'Выберите один из популярных стилей цитирования',
        'style_description': 'Описание:',
        'preview': 'Предпросмотр:',
        
        # Создание стиля
        'create_style_title': 'Создать пользовательский стиль',
        'create_style_desc': 'Перетащите элементы для изменения порядка, нажмите для настройки',
        'elements_title': 'Элементы ссылки',
        'drag_to_reorder': 'Перетащите для изменения порядка',
        'element_settings': 'Настройки элемента:',
        'italic': 'Курсив',
        'bold': 'Жирный',
        'parentheses': 'Скобки',
        'separator': 'Разделитель',
        'style_preview': 'Предпросмотр стиля:',
        'save_style_as': 'Сохранить стиль как:',
        'style_name': 'Название стиля',
        
        # Ввод данных
        'input_title': 'Ввод ссылок',
        'input_desc': 'Выберите способ предоставления ссылок',
        'upload_docx': '📎 Загрузить DOCX файл',
        'paste_text': '📝 Вставить текст',
        'enter_doi': '🔗 Ввести список DOI',
        'text_area_placeholder': 'Вставьте ссылки здесь (по одной на строку)...',
        'doi_area_placeholder': 'Введите список DOI (по одному на строку)...',
        'clear_input': '🗑️ Очистить',
        'browse_files': 'Выбрать файлы',
        'or': 'или',
        
        # Обработка
        'process_title': 'Настройки обработки',
        'process_desc': 'Настройте параметры вывода',
        'output_format': 'Формат вывода:',
        'format_docx': 'DOCX (с форматированием)',
        'format_txt': 'TXT (простой текст)',
        'format_bibtex': 'BibTeX',
        'format_ris': 'RIS',
        'additional_options': 'Дополнительные опции:',
        'number_references': 'Нумеровать ссылки',
        'highlight_duplicates': 'Выделять дубликаты',
        'add_statistics': 'Добавить статистику',
        'process_button': '🚀 Обработать ссылки',
        'processing': '⏳ Обработка...',
        'retry_processing': '🔄 Обработать снова',
        
        # Результаты
        'results_title': 'Результаты',
        'processed_count': 'Обработано:',
        'doi_found': 'DOI найдено:',
        'needs_check': 'Требуют проверки:',
        'download_section': 'Скачать:',
        'download_formatted': 'Форматированные ссылки (.docx)',
        'download_statistics': 'Отчет со статистикой (.pdf)',
        'download_doi_list': 'Список DOI (.txt)',
        'download_style': 'Сохранить стиль (.json)',
        'new_document': '🔄 Новый документ',
        'edit_style': '✏️ Изменить стиль',
        
        # Статистика
        'statistics': 'Статистика',
        'total_references': 'Всего ссылок:',
        'unique_dois': 'Уникальных DOI:',
        'most_common_journals': 'Самые частые журналы:',
        'year_distribution': 'Распределение по годам:',
        'frequent_authors': 'Частые авторы:',
        
        # Сообщения
        'success': 'Успех!',
        'error': 'Ошибка!',
        'warning': 'Предупреждение!',
        'info': 'Информация',
        'no_references': 'Ссылки не предоставлены',
        'no_style_selected': 'Стиль не выбран',
        'style_saved': 'Стиль успешно сохранен!',
        'style_loaded': 'Стиль успешно загружен!',
        'processing_complete': 'Обработка завершена!',
        'upload_file_first': 'Пожалуйста, загрузите файл сначала',
        'enter_text_first': 'Пожалуйста, введите текст сначала',
        'select_output_format': 'Пожалуйста, выберите формат вывода',
        
        # Подсказки
        'hint_drag_elements': 'Перетащите элементы, чтобы изменить их порядок в ссылке',
        'hint_click_configure': 'Нажмите на элемент, чтобы настроить параметры форматирования',
        'hint_multiple_formats': 'Вы можете скачать результаты в нескольких форматах',
        'hint_save_style': 'Сохраните ваш пользовательский стиль для будущего использования',
        
        # Кнопки действий
        'action_edit': 'Редактировать',
        'action_delete': 'Удалить',
        'action_duplicate': 'Дублировать',
        'action_preview': 'Предпросмотр',
        'action_download': 'Скачать',
        'action_upload': 'Загрузить',
        
        # Элементы
        'element_authors': 'Авторы',
        'element_title': 'Название',
        'element_journal': 'Журнал',
        'element_year': 'Год',
        'element_volume': 'Том',
        'element_issue': 'Выпуск',
        'element_pages': 'Страницы',
        'element_doi': 'DOI',
        
        # Форматы
        'format_author_smith_aa': 'Smith AA',
        'format_author_aa_smith': 'AA Smith',
        'format_author_a_a_smith': 'A.A. Smith',
        'format_author_smith_a_a': 'Smith A.A',
        'format_author_smith_comma_a_a': 'Smith, A.A.',
    }
}

# Кэширование DOI
class DOICache:
    """Кэш для хранения метаданных DOI"""
    
    def __init__(self, db_path: str = Config.DB_PATH):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS doi_cache (
                    doi TEXT PRIMARY KEY,
                    metadata TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_doi ON doi_cache(doi)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_accessed_at ON doi_cache(accessed_at)')
    
    def get(self, doi: str) -> Optional[Dict]:
        """Получение метаданных из кэша"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                result = conn.execute(
                    'SELECT metadata FROM doi_cache WHERE doi = ? AND datetime(accessed_at) > datetime("now", ?)',
                    (doi, f"-{Config.CACHE_TTL_HOURS} hours")
                ).fetchone()
                
                if result:
                    # Обновляем время доступа
                    conn.execute(
                        'UPDATE doi_cache SET accessed_at = CURRENT_TIMESTAMP WHERE doi = ?',
                        (doi,)
                    )
                    return json.loads(result[0])
        except Exception as e:
            logger.error(f"Cache get error for {doi}: {e}")
        return None
    
    def set(self, doi: str, metadata: Dict):
        """Сохранение метаданных в кэш"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'INSERT OR REPLACE INTO doi_cache (doi, metadata) VALUES (?, ?)',
                    (doi, json.dumps(metadata))
                )
        except Exception as e:
            logger.error(f"Cache set error for {doi}: {e}")
    
    def clear_old_entries(self):
        """Очистка устаревших записей"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'DELETE FROM doi_cache WHERE datetime(accessed_at) <= datetime("now", ?)',
                    (f"-{Config.CACHE_TTL_HOURS} hours",)
                )
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")

# Инициализация кэша
doi_cache = DOICache()

class UserPreferencesManager:
    """Менеджер пользовательских предпочтений"""
    
    def __init__(self, db_path: str = Config.USER_PREFS_DB):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных предпочтений"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    ip_address TEXT PRIMARY KEY,
                    language TEXT DEFAULT 'en',
                    theme TEXT DEFAULT 'light',
                    mobile_view INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_ip ON user_preferences(ip_address)')
    
    def get_user_ip(self):
        """Получение IP пользователя"""
        try:
            # В Streamlit можно получить IP через экспериментальный API
            if hasattr(st, 'experimental_user'):
                return getattr(st.experimental_user, 'ip', 'unknown')
        except:
            pass
        return 'unknown'
    
    def get_preferences(self, ip: str) -> Dict[str, Any]:
        """Получение предпочтений пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                result = conn.execute(
                    'SELECT language, theme, mobile_view FROM user_preferences WHERE ip_address = ?',
                    (ip,)
                ).fetchone()
                
                if result:
                    return {
                        'language': result[0],
                        'theme': result[1],
                        'mobile_view': bool(result[2])
                    }
        except Exception as e:
            logger.error(f"Error getting preferences for {ip}: {e}")
        
        return {
            'language': 'en',
            'theme': 'light',
            'mobile_view': False
        }
    
    def save_preferences(self, ip: str, preferences: Dict[str, Any]):
        """Сохранение предпочтений пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO user_preferences 
                    (ip_address, language, theme, mobile_view, updated_at) 
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    ip,
                    preferences.get('language', 'en'),
                    preferences.get('theme', 'light'),
                    int(preferences.get('mobile_view', False))
                ))
        except Exception as e:
            logger.error(f"Error saving preferences for {ip}: {e}")
    
    def detect_mobile_device(self, user_agent: str) -> bool:
        """Определение мобильного устройства по User-Agent"""
        try:
            # Простая проверка по ключевым словам в User-Agent
            mobile_keywords = [
                'mobile', 'android', 'iphone', 'ipad', 'tablet', 
                'blackberry', 'webos', 'windows phone'
            ]
            user_agent_lower = user_agent.lower()
            return any(keyword in user_agent_lower for keyword in mobile_keywords)
        except:
            return False

class StyleValidator:
    """Валидатор настроек стиля"""
    
    @staticmethod
    def validate_style_config(style_config: Dict) -> Tuple[bool, List[str]]:
        """Валидация конфигурации стиля"""
        errors = []
        warnings = []
        
        # Проверка наличия элементов или пресетов
        has_elements = bool(style_config.get('elements'))
        has_preset = any([
            style_config.get('gost_style', False),
            style_config.get('acs_style', False), 
            style_config.get('rsc_style', False),
            style_config.get('cta_style', False)
        ])
        
        if not has_elements and not has_preset:
            errors.append(get_text('validation_error_no_elements'))
        
        # Проверка корректности элементов
        if has_elements:
            elements = style_config['elements']
            for i, (element, config) in enumerate(elements):
                if not element:
                    errors.append(f"Element {i+1} is empty")
                if not config.get('separator', '').strip() and i < len(elements) - 1:
                    warnings.append(f"Element {i+1} has empty separator")
        
        return len(errors) == 0, errors + warnings
    
    @staticmethod
    def validate_references_count(references: List[str]) -> Tuple[bool, List[str]]:
        """Валидация количества ссылок"""
        errors = []
        warnings = []
        
        if len(references) > Config.MAX_REFERENCES:
            errors.append(get_text('validation_error_too_many_references').format(Config.MAX_REFERENCES))
        
        if len(references) < Config.MIN_REFERENCES_FOR_STATS:
            warnings.append(get_text('validation_warning_few_references'))
        
        return len(errors) == 0, errors + warnings

class ProgressManager:
    """Менеджер прогресса обработки"""
    
    def __init__(self):
        self.start_time = None
        self.progress_data = {
            'total': 0,
            'processed': 0,
            'found': 0,
            'errors': 0,
            'phase': 'initializing'
        }
    
    def start_processing(self, total: int):
        """Начало обработки"""
        self.start_time = time.time()
        self.progress_data = {
            'total': total,
            'processed': 0,
            'found': 0,
            'errors': 0,
            'phase': 'processing'
        }
    
    def update_progress(self, processed: int, found: int, errors: int, phase: str = None):
        """Обновление прогресса"""
        self.progress_data.update({
            'processed': processed,
            'found': found,
            'errors': errors
        })
        if phase:
            self.progress_data['phase'] = phase
    
    def get_progress_info(self) -> Dict[str, Any]:
        """Получение информации о прогрессе"""
        if not self.start_time:
            return self.progress_data
        
        elapsed = time.time() - self.start_time
        processed = self.progress_data['processed']
        total = self.progress_data['total']
        
        # Расчет оставшегося времени
        time_remaining = None
        if processed > 0 and total > 0:
            estimated_total = (elapsed / processed) * total
            time_remaining = estimated_total - elapsed
            if time_remaining < 0:
                time_remaining = 0
        
        # Расчет прогресса для цветового градиента
        progress_ratio = processed / total if total > 0 else 0
        
        return {
            **self.progress_data,
            'elapsed_time': elapsed,
            'time_remaining': time_remaining,
            'progress_ratio': progress_ratio
        }
    
    def get_progress_color(self, progress_ratio: float) -> str:
        """Получение цвета прогресс-бара на основе прогресса"""
        if progress_ratio < 0.33:
            return Config.PROGRESS_COLORS['start']
        elif progress_ratio < 0.66:
            return Config.PROGRESS_COLORS['middle']
        else:
            return Config.PROGRESS_COLORS['end']

# Инициализация глобальных состояний
def init_session_state():
    """Инициализация состояния сессии"""
    defaults = {
        # Навигация
        'current_step': 0,  # 0-start, 1-style_select, 2-style_create, 3-input, 4-process, 5-output
        'previous_steps': [],  # Стек предыдущих шагов для кнопки Back
        'selected_preset': None,
        'create_custom_style': False,
        
        # Пользовательские настройки
        'current_language': 'en',
        'current_theme': 'light',
        
        # Стиль
        'style_name': '',
        'style_elements': [
            {'id': 1, 'name': 'Authors', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 2, 'name': 'Title', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '},
            {'id': 3, 'name': 'Journal', 'enabled': True, 'italic': True, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 4, 'name': 'Year', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 5, 'name': 'Volume', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 6, 'name': 'Issue', 'enabled': False, 'italic': False, 'bold': False, 'parentheses': True, 'separator': ': '},
            {'id': 7, 'name': 'Pages', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '},
            {'id': 8, 'name': 'DOI', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ''},
        ],
        'selected_element_id': None,
        'author_format': 'Smith, A.A.',
        'page_format': '122–128',
        'doi_format': '10.10/xxx',
        'doi_hyperlink': True,
        'numbering_style': '1.',
        
        # Ввод данных
        'input_method': 'text',  # 'docx', 'text', 'doi'
        'uploaded_file': None,
        'input_text': '',
        'input_doi': '',
        'references': [],
        
        # Обработка
        'output_format': 'docx',  # 'docx', 'txt', 'bibtex', 'ris'
        'number_references': True,
        'highlight_duplicates': True,
        'add_statistics': True,
        
        # Результаты
        'processed_results': None,
        'processing_stats': {},
        'download_data': {},
        'show_results': False,
        
        # Управление
        'user_prefs_loaded': False,
        'style_import_processed': False,
        'last_imported_file_hash': None,
        
        # Совместимость с предыдущим кодом
        'imported_style': None,
        'style_applied': False,
        'apply_imported_style': False,
        'output_text_value': "",
        'use_and_checkbox': False,
        'use_ampersand_checkbox': False,
        'journal_style': '{Full Journal Name}',
        'num': "No numbering",
        'auth': "AA Smith",
        'sep': ", ",
        'etal': 0,
        'doi': "10.10/xxx",
        'doilink': True,
        'page': "122–128",
        'punct': "",
        'gost_style': False,
        'acs_style': False,
        'rsc_style': False,
        'cta_style': False,
        'last_style_update': 0,
        'cache_initialized': False,
        'file_processing_complete': False,
        'style_management_initialized': False,
        'max_undo_steps': 10,
    }
    
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default
    
    # Инициализация элементов конфигурации для совместимости
    for i in range(8):
        for prop in ['el', 'it', 'bd', 'pr', 'sp']:
            key = f"{prop}{i}"
            if key not in st.session_state:
                if prop == 'sp':
                    st.session_state[key] = ". "
                elif prop == 'el':
                    st.session_state[key] = ""
                else:
                    st.session_state[key] = False

def get_text(key: str) -> str:
    """Получение перевода по ключу"""
    return TRANSLATIONS[st.session_state.current_language].get(key, key)

# Базовые классы форматирования
class JournalAbbreviation:
    def __init__(self):
        self.ltwa_data = {}
        self.load_ltwa_data()
        self.uppercase_abbreviations = {'acs', 'ecs', 'rsc', 'ieee', 'iet', 'acm', 'aims', 'bmc', 'bmj', 'npj'}
        self.special_endings = {'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 
                               'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
                               'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'}
    
    def load_ltwa_data(self):
        """Загружает данные сокращений из файла ltwa.csv"""
        try:
            csv_path = Config.LTWA_CSV_PATH
            if os.path.exists(csv_path):
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f, delimiter='\t')
                    next(reader)
                    for row in reader:
                        if len(row) >= 2:
                            word = row[0].strip()
                            abbreviation = row[1].strip() if row[1].strip() else None
                            self.ltwa_data[word] = abbreviation
            else:
                logger.warning(f"Файл {csv_path} не найден, используется стандартное сокращение")
        except Exception as e:
            logger.error(f"Ошибка загрузки ltwa.csv: {e}")
    
    def abbreviate_word(self, word: str) -> str:
        """Сокращает одно слово на основе данных LTWA"""
        word_lower = word.lower()
        
        if word_lower in self.ltwa_data:
            abbr = self.ltwa_data[word_lower]
            return abbr if abbr else word
        
        for ltwa_word, abbr in self.ltwa_data.items():
            if ltwa_word.endswith('-') and word_lower.startswith(ltwa_word[:-1]):
                return abbr if abbr else word
        
        return word
    
    def extract_special_endings(self, journal_name: str) -> Tuple[str, str]:
        """Извлекает специальные окончания (A, B, C и т.д.) из названия журнала"""
        # Паттерны для поиска специальных окончаний
        patterns = [
            r'\s+([A-Z])\s*$',  # Одиночные буквы в конце
            r'\s+([IVX]+)\s*$',  # Римские цифры
            r'\s+Part\s+([A-Z0-9]+)\s*$',  # Part A, Part 1 и т.д.
            r'\s+([A-Z]):\s+[A-Z]',  # Буква с двоеточием: A: General, B: Environmental
        ]
        
        for pattern in patterns:
            match = re.search(pattern, journal_name)
            if match:
                ending = match.group(1)
                # Проверяем, является ли окончание специальным
                if ending in self.special_endings or re.match(r'^[A-Z]$', ending):
                    base_name = journal_name[:match.start()].strip()
                    return base_name, ending
        
        return journal_name, ""
    
    def abbreviate_journal_name(self, journal_name: str, style: str = "{J. Abbr.}") -> str:
        """Сокращает название журнала в соответствии с выбранным стилем"""
        if not journal_name:
            return ""
        
        # Извлекаем базовое название и специальное окончание
        base_name, special_ending = self.extract_special_endings(journal_name)
        
        words_to_remove = {'a', 'an', 'the', 'of', 'in', 'and', '&', 'for', 'on', 'with', 'by'}
        words = [word for word in base_name.split() if word.lower() not in words_to_remove]
        words = [word.replace(':', '') for word in words]
        
        if len(words) <= 1:
            result = journal_name
        else:
            abbreviated_words = []
            for i, word in enumerate(words):
                original_first_char = word[0]
                abbreviated = self.abbreviate_word(word.lower())
                
                if abbreviated and original_first_char.isupper():
                    abbreviated = abbreviated[0].upper() + abbreviated[1:]
                
                if i == 0 and abbreviated.lower() in self.uppercase_abbreviations:
                    abbreviated = abbreviated.upper()
                
                abbreviated_words.append(abbreviated)
            
            if style == "{J. Abbr.}":
                result = " ".join(abbreviated_words)
            elif style == "{J Abbr}":
                result = " ".join(abbr.replace('.', '') for abbr in abbreviated_words)
            else:
                result = base_name
        
        # Добавляем специальное окончание обратно
        if special_ending:
            if ':' in journal_name and special_ending + ':' in journal_name:
                # Для случаев типа "Applied Catalysis A: General"
                result += f" {special_ending}:"
                # Добавляем остаток после двоеточия
                after_colon = journal_name.split(special_ending + ':', 1)[1].strip()
                if after_colon:
                    result += f" {after_colon}"
            else:
                result += f" {special_ending}"
        
        result = re.sub(r'\.\.+', '.', result)
        return result

# Инициализация системы сокращений
journal_abbrev = JournalAbbreviation()

class BaseCitationFormatter:
    """Базовый класс для форматирования цитирования"""
    
    def __init__(self, style_config: Dict[str, Any]):
        self.style_config = style_config
    
    def format_authors(self, authors: List[Dict[str, str]]) -> str:
        """Форматирует список авторов"""
        if not authors:
            return ""
        
        author_format = self.style_config['author_format']
        separator = self.style_config['author_separator']
        et_al_limit = self.style_config['et_al_limit']
        use_and_bool = self.style_config['use_and_bool']
        use_ampersand_bool = self.style_config['use_ampersand_bool']
        
        author_str = ""
        
        if use_and_bool or use_ampersand_bool:
            limit = len(authors)
        else:
            limit = et_al_limit if et_al_limit and et_al_limit > 0 else len(authors)
        
        for i, author in enumerate(authors[:limit]):
            given = author['given']
            family = author['family']
            
            initials = given.split()[:2]
            first_initial = initials[0][0] if initials else ''
            second_initial = initials[1][0].upper() if len(initials) > 1 else ''
            
            if author_format == "AA Smith":
                formatted_author = f"{first_initial}{second_initial} {family}"
            elif author_format == "A.A. Smith":
                if second_initial:
                    formatted_author = f"{first_initial}.{second_initial}. {family}"
                else:
                    formatted_author = f"{first_initial}. {family}"
            elif author_format == "Smith AA":
                formatted_author = f"{family} {first_initial}{second_initial}"
            elif author_format == "Smith A.A":
                if second_initial:
                    formatted_author = f"{family} {first_initial}.{second_initial}."
                else:
                    formatted_author = f"{family} {first_initial}."
            elif author_format == "Smith, A.A.":
                if second_initial:
                    formatted_author = f"{family}, {first_initial}.{second_initial}."
                else:
                    formatted_author = f"{family}, {first_initial}."
            else:
                formatted_author = f"{first_initial}. {family}"
            
            author_str += formatted_author
            
            if i < len(authors[:limit]) - 1:
                if i == len(authors[:limit]) - 2 and (use_and_bool or use_ampersand_bool):
                    if use_and_bool:
                        author_str += " and "
                    else:
                        author_str += " & "
                else:
                    author_str += separator
        
        if et_al_limit and len(authors) > et_al_limit and not (use_and_bool or use_ampersand_bool):
            author_str += " et al"
        
        return author_str.strip()
          
    def format_pages(self, pages: str, article_number: str, style_type: str = "default") -> str:
        """Форматирует страницы в зависимости от стиля"""
        page_format = self.style_config['page_format']
        
        if pages:
            if style_type == "rsc":
                if '-' in pages:
                    first_page = pages.split('-')[0].strip()
                    return first_page
                else:
                    return pages.strip()
            elif style_type == "cta":
                if '-' in pages:
                    start, end = pages.split('-')
                    start = start.strip()
                    end = end.strip()
                    
                    if len(start) == len(end) and start[:-1] == end[:-1]:
                        return f"{start}–{end[-1]}"
                    elif len(start) > 1 and len(end) > 1 and start[:-2] == end[:-2]:
                        return f"{start}–{end[-2:]}"
                    else:
                        return f"{start}–{end}"
                else:
                    return pages.strip()
            else:
                # ИСПРАВЛЕНИЕ: Добавляем проверку для формата "122" (только первая страница)
                if '-' not in pages:
                    # Если страница одна и выбран формат "122", возвращаем её как есть
                    if page_format == "122":
                        return pages.strip()
                    return pages.strip()  # Для других форматов тоже возвращаем страницу
                
                start, end = pages.split('-')
                start = start.strip()
                end = end.strip()
                
                if page_format == "122 - 128":
                    return f"{start} - {end}"
                elif page_format == "122-128":
                    return f"{start}-{end}"
                elif page_format == "122 – 128":
                    return f"{start} – {end}"
                elif page_format == "122–128":
                    return f"{start}–{end}"
                elif page_format == "122–8":
                    i = 0
                    while i < len(start) and i < len(end) and start[i] == end[i]:
                        i += 1
                    return f"{start}–{end[i:]}"
                elif page_format == "122":
                    # ИСПРАВЛЕНИЕ: Для формата "122" возвращаем только первую страницу
                    return start
        
        return article_number
    
    def format_doi(self, doi: str) -> Tuple[str, str]:
        """Форматирует DOI и возвращает текст и URL"""
        doi_format = self.style_config['doi_format']
        
        if doi_format == "10.10/xxx":
            value = doi
        elif doi_format == "doi:10.10/xxx":
            value = f"doi:{doi}"
        elif doi_format == "DOI:10.10/xxx":
            value = f"DOI:{doi}"
        elif doi_format == "https://dx.doi.org/10.10/xxx":
            value = f"https://dx.doi.org/{doi}"
        else:
            value = doi
        
        return value, f"https://doi.org/{doi}"
    
    def format_journal_name(self, journal_name: str) -> str:
        """Форматирует название журнала с учетом выбранного стиля"""
        journal_style = self.style_config.get('journal_style', '{Full Journal Name}')
        return journal_abbrev.abbreviate_journal_name(journal_name, journal_style)

class CustomCitationFormatter(BaseCitationFormatter):
    """Форматировщик для пользовательских стилей с улучшенной обработкой Issue"""
    
    def format_reference(self, metadata: Dict[str, Any], for_preview: bool = False) -> Tuple[Any, bool]:
        if not metadata:
            error_message = "Ошибка: Не удалось отформатировать ссылку." if st.session_state.current_language == 'ru' else "Error: Could not format the reference."
            return (error_message, True)
        
        elements = []
        previous_element_was_empty = False
        
        for i, (element, config) in enumerate(self.style_config['elements']):
            value = ""
            doi_value = None
            element_empty = False
            
            if element == "Authors":
                value = self.format_authors(metadata['authors'])
                element_empty = not value
            elif element == "Title":
                value = metadata['title']
                element_empty = not value
            elif element == "Journal":
                value = self.format_journal_name(metadata['journal'])
                element_empty = not value
            elif element == "Year":
                value = str(metadata['year']) if metadata['year'] else ""
                element_empty = not value
            elif element == "Volume":
                value = metadata['volume']
                element_empty = not value
            elif element == "Issue":
                value = metadata['issue']
                element_empty = not value
            elif element == "Pages":
                value = self.format_pages(metadata['pages'], metadata['article_number'])
                element_empty = not value
            elif element == "DOI":
                doi = metadata['doi']
                doi_value = doi
                value, _ = self.format_doi(doi)
                element_empty = not value
            
            # Обработка пустых элементов и их разделителей
            if value:
                if config['parentheses'] and value:
                    value = f"({value})"
                
                # Определяем разделитель с учетом пустых элементов
                separator = ""
                if i < len(self.style_config['elements']) - 1:
                    if not element_empty:
                        # Если текущий элемент не пустой, используем его разделитель
                        separator = config['separator']
                    elif previous_element_was_empty:
                        # Если предыдущий элемент был пустой, пропускаем разделитель
                        separator = ""
                    else:
                        # Если текущий элемент пустой, но предыдущий был не пустой, используем разделитель
                        separator = config['separator']
                
                if for_preview:
                    formatted_value = value
                    if config['italic']:
                        formatted_value = f"<i>{formatted_value}</i>"
                    if config['bold']:
                        formatted_value = f"<b>{formatted_value}</b>"
                    
                    elements.append((formatted_value, False, False, separator, False, None, element_empty))
                else:
                    elements.append((value, config['italic'], config['bold'], separator,
                                   (element == "DOI" and self.style_config['doi_hyperlink']), doi_value, element_empty))
                
                previous_element_was_empty = False
            else:
                # Элемент пустой - запоминаем это для следующей итерации
                previous_element_was_empty = True
        
        # Пост-обработка для удаления лишних разделителей
        cleaned_elements = []
        for i, element_data in enumerate(elements):
            value, italic, bold, separator, is_doi_hyperlink, doi_value, element_empty = element_data
            
            # Если элемент не пустой, добавляем его
            if not element_empty:
                # Для последнего элемента убираем разделитель
                if i == len(elements) - 1:
                    separator = ""
                
                cleaned_elements.append((value, italic, bold, separator, is_doi_hyperlink, doi_value))
        
        if for_preview:
            ref_str = ""
            for i, (value, _, _, separator, _, _) in enumerate(cleaned_elements):
                ref_str += value
                if separator and i < len(cleaned_elements) - 1:
                    ref_str += separator
                elif i == len(cleaned_elements) - 1 and self.style_config['final_punctuation']:
                    ref_str = ref_str.rstrip(',.') + "."
            
            ref_str = re.sub(r'\.\.+', '.', ref_str)
            return ref_str, False
        else:
            return cleaned_elements, False

class GOSTCitationFormatter(BaseCitationFormatter):
    """Форматировщик для стиля ГОСТ (обновленная версия)"""
    
    def format_reference(self, metadata: Dict[str, Any], for_preview: bool = False) -> Tuple[Any, bool]:
        if not metadata:
            error_message = "Ошибка: Не удалось отформатировать ссылку." if st.session_state.current_language == 'ru' else "Error: Could not format the reference."
            return (error_message, True)
        
        # Форматирование авторов в новом формате: Smith J.A., Doe A.B.
        authors_str = ""
        for i, author in enumerate(metadata['authors']):
            given = author['given']
            family = author['family']
            initials = given.split()[:2]
            first_initial = initials[0][0] if initials else ''
            second_initial = initials[1][0].upper() if len(initials) > 1 else ''
            
            if second_initial:
                author_str = f"{family} {first_initial}.{second_initial}."
            else:
                author_str = f"{family} {first_initial}."
            
            authors_str += author_str
            
            if i < len(metadata['authors']) - 1:
                authors_str += ", "
        
        pages = metadata['pages']
        article_number = metadata['article_number']
        
        # Используем полное название журнала
        journal_name = metadata['journal']
        
        doi_url = f"https://doi.org/{metadata['doi']}"
        
        # Форматирование основной ссылки
        if metadata['issue']:
            gost_ref = f"{authors_str} {metadata['title']} // {journal_name}. – {metadata['year']}. – Vol. {metadata['volume']}, № {metadata['issue']}"
        else:
            gost_ref = f"{authors_str} {metadata['title']} // {journal_name}. – {metadata['year']}. – Vol. {metadata['volume']}"
        
        # НОВАЯ ЛОГИКА: Приоритет article-number над pages
        if article_number and article_number.strip():
            # Используем номер статьи (высший приоритет)
            gost_ref += f". – Art. {article_number.strip()}"
        elif pages and pages.strip():
            # Используем страницы (если нет article-number)
            # Форматирование страниц в формате "122-128" (с обычным дефисом)
            if '-' in pages:
                start_page, end_page = pages.split('-')
                pages_formatted = f"{start_page.strip()}-{end_page.strip()}"
            else:
                pages_formatted = pages.strip()
            gost_ref += f". – Р. {pages_formatted}"
        else:
            # Нет ни article-number, ни pages
            if st.session_state.current_language == 'ru':
                gost_ref += ". – [Без пагинации]"
            else:
                gost_ref += ". – [No pagination]"
        
        # Добавляем DOI
        gost_ref += f". – {doi_url}"
        
        if for_preview:
            return gost_ref, False
        else:
            elements = []
            text_before_doi = gost_ref.replace(doi_url, "")
            elements.append((text_before_doi, False, False, "", False, None))
            elements.append((doi_url, False, False, "", True, metadata['doi']))
            return elements, False

class ACSCitationFormatter(BaseCitationFormatter):
    """Форматировщик для стиля ACS (MDPI)"""
    
    def format_reference(self, metadata: Dict[str, Any], for_preview: bool = False) -> Tuple[Any, bool]:
        if not metadata:
            error_message = "Ошибка: Не удалось отформатировать ссылку." if st.session_state.current_language == 'ru' else "Error: Could not format the reference."
            return (error_message, True)
        
        authors_str = ""
        for i, author in enumerate(metadata['authors']):
            given = author['given']
            family = author['family']
            
            initials = given.split()[:2]
            first_initial = initials[0][0] if initials else ''
            second_initial = initials[1][0].upper() if len(initials) > 1 else ''
            
            if second_initial:
                author_str = f"{family}, {first_initial}.{second_initial}."
            else:
                author_str = f"{family}, {first_initial}."
            
            authors_str += author_str
            
            if i < len(metadata['authors']) - 1:
                authors_str += "; "
        
        pages = metadata['pages']
        article_number = metadata['article_number']
        
        # ИЗМЕНЕНИЕ 1: Используем полный формат страниц вместо сокращенного
        if pages:
            if '-' in pages:
                start_page, end_page = pages.split('-')
                start_page = start_page.strip()
                end_page = end_page.strip()
                # Убираем сокращение и используем полный формат
                pages_formatted = f"{start_page}–{end_page}"
            else:
                pages_formatted = pages
        elif article_number:
            pages_formatted = article_number
        else:
            pages_formatted = ""
        
        journal_name = self.format_journal_name(metadata['journal'])
        
        # Форматируем DOI как гиперссылку
        doi_url = f"https://dx.doi.org/{metadata['doi']}"
        
        # ИЗМЕНЕНИЕ 2: Добавляем DOI после страниц через ". "
        acs_ref = f"{authors_str} {metadata['title']}. {journal_name} {metadata['year']}, {metadata['volume']}, {pages_formatted}. {doi_url}"
        acs_ref = re.sub(r'\.\.+', '.', acs_ref)
        
        if for_preview:
            return acs_ref, False
        else:
            elements = []
            elements.append((authors_str, False, False, " ", False, None))
            elements.append((metadata['title'], False, False, ". ", False, None))
            elements.append((journal_name, True, False, " ", False, None))
            elements.append((str(metadata['year']), False, True, ", ", False, None))
            elements.append((metadata['volume'], True, False, ", ", False, None))
            elements.append((pages_formatted, False, False, ". ", False, None))
            # ИЗМЕНЕНИЕ 3: Добавляем DOI как отдельный элемент с гиперссылкой
            elements.append((doi_url, False, False, "", True, metadata['doi']))
            return elements, False

class RSCCitationFormatter(BaseCitationFormatter):
    """Форматировщик для стиля RSC"""
    
    def format_reference(self, metadata: Dict[str, Any], for_preview: bool = False) -> Tuple[Any, bool]:
        if not metadata:
            error_message = "Ошибка: Не удалось отформатировать ссылку." if st.session_state.current_language == 'ru' else "Error: Could not format the reference."
            return (error_message, True)
        
        authors_str = ""
        for i, author in enumerate(metadata['authors']):
            given = author['given']
            family = author['family']
            
            initials = given.split()[:2]
            first_initial = initials[0][0] if initials else ''
            second_initial = initials[1][0].upper() if len(initials) > 1 else ''
            
            if second_initial:
                author_str = f"{first_initial}.{second_initial}. {family}"
            else:
                author_str = f"{first_initial}. {family}"
            
            authors_str += author_str
            
            if i < len(metadata['authors']) - 1:
                if i == len(metadata['authors']) - 2:
                    authors_str += " and "
                else:
                    authors_str += ", "
        
        pages = metadata['pages']
        article_number = metadata['article_number']
        
        if pages:
            if '-' in pages:
                first_page = pages.split('-')[0].strip()
                pages_formatted = first_page
            else:
                pages_formatted = pages.strip()
        elif article_number:
            pages_formatted = article_number
        else:
            pages_formatted = ""
        
        journal_name = self.format_journal_name(metadata['journal'])
        rsc_ref = f"{authors_str}, {journal_name}, {metadata['year']}, {metadata['volume']}, {pages_formatted}."
        rsc_ref = re.sub(r'\.\.+', '.', rsc_ref)
        
        if for_preview:
            return rsc_ref, False
        else:
            elements = []
            elements.append((authors_str, False, False, ", ", False, None))
            elements.append((journal_name, True, False, ", ", False, None))
            elements.append((str(metadata['year']), False, False, ", ", False, None))
            elements.append((metadata['volume'], False, True, ", ", False, None))
            elements.append((pages_formatted, False, False, ".", False, None))
            return elements, False

class CTACitationFormatter(BaseCitationFormatter):
    """Форматировщик для стиля CTA"""
    
    def format_reference(self, metadata: Dict[str, Any], for_preview: bool = False) -> Tuple[Any, bool]:
        if not metadata:
            error_message = "Ошибка: Не удалось отформатировать ссылку." if st.session_state.current_language == 'ru' else "Error: Could not format the reference."
            return (error_message, True)
        
        authors_str = ""
        for i, author in enumerate(metadata['authors']):
            given = author['given']
            family = author['family']
            
            initials = given.split()[:2]
            first_initial = initials[0][0] if initials else ''
            second_initial = initials[1][0].upper() if len(initials) > 1 else ''
            
            if second_initial:
                author_str = f"{family} {first_initial}{second_initial}"
            else:
                author_str = f"{family} {first_initial}"
            
            authors_str += author_str
            
            if i < len(metadata['authors']) - 1:
                authors_str += ", "
        
        pages = metadata['pages']
        article_number = metadata['article_number']
        pages_formatted = self.format_pages(pages, article_number, "cta")
        journal_name = self.format_journal_name(metadata['journal'])
        issue_part = f"({metadata['issue']})" if metadata['issue'] else ""
        
        cta_ref = f"{authors_str}. {metadata['title']}. {journal_name}. {metadata['year']};{metadata['volume']}{issue_part}:{pages_formatted}. doi:{metadata['doi']}"
        
        if for_preview:
            return cta_ref, False
        else:
            elements = []
            elements.append((authors_str, False, False, ". ", False, None))
            elements.append((metadata['title'], False, False, ". ", False, None))
            elements.append((journal_name, True, False, ". ", False, None))
            elements.append((str(metadata['year']), False, False, ";", False, None))
            elements.append((metadata['volume'], False, False, "", False, None))
            if metadata['issue']:
                elements.append((f"({metadata['issue']})", False, False, ":", False, None))
            else:
                elements.append(("", False, False, ":", False, None))
            elements.append((pages_formatted, False, False, ". ", False, None))
            doi_text = f"doi:{metadata['doi']}"
            elements.append((doi_text, False, False, "", True, metadata['doi']))
            return elements, False

class CitationFormatterFactory:
    """Фабрика для создания форматировщиков цитирования"""
    
    @staticmethod
    def create_formatter(style_config: Dict[str, Any]) -> BaseCitationFormatter:
        if style_config.get('gost_style', False):
            return GOSTCitationFormatter(style_config)
        elif style_config.get('acs_style', False):
            return ACSCitationFormatter(style_config)
        elif style_config.get('rsc_style', False):
            return RSCCitationFormatter(style_config)
        elif style_config.get('cta_style', False):
            return CTACitationFormatter(style_config)
        else:
            return CustomCitationFormatter(style_config)

class DocumentGenerator:
    """Класс для генерации DOCX документов"""
    
    @staticmethod
    def add_hyperlink(paragraph, text, url):
        part = paragraph.part
        r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
        
        hyperlink = OxmlElement('w:hyperlink')
        hyperlink.set(qn('r:id'), r_id)
        
        new_run = OxmlElement('w:r')
        rPr = OxmlElement('w:rPr')
        
        color = OxmlElement('w:color')
        color.set(qn('w:val'), '0000FF')
        rPr.append(color)
        
        underline = OxmlElement('w:u')
        underline.set(qn('w:val'), 'single')
        rPr.append(underline)
        
        new_run.append(rPr)
        new_text = OxmlElement('w:t')
        new_text.text = text
        new_run.append(new_text)
        
        hyperlink.append(new_run)
        paragraph._p.append(hyperlink)
        
        return hyperlink
    
    @staticmethod
    def apply_yellow_background(run):
        shd = OxmlElement('w:shd')
        shd.set(qn('w:fill'), 'FFFF00')
        run._element.get_or_add_rPr().append(shd)
    
    @staticmethod
    def apply_blue_background(run):
        shd = OxmlElement('w:shd')
        shd.set(qn('w:fill'), 'E6F3FF')
        run._element.get_or_add_rPr().append(shd)
    
    @staticmethod
    def apply_red_color(run):
        color = OxmlElement('w:color')
        color.set(qn('w:val'), 'FF0000')
        run._element.get_or_add_rPr().append(color)
    
    @staticmethod
    def generate_document(formatted_refs: List[Tuple[Any, bool, Any]], 
                         statistics: Dict[str, Any],
                         style_config: Dict[str, Any],
                         duplicates_info: Dict[int, int] = None) -> io.BytesIO:
        output_doc = Document()
        output_doc.add_paragraph('Citation Style Construction / © IHTE, https://ihte.ru/ © CTA, https://chimicatechnoacta.ru / developed by daM©')
        output_doc.add_paragraph('See short stats after the References section')
        output_doc.add_heading('References', level=1)
        
        DocumentGenerator._add_formatted_references(output_doc, formatted_refs, style_config, duplicates_info)
        DocumentGenerator._add_statistics_section(output_doc, statistics)
        
        output_doc_buffer = io.BytesIO()
        output_doc.save(output_doc_buffer)
        output_doc_buffer.seek(0)
        return output_doc_buffer
    
    @staticmethod
    def _add_formatted_references(doc: Document, 
                                formatted_refs: List[Tuple[Any, bool, Any]], 
                                style_config: Dict[str, Any],
                                duplicates_info: Dict[int, int] = None):
        for i, (elements, is_error, metadata) in enumerate(formatted_refs):
            numbering = style_config['numbering_style']
            
            if numbering == "No numbering":
                prefix = ""
            elif numbering == "1":
                prefix = f"{i + 1} "
            elif numbering == "1.":
                prefix = f"{i + 1}. "
            elif numbering == "1)":
                prefix = f"{i + 1}) "
            elif numbering == "(1)":
                prefix = f"({i + 1}) "
            elif numbering == "[1]":
                prefix = f"[{i + 1}] "
            else:
                prefix = f"{i + 1}. "
            
            para = doc.add_paragraph(prefix)
            
            if is_error:
                run = para.add_run(str(elements))
                DocumentGenerator.apply_yellow_background(run)
            elif duplicates_info and i in duplicates_info:
                original_index = duplicates_info[i] + 1
                duplicate_note = get_text('duplicate_reference').format(original_index)
                
                if isinstance(elements, str):
                    run = para.add_run(elements)
                    DocumentGenerator.apply_blue_background(run)
                    para.add_run(f" - {duplicate_note}").italic = True
                else:
                    for j, (value, italic, bold, separator, is_doi_hyperlink, doi_value) in enumerate(elements):
                        if is_doi_hyperlink and doi_value:
                            DocumentGenerator.add_hyperlink(para, value, f"https://doi.org/{doi_value}")
                        else:
                            run = para.add_run(value)
                            if italic:
                                run.font.italic = True
                            if bold:
                                run.font.bold = True
                            DocumentGenerator.apply_blue_background(run)
                        
                        if separator and j < len(elements) - 1:
                            para.add_run(separator)
                    
                    para.add_run(f" - {duplicate_note}").italic = True
            else:
                if metadata is None:
                    run = para.add_run(str(elements))
                    run.font.italic = True
                else:
                    for j, (value, italic, bold, separator, is_doi_hyperlink, doi_value) in enumerate(elements):
                        if is_doi_hyperlink and doi_value:
                            DocumentGenerator.add_hyperlink(para, value, f"https://doi.org/{doi_value}")
                        else:
                            run = para.add_run(value)
                            if italic:
                                run.font.italic = True
                            if bold:
                                run.font.bold = True
                        
                        if separator and j < len(elements) - 1:
                            para.add_run(separator)
                    
                    if style_config['final_punctuation'] and not is_error:
                        para.add_run(".")
    
    @staticmethod
    def _add_statistics_section(doc: Document, statistics: Dict[str, Any]):
        doc.add_heading('Stats', level=1)
        
        doc.add_heading('Journal Frequency', level=2)
        journal_table = doc.add_table(rows=1, cols=3)
        journal_table.style = 'Table Grid'
        
        hdr_cells = journal_table.rows[0].cells
        hdr_cells[0].text = 'Journal Name'
        hdr_cells[1].text = 'Count'
        hdr_cells[2].text = 'Percentage (%)'
        
        for journal_stat in statistics['journal_stats']:
            row_cells = journal_table.add_row().cells
            row_cells[0].text = journal_stat['journal']
            row_cells[1].text = str(journal_stat['count'])
            row_cells[2].text = str(journal_stat['percentage'])
        
        doc.add_paragraph()
        
        doc.add_heading('Year Distribution', level=2)
        
        if statistics['needs_more_recent_references']:
            warning_para = doc.add_paragraph()
            warning_run = warning_para.add_run("To improve the relevance and significance of the research, consider including more recent references published within the last 3-4 years")
            DocumentGenerator.apply_red_color(warning_run)
            doc.add_paragraph()
        
        year_table = doc.add_table(rows=1, cols=3)
        year_table.style = 'Table Grid'
        
        hdr_cells = year_table.rows[0].cells
        hdr_cells[0].text = 'Year'
        hdr_cells[1].text = 'Count'
        hdr_cells[2].text = 'Percentage (%)'
        
        for year_stat in statistics['year_stats']:
            row_cells = year_table.add_row().cells
            row_cells[0].text = str(year_stat['year'])
            row_cells[1].text = str(year_stat['count'])
            row_cells[2].text = str(year_stat['percentage'])
        
        doc.add_paragraph()
        
        doc.add_heading('Author Distribution', level=2)
        
        if statistics['has_frequent_author']:
            warning_para = doc.add_paragraph()
            warning_run = warning_para.add_run("The author(s) are referenced frequently. Either reduce the number of references to the author(s), or expand the reference list to include more sources")
            DocumentGenerator.apply_red_color(warning_run)
            doc.add_paragraph()
        
        author_table = doc.add_table(rows=1, cols=3)
        author_table.style = 'Table Grid'
        
        hdr_cells = author_table.rows[0].cells
        hdr_cells[0].text = 'Author'
        hdr_cells[1].text = 'Count'
        hdr_cells[2].text = 'Percentage (%)'
        
        for author_stat in statistics['author_stats']:
            row_cells = author_table.add_row().cells
            row_cells[0].text = author_stat['author']
            row_cells[1].text = str(author_stat['count'])
            row_cells[2].text = str(author_stat['percentage'])

# Улучшенные функции обработки DOI
class DOIProcessor:
    """Процессор для работы с DOI"""
    
    def __init__(self):
        self.cache = doi_cache
        self.works = works
    
    def find_doi_enhanced(self, reference: str) -> Optional[str]:
        """Улучшенный поиск DOI с использованием нескольких стратегий"""
        if self._is_section_header(reference):
            return None
        
        # Стратегия 1: Поиск явного DOI
        explicit_doi = self._find_explicit_doi(reference)
        if explicit_doi:
            logger.info(f"Found explicit DOI: {explicit_doi}")
            return explicit_doi
        
        # Стратегия 2: Поиск по библиографическим данным в Crossref
        bibliographic_doi = self._find_bibliographic_doi(reference)
        if bibliographic_doi:
            logger.info(f"Found bibliographic DOI: {bibliographic_doi}")
            return bibliographic_doi
        
        # Стратегия 3: Поиск через OpenAlex (если подключен)
        openalex_doi = self._find_openalex_doi(reference)
        if openalex_doi:
            logger.info(f"Found OpenAlex DOI: {openalex_doi}")
            return openalex_doi
        
        logger.warning(f"No DOI found for reference: {reference[:100]}...")
        return None
    
    def _is_section_header(self, text: str) -> bool:
        """Определяет, является ли текст заголовком раздела"""
        text_upper = text.upper().strip()
        section_patterns = [
            r'^NOTES?\s+AND\s+REFERENCES?$',
            r'^REFERENCES?$',
            r'^BIBLIOGRAPHY$',
            r'^LITERATURE$',
            r'^WORKS?\s+CITED$',
            r'^SOURCES?$',
            r'^CHAPTER\s+\d+$',
            r'^SECTION\s+\d+$',
            r'^PART\s+\d+$'
        ]
        
        for pattern in section_patterns:
            if re.search(pattern, text_upper):
                return True
        return False
    
    def _find_explicit_doi(self, reference: str) -> Optional[str]:
        """Поиск явного DOI в тексте"""
        doi_patterns = [
            r'https?://doi\.org/(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)',
            r'doi:\s*(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)',
            r'DOI:\s*(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)',
            r'\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b'
        ]
        
        for pattern in doi_patterns:
            match = re.search(pattern, reference, re.IGNORECASE)
            if match:
                doi = match.group(1).rstrip('.,;:')
                return doi
        
        clean_ref = reference.strip()
        if re.match(r'^(doi:|DOI:)?\s*10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\s*$', clean_ref, re.IGNORECASE):
            doi_match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)', clean_ref)
            if doi_match:
                return doi_match.group(1).rstrip('.,;:')
        
        return None
    
    def _find_bibliographic_doi(self, reference: str) -> Optional[str]:
        """Поиск DOI по библиографическим данным"""
        clean_ref = re.sub(r'\s*(https?://doi\.org/|doi:|DOI:)\s*[^\s,;]+', '', reference, flags=re.IGNORECASE)
        clean_ref = clean_ref.strip()
        
        if len(clean_ref) < 30:
            return None
        
        try:
            query = self.works.query(bibliographic=clean_ref).sort('relevance').order('desc')
            for result in query:
                if 'DOI' in result:
                    return result['DOI']
        except Exception as e:
            logger.error(f"Bibliographic search error for '{clean_ref}': {e}")
        
        return None
    
    def _find_openalex_doi(self, reference: str) -> Optional[str]:
        """Поиск DOI через OpenAlex API"""
        # Заглушка для будущей реализации OpenAlex
        # OpenAlex предоставляет бесплатный API с хорошими лимитами
        return None

    def extract_metadata_with_cache(self, doi: str) -> Optional[Dict]:
        """Извлечение метаданных с использованием кэша"""
        # Проверка кэша
        cached_metadata = self.cache.get(doi)
        if cached_metadata:
            logger.info(f"Cache hit for DOI: {doi}")
            return cached_metadata
        
        # Извлечение из API
        logger.info(f"Cache miss for DOI: {doi}, fetching from API")
        metadata = self._extract_metadata_from_api(doi)
        
        if metadata:
            self.cache.set(doi, metadata)
        
        return metadata
    
    def _extract_metadata_from_api(self, doi: str) -> Optional[Dict]:
        """Извлечение метаданных из Crossref API"""
        try:
            result = self.works.doi(doi)
            if not result:
                return None
            
            authors = result.get('author', [])
            author_list = []
            for author in authors:
                given_name = author.get('given', '')
                family_name = self._normalize_name(author.get('family', ''))
                author_list.append({
                    'given': given_name,
                    'family': family_name
                })
            
            title = ''
            if 'title' in result and result['title']:
                title = self._clean_text(result['title'][0])
                title = re.sub(r'</?sub>|</?i>|</?SUB>|</?I>', '', title, flags=re.IGNORECASE)
            
            journal = ''
            if 'container-title' in result and result['container-title']:
                journal = self._clean_text(result['container-title'][0])
            
            year = None
            if 'published' in result and 'date-parts' in result['published']:
                date_parts = result['published']['date-parts']
                if date_parts and date_parts[0]:
                    year = date_parts[0][0]
            
            volume = result.get('volume', '')
            issue = result.get('issue', '')
            pages = result.get('page', '')
            article_number = result.get('article-number', '')
            
            metadata = {
                'authors': author_list,
                'title': title,
                'journal': journal,
                'year': year,
                'volume': volume,
                'issue': issue,
                'pages': pages,
                'article_number': article_number,
                'doi': doi,
                'original_doi': doi
            }
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting metadata for DOI {doi}: {e}")
            return None
    
    def _normalize_name(self, name: str) -> str:
        """Нормализует имя автора"""
        if not name:
            return ''
        
        if '-' in name or "'" in name or '’' in name:
            parts = re.split(r'([-\'’])', name)
            normalized_parts = []
            
            for i, part in enumerate(parts):
                if part in ['-', "'", '’']:
                    normalized_parts.append(part)
                else:
                    if part:
                        normalized_parts.append(part[0].upper() + part[1:].lower() if len(part) > 1 else part.upper())
            
            return ''.join(normalized_parts)
        else:
            if len(name) > 1:
                return name[0].upper() + name[1:].lower()
            else:
                return name.upper()
    
    def _clean_text(self, text: str) -> str:
        """Очищает текст от HTML тегов и entities"""
        if not text:
            return ""
        
        text = re.sub(r'<[^>]+>', '', text)
        text = html.unescape(text)
        text = re.sub(r'&[^;]+;', '', text)
        return text.strip()

# Основные функции обработки
class ReferenceProcessor:
    """Основной процессор для обработки ссылок"""
    
    def __init__(self):
        self.doi_processor = DOIProcessor()
        self.progress_manager = ProgressManager()
        self.validator = StyleValidator()
    
    def process_references(self, references: List[str], style_config: Dict, 
                         progress_container, status_container) -> Tuple[List, io.BytesIO, int, int, Dict]:
        """Обработка списка ссылок с отображением прогресса"""
        # Валидация
        is_valid, validation_messages = self.validator.validate_references_count(references)
        for msg in validation_messages:
            if "error" in msg.lower():
                st.error(msg)
            else:
                st.warning(msg)
        
        if not is_valid:
            return [], io.BytesIO(), 0, 0, {}
        
        doi_list = []
        formatted_refs = []
        doi_found_count = 0
        doi_not_found_count = 0
        
        # Сбор DOI для пакетной обработки
        valid_dois = []
        reference_doi_map = {}
        
        for i, ref in enumerate(references):
            if self.doi_processor._is_section_header(ref):
                doi_list.append(f"{ref} [SECTION HEADER - SKIPPED]")
                formatted_refs.append((ref, False, None))
                continue
                
            doi = self.doi_processor.find_doi_enhanced(ref)
            if doi:
                valid_dois.append(doi)
                reference_doi_map[i] = doi
                doi_list.append(doi)
            else:
                error_msg = f"{ref}\nПроверьте источник и добавьте DOI вручную." if st.session_state.current_language == 'ru' else f"{ref}\nPlease check this source and insert the DOI manually."
                doi_list.append(error_msg)
                formatted_refs.append((error_msg, True, None))
                doi_not_found_count += 1
        
        # Пакетная обработка DOI
        if valid_dois:
            self._process_doi_batch(valid_dois, reference_doi_map, references, 
                                  formatted_refs, doi_list, style_config,
                                  progress_container, status_container)
        
        # Подсчет статистики
        doi_found_count = len([ref for ref in formatted_refs if not ref[1] and ref[2]])
        
        # Поиск дубликатов
        duplicates_info = self._find_duplicates(formatted_refs)
        
        # Создание TXT файла
        txt_buffer = self._create_txt_file(doi_list)
        
        return formatted_refs, txt_buffer, doi_found_count, doi_not_found_count, duplicates_info
    
    def _process_doi_batch(self, valid_dois, reference_doi_map, references, 
                          formatted_refs, doi_list, style_config,
                          progress_container, status_container):
        """Пакетная обработка DOI"""
        status_container.info(get_text('batch_processing'))
        
        # Настройка прогресса
        self.progress_manager.start_processing(len(valid_dois))
        
        # Создаем прогресс-бар, который всегда будет виден
        progress_bar = progress_container.progress(0)
        status_display = status_container.empty()
        
        # Первая попытка обработки
        metadata_results = self._extract_metadata_batch(valid_dois, progress_bar, status_display)
        
        # Обработка результатов
        doi_to_metadata = dict(zip(valid_dois, metadata_results))
        
        for i, ref in enumerate(references):
            if i in reference_doi_map:
                doi = reference_doi_map[i]
                metadata = doi_to_metadata.get(doi)
                
                if metadata:
                    formatted_ref, is_error = self._format_reference(metadata, style_config)
                    formatted_refs.append((formatted_ref, is_error, metadata))
                else:
                    error_msg = self._create_error_message(ref, st.session_state.current_language)
                    doi_list[doi_list.index(doi)] = error_msg
                    formatted_refs.append((error_msg, True, None))
        
        # Обновление прогресса
        self._update_progress_display(progress_bar, status_display, len(valid_dois), len(valid_dois), 0)
    
    def _extract_metadata_batch(self, doi_list, progress_bar, status_display) -> List:
        """Пакетное извлечение метаданных"""
        results = [None] * len(doi_list)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=Config.CROSSREF_WORKERS) as executor:
            future_to_index = {
                executor.submit(self.doi_processor.extract_metadata_with_cache, doi): i 
                for i, doi in enumerate(doi_list)
            }
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result(timeout=Config.REQUEST_TIMEOUT)
                    results[index] = result
                except Exception as e:
                    logger.error(f"Error processing DOI at index {index}: {e}")
                    results[index] = None
                
                completed += 1
                self._update_progress_display(progress_bar, status_display, completed, len(doi_list), 0)
        
        # Повторная попытка для неудачных запросов
        failed_indices = [i for i, result in enumerate(results) if result is None]
        if failed_indices:
            logger.info(f"Retrying {len(failed_indices)} failed DOI requests")
            self._retry_failed_requests(failed_indices, doi_list, results, progress_bar, status_display)
        
        return results
    
    def _retry_failed_requests(self, failed_indices, doi_list, results, progress_bar, status_display):
        """Повторная попытка обработки неудачных запросов"""
        completed = len(doi_list) - len(failed_indices)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=Config.CROSSREF_RETRY_WORKERS) as executor:
            retry_futures = {}
            for index in failed_indices:
                doi = doi_list[index]
                future = executor.submit(self.doi_processor.extract_metadata_with_cache, doi)
                retry_futures[future] = index
            
            for future in concurrent.futures.as_completed(retry_futures):
                index = retry_futures[future]
                try:
                    result = future.result(timeout=Config.REQUEST_TIMEOUT)
                    results[index] = result
                except Exception as e:
                    logger.error(f"Error in retry processing DOI at index {index}: {e}")
                    results[index] = None
                
                completed += 1
                self._update_progress_display(progress_bar, status_display, completed, len(doi_list), len(failed_indices))
    
    def _update_progress_display(self, progress_bar, status_display, completed, total, errors):
        """Обновление отображения прогресса"""
        progress_info = self.progress_manager.get_progress_info()
        progress_ratio = completed / total if total > 0 else 0
        progress_color = self.progress_manager.get_progress_color(progress_ratio)
        
        # Обновляем прогресс-бар
        progress_bar.progress(progress_ratio)
        
        # Обновление стиля прогресс-бара с цветом
        progress_bar.markdown(f"""
            <style>
                .stProgress > div > div > div > div {{
                    background-color: {progress_color};
                }}
            </style>
        """, unsafe_allow_html=True)
        
        # Обновляем текст статуса
        status_text = f"Processed: {completed}/{total} | Errors: {errors}"
        if progress_info['time_remaining']:
            mins_remaining = int(progress_info['time_remaining'] / 60)
            status_text += f" | ETA: {mins_remaining} min"
        
        status_display.text(status_text)
    
    def _format_reference(self, metadata: Dict, style_config: Dict) -> Tuple[Any, bool]:
        """Форматирование ссылки"""
        formatter = CitationFormatterFactory.create_formatter(style_config)
        return formatter.format_reference(metadata, False)
    
    def _find_duplicates(self, formatted_refs: List) -> Dict[int, int]:
        """Поиск дубликатов ссылок"""
        seen_hashes = {}
        duplicates_info = {}
        
        for i, (elements, is_error, metadata) in enumerate(formatted_refs):
            if is_error or not metadata:
                continue
                
            ref_hash = self._generate_reference_hash(metadata)
            if not ref_hash:
                continue
                
            if ref_hash in seen_hashes:
                duplicates_info[i] = seen_hashes[ref_hash]
            else:
                seen_hashes[ref_hash] = i
        
        return duplicates_info
    
    def _generate_reference_hash(self, metadata: Dict) -> Optional[str]:
        """Генерация хеша для идентификации дубликатов"""
        if not metadata:
            return None
        
        hash_string = ""
        
        if metadata.get('authors'):
            authors_hash = "|".join(sorted([author.get('family', '').lower() for author in metadata['authors']]))
            hash_string += authors_hash + "||"
        
        title = metadata.get('title', '')[:50].lower()
        hash_string += title + "||"
        
        hash_string += (metadata.get('journal', '') + "||").lower()
        hash_string += str(metadata.get('year', '')) + "||"
        hash_string += metadata.get('volume', '') + "||"
        hash_string += metadata.get('pages', '') + "||"
        hash_string += self._normalize_doi(metadata.get('doi', ''))
        
        return hashlib.md5(hash_string.encode('utf-8')).hexdigest()
    
    def _normalize_doi(self, doi: str) -> str:
        """Нормализация DOI"""
        if not doi:
            return ""
        return re.sub(r'^(https?://doi\.org/|doi:|DOI:)', '', doi, flags=re.IGNORECASE).lower().strip()
    
    def _create_error_message(self, ref: str, language: str) -> str:
        """Создание сообщения об ошибке"""
        if language == 'ru':
            return f"{ref}\nПроверьте источник и добавьте DOI вручную."
        else:
            return f"{ref}\nPlease check this source and insert the DOI manually."
    
    def _create_txt_file(self, doi_list: List[str]) -> io.BytesIO:
        """Создание TXT файла со списком DOI"""
        output_txt_buffer = io.StringIO()
        for doi in doi_list:
            output_txt_buffer.write(f"{doi}\n")
        output_txt_buffer.seek(0)
        return io.BytesIO(output_txt_buffer.getvalue().encode('utf-8'))

# UI компоненты нового интерфейса
class ModernUIComponents:
    """Современные компоненты пользовательского интерфейса"""
    
    def __init__(self):
        self.user_prefs = UserPreferencesManager()
    
    def apply_theme_styles(self):
        """Применение стилей темы"""
        theme = Config.THEMES[st.session_state.current_theme]
        
        st.markdown(f"""
            <style>
            /* Основные стили */
            .main {{
                background-color: {theme['background']};
                color: {theme['text']};
                font-family: {theme['font']};
                padding: 1rem;
            }}
            
            /* Карточки */
            .card {{
                background-color: {theme['cardBackground']};
                border-radius: {theme['radius']};
                padding: 1.5rem;
                margin-bottom: 1rem;
                box-shadow: {theme['shadow']};
                border: 1px solid {theme['border']};
            }}
            
            /* Кнопки */
            .stButton > button {{
                background-color: {theme['primary']};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0.75rem 1.5rem;
                font-weight: 600;
                transition: all 0.2s;
            }}
            
            .stButton > button:hover {{
                background-color: {theme['secondary']};
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            }}
            
            /* Индикатор шагов */
            .step-indicator {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 2rem;
                position: relative;
            }}
            
            .step-indicator::before {{
                content: '';
                position: absolute;
                top: 15px;
                left: 0;
                right: 0;
                height: 2px;
                background-color: {theme['border']};
                z-index: 1;
            }}
            
            .step {{
                position: relative;
                z-index: 2;
                text-align: center;
                flex: 1;
            }}
            
            .step-circle {{
                width: 32px;
                height: 32px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 0.5rem;
                font-weight: 600;
                background-color: {theme['secondaryBackground']};
                border: 2px solid {theme['border']};
                color: {theme['textSecondary']};
            }}
            
            .step.active .step-circle {{
                background-color: {theme['primary']};
                border-color: {theme['primary']};
                color: white;
            }}
            
            .step.completed .step-circle {{
                background-color: {theme['success']};
                border-color: {theme['success']};
                color: white;
            }}
            
            .step-label {{
                font-size: 0.875rem;
                color: {theme['textSecondary']};
            }}
            
            .step.active .step-label {{
                color: {theme['primary']};
                font-weight: 600;
            }}
            
            /* Карточки выбора */
            .choice-card {{
                cursor: pointer;
                transition: all 0.3s;
                border: 2px solid {theme['border']};
            }}
            
            .choice-card:hover {{
                border-color: {theme['primary']};
                transform: translateY(-4px);
                box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
            }}
            
            .choice-card.selected {{
                border-color: {theme['primary']};
                background-color: rgba(59, 130, 246, 0.05);
            }}
            
            /* Элементы drag-and-drop */
            .draggable-item {{
                padding: 0.75rem 1rem;
                margin-bottom: 0.5rem;
                background-color: {theme['secondaryBackground']};
                border-radius: 8px;
                border: 1px solid {theme['border']};
                cursor: move;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }}
            
            .draggable-item:hover {{
                border-color: {theme['primary']};
            }}
            
            .element-controls {{
                display: flex;
                gap: 0.5rem;
                align-items: center;
            }}
            
            /* Предпросмотр */
            .preview-box {{
                background-color: {theme['secondaryBackground']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 1rem;
                margin-top: 1rem;
                font-style: italic;
            }}
            
            /* Хедер */
            .app-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 2rem;
                padding-bottom: 1rem;
                border-bottom: 1px solid {theme['border']};
            }}
            
            .header-controls {{
                display: flex;
                gap: 1rem;
                align-items: center;
            }}
            
            /* Навигация */
            .navigation {{
                display: flex;
                justify-content: space-between;
                margin-top: 2rem;
                padding-top: 1rem;
                border-top: 1px solid {theme['border']};
            }}
            
            /* Результаты */
            .result-card {{
                background-color: {theme['success']}10;
                border: 1px solid {theme['success']}30;
                border-radius: 12px;
                padding: 1.5rem;
            }}
            
            .download-button {{
                width: 100%;
                margin-bottom: 0.5rem;
            }}
            
            /* Адаптивность */
            @media (max-width: 768px) {{
                .card {{
                    padding: 1rem;
                }}
                .step-label {{
                    font-size: 0.75rem;
                }}
            }}
            </style>
        """, unsafe_allow_html=True)
    
    def render_header(self):
        """Рендер заголовка приложения"""
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.markdown(f"<h1 style='color: {Config.THEMES[st.session_state.current_theme]['primary']}; margin: 0;'>{get_text('app_title')}</h1>", unsafe_allow_html=True)
        
        with col2:
            language = st.selectbox(
                get_text('language_select'),
                ['English', 'Русский'],
                index=0 if st.session_state.current_language == 'en' else 1,
                key="language_select_header"
            )
            if language == 'English' and st.session_state.current_language != 'en':
                st.session_state.current_language = 'en'
                st.rerun()
            elif language == 'Русский' and st.session_state.current_language != 'ru':
                st.session_state.current_language = 'ru'
                st.rerun()
        
        with col3:
            theme_options = {
                'Light': get_text('theme_light'),
                'Dark': get_text('theme_dark'),
                'Contrast': get_text('theme_contrast')
            }
            theme_names = list(theme_options.values())
            current_theme_name = theme_options[st.session_state.current_theme.capitalize()]
            
            theme = st.selectbox(
                get_text('theme_select'),
                theme_names,
                index=theme_names.index(current_theme_name),
                key="theme_select_header"
            )
            
            theme_map = {v: k.lower() for k, v in theme_options.items()}
            if theme_map[theme] != st.session_state.current_theme:
                st.session_state.current_theme = theme_map[theme]
                st.rerun()
    
    def render_step_indicator(self):
        """Рендер индикатора шагов"""
        steps = [
            get_text('step_start'),
            get_text('step_style'),
            get_text('step_input'),
            get_text('step_process'),
            get_text('step_output')
        ]
        
        current_step_index = st.session_state.current_step
        
        html = f"""
        <div class="step-indicator">
        """
        
        for i, step in enumerate(steps):
            status = ""
            if i == current_step_index:
                status = "active"
            elif i < current_step_index:
                status = "completed"
            
            html += f"""
            <div class="step {status}">
                <div class="step-circle">{i+1}</div>
                <div class="step-label">{step}</div>
            </div>
            """
        
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)
    
    def render_navigation_buttons(self):
        """Рендер кнопок навигации"""
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col1:
            if st.session_state.current_step > 0:
                if st.button(get_text('back'), use_container_width=True, key="nav_back"):
                    self._go_back()
        
        with col2:
            if st.session_state.current_step == 0:
                pass
            elif st.session_state.current_step < 4:
                if st.button(get_text('next'), use_container_width=True, key="nav_next"):
                    self._go_next()
        
        with col3:
            if st.button(get_text('clear_all'), use_container_width=True, key="nav_clear"):
                self._clear_all()
    
    def _go_back(self):
        """Переход на предыдущий шаг"""
        if len(st.session_state.previous_steps) > 0:
            st.session_state.current_step = st.session_state.previous_steps.pop()
        else:
            st.session_state.current_step = max(0, st.session_state.current_step - 1)
        st.rerun()
    
    def _go_next(self):
        """Переход на следующий шаг"""
        # Сохраняем текущий шаг в историю
        st.session_state.previous_steps.append(st.session_state.current_step)
        # Ограничиваем историю 3 шагами
        if len(st.session_state.previous_steps) > Config.MAX_UNDO_STEPS:
            st.session_state.previous_steps.pop(0)
        
        st.session_state.current_step = min(4, st.session_state.current_step + 1)
        st.rerun()
    
    def _clear_all(self):
        """Очистка всех данных и возврат к началу"""
        # Сохраняем язык и тему
        language = st.session_state.current_language
        theme = st.session_state.current_theme
        
        # Очищаем все состояния
        for key in list(st.session_state.keys()):
            if key not in ['current_language', 'current_theme', 'user_prefs_loaded']:
                del st.session_state[key]
        
        # Восстанавливаем язык и тему
        st.session_state.current_language = language
        st.session_state.current_theme = theme
        
        # Инициализируем заново
        init_session_state()
        st.rerun()
    
    def render_step_start(self):
        """Рендер стартового шага"""
        st.markdown(f"<h2>{get_text('welcome')}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: {Config.THEMES[st.session_state.current_theme]['textSecondary']}; margin-bottom: 2rem;'>Выберите способ создания стиля цитирования</p>", unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button(f"""
                <div style='text-align: center; padding: 2rem;'>
                    <div style='font-size: 3rem; margin-bottom: 1rem;'>🎨</div>
                    <h3 style='margin: 0 0 0.5rem 0;'>{get_text('create_new_style')}</h3>
                    <p style='color: #666; margin: 0; font-size: 0.9rem;'>{get_text('create_new_desc')}</p>
                </div>
            """, use_container_width=True, key="btn_create_new"):
                st.session_state.create_custom_style = True
                st.session_state.current_step = 2  # Переходим к созданию стиля
                st.rerun()
        
        with col2:
            if st.button(f"""
                <div style='text-align: center; padding: 2rem;'>
                    <div style='font-size: 3rem; margin-bottom: 1rem;'>📚</div>
                    <h3 style='margin: 0 0 0.5rem 0;'>{get_text('choose_preset')}</h3>
                    <p style='color: #666; margin: 0; font-size: 0.9rem;'>{get_text('choose_preset_desc')}</p>
                </div>
            """, use_container_width=True, key="btn_choose_preset"):
                st.session_state.create_custom_style = False
                st.session_state.current_step = 1  # Переходим к выбору стиля
                st.rerun()
        
        st.markdown("---")
        
        # Загрузка сохраненного стиля
        uploaded_file = st.file_uploader(
            get_text('load_saved'),
            type=['json'],
            key="style_loader_start"
        )
        
        if uploaded_file is not None:
            try:
                content = uploaded_file.read().decode('utf-8')
                imported_style = json.loads(content)
                
                if 'style_config' in imported_style:
                    style_config = imported_style['style_config']
                else:
                    style_config = imported_style
                
                # Применяем импортированный стиль
                self._apply_imported_style_to_new_ui(style_config)
                st.success(get_text('style_loaded'))
                st.session_state.current_step = 3  # Переходим к вводу данных
                st.rerun()
                
            except Exception as e:
                st.error(f"{get_text('error')}: {str(e)}")
    
    def _apply_imported_style_to_new_ui(self, style_config):
        """Применение импортированного стиля к новому UI"""
        # Сбрасываем элементы стиля
        st.session_state.style_elements = [
            {'id': 1, 'name': 'Authors', 'enabled': False, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 2, 'name': 'Title', 'enabled': False, 'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '},
            {'id': 3, 'name': 'Journal', 'enabled': False, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 4, 'name': 'Year', 'enabled': False, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 5, 'name': 'Volume', 'enabled': False, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 6, 'name': 'Issue', 'enabled': False, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ': '},
            {'id': 7, 'name': 'Pages', 'enabled': False, 'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '},
            {'id': 8, 'name': 'DOI', 'enabled': False, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ''},
        ]
        
        # Применяем элементы из конфига
        if 'elements' in style_config:
            for i, (element_name, config) in enumerate(style_config['elements']):
                if i < len(st.session_state.style_elements):
                    for elem in st.session_state.style_elements:
                        if elem['name'] == element_name:
                            elem['enabled'] = True
                            elem['italic'] = config.get('italic', False)
                            elem['bold'] = config.get('bold', False)
                            elem['parentheses'] = config.get('parentheses', False)
                            elem['separator'] = config.get('separator', '. ')
                            break
        
        # Применяем другие настройки
        if 'author_format' in style_config:
            st.session_state.author_format = style_config['author_format']
        if 'page_format' in style_config:
            st.session_state.page_format = style_config['page_format']
        if 'doi_format' in style_config:
            st.session_state.doi_format = style_config['doi_format']
        if 'doi_hyperlink' in style_config:
            st.session_state.doi_hyperlink = style_config['doi_hyperlink']
        if 'numbering_style' in style_config:
            st.session_state.numbering_style = style_config['numbering_style']
    
    def render_step_style_select(self):
        """Рендер шага выбора готового стиля"""
        st.markdown(f"<h2>{get_text('select_preset_title')}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: {Config.THEMES[st.session_state.current_theme]['textSecondary']}; margin-bottom: 2rem;'>{get_text('select_preset_desc')}</p>", unsafe_allow_html=True)
        
        # Фильтруем стили по языку
        if st.session_state.current_language == 'ru':
            # Для русского показываем ГОСТ и международные стили
            preset_keys = ['gost', 'apa', 'vancouver', 'ieee', 'harvard', 'acs', 'rsc', 'chicago']
        else:
            # Для английского показываем все, кроме ГОСТ
            preset_keys = ['apa', 'vancouver', 'ieee', 'harvard', 'acs', 'rsc', 'chicago']
        
        # Создаем сетку 2x4
        cols = st.columns(2)
        
        for idx, preset_key in enumerate(preset_keys):
            with cols[idx % 2]:
                preset = Config.PRESET_STYLES[preset_key]
                
                if st.button(f"""
                    <div style='text-align: center; padding: 1.5rem;'>
                        <div style='font-size: 2rem; margin-bottom: 0.5rem;'>
                            {'🇷🇺' if preset_key == 'gost' else '🌐'}
                        </div>
                        <h3 style='margin: 0 0 0.5rem 0;'>{preset['name']}</h3>
                        <p style='color: #666; margin: 0; font-size: 0.8rem;'>{preset['description']}</p>
                    </div>
                """, use_container_width=True, key=f"preset_{preset_key}"):
                    st.session_state.selected_preset = preset_key
                    self._apply_preset_style(preset_key)
                    st.session_state.current_step = 3  # Переходим к вводу данных
                    st.rerun()
        
        # Предпросмотр выбранного стиля
        if st.session_state.selected_preset:
            st.markdown("---")
            preset = Config.PRESET_STYLES[st.session_state.selected_preset]
            st.markdown(f"**{get_text('preview')}**")
            
            preview_text = self._get_preset_preview(st.session_state.selected_preset)
            st.markdown(f"""
                <div class="preview-box">
                    {preview_text}
                </div>
            """, unsafe_allow_html=True)
    
    def _apply_preset_style(self, preset_key):
        """Применение выбранного пресет-стиля"""
        # Сбрасываем настройки
        st.session_state.style_elements = [
            {'id': 1, 'name': 'Authors', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 2, 'name': 'Title', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '},
            {'id': 3, 'name': 'Journal', 'enabled': True, 'italic': True, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 4, 'name': 'Year', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 5, 'name': 'Volume', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '},
            {'id': 6, 'name': 'Issue', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': True, 'separator': ': '},
            {'id': 7, 'name': 'Pages', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '},
            {'id': 8, 'name': 'DOI', 'enabled': True, 'italic': False, 'bold': False, 'parentheses': False, 'separator': ''},
        ]
        
        # Применяем настройки в зависимости от стиля
        if preset_key == 'gost':
            st.session_state.author_format = 'Smith A.A'
            st.session_state.page_format = '122-128'
            st.session_state.doi_format = 'https://dx.doi.org/10.10/xxx'
            st.session_state.doi_hyperlink = True
            st.session_state.numbering_style = '1.'
            # Для ГОСТ меняем порядок и настройки
            st.session_state.style_elements[5]['enabled'] = True  # Issue
            st.session_state.style_elements[5]['parentheses'] = False
            st.session_state.style_elements[5]['separator'] = ', '
        
        elif preset_key == 'apa':
            st.session_state.author_format = 'Smith, A.A.'
            st.session_state.page_format = '122-128'
            st.session_state.doi_format = 'https://dx.doi.org/10.10/xxx'
            st.session_state.doi_hyperlink = True
            st.session_state.numbering_style = '1.'
        
        elif preset_key == 'acs':
            st.session_state.author_format = 'Smith, A.A.'
            st.session_state.page_format = '122–128'
            st.session_state.doi_format = '10.10/xxx'
            st.session_state.doi_hyperlink = True
            st.session_state.numbering_style = 'No numbering'
            st.session_state.style_elements[3]['italic'] = False  # Journal не курсив
            st.session_state.style_elements[3]['bold'] = True  # Journal жирный
        
        # Для других стилей аналогично...
    
    def _get_preset_preview(self, preset_key):
        """Получение текста предпросмотра для стиля"""
        previews = {
            'gost': 'Смит Дж.А., Доу А.Б. Название статьи // Название журнала. – 2023. – Т. 15, № 3. – С. 122-128. – https://doi.org/10.1000/xyz123',
            'apa': 'Smith, J. A., & Doe, A. B. (2023). Article title. Journal Name, 15(3), 122-128. https://doi.org/10.1000/xyz123',
            'vancouver': '1. Smith JA, Doe AB. Article title. J Name. 2023;15(3):122-8.',
            'ieee': '[1] J. A. Smith and A. B. Doe, "Article title," J. Name, vol. 15, no. 3, pp. 122-128, 2023.',
            'harvard': 'Smith, J.A. and Doe, A.B. (2023) "Article title", Journal Name, 15(3), pp. 122-128.',
            'acs': 'Smith, J. A.; Doe, A. B. Article Title. J. Name 2023, 15, 122-128. https://doi.org/10.1000/xyz123',
            'rsc': 'J. A. Smith and A. B. Doe, J. Name, 2023, 15, 122.',
            'chicago': 'Smith, John A., and Alice B. Doe. "Article Title." Journal Name 15, no. 3 (2023): 122-128.'
        }
        return previews.get(preset_key, 'Preview not available')
    
    def render_step_style_create(self):
        """Рендер шага создания стиля"""
        st.markdown(f"<h2>{get_text('create_style_title')}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: {Config.THEMES[st.session_state.current_theme]['textSecondary']}; margin-bottom: 1rem;'>{get_text('create_style_desc')}</p>", unsafe_allow_html=True)
        
        # Drag-and-drop для элементов
        st.markdown(f"<h3>{get_text('elements_title')}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: {Config.THEMES[st.session_state.current_theme]['textSecondary']}; margin-bottom: 1rem; font-size: 0.9rem;'>{get_text('drag_to_reorder')}</p>", unsafe_allow_html=True)
        
        # Создаем список элементов для drag-and-drop
        items = []
        for elem in st.session_state.style_elements:
            if elem['enabled']:
                status = "✓"
                style = "background-color: #10B98120; border-color: #10B981;"
            else:
                status = "○"
                style = ""
            
            # Создаем HTML для элемента
            controls_html = f"""
            <div style="display: flex; gap: 8px; align-items: center;">
                <span style="font-weight: bold; color: #3B82F6;">{status}</span>
                <span style="color: {'#EF4444' if elem['italic'] else '#6B7280'}">I</span>
                <span style="color: {'#EF4444' if elem['bold'] else '#6B7280'}">B</span>
                <span style="color: {'#EF4444' if elem['parentheses'] else '#6B7280'}">()</span>
                <span style="color: #6B7280; font-size: 0.8rem;">{elem['separator']}</span>
            </div>
            """
            
            items.append({
                'id': elem['id'],
                'content': f"""
                <div style="display: flex; justify-content: space-between; align-items: center; width: 100%; {style}">
                    <span>{get_text(f'element_{elem["name"].lower()}')}</span>
                    {controls_html}
                </div>
                """
            })

        # Простая альтернатива без drag-and-drop
        sorted_items = items
        
        # Добавляем селекты для изменения порядка
        st.markdown("**Change element order:**")
        for i, elem in enumerate(st.session_state.style_elements):
            if elem['enabled']:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"▪️ {get_text(f'element_{elem['name'].lower()}')}")
                with col2:
                    if st.button("↑", key=f"up_{elem['id']}", disabled=i==0):
                        # Переместить вверх
                        st.session_state.style_elements[i], st.session_state.style_elements[i-1] = st.session_state.style_elements[i-1], st.session_state.style_elements[i]
                        st.rerun()
                    if st.button("↓", key=f"down_{elem['id']}", disabled=i==len(st.session_state.style_elements)-1):
                        # Переместить вниз
                        st.session_state.style_elements[i], st.session_state.style_elements[i+1] = st.session_state.style_elements[i+1], st.session_state.style_elements[i]
                        st.rerun()
        
        # Обновляем порядок элементов
        if sorted_items:
            new_order = [item['id'] for item in sorted_items]
            # Сортируем элементы по новому порядку
            st.session_state.style_elements.sort(key=lambda x: new_order.index(x['id']))
        
        # Кнопки для добавления/удаления элементов
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("➕ Authors", use_container_width=True):
                self._toggle_element('Authors')
        
        with col2:
            if st.button("➕ Title", use_container_width=True):
                self._toggle_element('Title')
        
        with col3:
            if st.button("➕ Journal", use_container_width=True):
                self._toggle_element('Journal')
        
        with col4:
            if st.button("➕ Year", use_container_width=True):
                self._toggle_element('Year')
        
        col5, col6, col7, col8 = st.columns(4)
        
        with col5:
            if st.button("➕ Volume", use_container_width=True):
                self._toggle_element('Volume')
        
        with col6:
            if st.button("➕ Issue", use_container_width=True):
                self._toggle_element('Issue')
        
        with col7:
            if st.button("➕ Pages", use_container_width=True):
                self._toggle_element('Pages')
        
        with col8:
            if st.button("➕ DOI", use_container_width=True):
                self._toggle_element('DOI')
        
        # Настройки элемента
        st.markdown("---")
        st.markdown(f"<h3>{get_text('element_settings')}</h3>", unsafe_allow_html=True)
        
        # Выбор элемента для настройки
        enabled_elements = [elem for elem in st.session_state.style_elements if elem['enabled']]
        if enabled_elements:
            element_names = [get_text(f'element_{elem["name"].lower()}') for elem in enabled_elements]
            selected_element_name = st.selectbox(
                "Select element to configure:",
                element_names,
                key="element_selector"
            )
            
            # Находим выбранный элемент
            selected_element = None
            for elem in enabled_elements:
                if get_text(f'element_{elem["name"].lower()}') == selected_element_name:
                    selected_element = elem
                    break
            
            if selected_element:
                col_a, col_b, col_c = st.columns(3)
                
                with col_a:
                    italic = st.checkbox(
                        get_text('italic'),
                        value=selected_element['italic'],
                        key=f"italic_{selected_element['id']}"
                    )
                    selected_element['italic'] = italic
                
                with col_b:
                    bold = st.checkbox(
                        get_text('bold'),
                        value=selected_element['bold'],
                        key=f"bold_{selected_element['id']}"
                    )
                    selected_element['bold'] = bold
                
                with col_c:
                    parentheses = st.checkbox(
                        get_text('parentheses'),
                        value=selected_element['parentheses'],
                        key=f"parentheses_{selected_element['id']}"
                    )
                    selected_element['parentheses'] = parentheses
                
                # Разделитель
                separator = st.text_input(
                    get_text('separator'),
                    value=selected_element['separator'],
                    key=f"separator_{selected_element['id']}"
                )
                selected_element['separator'] = separator
        
        # Общие настройки
        st.markdown("---")
        st.markdown("<h3>General Settings</h3>", unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.session_state.author_format = st.selectbox(
                "Author format:",
                ["Smith, A.A.", "Smith AA", "AA Smith", "A.A. Smith", "Smith A.A"],
                index=["Smith, A.A.", "Smith AA", "AA Smith", "A.A. Smith", "Smith A.A"].index(st.session_state.author_format),
                key="author_format_select"
            )
            
            st.session_state.page_format = st.selectbox(
                "Page format:",
                ["122-128", "122–128", "122–8", "122 - 128"],
                index=["122-128", "122–128", "122–8", "122 - 128"].index(st.session_state.page_format),
                key="page_format_select"
            )
        
        with col2:
            st.session_state.doi_format = st.selectbox(
                "DOI format:",
                ["10.10/xxx", "doi:10.10/xxx", "https://dx.doi.org/10.10/xxx"],
                index=["10.10/xxx", "doi:10.10/xxx", "https://dx.doi.org/10.10/xxx"].index(st.session_state.doi_format),
                key="doi_format_select"
            )
            
            st.session_state.numbering_style = st.selectbox(
                "Numbering:",
                ["1.", "1", "1)", "(1)", "[1]", "No numbering"],
                index=["1.", "1", "1)", "(1)", "[1]", "No numbering"].index(st.session_state.numbering_style),
                key="numbering_select"
            )
            
            st.session_state.doi_hyperlink = st.checkbox(
                "DOI as hyperlink",
                value=st.session_state.doi_hyperlink,
                key="doi_hyperlink_check"
            )
        
        # Предпросмотр
        st.markdown("---")
        st.markdown(f"<h3>{get_text('style_preview')}</h3>", unsafe_allow_html=True)
        
        preview_text = self._generate_style_preview()
        st.markdown(f"""
            <div class="preview-box">
                {preview_text}
            </div>
        """, unsafe_allow_html=True)
        
        # Сохранение стиля
        st.markdown("---")
        st.markdown(f"<h3>{get_text('save_style_as')}</h3>", unsafe_allow_html=True)
        
        col_save1, col_save2 = st.columns([2, 1])
        
        with col_save1:
            st.session_state.style_name = st.text_input(
                get_text('style_name'),
                value=st.session_state.style_name,
                placeholder="Enter style name",
                key="style_name_input"
            )
        
        with col_save2:
            if st.button(get_text('save'), use_container_width=True, key="save_style_btn"):
                if st.session_state.style_name:
                    self._save_current_style()
                    st.success(get_text('style_saved'))
                else:
                    st.warning("Please enter a style name")
    
    def _toggle_element(self, element_name):
        """Включение/выключение элемента"""
        for elem in st.session_state.style_elements:
            if elem['name'] == element_name:
                elem['enabled'] = not elem['enabled']
                break
        st.rerun()
    
    def _generate_style_preview(self):
        """Генерация предпросмотра стиля"""
        enabled_elements = [elem for elem in st.session_state.style_elements if elem['enabled']]
        
        if not enabled_elements:
            return "No elements selected"
        
        # Создаем пример на основе выбранных элементов
        preview_parts = []
        
        for elem in enabled_elements:
            element_text = get_text(f'element_{elem["name"].lower()}')
            
            # Добавляем форматирование
            if elem['italic']:
                element_text = f"<i>{element_text}</i>"
            if elem['bold']:
                element_text = f"<b>{element_text}</b>"
            if elem['parentheses']:
                element_text = f"({element_text})"
            
            preview_parts.append(element_text)
        
        # Добавляем разделители
        preview = ""
        for i, part in enumerate(preview_parts):
            preview += part
            if i < len(enabled_elements) - 1:
                separator = enabled_elements[i]['separator']
                if separator:
                    preview += separator
        
        # Добавляем нумерацию
        if st.session_state.numbering_style != "No numbering":
            preview = f"1{st.session_state.numbering_style.replace('1', '')} {preview}"
        
        return preview
    
    def _save_current_style(self):
        """Сохранение текущего стиля"""
        style_config = {
            'name': st.session_state.style_name,
            'created_at': str(datetime.now()),
            'author_format': st.session_state.author_format,
            'page_format': st.session_state.page_format,
            'doi_format': st.session_state.doi_format,
            'doi_hyperlink': st.session_state.doi_hyperlink,
            'numbering_style': st.session_state.numbering_style,
            'elements': []
        }
        
        for elem in st.session_state.style_elements:
            if elem['enabled']:
                style_config['elements'].append({
                    'name': elem['name'],
                    'italic': elem['italic'],
                    'bold': elem['bold'],
                    'parentheses': elem['parentheses'],
                    'separator': elem['separator']
                })
        
        # Создаем JSON для скачивания
        json_data = json.dumps(style_config, indent=2, ensure_ascii=False)
        
        # Предлагаем скачать файл
        st.download_button(
            label="💾 Download Style",
            data=json_data,
            file_name=f"{st.session_state.style_name.replace(' ', '_')}.json",
            mime="application/json",
            key="download_style_btn"
        )
    
    def render_step_input(self):
        """Рендер шага ввода данных"""
        st.markdown(f"<h2>{get_text('input_title')}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: {Config.THEMES[st.session_state.current_theme]['textSecondary']}; margin-bottom: 2rem;'>{get_text('input_desc')}</p>", unsafe_allow_html=True)
        
        # Выбор метода ввода
        input_method = st.radio(
            "",
            [get_text('upload_docx'), get_text('paste_text'), get_text('enter_doi')],
            key="input_method_radio",
            horizontal=True
        )
        
        st.session_state.input_method = {
            get_text('upload_docx'): 'docx',
            get_text('paste_text'): 'text',
            get_text('enter_doi'): 'doi'
        }[input_method]
        
        # Контейнер для ввода
        if st.session_state.input_method == 'docx':
            uploaded_file = st.file_uploader(
                get_text('browse_files'),
                type=['docx'],
                key="docx_uploader_input"
            )
            
            if uploaded_file:
                st.session_state.uploaded_file = uploaded_file
                # Парсим DOCX для предпросмотра
                try:
                    doc = Document(uploaded_file)
                    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
                    if paragraphs:
                        st.info(f"Found {len(paragraphs)} paragraphs in document")
                        with st.expander("Preview first 5 references"):
                            for i, p in enumerate(paragraphs[:5]):
                                st.text(f"{i+1}. {p[:100]}...")
                except Exception as e:
                    st.error(f"Error reading DOCX: {str(e)}")
        
        elif st.session_state.input_method == 'text':
            st.session_state.input_text = st.text_area(
                "",
                value=st.session_state.input_text,
                placeholder=get_text('text_area_placeholder'),
                height=200,
                key="text_input_area"
            )
            
            if st.session_state.input_text:
                lines = [line.strip() for line in st.session_state.input_text.split('\n') if line.strip()]
                st.info(f"Found {len(lines)} references")
        
        else:  # DOI
            st.session_state.input_doi = st.text_area(
                "",
                value=st.session_state.input_doi,
                placeholder=get_text('doi_area_placeholder'),
                height=200,
                key="doi_input_area"
            )
            
            if st.session_state.input_doi:
                lines = [line.strip() for line in st.session_state.input_doi.split('\n') if line.strip()]
                st.info(f"Found {len(lines)} DOI entries")
        
        # Кнопка очистки
        if st.button(get_text('clear_input'), use_container_width=True, key="clear_input_btn"):
            st.session_state.uploaded_file = None
            st.session_state.input_text = ''
            st.session_state.input_doi = ''
            st.rerun()
    
    def render_step_process(self):
        """Рендер шага обработки"""
        st.markdown(f"<h2>{get_text('process_title')}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: {Config.THEMES[st.session_state.current_theme]['textSecondary']}; margin-bottom: 2rem;'>{get_text('process_desc')}</p>", unsafe_allow_html=True)
        
        # Проверяем, есть ли данные для обработки
        has_data = False
        if st.session_state.input_method == 'docx' and st.session_state.uploaded_file:
            has_data = True
        elif st.session_state.input_method == 'text' and st.session_state.input_text.strip():
            has_data = True
        elif st.session_state.input_method == 'doi' and st.session_state.input_doi.strip():
            has_data = True
        
        if not has_data:
            st.warning(get_text('no_references'))
            return
        
        # Выбор формата вывода
        st.markdown(f"**{get_text('output_format')}**")
        output_format = st.radio(
            "",
            [get_text('format_docx'), get_text('format_txt'), get_text('format_bibtex'), get_text('format_ris')],
            key="output_format_radio",
            horizontal=True
        )
        
        st.session_state.output_format = {
            get_text('format_docx'): 'docx',
            get_text('format_txt'): 'txt',
            get_text('format_bibtex'): 'bibtex',
            get_text('format_ris'): 'ris'
        }[output_format]
        
        # Дополнительные опции
        st.markdown(f"**{get_text('additional_options')}**")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.session_state.number_references = st.checkbox(
                get_text('number_references'),
                value=st.session_state.number_references,
                key="number_refs_check"
            )
        
        with col2:
            st.session_state.highlight_duplicates = st.checkbox(
                get_text('highlight_duplicates'),
                value=st.session_state.highlight_duplicates,
                key="highlight_dups_check"
            )
        
        with col3:
            st.session_state.add_statistics = st.checkbox(
                get_text('add_statistics'),
                value=st.session_state.add_statistics,
                key="add_stats_check"
            )
        
        # Кнопка обработки
        st.markdown("---")
        if st.button(get_text('process_button'), use_container_width=True, key="process_btn_main"):
            # Собираем ссылки
            references = self._collect_references()
            
            if references:
                # Создаем конфиг стиля
                style_config = self._create_style_config()
                
                # Обрабатываем ссылки
                with st.spinner(get_text('processing')):
                    try:
                        processor = ReferenceProcessor()
                        progress_container = st.empty()
                        status_container = st.empty()
                        
                        formatted_refs, txt_buffer, doi_found, doi_not_found, duplicates_info = processor.process_references(
                            references, style_config, progress_container, status_container
                        )
                        
                        # Генерируем статистику
                        statistics = generate_statistics(formatted_refs)
                        
                        # Генерируем документ
                        if st.session_state.output_format == 'docx':
                            doc_buffer = DocumentGenerator.generate_document(
                                formatted_refs, statistics, style_config, duplicates_info
                            )
                        else:
                            doc_buffer = io.BytesIO()
                        
                        # Сохраняем результаты
                        st.session_state.processed_results = {
                            'formatted_refs': formatted_refs,
                            'txt_buffer': txt_buffer,
                            'doc_buffer': doc_buffer,
                            'statistics': statistics,
                            'doi_found': doi_found,
                            'doi_not_found': doi_not_found,
                            'total': len(references)
                        }
                        
                        # Переходим к результатам
                        st.session_state.current_step = 4
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"{get_text('error')}: {str(e)}")
            else:
                st.warning(get_text('no_references'))
    
    def _collect_references(self):
        """Сбор ссылок из выбранного источника"""
        references = []
        
        if st.session_state.input_method == 'docx' and st.session_state.uploaded_file:
            try:
                doc = Document(st.session_state.uploaded_file)
                references = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            except Exception as e:
                st.error(f"Error reading DOCX: {str(e)}")
        
        elif st.session_state.input_method == 'text' and st.session_state.input_text.strip():
            references = [line.strip() for line in st.session_state.input_text.split('\n') if line.strip()]
        
        elif st.session_state.input_method == 'doi' and st.session_state.input_doi.strip():
            references = [line.strip() for line in st.session_state.input_doi.split('\n') if line.strip()]
        
        return references
    
    def _create_style_config(self):
        """Создание конфигурации стиля для обработки"""
        # Собираем элементы
        elements = []
        for elem in st.session_state.style_elements:
            if elem['enabled']:
                elements.append((
                    elem['name'],
                    {
                        'italic': elem['italic'],
                        'bold': elem['bold'],
                        'parentheses': elem['parentheses'],
                        'separator': elem['separator']
                    }
                ))
        
        # Создаем конфиг
        style_config = {
            'author_format': st.session_state.author_format,
            'author_separator': ', ',
            'et_al_limit': None,
            'use_and_bool': False,
            'use_ampersand_bool': False,
            'doi_format': st.session_state.doi_format,
            'doi_hyperlink': st.session_state.doi_hyperlink,
            'page_format': st.session_state.page_format,
            'final_punctuation': '',
            'numbering_style': st.session_state.numbering_style,
            'journal_style': '{Full Journal Name}',
            'elements': elements,
            'gost_style': False,
            'acs_style': False,
            'rsc_style': False,
            'cta_style': False
        }
        
        return style_config
    
    def render_step_output(self):
        """Рендер шага результатов"""
        if not st.session_state.processed_results:
            st.warning("No results to display")
            return
        
        results = st.session_state.processed_results
        
        st.markdown(f"<h2>{get_text('results_title')}</h2>", unsafe_allow_html=True)
        
        # Статистика
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"""
                <div style="text-align: center; padding: 1rem; background-color: #3B82F610; border-radius: 12px;">
                    <div style="font-size: 2rem; font-weight: bold; color: #3B82F6;">{results['total']}</div>
                    <div style="color: #6B7280; font-size: 0.9rem;">{get_text('processed_count')}</div>
                </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
                <div style="text-align: center; padding: 1rem; background-color: #10B98110; border-radius: 12px;">
                    <div style="font-size: 2rem; font-weight: bold; color: #10B981;">{results['doi_found']}</div>
                    <div style="color: #6B7280; font-size: 0.9rem;">{get_text('doi_found')}</div>
                </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
                <div style="text-align: center; padding: 1rem; background-color: #F59E0B10; border-radius: 12px;">
                    <div style="font-size: 2rem; font-weight: bold; color: #F59E0B;">{results['doi_not_found']}</div>
                    <div style="color: #6B7280; font-size: 0.9rem;">{get_text('needs_check')}</div>
                </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Загрузка результатов
        st.markdown(f"<h3>{get_text('download_section')}</h3>", unsafe_allow_html=True)
        
        col_dl1, col_dl2 = st.columns(2)
        
        with col_dl1:
            # Форматированные ссылки
            if results['doc_buffer']:
                st.download_button(
                    label=get_text('download_formatted'),
                    data=results['doc_buffer'].getvalue(),
                    file_name="formatted_references.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    key="download_docx"
                )
            
            # Список DOI
            if results['txt_buffer']:
                st.download_button(
                    label=get_text('download_doi_list'),
                    data=results['txt_buffer'].getvalue(),
                    file_name="doi_list.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key="download_txt"
                )
        
        with col_dl2:
            # Сохранение стиля
            if st.button(get_text('download_style'), use_container_width=True, key="save_style_results"):
                style_config = self._create_style_config()
                style_data = {
                    'name': st.session_state.style_name or 'My Citation Style',
                    'created_at': str(datetime.now()),
                    'style_config': style_config
                }
                json_data = json.dumps(style_data, indent=2, ensure_ascii=False)
                
                st.download_button(
                    label="💾 Download Now",
                    data=json_data,
                    file_name=f"{style_data['name'].replace(' ', '_')}.json",
                    mime="application/json",
                    key="download_style_now"
                )
        
        st.markdown("---")
        
        # Действия
        col_act1, col_act2 = st.columns(2)
        
        with col_act1:
            if st.button(get_text('new_document'), use_container_width=True, key="new_doc_btn"):
                # Очищаем только данные ввода
                st.session_state.uploaded_file = None
                st.session_state.input_text = ''
                st.session_state.input_doi = ''
                st.session_state.processed_results = None
                st.session_state.current_step = 3  # Возвращаемся к вводу
                st.rerun()
        
        with col_act2:
            if st.button(get_text('edit_style'), use_container_width=True, key="edit_style_btn"):
                st.session_state.current_step = 2  # Возвращаемся к редактированию стиля
                st.rerun()

# Основной класс приложения с новым интерфейсом
class ModernCitationStyleApp:
    """Современное приложение с пошаговым интерфейсом"""
    
    def __init__(self):
        self.ui = ModernUIComponents()
        init_session_state()
    
    def run(self):
        """Запуск приложения"""
        st.set_page_config(
            page_title=get_text('app_title'),
            page_icon="🎨",
            layout="wide"
        )
        
        # Применяем стили темы
        self.ui.apply_theme_styles()
        
        # Рендер заголовка
        self.ui.render_header()
        
        # Рендер индикатора шагов
        self.ui.render_step_indicator()
        
        # Рендер текущего шага
        self._render_current_step()
        
        # Рендер кнопок навигации
        self.ui.render_navigation_buttons()
    
    def _render_current_step(self):
        """Рендер текущего шага"""
        if st.session_state.current_step == 0:
            self.ui.render_step_start()
        elif st.session_state.current_step == 1:
            self.ui.render_step_style_select()
        elif st.session_state.current_step == 2:
            self.ui.render_step_style_create()
        elif st.session_state.current_step == 3:
            self.ui.render_step_input()
        elif st.session_state.current_step == 4:
            self.ui.render_step_process()
        elif st.session_state.current_step == 5:
            self.ui.render_step_output()

# Совместимость со старым кодом
def get_style_config_for_compatibility():
    """Получение конфигурации стиля для совместимости со старым кодом"""
    element_configs = []
    used_elements = set()
    
    for i in range(8):
        element = st.session_state[f"el{i}"]
        if element and element not in used_elements:
            element_configs.append((
                element, 
                {
                    'italic': st.session_state[f"it{i}"],
                    'bold': st.session_state[f"bd{i}"],
                    'parentheses': st.session_state[f"pr{i}"],
                    'separator': st.session_state[f"sp{i}"]
                }
            ))
            used_elements.add(element)
    
    return {
        'author_format': st.session_state.auth,
        'author_separator': st.session_state.sep,
        'et_al_limit': st.session_state.etal if st.session_state.etal > 0 else None,
        'use_and_bool': st.session_state.use_and_checkbox,
        'use_ampersand_bool': st.session_state.use_ampersand_checkbox,
        'doi_format': st.session_state.doi,
        'doi_hyperlink': st.session_state.doilink,
        'page_format': st.session_state.page,
        'final_punctuation': st.session_state.punct,
        'numbering_style': st.session_state.num,
        'journal_style': st.session_state.journal_style,
        'elements': element_configs,
        'gost_style': st.session_state.get('gost_style', False),
        'acs_style': st.session_state.get('acs_style', False),
        'rsc_style': st.session_state.get('rsc_style', False),
        'cta_style': st.session_state.get('cta_style', False)
    }

# Вспомогательные функции (сохранены для совместимости)
def clean_text(text):
    return DOIProcessor()._clean_text(text)

def normalize_name(name):
    return DOIProcessor()._normalize_name(name)

def is_section_header(text):
    return DOIProcessor()._is_section_header(text)

def find_doi(reference):
    return DOIProcessor().find_doi_enhanced(reference)

def normalize_doi(doi):
    processor = ReferenceProcessor()
    return processor._normalize_doi(doi)

def generate_reference_hash(metadata):
    processor = ReferenceProcessor()
    return processor._generate_reference_hash(metadata)

def extract_metadata_batch(doi_list, progress_callback=None):
    processor = ReferenceProcessor()
    return [processor.doi_processor.extract_metadata_with_cache(doi) for doi in doi_list]

def extract_metadata_sync(doi):
    processor = ReferenceProcessor()
    return processor.doi_processor.extract_metadata_with_cache(doi)

def format_reference(metadata, style_config, for_preview=False):
    formatter = CitationFormatterFactory.create_formatter(style_config)
    return formatter.format_reference(metadata, for_preview)

def find_duplicate_references(formatted_refs):
    processor = ReferenceProcessor()
    return processor._find_duplicates(formatted_refs)

def generate_statistics(formatted_refs):
    journals = []
    years = []
    authors = []
    
    current_year = datetime.now().year
    
    for _, _, metadata in formatted_refs:
        if not metadata:
            continue
            
        if metadata.get('journal'):
            journals.append(metadata['journal'])
        
        if metadata.get('year'):
            years.append(metadata['year'])
        
        if metadata.get('authors'):
            for author in metadata['authors']:
                given = author.get('given', '')
                family = author.get('family', '')
                if family:
                    first_initial = given[0] if given else ''
                    author_formatted = f"{family} {first_initial}." if first_initial else family
                    authors.append(author_formatted)
    
    unique_dois = set()
    for _, _, metadata in formatted_refs:
        if metadata and metadata.get('doi'):
            unique_dois.add(metadata['doi'])
    
    total_unique_dois = len(unique_dois)
    
    journal_counter = Counter(journals)
    journal_stats = []
    for journal, count in journal_counter.most_common(20):
        percentage = (count / total_unique_dois) * 100 if total_unique_dois > 0 else 0
        journal_stats.append({
            'journal': journal,
            'count': count,
            'percentage': round(percentage, 2)
        })
    
    year_counter = Counter(years)
    year_stats = []
    for year in range(current_year, 2009, -1):
        if year in year_counter:
            count = year_counter[year]
            percentage = (count / total_unique_dois) * 100 if total_unique_dois > 0 else 0
            year_stats.append({
                'year': year,
                'count': count,
                'percentage': round(percentage, 2)
            })
    
    recent_years = [current_year - i for i in range(4)]
    recent_count = sum(year_counter.get(year, 0) for year in recent_years)
    recent_percentage = (recent_count / total_unique_dois) * 100 if total_unique_dois > 0 else 0
    needs_more_recent_references = recent_percentage < 20
    
    author_counter = Counter(authors)
    author_stats = []
    for author, count in author_counter.most_common(20):
        percentage = (count / total_unique_dois) * 100 if total_unique_dois > 0 else 0
        author_stats.append({
            'author': author,
            'count': count,
            'percentage': round(percentage, 2)
        })
    
    has_frequent_author = any(stats['percentage'] > 30 for stats in author_stats)
    
    return {
        'journal_stats': journal_stats,
        'year_stats': year_stats,
        'author_stats': author_stats,
        'total_unique_dois': total_unique_dois,
        'needs_more_recent_references': needs_more_recent_references,
        'has_frequent_author': has_frequent_author
    }

def process_references_with_progress(references, style_config, progress_container, status_container):
    processor = ReferenceProcessor()
    return processor.process_references(references, style_config, progress_container, status_container)

def process_docx(input_file, style_config, progress_container, status_container):
    processor = ReferenceProcessor()
    doc = Document(input_file)
    references = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
    return processor.process_references(references, style_config, progress_container, status_container)

def export_style(style_config, file_name):
    export_data = {
        'version': '2.0',
        'export_date': str(datetime.now()),
        'style_config': style_config
    }
    json_data = json.dumps(export_data, indent=2, ensure_ascii=False)
    return json_data.encode('utf-8')

def import_style(uploaded_file):
    try:
        content = uploaded_file.read().decode('utf-8')
        import_data = json.loads(content)
        
        if 'style_config' in import_data:
            return import_data['style_config']
        elif 'version' in import_data:
            return import_data.get('style_config', import_data)
        else:
            return import_data
            
    except Exception as e:
        logger.error(f"Style import error: {e}")
        return None

def apply_imported_style(imported_style):
    """Функция для применения импортированного стиля (для обратной совместимости)"""
    app = ModernCitationStyleApp()
    # Эта функция будет реализована при необходимости
    pass

def main():
    """Основная функция"""
    app = ModernCitationStyleApp()
    app.run()

if __name__ == "__main__":
    main()


