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
    
    # Настройки тем (обновленные для лучшего контраста)
    THEMES = {
        'light': {
            'primary': '#1f77b4',
            'background': '#f8f9fa',
            'secondaryBackground': '#ffffff',
            'text': '#212529',
            'font': 'sans-serif',
            'border': '#dee2e6',
            'cardBackground': '#ffffff',
            'accent': '#4ECDC4',
            'toolbar': '#e9ecef',
            'success': '#28a745',
            'warning': '#ffc107',
            'danger': '#dc3545',
            'info': '#17a2b8'
        },
        'dark': {
            'primary': '#4ECDC4',
            'background': '#1a1d23',
            'secondaryBackground': '#2d323d',
            'text': '#e9ecef',
            'font': 'sans-serif',
            'border': '#495057',
            'cardBackground': '#2d323d',
            'accent': '#FF6B6B',
            'toolbar': '#343a40',
            'success': '#28a745',
            'warning': '#ffc107',
            'danger': '#dc3545',
            'info': '#17a2b8'
        },
        'lab': {
            'primary': '#00d4aa',
            'background': '#0d1117',
            'secondaryBackground': '#161b22',
            'text': '#c9d1d9',
            'font': 'monospace, "Courier New"',
            'border': '#30363d',
            'cardBackground': '#161b22',
            'accent': '#ff7b72',
            'toolbar': '#21262d',
            'success': '#3fb950',
            'warning': '#d29922',
            'danger': '#f85149',
            'info': '#79c0ff'
        },
        'library': {
            'primary': '#8b4513',
            'background': '#f5f1e8',
            'secondaryBackground': '#fffef7',
            'text': '#2c1810',
            'font': '"Georgia", "Times New Roman", serif',
            'border': '#d4b59e',
            'cardBackground': '#fffef7',
            'accent': '#2e8b57',
            'toolbar': '#e8dfd0',
            'success': '#2e8b57',
            'warning': '#daa520',
            'danger': '#8b0000',
            'info': '#4682b4'
        }
    }
    
    # Интерфейсные константы
    UI_MODES = ['wizard_mode', 'expert_mode']
    UI_MODE_NAMES = {
        'en': {
            'wizard_mode': 'Wizard Mode',
            'expert_mode': 'Expert Mode'
        },
        'ru': {
            'wizard_mode': 'Режим мастера',
            'expert_mode': 'Экспертный режим'
        }
    }

# Инициализация Crossref
works = Works()

# Полный словарь переводов (только русский и английский)
TRANSLATIONS = {
    'en': {
        # Основные
        'header': '🎓 Citation Style Constructor',
        'quick_start': '🚀 Quick Start',
        'style_designer': '🎨 Style Designer',
        'reference_processor': '⚙️ Reference Processor',
        'results_exporter': '📤 Results Exporter',
        
        # Быстрый старт
        'i_have_docx': 'I have a DOCX file',
        'i_have_list': 'I have a reference list',
        'i_want_design': 'I want to design a style',
        'drag_drop_docx': 'Drag & drop DOCX file',
        'or': 'or',
        'browse': 'Browse',
        'paste_references': 'Paste references (one per line)',
        'start_processing': 'Start Processing',
        
        # Шаги мастера
        'step_1': 'Step 1: Choose or Create Style',
        'step_2': 'Step 2: Upload References',
        'step_3': 'Step 3: Export Results',
        'next_step': 'Next Step',
        'prev_step': 'Previous Step',
        'finish': 'Finish',
        
        # Стили
        'style_presets': 'Style Presets',
        'create_custom_style': 'Create Custom Style',
        'gost_style': 'GOST',
        'acs_style': 'ACS (MDPI)',
        'rsc_style': 'RSC',
        'cta_style': 'CTA',
        'style_preset_tooltip': 'Ready-to-use citation styles',
        
        # Конструктор стилей
        'drag_elements_here': 'Drag elements here',
        'available_elements': 'Available Elements',
        'element_settings': 'Element Settings',
        'preview_panel': 'Live Preview',
        'add_element': '+ Add Element',
        'remove_element': 'Remove',
        'move_up': 'Move Up',
        'move_down': 'Move Down',
        
        # Элементы с иконками
        'authors': '👥 Authors',
        'title': '📖 Title',
        'journal': '🏢 Journal',
        'year': '📅 Year',
        'volume': '📚 Volume',
        'issue': '🔢 Issue',
        'pages': '📄 Pages',
        'doi': '🔗 DOI',
        
        # Настройки
        'general_settings': 'General Settings',
        'numbering_style': 'Numbering:',
        'author_format': 'Authors format:',
        'author_separator': 'Separator:',
        'et_al_limit': 'Et al after:',
        'use_and': "'and' before last author",
        'use_ampersand': "'&' before last author",
        'doi_format': 'DOI format:',
        'doi_hyperlink': 'DOI as hyperlink',
        'page_format': 'Pages format:',
        'final_punctuation': 'Final punctuation:',
        'journal_style': 'Journal style:',
        'full_journal_name': 'Full Journal Name',
        'journal_abbr_with_dots': 'J. Abbr.',
        'journal_abbr_no_dots': 'J Abbr',
        
        # Форматирование
        'italic': 'Italic',
        'bold': 'Bold',
        'parentheses': 'Parentheses',
        'separator': 'Separator',
        
        # Обработка
        'processing': 'Processing...',
        'found_references': 'Found {} references',
        'doi_found': '{} DOI found',
        'doi_not_found': '{} DOI not found',
        'duplicates_detected': '{} duplicates detected',
        
        # Результаты
        'formatted_references': 'Formatted References',
        'export_options': 'Export Options',
        'recommended': 'Recommended',
        'copy_to_clipboard': 'Copy to Clipboard',
        'download_txt': 'Download TXT',
        'download_docx': 'Download DOCX',
        'with_statistics': 'With statistics',
        'with_formatting': 'With formatting',
        
        # Статистика
        'statistics': '📊 Statistics',
        'reference_analysis': 'Reference Analysis',
        'year_distribution': 'Year Distribution',
        'journal_distribution': 'Journal Distribution',
        'author_frequency': 'Author Frequency',
        'recent_references': 'Recent references (<5 years): {}%',
        'top_journals': 'Top 3 journals: {}',
        'frequent_authors': 'Frequent authors (>30%): {}',
        
        # Подсказки
        'tip_style_selection': '💡 Tip: For most chemistry journals, use ACS style',
        'tip_doi_check': '💡 Tip: {} references need DOI verification',
        'tip_recent_papers': '💡 Tip: Consider adding more recent references (last 3-4 years)',
        'tip_duplicate_authors': '💡 Tip: High author concentration - diversify your sources',
        
        # Управление
        'save_style': '💾 Save Style',
        'load_style': '📂 Load Style',
        'reset_style': '🔄 Reset Style',
        'clear_all': '🗑️ Clear All',
        
        # Тема
        'theme': 'Theme:',
        'light_theme': 'Light',
        'dark_theme': 'Dark',
        'lab_theme': 'Lab',
        'library_theme': 'Library',
        
        # Язык
        'language': 'Language:',
        'english': 'English',
        'russian': 'Russian',
        
        # Мода
        'simple_mode': 'Simple Mode',
        'expert_mode': 'Expert Mode',
        
        # Новые для экспертного режима
        'two_panel_view': 'Two-Panel View',
        'style_constructor': 'Style Constructor',
        'results_view': 'Results View',
        'quick_actions': 'Quick Actions',
        'batch_processing': 'Batch Processing',
        'advanced_settings': 'Advanced Settings',
        
        # Сообщения
        'upload_file_first': 'Please upload a file first',
        'select_style_first': 'Please select a style first',
        'processing_complete': 'Processing complete!',
        'style_saved': 'Style saved successfully',
        'style_loaded': 'Style loaded successfully',
        'clipboard_copied': 'Copied to clipboard',
        
        # Руководство
        'short_guide': 'Quick Guide',
        'guide_step1': '1. Choose a style or create your own',
        'guide_step2': '2. Upload references (DOCX or text)',
        'guide_step3': '3. Export formatted references',
        'guide_note': 'DOCX export preserves formatting and includes statistics',
        
        # Валидация
        'validation_error': 'Error: {}',
        'validation_warning': 'Warning: {}',
        'no_references': 'No references found',
        'too_many_references': 'Too many references (max {})',
    },
    'ru': {
        # Основные
        'header': '🎓 Конструктор стилей цитирования',
        'quick_start': '🚀 Быстрый старт',
        'style_designer': '🎨 Конструктор стилей',
        'reference_processor': '⚙️ Обработчик ссылок',
        'results_exporter': '📤 Экспорт результатов',
        
        # Быстрый старт
        'i_have_docx': 'У меня есть DOCX файл',
        'i_have_list': 'У меня есть список ссылок',
        'i_want_design': 'Хочу создать стиль',
        'drag_drop_docx': 'Перетащите DOCX файл',
        'or': 'или',
        'browse': 'Выбрать файл',
        'paste_references': 'Вставьте ссылки (по одной на строку)',
        'start_processing': 'Начать обработку',
        
        # Шаги мастера
        'step_1': 'Шаг 1: Выберите или создайте стиль',
        'step_2': 'Шаг 2: Загрузите ссылки',
        'step_3': 'Шаг 3: Экспортируйте результаты',
        'next_step': 'Следующий шаг',
        'prev_step': 'Предыдущий шаг',
        'finish': 'Завершить',
        
        # Стили
        'style_presets': 'Готовые стили',
        'create_custom_style': 'Создать свой стиль',
        'gost_style': 'ГОСТ',
        'acs_style': 'ACS (MDPI)',
        'rsc_style': 'RSC',
        'cta_style': 'CTA',
        'style_preset_tooltip': 'Готовые стили цитирования',
        
        # Конструктор стилей
        'drag_elements_here': 'Перетащите элементы сюда',
        'available_elements': 'Доступные элементы',
        'element_settings': 'Настройки элемента',
        'preview_panel': 'Живой предпросмотр',
        'add_element': '+ Добавить элемент',
        'remove_element': 'Удалить',
        'move_up': 'Вверх',
        'move_down': 'Вниз',
        
        # Элементы с иконками
        'authors': '👥 Авторы',
        'title': '📖 Название',
        'journal': '🏢 Журнал',
        'year': '📅 Год',
        'volume': '📚 Том',
        'issue': '🔢 Выпуск',
        'pages': '📄 Страницы',
        'doi': '🔗 DOI',
        
        # Настройки
        'general_settings': 'Общие настройки',
        'numbering_style': 'Нумерация:',
        'author_format': 'Формат авторов:',
        'author_separator': 'Разделитель:',
        'et_al_limit': 'Et al после:',
        'use_and': "'и' перед последним автором",
        'use_ampersand': "'&' перед последним автором",
        'doi_format': 'Формат DOI:',
        'doi_hyperlink': 'DOI как ссылка',
        'page_format': 'Формат страниц:',
        'final_punctuation': 'Конечная пунктуация:',
        'journal_style': 'Стиль журнала:',
        'full_journal_name': 'Полное название',
        'journal_abbr_with_dots': 'J. Abbr.',
        'journal_abbr_no_dots': 'J Abbr',
        
        # Форматирование
        'italic': 'Курсив',
        'bold': 'Жирный',
        'parentheses': 'Скобки',
        'separator': 'Разделитель',
        
        # Обработка
        'processing': 'Обработка...',
        'found_references': 'Найдено {} ссылок',
        'doi_found': 'Найдено {} DOI',
        'doi_not_found': 'Не найдено {} DOI',
        'duplicates_detected': 'Обнаружено {} дубликатов',
        
        # Результаты
        'formatted_references': 'Отформатированные ссылки',
        'export_options': 'Опции экспорта',
        'recommended': 'Рекомендуется',
        'copy_to_clipboard': 'Копировать',
        'download_txt': 'Скачать TXT',
        'download_docx': 'Скачать DOCX',
        'with_statistics': 'Со статистикой',
        'with_formatting': 'С форматированием',
        
        # Статистика
        'statistics': '📊 Статистика',
        'reference_analysis': 'Анализ ссылок',
        'year_distribution': 'Распределение по годам',
        'journal_distribution': 'Распределение по журналам',
        'author_frequency': 'Частота авторов',
        'recent_references': 'Свежие ссылки (<5 лет): {}%',
        'top_journals': 'Топ-3 журнала: {}',
        'frequent_authors': 'Частые авторы (>30%): {}',
        
        # Подсказки
        'tip_style_selection': '💡 Совет: Для химических журналов используйте стиль ACS',
        'tip_doi_check': '💡 Совет: {} ссылок требуют проверки DOI',
        'tip_recent_papers': '💡 Совет: Добавьте больше свежих ссылок (последние 3-4 года)',
        'tip_duplicate_authors': '💡 Совет: Высокая концентрация авторов - разнообразьте источники',
        
        # Управление
        'save_style': '💾 Сохранить стиль',
        'load_style': '📂 Загрузить стиль',
        'reset_style': '🔄 Сбросить стиль',
        'clear_all': '🗑️ Очистить всё',
        
        # Тема
        'theme': 'Тема:',
        'light_theme': 'Светлая',
        'dark_theme': 'Тёмная',
        'lab_theme': 'Лаборатория',
        'library_theme': 'Библиотека',
        
        # Язык
        'language': 'Язык:',
        'english': 'Английский',
        'russian': 'Русский',
        
        # Мода
        'simple_mode': 'Простой режим',
        'expert_mode': 'Экспертный режим',
        
        # Новые для экспертного режима
        'two_panel_view': 'Двухпанельный вид',
        'style_constructor': 'Конструктор стилей',
        'results_view': 'Просмотр результатов',
        'quick_actions': 'Быстрые действия',
        'batch_processing': 'Пакетная обработка',
        'advanced_settings': 'Расширенные настройки',
        
        # Сообщения
        'upload_file_first': 'Сначала загрузите файл',
        'select_style_first': 'Сначала выберите стиль',
        'processing_complete': 'Обработка завершена!',
        'style_saved': 'Стиль сохранен успешно',
        'style_loaded': 'Стиль загружен успешно',
        'clipboard_copied': 'Скопировано в буфер',
        
        # Руководство
        'short_guide': 'Краткое руководство',
        'guide_step1': '1. Выберите стиль или создайте свой',
        'guide_step2': '2. Загрузите ссылки (DOCX или текст)',
        'guide_step3': '3. Экспортируйте отформатированные ссылки',
        'guide_note': 'Экспорт DOCX сохраняет форматирование и включает статистику',
        
        # Валидация
        'validation_error': 'Ошибка: {}',
        'validation_warning': 'Предупреждение: {}',
        'no_references': 'Ссылки не найдены',
        'too_many_references': 'Слишком много ссылок (макс. {})',
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
                    ui_mode TEXT DEFAULT 'wizard_mode',
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
                    'SELECT language, theme, ui_mode FROM user_preferences WHERE ip_address = ?',
                    (ip,)
                ).fetchone()
                
                if result:
                    return {
                        'language': result[0],
                        'theme': result[1],
                        'ui_mode': result[2] if result[2] else 'wizard_mode'
                    }
        except Exception as e:
            logger.error(f"Error getting preferences for {ip}: {e}")
        
        return {
            'language': 'en',
            'theme': 'light',
            'ui_mode': 'wizard_mode'
        }
    
    def save_preferences(self, ip: str, preferences: Dict[str, Any]):
        """Сохранение предпочтений пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO user_preferences 
                    (ip_address, language, theme, ui_mode, updated_at) 
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    ip,
                    preferences.get('language', 'en'),
                    preferences.get('theme', 'light'),
                    preferences.get('ui_mode', 'wizard_mode')
                ))
        except Exception as e:
            logger.error(f"Error saving preferences for {ip}: {e}")

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
        'current_language': 'en',
        'current_theme': 'light',
        'ui_mode': 'wizard_mode',
        'imported_style': None,
        'style_applied': False,
        'apply_imported_style': False,
        'output_text_value': "",
        'show_results': False,
        'download_data': {},
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
        'user_prefs_loaded': False,
        'file_processing_complete': False,
        'style_import_processed': False,
        'last_imported_file_hash': None,
        'style_management_initialized': False,
        'previous_states': [],
        'max_undo_steps': 10,
        'show_stats': False,
        'style_elements': [],
        'dragged_element': None,
        'active_element_index': -1,
        'process_triggered': False,
        'process_data': {},
        'current_step': 1,
        'uploaded_file': None,
        'references_input': '',
        'selected_preset': None,
        'show_quick_start': True,
        'show_style_designer': False,
        'processing_complete': False,
        'formatted_results': None,
        'statistics_data': None,
        'duplicates_info': None,
    }
    
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default
    
    # Инициализация элементов конфигурации (для обратной совместимости)
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
                    abbreviated = abbreviated[0].upper() + abbreviated[1:].lower()
                
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

# UI компоненты - ПОЛНОСТЬЮ ПЕРЕРАБОТАННЫЕ
class ModernUIComponents:
    """Современные компоненты пользовательского интерфейса"""
    
    def __init__(self):
        self.user_prefs = UserPreferencesManager()
        self.processor = ReferenceProcessor()
    
    def apply_theme_styles(self):
        """Применение стилей темы"""
        theme = Config.THEMES[st.session_state.current_theme]
        
        st.markdown(f"""
            <style>
            /* Основные стили */
            .block-container {{
                padding: 0.5rem 1rem;
                background-color: {theme['background']};
                color: {theme['text']};
                font-family: {theme['font']};
            }}
            
            /* Заголовки */
            h1, h2, h3, h4, h5, h6 {{
                color: {theme['primary']} !important;
            }}
            
            h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; font-weight: 700; }}
            h2 {{ font-size: 1.4rem; margin-bottom: 0.5rem; font-weight: 600; }}
            h3 {{ font-size: 1.2rem; margin-bottom: 0.5rem; font-weight: 600; }}
            
            /* Карточки */
            .card {{
                background-color: {theme['cardBackground']};
                border: 1px solid {theme['border']};
                border-radius: 10px;
                padding: 1.5rem;
                margin-bottom: 1.5rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                transition: all 0.3s ease;
            }}
            
            .card:hover {{
                box-shadow: 0 4px 16px rgba(0,0,0,0.1);
                transform: translateY(-2px);
            }}
            
            .card-header {{
                font-size: 1.1rem;
                font-weight: 600;
                color: {theme['primary']};
                margin-bottom: 1rem;
                padding-bottom: 0.5rem;
                border-bottom: 2px solid {theme['primary']}20;
            }}
            
            /* Кнопки быстрого старта */
            .quick-start-btn {{
                background-color: {theme['cardBackground']};
                border: 2px solid {theme['border']};
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                height: 100%;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                min-height: 180px;
            }}
            
            .quick-start-btn:hover {{
                background-color: {theme['primary']}10;
                border-color: {theme['primary']};
                transform: translateY(-3px);
            }}
            
            .quick-start-btn.active {{
                background-color: {theme['primary']}20;
                border-color: {theme['primary']};
                box-shadow: 0 4px 12px {theme['primary']}30;
            }}
            
            .quick-start-icon {{
                font-size: 2.5rem;
                margin-bottom: 0.8rem;
            }}
            
            .quick-start-title {{
                font-size: 1.2rem;
                font-weight: 600;
                margin-bottom: 0.5rem;
                color: {theme['text']};
            }}
            
            .quick-start-desc {{
                font-size: 0.9rem;
                color: {theme['text']}90;
                line-height: 1.4;
            }}
            
            /* Стили для пресетов стилей */
            .style-preset {{
                background-color: {theme['cardBackground']};
                border: 2px solid {theme['border']};
                border-radius: 10px;
                padding: 1.2rem;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                min-height: 120px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }}
            
            .style-preset:hover {{
                border-color: {theme['primary']};
                transform: translateY(-2px);
            }}
            
            .style-preset.active {{
                background-color: {theme['primary']}15;
                border-color: {theme['primary']};
                box-shadow: 0 4px 12px {theme['primary']}20;
            }}
            
            .style-preset-name {{
                font-size: 1.1rem;
                font-weight: 600;
                margin-bottom: 0.5rem;
                color: {theme['text']};
            }}
            
            .style-preset-desc {{
                font-size: 0.85rem;
                color: {theme['text']}80;
                line-height: 1.3;
            }}
            
            /* Элементы конструктора */
            .element-pill {{
                background-color: {theme['cardBackground']};
                border: 1px solid {theme['border']};
                border-radius: 20px;
                padding: 0.5rem 1rem;
                margin: 0.3rem;
                cursor: grab;
                display: inline-block;
                transition: all 0.2s ease;
            }}
            
            .element-pill:hover {{
                background-color: {theme['primary']}10;
                border-color: {theme['primary']};
            }}
            
            .element-sequence {{
                background-color: {theme['cardBackground']};
                border: 2px dashed {theme['border']};
                border-radius: 12px;
                min-height: 200px;
                padding: 1.5rem;
                margin: 1rem 0;
            }}
            
            .element-sequence.empty {{
                display: flex;
                align-items: center;
                justify-content: center;
                color: {theme['text']}60;
                font-style: italic;
            }}
            
            .sequence-item {{
                background-color: {theme['secondaryBackground']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 0.8rem 1rem;
                margin-bottom: 0.8rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
                transition: all 0.2s ease;
            }}
            
            .sequence-item:hover {{
                background-color: {theme['primary']}10;
                border-color: {theme['primary']};
            }}
            
            .sequence-item.active {{
                background-color: {theme['primary']}20;
                border-color: {theme['primary']};
            }}
            
            .sequence-item-name {{
                font-weight: 600;
                color: {theme['text']};
            }}
            
            .sequence-item-controls {{
                display: flex;
                gap: 0.3rem;
            }}
            
            /* Панель предпросмотра */
            .preview-panel {{
                background-color: {theme['background']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 1.5rem;
                margin: 1rem 0;
                font-family: monospace;
                font-size: 0.9rem;
                line-height: 1.6;
                min-height: 120px;
            }}
            
            /* Статистика */
            .stat-card {{
                background-color: {theme['cardBackground']};
                border-radius: 10px;
                padding: 1rem;
                text-align: center;
                margin: 0.5rem;
            }}
            
            .stat-value {{
                font-size: 1.8rem;
                font-weight: 700;
                color: {theme['primary']};
                margin-bottom: 0.3rem;
            }}
            
            .stat-label {{
                font-size: 0.9rem;
                color: {theme['text']}80;
            }}
            
            /* Шаги прогресса */
            .step-progress {{
                display: flex;
                justify-content: space-between;
                margin: 2rem 0;
                position: relative;
            }}
            
            .step-progress::before {{
                content: '';
                position: absolute;
                top: 20px;
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
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background-color: {theme['border']};
                color: {theme['text']};
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 0.5rem;
                font-weight: 600;
                transition: all 0.3s ease;
            }}
            
            .step.active .step-circle {{
                background-color: {theme['primary']};
                color: white;
                transform: scale(1.1);
            }}
            
            .step.completed .step-circle {{
                background-color: {theme['success']};
                color: white;
            }}
            
            .step-label {{
                font-size: 0.9rem;
                font-weight: 600;
                color: {theme['text']}80;
            }}
            
            .step.active .step-label {{
                color: {theme['primary']};
            }}
            
            /* Результаты */
            .result-reference {{
                background-color: {theme['cardBackground']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 1rem;
                margin-bottom: 0.8rem;
                font-size: 0.9rem;
                line-height: 1.5;
            }}
            
            .result-reference.duplicate {{
                background-color: {theme['warning']}20;
                border-color: {theme['warning']};
            }}
            
            .result-reference.error {{
                background-color: {theme['danger']}20;
                border-color: {theme['danger']};
            }}
            
            /* Кнопки экспорта */
            .export-option {{
                background-color: {theme['cardBackground']};
                border: 2px solid {theme['border']};
                border-radius: 10px;
                padding: 1.5rem;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                height: 100%;
            }}
            
            .export-option:hover {{
                border-color: {theme['primary']};
                transform: translateY(-2px);
            }}
            
            .export-option.recommended {{
                border-color: {theme['success']};
                background-color: {theme['success']}10;
            }}
            
            .export-icon {{
                font-size: 2rem;
                margin-bottom: 0.8rem;
            }}
            
            .export-badge {{
                background-color: {theme['success']};
                color: white;
                padding: 0.2rem 0.8rem;
                border-radius: 12px;
                font-size: 0.8rem;
                margin-bottom: 0.5rem;
                display: inline-block;
            }}
            
            /* Подсказки */
            .tip-box {{
                background-color: {theme['info']}15;
                border: 1px solid {theme['info']}30;
                border-radius: 8px;
                padding: 1rem;
                margin: 1rem 0;
                font-size: 0.9rem;
            }}
            
            .tip-icon {{
                font-size: 1.2rem;
                margin-right: 0.5rem;
                vertical-align: middle;
            }}
            
            /* Кнопки действий */
            .action-button {{
                background-color: {theme['primary']};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0.8rem 1.5rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                width: 100%;
                margin: 0.5rem 0;
            }}
            
            .action-button:hover {{
                background-color: {theme['primary']}90;
                transform: translateY(-2px);
                box-shadow: 0 4px 12px {theme['primary']}30;
            }}
            
            .action-button.secondary {{
                background-color: {theme['cardBackground']};
                color: {theme['text']};
                border: 1px solid {theme['border']};
            }}
            
            .action-button.secondary:hover {{
                background-color: {theme['secondaryBackground']};
                border-color: {theme['primary']};
            }}
            
            /* Область drag-and-drop */
            .drop-zone {{
                border: 2px dashed {theme['border']};
                border-radius: 12px;
                padding: 3rem 2rem;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                margin: 1rem 0;
            }}
            
            .drop-zone:hover {{
                border-color: {theme['primary']};
                background-color: {theme['primary']}05;
            }}
            
            .drop-zone.dragover {{
                border-color: {theme['primary']};
                background-color: {theme['primary']}10;
            }}
            
            .drop-icon {{
                font-size: 3rem;
                color: {theme['primary']};
                margin-bottom: 1rem;
            }}
            
            /* Инфографика статистики */
            .metric-bar {{
                height: 8px;
                background-color: {theme['border']};
                border-radius: 4px;
                margin: 0.5rem 0;
                overflow: hidden;
            }}
            
            .metric-fill {{
                height: 100%;
                background-color: {theme['primary']};
                border-radius: 4px;
                transition: width 1s ease;
            }}
            
            /* Адаптивность */
            @media (max-width: 768px) {{
                .card {{
                    padding: 1rem;
                }}
                
                .quick-start-btn {{
                    min-height: 150px;
                    padding: 1rem;
                }}
                
                .quick-start-icon {{
                    font-size: 2rem;
                }}
                
                .style-preset {{
                    padding: 1rem;
                    min-height: 100px;
                }}
                
                .step-circle {{
                    width: 32px;
                    height: 32px;
                    font-size: 0.9rem;
                }}
            }}
            
            /* Утилиты */
            .text-success {{ color: {theme['success']}; }}
            .text-warning {{ color: {theme['warning']}; }}
            .text-danger {{ color: {theme['danger']}; }}
            .text-info {{ color: {theme['info']}; }}
            
            .bg-success {{ background-color: {theme['success']}20; }}
            .bg-warning {{ background-color: {theme['warning']}20; }}
            .bg-danger {{ background-color: {theme['danger']}20; }}
            .bg-info {{ background-color: {theme['info']}20; }}
            
            .border-success {{ border-color: {theme['success']}; }}
            .border-warning {{ border-color: {theme['warning']}; }}
            .border-danger {{ border-color: {theme['danger']}; }}
            .border-info {{ border-color: {theme['info']}; }}
            </style>
        """, unsafe_allow_html=True)
           
    def render_header(self):
        """Рендер заголовка и контролов"""
        st.markdown("<div style='padding-top: 20px;'></div>", unsafe_allow_html=True)
        
        col_title, col_controls = st.columns([2, 3])
        
        with col_title:
            st.markdown(f"<h1 style='margin-top: 0;'>🎓 {get_text('header')}</h1>", unsafe_allow_html=True)
        
        with col_controls:
            # Компактные контролы в строку
            control_cols = st.columns(4)
            
            with control_cols[0]:
                # Язык
                languages = [('English', 'en'), ('Русский', 'ru')]
                current_lang = st.session_state.current_language
                current_lang_name = next((name for name, code in languages if code == current_lang), 'English')
                
                selected_language = st.selectbox(
                    get_text('language'),
                    languages,
                    format_func=lambda x: x[0],
                    index=next(i for i, (_, code) in enumerate(languages) if code == current_lang),
                    key="language_selector",
                    label_visibility="collapsed"
                )
                
                if selected_language[1] != st.session_state.current_language:
                    st.session_state.current_language = selected_language[1]
                    st.rerun()
            
            with control_cols[1]:
                # Тема
                themes = [
                    (get_text('light_theme'), 'light'),
                    (get_text('dark_theme'), 'dark'),
                    (get_text('lab_theme'), 'lab'),
                    (get_text('library_theme'), 'library')
                ]
                
                selected_theme = st.selectbox(
                    get_text('theme'),
                    themes,
                    format_func=lambda x: x[0],
                    index=next(i for i, (_, code) in enumerate(themes) if code == st.session_state.current_theme),
                    key="theme_selector",
                    label_visibility="collapsed"
                )
                
                if selected_theme[1] != st.session_state.current_theme:
                    st.session_state.current_theme = selected_theme[1]
                    st.rerun()
            
            with control_cols[2]:
                # Режим
                modes = [
                    (get_text('simple_mode'), 'wizard_mode'),
                    (get_text('expert_mode'), 'expert_mode')
                ]
                
                selected_mode = st.selectbox(
                    "Mode",
                    modes,
                    format_func=lambda x: x[0],
                    index=0 if st.session_state.ui_mode == 'wizard_mode' else 1,
                    key="mode_selector",
                    label_visibility="collapsed"
                )
                
                if selected_mode[1] != st.session_state.ui_mode:
                    st.session_state.ui_mode = selected_mode[1]
                    st.rerun()
            
            with control_cols[3]:
                # Дополнительные действия
                with st.popover("⚙️", use_container_width=True):
                    if st.button(get_text('clear_all'), use_container_width=True):
                        self._clear_all()
                    
                    if st.button(get_text('short_guide'), use_container_width=True):
                        self._show_quick_guide()
                    
                    if st.button("📊 Stats", use_container_width=True):
                        st.session_state.show_stats = not st.session_state.get('show_stats', False)
    
    def _clear_all(self):
        """Очистка всех данных"""
        # Сброс состояния
        st.session_state.current_step = 1
        st.session_state.uploaded_file = None
        st.session_state.references_input = ''
        st.session_state.selected_preset = None
        st.session_state.style_elements = []
        st.session_state.processing_complete = False
        st.session_state.formatted_results = None
        st.session_state.statistics_data = None
        st.session_state.duplicates_info = None
        st.session_state.show_quick_start = True
        st.session_state.show_style_designer = False
        st.rerun()
    
    def _show_quick_guide(self):
        """Показ краткого руководства"""
        with st.expander(get_text('short_guide'), expanded=True):
            st.markdown(f"**{get_text('guide_step1')}**")
            st.markdown(f"**{get_text('guide_step2')}**")
            st.markdown(f"**{get_text('guide_step3')}**")
            st.markdown(f"*{get_text('guide_note')}*")
    
    def render_wizard_interface(self):
        """Рендер интерфейса в режиме мастера"""
        # Шаги прогресса
        self._render_progress_steps()
        
        # Отображение текущего шага
        if st.session_state.current_step == 1:
            self._render_step_1()
        elif st.session_state.current_step == 2:
            self._render_step_2()
        elif st.session_state.current_step == 3:
            self._render_step_3()

    def _render_progress_steps(self):
        """Рендер шагов прогресса"""
        steps = [
            (get_text('step_1'), 1),
            (get_text('step_2'), 2),
            (get_text('step_3'), 3)
        ]
        
        # Создаем колонки для каждого шага
        cols = st.columns(len(steps))
        
        for idx, (col, (label, step_num)) in enumerate(zip(cols, steps)):
            with col:
                # Определяем статус шага
                is_active = step_num == st.session_state.current_step
                is_completed = step_num < st.session_state.current_step
                
                # Определяем цвет и символ
                if is_active:
                    circle_color = "var(--primary-color)"
                    circle_text = f"**{step_num}**"
                    label_color = "var(--primary-color)"
                elif is_completed:
                    circle_color = "var(--success)"
                    circle_text = "✓"
                    label_color = "var(--success)"
                else:
                    circle_color = "var(--border)"
                    circle_text = str(step_num)
                    label_color = "var(--text-color-secondary)"
                
                # Отображаем круг шага
                st.markdown(
                    f"""
                    <div style='
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        margin-bottom: 1rem;
                    '>
                        <div style='
                            width: 40px;
                            height: 40px;
                            border-radius: 50%;
                            background-color: {circle_color};
                            color: white;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            font-weight: bold;
                            font-size: 1.2rem;
                            margin-bottom: 0.5rem;
                            transition: all 0.3s ease;
                        '>
                            {circle_text}
                        </div>
                        <div style='
                            font-size: 0.9rem;
                            font-weight: 600;
                            color: {label_color};
                            text-align: center;
                        '>
                            {label}
                        </div>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
        
        # Линия прогресса под шагами
        st.markdown(
            """
            <div style='
                height: 3px;
                background-color: var(--border);
                margin: -10px 20px 20px 20px;
                position: relative;
            '>
                <div style='
                    position: absolute;
                    top: 0;
                    left: 0;
                    height: 100%;
                    background-color: var(--primary-color);
                    width: {}%;
                    transition: width 0.5s ease;
                '></div>
            </div>
            """.format(
                (st.session_state.current_step - 1) * 50  # 0%, 50%, 100%
            ),
            unsafe_allow_html=True
        )
    
    def _render_step_1(self):
        """Рендер шага 1: Выбор или создание стиля"""
        st.markdown(f"<h2>{get_text('step_1')}</h2>", unsafe_allow_html=True)
        
        # Быстрый старт (только при первом посещении)
        if st.session_state.show_quick_start:
            self._render_quick_start()
        
        # Пресеты стилей
        st.markdown(f'<div class="card-header">{get_text("style_presets")}</div>', unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns(4)
        presets = [
            (get_text('gost_style'), 'gost', 'ГОСТ Р 7.0.5-2008', col1),
            (get_text('acs_style'), 'acs', 'American Chemical Society', col2),
            (get_text('rsc_style'), 'rsc', 'Royal Society of Chemistry', col3),
            (get_text('cta_style'), 'cta', 'Chimica Techno Acta', col4)
        ]
        
        for name, preset_id, description, col in presets:
            with col:
                preset_class = "style-preset"
                if st.session_state.selected_preset == preset_id:
                    preset_class += " active"
                
                if st.button(name, key=f"preset_{preset_id}", use_container_width=True):
                    self._apply_preset_style(preset_id)
        
        # Кнопка создания своего стиля
        st.markdown("<br>", unsafe_allow_html=True)
        col_create, _, _ = st.columns([1, 1, 1])
        with col_create:
            if st.button(f"🎨 {get_text('create_custom_style')}", use_container_width=True, type="secondary"):
                st.session_state.show_style_designer = True
                st.session_state.selected_preset = None
                st.rerun()
        
        # Конструктор стилей (если выбран)
        if st.session_state.show_style_designer:
            self._render_style_designer()
        
        # Навигация
        st.markdown("<br><br>", unsafe_allow_html=True)
        col_prev, _, col_next = st.columns([1, 2, 1])
        with col_next:
            if st.button(f"➡️ {get_text('next_step')}", use_container_width=True, type="primary"):
                if st.session_state.selected_preset or st.session_state.style_elements:
                    st.session_state.current_step = 2
                    st.rerun()
                else:
                    st.warning(get_text('select_style_first'))
        
        # JavaScript для обработки кликов
        st.markdown("""
            <script>
            function selectPreset(presetId) {
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: {preset: presetId, type: 'select_preset'}
                }, '*');
            }
            </script>
        """, unsafe_allow_html=True)
    
    def _render_quick_start(self):
        """Рендер быстрого старта"""
        st.markdown(f'<div class="card-header">{get_text("quick_start")}</div>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"""
                <div class="quick-start-btn" onclick="window.quickStart('docx')">
                    <div class="quick-start-icon">📄</div>
                    <div class="quick-start-title">{get_text('i_have_docx')}</div>
                    <div class="quick-start-desc">{get_text('drag_drop_docx')}</div>
                </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
                <div class="quick-start-btn" onclick="window.quickStart('list')">
                    <div class="quick-start-icon">📝</div>
                    <div class="quick-start-title">{get_text('i_have_list')}</div>
                    <div class="quick-start-desc">{get_text('paste_references')}</div>
                </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
                <div class="quick-start-btn" onclick="window.quickStart('design')">
                    <div class="quick-start-icon">🎨</div>
                    <div class="quick-start-title">{get_text('i_want_design')}</div>
                    <div class="quick-start-desc">{get_text('create_custom_style')}</div>
                </div>
            """, unsafe_allow_html=True)
        
        # JavaScript для быстрого старта
        st.markdown("""
            <script>
            function quickStart(action) {
                if (action === 'design') {
                    window.parent.postMessage({
                        type: 'streamlit:setComponentValue',
                        value: {action: 'show_designer', type: 'quick_start'}
                    }, '*');
                } else if (action === 'docx') {
                    window.parent.postMessage({
                        type: 'streamlit:setComponentValue', 
                        value: {action: 'upload_docx', type: 'quick_start'}
                    }, '*');
                } else if (action === 'list') {
                    window.parent.postMessage({
                        type: 'streamlit:setComponentValue',
                        value: {action: 'paste_list', type: 'quick_start'}
                    }, '*');
                }
            }
            </script>
        """, unsafe_allow_html=True)
    
    def _render_style_designer(self):
        """Рендер конструктора стилей"""
        st.markdown(f'<div class="card-header">{get_text("style_designer")}</div>', unsafe_allow_html=True)
        
        # Две колонки: доступные элементы и последовательность
        col_elements, col_sequence = st.columns([1, 2])
        
        with col_elements:
            st.markdown(f"**{get_text('available_elements')}**")
            elements = [
                (get_text('authors'), 'Authors'),
                (get_text('title'), 'Title'),
                (get_text('journal'), 'Journal'),
                (get_text('year'), 'Year'),
                (get_text('volume'), 'Volume'),
                (get_text('issue'), 'Issue'),
                (get_text('pages'), 'Pages'),
                (get_text('doi'), 'DOI')
            ]
            
            for icon_name, element_name in elements:
                if st.button(icon_name, key=f"add_{element_name}", use_container_width=True):
                    self._add_element_to_sequence(element_name)
        
        with col_sequence:
            st.markdown(f"**{get_text('drag_elements_here')}**")
            
            # Последовательность элементов
            sequence_class = "element-sequence"
            if not st.session_state.style_elements:
                sequence_class += " empty"
                placeholder = f'<div style="text-align: center; padding: 2rem;">{get_text("drag_elements_here")}</div>'
                st.markdown(f'<div class="{sequence_class}">{placeholder}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="{sequence_class}">', unsafe_allow_html=True)
                for i, element_data in enumerate(st.session_state.style_elements):
                    element_name = element_data.get('element', '')
                    element_config = element_data.get('config', {})
                    
                    item_class = "sequence-item"
                    if i == st.session_state.get('active_element_index', -1):
                        item_class += " active"
                    
                    # Форматирование настроек
                    config_text = ""
                    if element_config.get('italic'):
                        config_text += "<i>I</i> "
                    if element_config.get('bold'):
                        config_text += "<b>B</b> "
                    if element_config.get('parentheses'):
                        config_text += "() "
                    
                    st.markdown(f"""
                        <div class="{item_class}" onclick="window.selectElement({i})">
                            <div>
                                <div class="sequence-item-name">{element_name}</div>
                                <div style="font-size: 0.8rem; color: var(--text-color-secondary);">
                                    {config_text}sep: "{element_config.get('separator', '. ')}"
                                </div>
                            </div>
                            <div class="sequence-item-controls">
                                <button onclick="event.stopPropagation(); window.moveElement({i}, -1)">↑</button>
                                <button onclick="event.stopPropagation(); window.moveElement({i}, 1)">↓</button>
                                <button onclick="event.stopPropagation(); window.removeElement({i})">×</button>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        
        # Настройки выбранного элемента
        if st.session_state.active_element_index >= 0 and st.session_state.active_element_index < len(st.session_state.style_elements):
            self._render_element_settings()
        
        # Общие настройки
        st.markdown(f"**{get_text('general_settings')}**")
        col_gen1, col_gen2 = st.columns(2)
        
        with col_gen1:
            st.selectbox(
                get_text('numbering_style'),
                Config.NUMBERING_STYLES,
                key="num",
                index=Config.NUMBERING_STYLES.index(st.session_state.num)
            )
            
            st.selectbox(
                get_text('author_format'),
                Config.AUTHOR_FORMATS,
                key="auth",
                index=Config.AUTHOR_FORMATS.index(st.session_state.auth)
            )
        
        with col_gen2:
            st.text_input(get_text('author_separator'), key="sep", value=st.session_state.sep)
            st.number_input(get_text('et_al_limit'), key="etal", value=st.session_state.etal, min_value=0)
        
        # Предпросмотр
        st.markdown(f"**{get_text('preview_panel')}**")
        preview_metadata = self._get_preview_metadata()
        if preview_metadata:
            style_config = self._get_style_config()
            preview_ref, _ = format_reference(preview_metadata, style_config, for_preview=True)
            st.markdown(f'<div class="preview-panel">{preview_ref}</div>', unsafe_allow_html=True)
        
        # JavaScript для конструктора
        st.markdown("""
            <script>
            function addElement(elementName) {
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: {element: elementName, type: 'add_element'}
                }, '*');
            }
            
            function selectElement(index) {
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: {index: index, type: 'select_element'}
                }, '*');
            }
            
            function moveElement(index, direction) {
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: {index: index, direction: direction, type: 'move_element'}
                }, '*');
            }
            
            function removeElement(index) {
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: {index: index, type: 'remove_element'}
                }, '*');
            }
            </script>
        """, unsafe_allow_html=True)
    
    def _render_element_settings(self):
        """Рендер настроек элемента"""
        active_index = st.session_state.active_element_index
        element_data = st.session_state.style_elements[active_index]
        element_name = element_data.get('element', '')
        element_config = element_data.get('config', {})
        
        st.markdown(f"**{get_text('element_settings')}: {element_name}**")
        
        col_set1, col_set2 = st.columns(2)
        
        with col_set1:
            italic = st.checkbox(get_text('italic'), value=element_config.get('italic', False),
                               key=f"elem_italic_{active_index}")
            bold = st.checkbox(get_text('bold'), value=element_config.get('bold', False),
                             key=f"elem_bold_{active_index}")
        
        with col_set2:
            parentheses = st.checkbox(get_text('parentheses'), value=element_config.get('parentheses', False),
                                    key=f"elem_parentheses_{active_index}")
        
        separator = st.text_input(get_text('separator'), value=element_config.get('separator', '. '),
                                key=f"elem_separator_{active_index}")
        
        # Сохранение настроек
        if st.button("💾 Update Settings", key=f"update_elem_{active_index}", use_container_width=True):
            st.session_state.style_elements[active_index]['config'] = {
                'italic': italic,
                'bold': bold,
                'parentheses': parentheses,
                'separator': separator
            }
            st.success("Settings updated!")
            st.rerun()
    
    def _render_step_2(self):
        """Рендер шага 2: Загрузка ссылок"""
        st.markdown(f"<h2>{get_text('step_2')}</h2>", unsafe_allow_html=True)
        
        # Выбранный стиль
        if st.session_state.selected_preset:
            preset_name = {
                'gost': get_text('gost_style'),
                'acs': get_text('acs_style'),
                'rsc': get_text('rsc_style'),
                'cta': get_text('cta_style')
            }.get(st.session_state.selected_preset, get_text('custom_style'))
            st.info(f"Selected style: **{preset_name}**")
        elif st.session_state.style_elements:
            st.info(f"Custom style with {len(st.session_state.style_elements)} elements")
        
        # Выбор способа загрузки
        upload_option = st.radio(
            "Upload option",
            [get_text('i_have_docx'), get_text('i_have_list')],
            horizontal=True,
            key="upload_option"
        )
        
        if upload_option == get_text('i_have_docx'):
            self._render_docx_upload()
        else:
            self._render_text_input()
        
        # Навигация
        st.markdown("<br><br>", unsafe_allow_html=True)
        col_prev, col_process, col_next = st.columns([1, 2, 1])
        
        with col_prev:
            if st.button(f"⬅️ {get_text('prev_step')}", use_container_width=True, type="secondary"):
                st.session_state.current_step = 1
                st.rerun()
        
        with col_process:
            if st.button(f"⚙️ {get_text('start_processing')}", use_container_width=True, type="primary"):
                self._start_processing()
        
        with col_next:
            if st.session_state.processing_complete:
                if st.button(f"➡️ {get_text('next_step')}", use_container_width=True, type="primary"):
                    st.session_state.current_step = 3
                    st.rerun()
    
    def _render_docx_upload(self):
        """Рендер загрузки DOCX"""
        st.markdown(f"""
            <div class="drop-zone" onclick="document.getElementById('docx-upload').click()">
                <div class="drop-icon">📄</div>
                <div style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem;">
                    {get_text('drag_drop_docx')}
                </div>
                <div style="font-size: 0.9rem; color: var(--text-color-secondary);">
                    {get_text('or')} <span style="color: var(--primary-color);">{get_text('browse')}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader(
            "",
            type=['docx'],
            label_visibility="collapsed",
            key="docx_upload_input"
        )
        
        if uploaded_file:
            st.session_state.uploaded_file = uploaded_file
            # Чтение DOCX для предпросмотра
            try:
                doc = Document(uploaded_file)
                references = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
                st.success(f"✅ {get_text('found_references').format(len(references))}")
                
                # Предпросмотр первых 3 ссылок
                if references:
                    with st.expander("📋 Preview references"):
                        for i, ref in enumerate(references[:3]):
                            st.text(f"{i+1}. {ref[:100]}...")
                        if len(references) > 3:
                            st.text(f"... and {len(references) - 3} more")
            except Exception as e:
                st.error(f"Error reading DOCX: {str(e)}")
    
    def _render_text_input(self):
        """Рендер текстового ввода"""
        references_input = st.text_area(
            get_text('paste_references'),
            height=200,
            placeholder="1. Smith J. et al. J. Am. Chem. Soc. 2023, 15, 123-128\n2. Doe A. et al. Nature 2022, 610, 123-129\n3. ...",
            key="references_text_input"
        )
        
        if references_input:
            st.session_state.references_input = references_input
            references = [ref.strip() for ref in references_input.split('\n') if ref.strip()]
            st.success(f"✅ {get_text('found_references').format(len(references))}")
    
    def _start_processing(self):
        """Начало обработки"""
        # Проверка данных
        has_file = st.session_state.uploaded_file is not None
        has_text = bool(st.session_state.references_input.strip())
        
        if not has_file and not has_text:
            st.error(get_text('upload_file_first'))
            return
        
        # Подготовка данных
        if has_file:
            doc = Document(st.session_state.uploaded_file)
            references = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
        else:
            references = [ref.strip() for ref in st.session_state.references_input.split('\n') if ref.strip()]
        
        # Проверка количества ссылок
        if len(references) > Config.MAX_REFERENCES:
            st.error(get_text('too_many_references').format(Config.MAX_REFERENCES))
            return
        
        if len(references) == 0:
            st.error(get_text('no_references'))
            return
        
        # Получение конфигурации стиля
        style_config = self._get_style_config()
        
        # Обработка с прогрессом
        with st.spinner(get_text('processing')):
            progress_container = st.empty()
            status_container = st.empty()
            
            formatted_refs, txt_bytes, doi_found_count, doi_not_found_count, duplicates_info = (
                self.processor.process_references(references, style_config, progress_container, status_container)
            )
            
            # Генерация статистики
            statistics_data = generate_statistics(formatted_refs)
            
            # Генерация DOCX
            output_doc_buffer = DocumentGenerator.generate_document(
                formatted_refs, statistics_data, style_config, duplicates_info
            )
            
            # Сохранение результатов
            st.session_state.formatted_results = formatted_refs
            st.session_state.statistics_data = statistics_data
            st.session_state.duplicates_info = duplicates_info
            st.session_state.download_data = {
                'txt_bytes': txt_bytes,
                'output_doc_buffer': output_doc_buffer
            }
            st.session_state.processing_complete = True
            
            # Отображение статистики
            self._render_processing_stats(doi_found_count, doi_not_found_count, duplicates_info, statistics_data)
    
    def _render_processing_stats(self, doi_found, doi_not_found, duplicates_info, statistics):
        """Рендер статистики обработки"""
        st.success(f"✅ {get_text('processing_complete')}")
        
        # Основные метрики
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-value">{len(st.session_state.formatted_results)}</div>
                    <div class="stat-label">{get_text('found_references').replace('{}', '')}</div>
                </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-value text-success">{doi_found}</div>
                    <div class="stat-label">{get_text('doi_found').replace('{}', '')}</div>
                </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-value text-warning">{doi_not_found}</div>
                    <div class="stat-label">{get_text('doi_not_found').replace('{}', '')}</div>
                </div>
            """, unsafe_allow_html=True)
        
        with col4:
            duplicate_count = len(duplicates_info) if duplicates_info else 0
            st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-value text-info">{duplicate_count}</div>
                    <div class="stat-label">{get_text('duplicates_detected').replace('{}', '')}</div>
                </div>
            """, unsafe_allow_html=True)
        
        # Подсказки на основе статистики
        if statistics['needs_more_recent_references']:
            st.markdown(f"""
                <div class="tip-box">
                    <span class="tip-icon">💡</span>
                    {get_text('tip_recent_papers')}
                </div>
            """, unsafe_allow_html=True)
        
        if statistics['has_frequent_author']:
            st.markdown(f"""
                <div class="tip-box">
                    <span class="tip-icon">💡</span>
                    {get_text('tip_duplicate_authors')}
                </div>
            """, unsafe_allow_html=True)
        
        if doi_not_found > 0:
            st.markdown(f"""
                <div class="tip-box">
                    <span class="tip-icon">💡</span>
                    {get_text('tip_doi_check').format(doi_not_found)}
                </div>
            """, unsafe_allow_html=True)
    
    def _render_step_3(self):
        """Рендер шага 3: Экспорт результатов"""
        st.markdown(f"<h2>{get_text('step_3')}</h2>", unsafe_allow_html=True)
        
        if not st.session_state.processing_complete:
            st.warning("Please complete processing first")
            return
        
        # Две колонки: результаты и экспорт
        col_results, col_export = st.columns([2, 1])
        
        with col_results:
            st.markdown(f"**{get_text('formatted_references')}**")
            
            # Отображение отформатированных ссылок
            for i, (elements, is_error, metadata) in enumerate(st.session_state.formatted_results[:10]):  # Показываем первые 10
                ref_class = "result-reference"
                if is_error:
                    ref_class += " error"
                elif st.session_state.duplicates_info and i in st.session_state.duplicates_info:
                    ref_class += " duplicate"
                
                ref_text = self._format_result_reference(elements, i)
                st.markdown(f'<div class="{ref_class}">{ref_text}</div>', unsafe_allow_html=True)
            
            if len(st.session_state.formatted_results) > 10:
                st.info(f"... and {len(st.session_state.formatted_results) - 10} more references")
            
            # Статистика
            if st.session_state.statistics_data:
                with st.expander(f"📊 {get_text('statistics')}", expanded=True):
                    self._render_statistics_charts()
        
        with col_export:
            st.markdown(f"**{get_text('export_options')}**")
            
            # Опции экспорта
            col_exp1, col_exp2 = st.columns(2)
            
            with col_exp1:
                st.markdown(f"""
                    <div class="export-option recommended" onclick="window.exportDocx()">
                        <div class="export-badge">{get_text('recommended')}</div>
                        <div class="export-icon">📄</div>
                        <div style="font-weight: 600; margin-bottom: 0.3rem;">DOCX</div>
                        <div style="font-size: 0.85rem; color: var(--text-color-secondary);">
                            {get_text('with_statistics')}<br>{get_text('with_formatting')}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            
            with col_exp2:
                st.markdown(f"""
                    <div class="export-option" onclick="window.exportTxt()">
                        <div class="export-icon">📝</div>
                        <div style="font-weight: 600; margin-bottom: 0.3rem;">TXT</div>
                        <div style="font-size: 0.85rem; color: var(--text-color-secondary);">
                            Plain text<br>DOI list
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            
            # Кнопки скачивания
            st.markdown("<br>", unsafe_allow_html=True)
            
            if st.session_state.download_data.get('output_doc_buffer'):
                st.download_button(
                    label=f"📥 {get_text('download_docx')}",
                    data=st.session_state.download_data['output_doc_buffer'],
                    file_name='formatted_references.docx',
                    mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    use_container_width=True
                )
            
            if st.session_state.download_data.get('txt_bytes'):
                st.download_button(
                    label=f"📥 {get_text('download_txt')}",
                    data=st.session_state.download_data['txt_bytes'],
                    file_name='doi_list.txt',
                    mime='text/plain',
                    use_container_width=True
                )
            
            # Кнопка копирования
            if st.button(f"📋 {get_text('copy_to_clipboard')}", use_container_width=True):
                # Здесь должна быть логика копирования в буфер
                st.success(get_text('clipboard_copied'))
        
        # Навигация
        st.markdown("<br><br>", unsafe_allow_html=True)
        col_prev, _, col_new = st.columns([1, 2, 1])
        
        with col_prev:
            if st.button(f"⬅️ {get_text('prev_step')}", use_container_width=True, type="secondary"):
                st.session_state.current_step = 2
                st.rerun()
        
        with col_new:
            if st.button("🔄 New Processing", use_container_width=True, type="primary"):
                self._clear_all()
                st.rerun()
        
        # JavaScript для экспорта
        st.markdown("""
            <script>
            function exportDocx() {
                document.querySelector('[data-testid="stDownloadButton"] button').click();
            }
            
            function exportTxt() {
                // Активация кнопки скачивания TXT
                const txtButtons = document.querySelectorAll('[data-testid="stDownloadButton"] button');
                if (txtButtons.length > 1) {
                    txtButtons[1].click();
                }
            }
            </script>
        """, unsafe_allow_html=True)
    
    def _format_result_reference(self, elements, index):
        """Форматирование ссылки для отображения в результатах"""
        if isinstance(elements, str):
            return elements
        
        ref_parts = []
        for value, italic, bold, separator, is_doi_hyperlink, doi_value in elements:
            if is_doi_hyperlink:
                ref_parts.append(f'<a href="https://doi.org/{doi_value}" style="color: var(--primary-color); text-decoration: none;">{value}</a>')
            else:
                styled_value = value
                if italic:
                    styled_value = f'<i>{styled_value}</i>'
                if bold:
                    styled_value = f'<b>{styled_value}</b>'
                ref_parts.append(styled_value)
        
        # Добавление нумерации
        numbering = st.session_state.num
        prefix = ""
        if numbering == "1":
            prefix = f"{index + 1} "
        elif numbering == "1.":
            prefix = f"{index + 1}. "
        elif numbering == "1)":
            prefix = f"{index + 1}) "
        elif numbering == "(1)":
            prefix = f"({index + 1}) "
        elif numbering == "[1]":
            prefix = f"[{index + 1}] "
        
        return f"<div style='font-size: 0.9rem; line-height: 1.5;'>{prefix}{''.join(ref_parts)}</div>"
    
    def _render_statistics_charts(self):
        """Рендер графиков статистики"""
        if not st.session_state.statistics_data:
            return
        
        stats = st.session_state.statistics_data
        
        # Распределение по годам
        st.markdown(f"**{get_text('year_distribution')}**")
        for year_stat in stats['year_stats'][:5]:  # Топ-5 годов
            percentage = year_stat['percentage']
            st.markdown(f"""
                <div style="margin: 0.5rem 0;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.2rem;">
                        <span>{year_stat['year']}</span>
                        <span>{percentage}% ({year_stat['count']})</span>
                    </div>
                    <div class="metric-bar">
                        <div class="metric-fill" style="width: {percentage}%"></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        
        # Топ журналов
        st.markdown(f"<br>**{get_text('journal_distribution')}**", unsafe_allow_html=True)
        for journal_stat in stats['journal_stats'][:3]:  # Топ-3 журнала
            percentage = journal_stat['percentage']
            journal_name = journal_stat['journal'][:30] + "..." if len(journal_stat['journal']) > 30 else journal_stat['journal']
            st.markdown(f"""
                <div style="margin: 0.5rem 0;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.2rem;">
                        <span title="{journal_stat['journal']}">{journal_name}</span>
                        <span>{percentage}%</span>
                    </div>
                    <div class="metric-bar">
                        <div class="metric-fill" style="width: {percentage}%"></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
    
    def render_expert_interface(self):
        """Рендер экспертного режима (двухпанельный)"""
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown(f"<h3>🎨 {get_text('style_constructor')}</h3>", unsafe_allow_html=True)
            self._render_expert_style_designer()
        
        with col_right:
            st.markdown(f"<h3>📊 {get_text('results_view')}</h3>", unsafe_allow_html=True)
            self._render_expert_results_view()
    
    def _render_expert_style_designer(self):
        """Рендер конструктора стилей для экспертного режима"""
        # Быстрый выбор пресетов
        preset_cols = st.columns(4)
        presets = [
            (get_text('gost_style'), 'gost'),
            (get_text('acs_style'), 'acs'),
            (get_text('rsc_style'), 'rsc'),
            (get_text('cta_style'), 'cta')
        ]
        
        for (name, preset_id), col in zip(presets, preset_cols):
            with col:
                if st.button(name, use_container_width=True, key=f"preset_{preset_id}"):
                    self._apply_preset_style(preset_id)
        
        # Элементы конструктора (более компактные)
        st.markdown("**Elements**")
        element_cols = st.columns(4)
        elements = [
            (get_text('authors'), 'Authors'),
            (get_text('title'), 'Title'),
            (get_text('journal'), 'Journal'),
            (get_text('year'), 'Year'),
            (get_text('volume'), 'Volume'),
            (get_text('issue'), 'Issue'),
            (get_text('pages'), 'Pages'),
            (get_text('doi'), 'DOI')
        ]
        
        for i, (icon_name, element_name) in enumerate(elements):
            with element_cols[i % 4]:
                if st.button(icon_name, use_container_width=True, key=f"add_{element_name}"):
                    self._add_element_to_sequence(element_name)
        
        # Последовательность элементов
        if st.session_state.style_elements:
            for i, element_data in enumerate(st.session_state.style_elements):
                element_name = element_data.get('element', '')
                element_config = element_data.get('config', {})
                
                col_elem, col_up, col_down, col_del = st.columns([3, 1, 1, 1])
                
                with col_elem:
                    st.markdown(f"**{element_name}**")
                    config_text = []
                    if element_config.get('italic'):
                        config_text.append("I")
                    if element_config.get('bold'):
                        config_text.append("B")
                    if element_config.get('parentheses'):
                        config_text.append("()")
                    if config_text:
                        st.caption(" | ".join(config_text))
                
                with col_up:
                    if st.button("↑", key=f"up_{i}", use_container_width=True):
                        self._move_element(i, -1)
                
                with col_down:
                    if st.button("↓", key=f"down_{i}", use_container_width=True):
                        self._move_element(i, 1)
                
                with col_del:
                    if st.button("×", key=f"del_{i}", use_container_width=True):
                        self._remove_element(i)
        
        # Общие настройки
        with st.expander("⚙️ General Settings", expanded=True):
            col_gen1, col_gen2 = st.columns(2)
            
            with col_gen1:
                st.selectbox(
                    get_text('numbering_style'),
                    Config.NUMBERING_STYLES,
                    key="num_expert",
                    index=Config.NUMBERING_STYLES.index(st.session_state.num)
                )
                
                st.selectbox(
                    get_text('author_format'),
                    Config.AUTHOR_FORMATS,
                    key="auth_expert",
                    index=Config.AUTHOR_FORMATS.index(st.session_state.auth)
                )
            
            with col_gen2:
                st.text_input(get_text('author_separator'), key="sep_expert", value=st.session_state.sep)
                st.number_input(get_text('et_al_limit'), key="etal_expert", value=st.session_state.etal, min_value=0)
        
        # Предпросмотр
        preview_metadata = self._get_preview_metadata()
        if preview_metadata:
            style_config = self._get_style_config()
            preview_ref, _ = format_reference(preview_metadata, style_config, for_preview=True)
            st.markdown(f"**Preview:** {preview_ref}")
    
    def _render_expert_results_view(self):
        """Рендер просмотра результатов для экспертного режима"""
        # Быстрая загрузка
        upload_tab, text_tab = st.tabs(["📄 Upload DOCX", "📝 Paste Text"])
        
        with upload_tab:
            uploaded_file = st.file_uploader(
                "Choose DOCX file",
                type=['docx'],
                key="expert_docx_upload"
            )
            if uploaded_file:
                st.session_state.uploaded_file = uploaded_file
        
        with text_tab:
            references_input = st.text_area(
                "Paste references",
                height=150,
                key="expert_text_input"
            )
            if references_input:
                st.session_state.references_input = references_input
        
        # Кнопка обработки
        if st.button("⚙️ Process References", use_container_width=True, type="primary"):
            self._start_expert_processing()
        
        # Отображение результатов
        if st.session_state.processing_complete and st.session_state.formatted_results:
            st.markdown(f"**Results ({len(st.session_state.formatted_results)} references)**")
            
            # Быстрый экспорт
            export_cols = st.columns(3)
            
            with export_cols[0]:
                if st.session_state.download_data.get('output_doc_buffer'):
                    st.download_button(
                        label="📥 DOCX",
                        data=st.session_state.download_data['output_doc_buffer'],
                        file_name='references.docx',
                        mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        use_container_width=True
                    )
            
            with export_cols[1]:
                if st.session_state.download_data.get('txt_bytes'):
                    st.download_button(
                        label="📥 TXT",
                        data=st.session_state.download_data['txt_bytes'],
                        file_name='doi_list.txt',
                        mime='text/plain',
                        use_container_width=True
                    )
            
            with export_cols[2]:
                if st.button("📋 Copy", use_container_width=True):
                    st.success("Copied!")
            
            # Предпросмотр результатов
            with st.expander("📋 Preview Results", expanded=True):
                for i, (elements, is_error, metadata) in enumerate(st.session_state.formatted_results[:5]):
                    ref_text = self._format_result_reference(elements, i)
                    st.markdown(ref_text, unsafe_allow_html=True)
                
                if len(st.session_state.formatted_results) > 5:
                    st.text(f"... and {len(st.session_state.formatted_results) - 5} more")
        
        # Статистика
        if st.session_state.statistics_data:
            with st.expander("📊 Statistics", expanded=False):
                self._render_expert_statistics()
    
    def _start_expert_processing(self):
        """Начало обработки в экспертом режиме"""
        self._start_processing()
    
    def _render_expert_statistics(self):
        """Рендер статистики для экспертного режима"""
        if not st.session_state.statistics_data:
            return
        
        stats = st.session_state.statistics_data
        
        # Ключевые метрики
        metric_cols = st.columns(3)
        
        with metric_cols[0]:
            st.metric("Total References", len(st.session_state.formatted_results))
        
        with metric_cols[1]:
            recent_years = [datetime.now().year - i for i in range(4)]
            recent_count = sum(1 for ref in st.session_state.formatted_results 
                             if ref[2] and ref[2].get('year') in recent_years)
            recent_percent = int((recent_count / len(st.session_state.formatted_results)) * 100) if st.session_state.formatted_results else 0
            st.metric("Recent (<4 yrs)", f"{recent_percent}%")
        
        with metric_cols[2]:
            unique_authors = set()
            for ref in st.session_state.formatted_results:
                if ref[2] and ref[2].get('authors'):
                    for author in ref[2]['authors']:
                        unique_authors.add(author.get('family', ''))
            st.metric("Unique Authors", len(unique_authors))
        
        # Диаграммы
        tab_years, tab_journals = st.tabs(["Years", "Journals"])
        
        with tab_years:
            year_data = {str(ys['year']): ys['count'] for ys in stats['year_stats'][:10]}
            if year_data:
                st.bar_chart(year_data)
        
        with tab_journals:
            journal_data = {js['journal'][:20]: js['count'] for js in stats['journal_stats'][:10]}
            if journal_data:
                st.bar_chart(journal_data)
    
    def _get_preview_metadata(self):
        """Получение метаданных для предпросмотра"""
        preset = st.session_state.selected_preset
        
        if preset == 'gost':
            return {
                'authors': [{'given': 'Иван', 'family': 'Иванов'}, {'given': 'Петр', 'family': 'Петров'}],
                'title': 'Название статьи на русском',
                'journal': 'Журнал Российской академии наук',
                'year': 2023,
                'volume': '15',
                'issue': '3',
                'pages': '122-128',
                'article_number': '',
                'doi': '10.1000/xyz123'
            }
        elif preset == 'acs':
            return {
                'authors': [{'given': 'John A.', 'family': 'Smith'}, {'given': 'Alice B.', 'family': 'Doe'}],
                'title': 'Advanced Materials for Energy Storage',
                'journal': 'Journal of the American Chemical Society',
                'year': 2023,
                'volume': '145',
                'issue': '15',
                'pages': '8345-8352',
                'article_number': '',
                'doi': '10.1021/jacs.3c01234'
            }
        elif preset == 'rsc':
            return {
                'authors': [{'given': 'Robert', 'family': 'Brown'}, {'given': 'Emma', 'family': 'Wilson'}],
                'title': 'Sustainable Catalysis for Green Chemistry',
                'journal': 'Chemical Science',
                'year': 2023,
                'volume': '14',
                'issue': '8',
                'pages': '1234-1245',
                'article_number': '',
                'doi': '10.1039/d2sc06999a'
            }
        elif preset == 'cta':
            return {
                'authors': [
                    {'given': 'Fei', 'family': 'He'}, 
                    {'given': 'Feng', 'family': 'Ma'},
                    {'given': 'Juan', 'family': 'Li'}
                ],
                'title': 'Effect of calcination temperature on photocatalytic activities',
                'journal': 'Ceramics International',
                'year': 2014,
                'volume': '40',
                'issue': '5',
                'pages': '6441-6446',
                'article_number': '',
                'doi': '10.1016/j.ceramint.2013.11.094'
            }
        elif st.session_state.style_elements:
            return {
                'authors': [{'given': 'John A.', 'family': 'Smith'}, {'given': 'Alice B.', 'family': 'Doe'}],
                'title': 'Research Article Title',
                'journal': 'Nature Communications',
                'year': 2023,
                'volume': '14',
                'issue': '1',
                'pages': '1234-1245',
                'article_number': '12345',
                'doi': '10.1038/s41467-023-45678-1'
            }
        else:
            return None
    
    def _get_style_config(self):
        """Получение конфигурации стиля"""
        elements = []
        for elem_data in st.session_state.style_elements:
            elements.append((
                elem_data['element'],
                {
                    'italic': elem_data['config'].get('italic', False),
                    'bold': elem_data['config'].get('bold', False),
                    'parentheses': elem_data['config'].get('parentheses', False),
                    'separator': elem_data['config'].get('separator', '. ')
                }
            ))
        
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
            'elements': elements,
            'gost_style': st.session_state.selected_preset == 'gost',
            'acs_style': st.session_state.selected_preset == 'acs',
            'rsc_style': st.session_state.selected_preset == 'rsc',
            'cta_style': st.session_state.selected_preset == 'cta'
        }
    
    def _apply_preset_style(self, preset_id):
        """Применение пресетного стиля"""
        st.session_state.selected_preset = preset_id
        st.session_state.style_elements = []
        
        if preset_id == 'gost':
            st.session_state.style_elements = [
                {'element': 'Authors', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ' '}},
                {'element': 'Title', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ' // '}},
                {'element': 'Journal', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. – '}},
                {'element': 'Year', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. – Vol. '}},
                {'element': 'Volume', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '}},
                {'element': 'Issue', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ''}},
                {'element': 'Pages', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. – '}},
                {'element': 'DOI', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. – '}}
            ]
            st.session_state.auth = "Smith AA"
            st.session_state.sep = ", "
            st.session_state.num = "No numbering"
        elif preset_id == 'acs':
            st.session_state.style_elements = [
                {'element': 'Authors', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ' '}},
                {'element': 'Title', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '}},
                {'element': 'Journal', 'config': {'italic': True, 'bold': False, 'parentheses': False, 'separator': ' '}},
                {'element': 'Year', 'config': {'italic': False, 'bold': True, 'parentheses': False, 'separator': ', '}},
                {'element': 'Volume', 'config': {'italic': True, 'bold': False, 'parentheses': False, 'separator': ', '}},
                {'element': 'Pages', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '}},
                {'element': 'DOI', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ''}}
            ]
            st.session_state.auth = "Smith, A.A."
            st.session_state.sep = "; "
            st.session_state.num = "No numbering"
        elif preset_id == 'rsc':
            st.session_state.style_elements = [
                {'element': 'Authors', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '}},
                {'element': 'Journal', 'config': {'italic': True, 'bold': False, 'parentheses': False, 'separator': ', '}},
                {'element': 'Year', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '}},
                {'element': 'Volume', 'config': {'italic': False, 'bold': True, 'parentheses': False, 'separator': ', '}},
                {'element': 'Pages', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '.'}}
            ]
            st.session_state.auth = "A.A. Smith"
            st.session_state.sep = ", "
            st.session_state.use_and_checkbox = True
            st.session_state.num = "No numbering"
        elif preset_id == 'cta':
            st.session_state.style_elements = [
                {'element': 'Authors', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '}},
                {'element': 'Title', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '}},
                {'element': 'Journal', 'config': {'italic': True, 'bold': False, 'parentheses': False, 'separator': '. '}},
                {'element': 'Year', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ';'}},
                {'element': 'Volume', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ''}},
                {'element': 'Issue', 'config': {'italic': False, 'bold': False, 'parentheses': True, 'separator': ':'}},
                {'element': 'Pages', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '}},
                {'element': 'DOI', 'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ''}}
            ]
            st.session_state.auth = "Smith AA"
            st.session_state.sep = ", "
            st.session_state.num = "No numbering"
        
        st.rerun()
    
    def _add_element_to_sequence(self, element_name):
        """Добавление элемента в последовательность"""
        if not st.session_state.style_elements:
            st.session_state.style_elements = []
        
        # Проверяем, нет ли уже такого элемента
        for elem in st.session_state.style_elements:
            if elem.get('element') == element_name:
                st.warning(f"Element '{element_name}' already in sequence")
                return
        
        # Добавляем новый элемент
        st.session_state.style_elements.append({
            'element': element_name,
            'config': {
                'italic': False,
                'bold': False,
                'parentheses': False,
                'separator': '. '
            }
        })
        st.session_state.active_element_index = len(st.session_state.style_elements) - 1
        st.session_state.selected_preset = None  # Сбрасываем пресет при добавлении элемента
        st.rerun()
    
    def _move_element(self, index, direction):
        """Перемещение элемента"""
        new_index = index + direction
        if 0 <= new_index < len(st.session_state.style_elements):
            st.session_state.style_elements[index], st.session_state.style_elements[new_index] = \
                st.session_state.style_elements[new_index], st.session_state.style_elements[index]
            
            if st.session_state.active_element_index == index:
                st.session_state.active_element_index = new_index
            elif st.session_state.active_element_index == new_index:
                st.session_state.active_element_index = index
            
            st.rerun()
    
    def _remove_element(self, index):
        """Удаление элемента"""
        if 0 <= index < len(st.session_state.style_elements):
            st.session_state.style_elements.pop(index)
            
            if st.session_state.active_element_index == index:
                st.session_state.active_element_index = -1
            elif st.session_state.active_element_index > index:
                st.session_state.active_element_index -= 1
            
            st.rerun()
    
    def handle_ui_events(self):
        """Обработка событий UI"""
        # Обработка сообщений от JavaScript
        if 'select_preset' in st.session_state:
            preset_id = st.session_state.select_preset.get('preset')
            if preset_id:
                self._apply_preset_style(preset_id)
            del st.session_state.select_preset
        
        if 'add_element' in st.session_state:
            element_name = st.session_state.add_element.get('element')
            if element_name:
                self._add_element_to_sequence(element_name)
            del st.session_state.add_element
        
        if 'select_element' in st.session_state:
            index = st.session_state.select_element.get('index')
            if index is not None:
                st.session_state.active_element_index = index
            del st.session_state.select_element
        
        if 'move_element' in st.session_state:
            index = st.session_state.move_element.get('index')
            direction = st.session_state.move_element.get('direction')
            if index is not None and direction is not None:
                self._move_element(index, direction)
            del st.session_state.move_element
        
        if 'remove_element' in st.session_state:
            index = st.session_state.remove_element.get('index')
            if index is not None:
                self._remove_element(index)
            del st.session_state.remove_element
        
        if 'quick_start' in st.session_state:
            action = st.session_state.quick_start.get('action')
            if action == 'show_designer':
                st.session_state.show_style_designer = True
                st.session_state.show_quick_start = False
                st.rerun()
            elif action == 'upload_docx':
                st.session_state.current_step = 2
                st.session_state.show_quick_start = False
                st.rerun()
            elif action == 'paste_list':
                st.session_state.current_step = 2
                st.session_state.show_quick_start = False
                st.rerun()
            del st.session_state.quick_start

# Основной класс приложения - ОБНОВЛЕННЫЙ
class CitationStyleApp:
    """Основной класс приложения с новым интерфейсом"""
    
    def __init__(self):
        self.processor = ReferenceProcessor()
        self.validator = StyleValidator()
        self.ui = ModernUIComponents()
        init_session_state()
    
    def run(self):
        """Запуск приложения"""
        st.set_page_config(
            layout="wide", 
            page_title="Citation Style Constructor",
            page_icon="🎓"
        )
        
        # Загрузка пользовательских предпочтений
        self._load_user_preferences()
        
        # Обработка импортированного стиля (если есть)
        self._handle_imported_style()
        
        # Применение стилей темы
        self.ui.apply_theme_styles()
        
        # Рендер заголовка
        self.ui.render_header()
        
        # Обработка событий UI
        self.ui.handle_ui_events()
        
        # Рендер основного интерфейса в зависимости от режима
        if st.session_state.ui_mode == 'wizard_mode':
            self.ui.render_wizard_interface()
        else:
            self.ui.render_expert_interface()
        
        # Обработка триггера обработки
        self._handle_processing_trigger()
    
    def _load_user_preferences(self):
        """Загрузка пользовательских предпочтений"""
        if not st.session_state.user_prefs_loaded:
            ip = self.ui.user_prefs.get_user_ip()
            prefs = self.ui.user_prefs.get_preferences(ip)
            
            st.session_state.current_language = prefs['language']
            st.session_state.current_theme = prefs['theme'] 
            st.session_state.ui_mode = prefs['ui_mode']
            st.session_state.user_prefs_loaded = True
    
    def _save_user_preferences(self):
        """Сохранение пользовательских предпочтений"""
        ip = self.ui.user_prefs.get_user_ip()
        preferences = {
            'language': st.session_state.current_language,
            'theme': st.session_state.current_theme,
            'ui_mode': st.session_state.ui_mode
        }
        self.ui.user_prefs.save_preferences(ip, preferences)
    
    def _handle_imported_style(self):
        """Обработка импортированного стиля"""
        if (st.session_state.get('imported_style') and 
            st.session_state.get('apply_imported_style') and 
            not st.session_state.get('style_import_processed')):

            self._apply_imported_style(st.session_state.imported_style)
            
            st.session_state.apply_imported_style = False
            st.session_state.imported_style = None
            st.session_state.style_import_processed = True
            
            st.rerun()
    
    def _handle_processing_trigger(self):
        """Обработка триггера обработки данных"""
        if st.session_state.get('process_triggered'):
            process_data = st.session_state.process_data
            input_data = process_data['input_data']
            style_config = process_data['style_config']
            output_method = process_data['output_method']
            
            # Сбрасываем триггер
            st.session_state.process_triggered = False
            
            # Выполняем обработку
            self._process_data(input_data, style_config, output_method)
    
    def _process_data(self, input_data, style_config, output_method):
        """Обработка данных (для обратной совместимости)"""
        # Эта функция теперь вызывается из UI компонентов
        pass
    
    def _apply_imported_style(self, imported_style):
        """Применение импортированного стиля к состоянию сессии"""
        if not imported_style:
            return
    
        def apply_style_callback():
            # Общие настройки
            if isinstance(imported_style, dict):
                if 'style_config' in imported_style:
                    style_cfg = imported_style['style_config']
                else:
                    style_cfg = imported_style
                
                # Применяем настройки из стиля
                if 'author_format' in style_cfg:
                    st.session_state.auth = style_cfg['author_format']
                if 'author_separator' in style_cfg:
                    st.session_state.sep = style_cfg['author_separator']
                if 'et_al_limit' in style_cfg:
                    st.session_state.etal = style_cfg['et_al_limit'] or 0
                if 'use_and_bool' in style_cfg:
                    st.session_state.use_and_checkbox = style_cfg['use_and_bool']
                if 'use_ampersand_bool' in style_cfg:
                    st.session_state.use_ampersand_checkbox = style_cfg['use_ampersand_bool']
                if 'doi_format' in style_cfg:
                    st.session_state.doi = style_cfg['doi_format']
                if 'doi_hyperlink' in style_cfg:
                    st.session_state.doilink = style_cfg['doi_hyperlink']
                if 'page_format' in style_cfg:
                    st.session_state.page = style_cfg['page_format']
                if 'final_punctuation' in style_cfg:
                    st.session_state.punct = style_cfg['final_punctuation']
                if 'journal_style' in style_cfg:
                    st.session_state.journal_style = style_cfg['journal_style']
                if 'numbering_style' in style_cfg:
                    st.session_state.num = style_cfg['numbering_style']
                
                # Пресеты стилей
                if 'gost_style' in style_cfg:
                    st.session_state.selected_preset = 'gost' if style_cfg['gost_style'] else None
                if 'acs_style' in style_cfg:
                    st.session_state.selected_preset = 'acs' if style_cfg['acs_style'] else None
                if 'rsc_style' in style_cfg:
                    st.session_state.selected_preset = 'rsc' if style_cfg['rsc_style'] else None
                if 'cta_style' in style_cfg:
                    st.session_state.selected_preset = 'cta' if style_cfg['cta_style'] else None
                
                # Режим интерфейса
                if 'ui_mode' in imported_style:
                    st.session_state.ui_mode = imported_style['ui_mode']
                
                # Элементы стиля
                if 'timeline_elements' in imported_style:
                    st.session_state.style_elements = imported_style['timeline_elements']
                elif 'elements' in style_cfg:
                    elements = style_cfg['elements']
                    style_elements = []
                    for element, config in elements:
                        style_elements.append({
                            'element': element,
                            'config': {
                                'italic': config.get('italic', False),
                                'bold': config.get('bold', False),
                                'parentheses': config.get('parentheses', False),
                                'separator': config.get('separator', '. ')
                            }
                        })
                    st.session_state.style_elements = style_elements
            
            st.session_state.style_applied = True
            st.session_state.style_import_processed = True
        
        apply_style_callback()

# Вспомогательные функции (остаются без изменений для обратной совместимости)
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
    app = CitationStyleApp()
    return app.ui._export_style(style_config, file_name)

def import_style(uploaded_file):
    app = CitationStyleApp()
    return app.ui._import_style(uploaded_file)

def apply_imported_style(imported_style):
    """Функция для применения импортированного стиля (для обратной совместимости)"""
    app = CitationStyleApp()
    app._apply_imported_style(imported_style)

def main():
    """Основная функция"""
    app = CitationStyleApp()
    app.run()

if __name__ == "__main__":
    main()



