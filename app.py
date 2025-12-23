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
    
    # Настройки тем (обновленные)
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
            'success': '#28a745',
            'warning': '#ffc107',
            'danger': '#dc3545'
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
            'success': '#20c997',
            'warning': '#fd7e14',
            'danger': '#e83e8c'
        },
        'library': {
            'primary': '#8B4513',
            'background': '#F5F5DC',
            'secondaryBackground': '#FAF0E6',
            'text': '#3E2723',
            'font': 'Georgia, serif',
            'border': '#D2B48C',
            'cardBackground': '#FFF8DC',
            'accent': '#556B2F',
            'success': '#228B22',
            'warning': '#DAA520',
            'danger': '#8B0000'
        },
        'barbie': {
            'primary': '#FF69B4',
            'background': '#FFF0F5',
            'secondaryBackground': '#FFE4E9',
            'text': '#880E4F',
            'font': 'Comic Sans MS, cursive',
            'border': '#FFC0CB',
            'cardBackground': '#FFE4E1',
            'accent': '#FF1493',
            'success': '#00CED1',
            'warning': '#FFD700',
            'danger': '#FF4500'
        },
        'neon': {
            'primary': '#00FF00',
            'background': '#000000',
            'secondaryBackground': '#111111',
            'text': '#FFFFFF',
            'font': 'Courier New, monospace',
            'border': '#FF00FF',
            'cardBackground': '#222222',
            'accent': '#00FFFF',
            'success': '#39FF14',
            'warning': '#FFFF00',
            'danger': '#FF0000'
        }
    }

# Инициализация Crossref
works = Works()

# Полный словарь переводов (только русский и английский)
TRANSLATIONS = {
    'en': {
        # Этапы
        'stage_start': '🎯 Start',
        'stage_style': '🎨 Style',
        'stage_create': '🔧 Create Style',
        'stage_io': '📁 Input-Output',
        'stage_results': '📊 Results',
        
        # Этап Start
        'start_title': 'Citation Style Constructor',
        'start_subtitle': 'Select how you want to proceed',
        'choose_preset': 'Choose Preset Style',
        'create_new': 'Create New Style',
        'load_saved': 'Load Saved Style',
        'upload_style_file': 'Upload style file',
        'no_file_selected': 'No file selected',
        'style_loaded': 'Style loaded successfully!',
        'style_load_error': 'Error loading style file!',
        
        # Этап Style
        'style_title': 'Select Preset Style',
        'style_subtitle': 'Choose one of the predefined styles',
        'cta_style': 'CTA Style',
        'rsc_style': 'RSC Style',
        'acs_style': 'ACS (MDPI) Style',
        'gost_style': 'GOST Style',
        'style_description': 'Description:',
        'cta_description': 'Chemical Technology Acta format with abbreviated journal names',
        'rsc_description': 'Royal Society of Chemistry format with "and" separator',
        'acs_description': 'American Chemical Society format used by MDPI journals',
        'gost_description': 'Russian GOST standard with full journal names',
        
        # Этап Create
        'create_title': 'Create Custom Style',
        'create_subtitle': 'Configure all style elements on one page',
        'general_settings': 'General Settings',
        'element_configuration': 'Element Configuration',
        'numbering_style': 'Numbering:',
        'author_format': 'Authors:',
        'author_separator': 'Separator:',
        'et_al_limit': 'Et al after:',
        'use_and': "'and'",
        'use_ampersand': "'&'",
        'journal_style': 'Journal style:',
        'full_journal_name': 'Full Journal Name',
        'journal_abbr_with_dots': 'J. Abbr.',
        'journal_abbr_no_dots': 'J Abbr',
        'page_format': 'Pages:',
        'doi_format': 'DOI format:',
        'doi_hyperlink': 'DOI as hyperlink',
        'final_punctuation': 'Final punctuation:',
        'element': 'Element',
        'italic': 'Italic',
        'bold': 'Bold',
        'parentheses': 'Parentheses',
        'separator': 'Separator',
        'save_style': '💾 Save Style',
        'save_style_name': 'Style name:',
        'style_saved': 'Style saved successfully!',
        'proceed_to_io': '➡️ Proceed to Input-Output',
        
        # Этап Input-Output
        'io_title': 'Input and Output',
        'io_subtitle': 'Configure input and output options',
        'input_method': 'Input Method:',
        'upload_docx': 'Upload DOCX File',
        'paste_text': 'Paste Text',
        'output_format': 'Output Format:',
        'output_docx': 'DOCX',
        'output_txt': 'TXT',
        'output_display': 'Display in interface',
        'references': 'References:',
        'enter_references': 'Enter references (one per line)',
        'process': '🚀 Process',
        'processing': '⏳ Processing...',
        'no_input': 'Please provide input data',
        'no_file': 'Please upload a file',
        
        # Этап Results
        'results_title': 'Results and Statistics',
        'results_subtitle': 'Download results and view statistics',
        'download_results': 'Download Results',
        'statistics': 'Statistics',
        'journal_frequency': 'Journal Frequency',
        'year_distribution': 'Year Distribution',
        'author_distribution': 'Author Distribution',
        'total_references': 'Total References:',
        'doi_found': 'DOI Found:',
        'doi_not_found': 'DOI Not Found:',
        'unique_dois': 'Unique DOIs:',
        'download_docx': '📥 Download DOCX',
        'download_txt': '📥 Download TXT',
        'view_in_interface': '👁️ View in Interface',
        
        # Общие
        'back': '↩️ Back',
        'clear_all': '🗑️ Clear All',
        'language': 'Language:',
        'theme': 'Theme:',
        'english': 'English',
        'russian': 'Русский',
        'light': 'Light',
        'dark': 'Dark',
        'library': 'Library',
        'barbie': 'Barbie',
        'neon': 'Neon',
        'cancel': 'Cancel',
        'confirm': 'Confirm',
        'error': 'Error',
        'warning': 'Warning',
        'success': 'Success',
        'info': 'Info',
        
        # Валидация
        'validation_error': 'Please check the configuration',
        'no_elements_error': 'Please configure at least one element',
        'too_many_references': 'Too many references (maximum {} allowed)',
        'no_references': 'Please enter references',
        
        # Статистика
        'journal': 'Journal',
        'count': 'Count',
        'percentage': 'Percentage',
        'year': 'Year',
        'author': 'Author',
        'frequent_author_warning': 'Frequent author detected',
        'recent_references_warning': 'Consider adding more recent references',
    },
    'ru': {
        # Этапы
        'stage_start': '🎯 Старт',
        'stage_style': '🎨 Стиль',
        'stage_create': '🔧 Создание стиля',
        'stage_io': '📁 Ввод-Вывод',
        'stage_results': '📊 Результаты',
        
        # Этап Start
        'start_title': 'Конструктор стилей цитирования',
        'start_subtitle': 'Выберите как продолжить',
        'choose_preset': 'Выбрать готовый стиль',
        'create_new': 'Создать новый стиль',
        'load_saved': 'Загрузить сохраненный стиль',
        'upload_style_file': 'Загрузить файл стиля',
        'no_file_selected': 'Файл не выбран',
        'style_loaded': 'Стиль загружен успешно!',
        'style_load_error': 'Ошибка загрузки файла стиля!',
        
        # Этап Style
        'style_title': 'Выбор готового стиля',
        'style_subtitle': 'Выберите один из предопределенных стилей',
        'cta_style': 'Стиль CTA',
        'rsc_style': 'Стиль RSC',
        'acs_style': 'Стиль ACS (MDPI)',
        'gost_style': 'Стиль ГОСТ',
        'style_description': 'Описание:',
        'cta_description': 'Формат Chemical Technology Acta с сокращенными названиями журналов',
        'rsc_description': 'Формат Royal Society of Chemistry с разделителем "и"',
        'acs_description': 'Формат American Chemical Society, используемый журналами MDPI',
        'gost_description': 'Российский стандарт ГОСТ с полными названиями журналов',
        
        # Этап Create
        'create_title': 'Создание пользовательского стиля',
        'create_subtitle': 'Настройте все элементы стиля на одной странице',
        'general_settings': 'Общие настройки',
        'element_configuration': 'Конфигурация элементов',
        'numbering_style': 'Нумерация:',
        'author_format': 'Авторы:',
        'author_separator': 'Разделитель:',
        'et_al_limit': 'Et al после:',
        'use_and': "'и'",
        'use_ampersand': "'&'",
        'journal_style': 'Стиль журнала:',
        'full_journal_name': 'Полное название',
        'journal_abbr_with_dots': 'Сокр. с точками',
        'journal_abbr_no_dots': 'Сокр. без точек',
        'page_format': 'Страницы:',
        'doi_format': 'Формат DOI:',
        'doi_hyperlink': 'DOI как ссылка',
        'final_punctuation': 'Конечная пунктуация:',
        'element': 'Элемент',
        'italic': 'Курсив',
        'bold': 'Жирный',
        'parentheses': 'Скобки',
        'separator': 'Разделитель',
        'save_style': '💾 Сохранить стиль',
        'save_style_name': 'Имя стиля:',
        'style_saved': 'Стиль сохранен успешно!',
        'proceed_to_io': '➡️ Перейти к Вводу-Выводу',
        
        # Этап Input-Output
        'io_title': 'Ввод и Вывод',
        'io_subtitle': 'Настройка параметров ввода и вывода',
        'input_method': 'Способ ввода:',
        'upload_docx': 'Загрузить DOCX файл',
        'paste_text': 'Вставить текст',
        'output_format': 'Формат вывода:',
        'output_docx': 'DOCX',
        'output_txt': 'TXT',
        'output_display': 'Показать в интерфейсе',
        'references': 'Ссылки:',
        'enter_references': 'Введите ссылки (по одной на строку)',
        'process': '🚀 Обработать',
        'processing': '⏳ Обработка...',
        'no_input': 'Пожалуйста, предоставьте данные',
        'no_file': 'Пожалуйста, загрузите файл',
        
        # Этап Results
        'results_title': 'Результаты и Статистика',
        'results_subtitle': 'Скачайте результаты и просмотрите статистику',
        'download_results': 'Скачать результаты',
        'statistics': 'Статистика',
        'journal_frequency': 'Частота журналов',
        'year_distribution': 'Распределение по годам',
        'author_distribution': 'Распределение авторов',
        'total_references': 'Всего ссылок:',
        'doi_found': 'DOI найдено:',
        'doi_not_found': 'DOI не найдено:',
        'unique_dois': 'Уникальных DOI:',
        'download_docx': '📥 Скачать DOCX',
        'download_txt': '📥 Скачать TXT',
        'view_in_interface': '👁️ Показать в интерфейсе',
        
        # Общие
        'back': '↩️ Назад',
        'clear_all': '🗑️ Очистить всё',
        'language': 'Язык:',
        'theme': 'Тема:',
        'english': 'English',
        'russian': 'Русский',
        'light': 'Светлая',
        'dark': 'Тёмная',
        'library': 'Библиотечная',
        'barbie': 'Барби',
        'neon': 'Неоновая',
        'cancel': 'Отмена',
        'confirm': 'Подтвердить',
        'error': 'Ошибка',
        'warning': 'Предупреждение',
        'success': 'Успех',
        'info': 'Информация',
        
        # Валидация
        'validation_error': 'Пожалуйста, проверьте конфигурацию',
        'no_elements_error': 'Настройте хотя бы один элемент',
        'too_many_references': 'Слишком много ссылок (максимум {} разрешено)',
        'no_references': 'Пожалуйста, введите ссылки',
        
        # Статистика
        'journal': 'Журнал',
        'count': 'Количество',
        'percentage': 'Процент',
        'year': 'Год',
        'author': 'Автор',
        'frequent_author_warning': 'Обнаружен часто встречающийся автор',
        'recent_references_warning': 'Рекомендуется добавить более свежие ссылки',
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_ip ON user_preferences(ip_address)')
    
    def get_user_ip(self):
        """Получение IP пользователя"""
        try:
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
                    'SELECT language, theme FROM user_preferences WHERE ip_address = ?',
                    (ip,)
                ).fetchone()
                
                if result:
                    return {
                        'language': result[0],
                        'theme': result[1]
                    }
        except Exception as e:
            logger.error(f"Error getting preferences for {ip}: {e}")
        
        return {
            'language': 'en',
            'theme': 'light'
        }
    
    def save_preferences(self, ip: str, preferences: Dict[str, Any]):
        """Сохранение предпочтений пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO user_preferences 
                    (ip_address, language, theme, updated_at) 
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    ip,
                    preferences.get('language', 'en'),
                    preferences.get('theme', 'light')
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
            errors.append('validation_error')
        
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
            errors.append('too_many_references')
        
        if len(references) < Config.MIN_REFERENCES_FOR_STATS:
            warnings.append('validation_warning')
        
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
        'current_stage': 'start',  # start, style, create, io, results
        'previous_stages': [],
        
        # Язык и тема
        'current_language': 'en',
        'current_theme': 'light',
        
        # Стили
        'style_config': {},
        'selected_preset': None,  # 'cta', 'rsc', 'acs', 'gost'
        'custom_style_name': '',
        'imported_style': None,
        
        # Ввод-вывод
        'input_method': 'text',  # 'docx' or 'text'
        'output_format': ['docx', 'display'],  # List of selected formats
        'references_input': '',
        'uploaded_file': None,
        
        # Результаты
        'processed_results': None,
        'statistics': None,
        'download_data': {},
        
        # Временные данные
        'processing_in_progress': False,
        'last_processed_time': 0,
    }
    
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

def get_text(key: str) -> str:
    """Получение перевода по ключу"""
    return TRANSLATIONS[st.session_state.current_language].get(key, key)

def navigate_to(stage: str):
    """Навигация между этапами"""
    if stage != st.session_state.current_stage:
        st.session_state.previous_stages.append(st.session_state.current_stage)
        st.session_state.current_stage = stage
        st.rerun()

def navigate_back():
    """Возврат на предыдущий этап"""
    if st.session_state.previous_stages:
        previous_stage = st.session_state.previous_stages.pop()
        st.session_state.current_stage = previous_stage
        st.rerun()

def clear_all():
    """Очистка всех настроек и возврат на старт"""
    st.session_state.current_stage = 'start'
    st.session_state.previous_stages = []
    st.session_state.style_config = {}
    st.session_state.selected_preset = None
    st.session_state.custom_style_name = ''
    st.session_state.imported_style = None
    st.session_state.input_method = 'text'
    st.session_state.output_format = ['docx', 'display']
    st.session_state.references_input = ''
    st.session_state.uploaded_file = None
    st.session_state.processed_results = None
    st.session_state.statistics = None
    st.session_state.download_data = {}
    st.rerun()

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
        patterns = [
            r'\s+([A-Z])\s*$',
            r'\s+([IVX]+)\s*$',
            r'\s+Part\s+([A-Z0-9]+)\s*$',
            r'\s+([A-Z]):\s+[A-Z]',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, journal_name)
            if match:
                ending = match.group(1)
                if ending in self.special_endings or re.match(r'^[A-Z]$', ending):
                    base_name = journal_name[:match.start()].strip()
                    return base_name, ending
        
        return journal_name, ""
    
    def abbreviate_journal_name(self, journal_name: str, style: str = "{J. Abbr.}") -> str:
        """Сокращает название журнала в соответствии с выбранным стилем"""
        if not journal_name:
            return ""
        
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
        
        if special_ending:
            if ':' in journal_name and special_ending + ':' in journal_name:
                result += f" {special_ending}:"
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
                if '-' not in pages:
                    if page_format == "122":
                        return pages.strip()
                    return pages.strip()
                
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
            
            if value:
                if config['parentheses'] and value:
                    value = f"({value})"
                
                separator = ""
                if i < len(self.style_config['elements']) - 1:
                    if not element_empty:
                        separator = config['separator']
                    elif previous_element_was_empty:
                        separator = ""
                    else:
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
                previous_element_was_empty = True
        
        cleaned_elements = []
        for i, element_data in enumerate(elements):
            value, italic, bold, separator, is_doi_hyperlink, doi_value, element_empty = element_data
            
            if not element_empty:
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
        
        journal_name = metadata['journal']
        
        doi_url = f"https://doi.org/{metadata['doi']}"
        
        if metadata['issue']:
            gost_ref = f"{authors_str} {metadata['title']} // {journal_name}. – {metadata['year']}. – Vol. {metadata['volume']}, № {metadata['issue']}"
        else:
            gost_ref = f"{authors_str} {metadata['title']} // {journal_name}. – {metadata['year']}. – Vol. {metadata['volume']}"
        
        if article_number and article_number.strip():
            gost_ref += f". – Art. {article_number.strip()}"
        elif pages and pages.strip():
            if '-' in pages:
                start_page, end_page = pages.split('-')
                pages_formatted = f"{start_page.strip()}-{end_page.strip()}"
            else:
                pages_formatted = pages.strip()
            gost_ref += f". – Р. {pages_formatted}"
        else:
            if st.session_state.current_language == 'ru':
                gost_ref += ". – [Без пагинации]"
            else:
                gost_ref += ". – [No pagination]"
        
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
        
        if pages:
            if '-' in pages:
                start_page, end_page = pages.split('-')
                start_page = start_page.strip()
                end_page = end_page.strip()
                pages_formatted = f"{start_page}–{end_page}"
            else:
                pages_formatted = pages
        elif article_number:
            pages_formatted = article_number
        else:
            pages_formatted = ""
        
        journal_name = self.format_journal_name(metadata['journal'])
        
        doi_url = f"https://dx.doi.org/{metadata['doi']}"
        
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
                duplicate_note = f"Repeated Reference (See #{original_index})"
                
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
        
        explicit_doi = self._find_explicit_doi(reference)
        if explicit_doi:
            logger.info(f"Found explicit DOI: {explicit_doi}")
            return explicit_doi
        
        bibliographic_doi = self._find_bibliographic_doi(reference)
        if bibliographic_doi:
            logger.info(f"Found bibliographic DOI: {bibliographic_doi}")
            return bibliographic_doi
        
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
        return None

    def extract_metadata_with_cache(self, doi: str) -> Optional[Dict]:
        """Извлечение метаданных с использованием кэша"""
        cached_metadata = self.cache.get(doi)
        if cached_metadata:
            logger.info(f"Cache hit for DOI: {doi}")
            return cached_metadata
        
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
        is_valid, validation_messages = self.validator.validate_references_count(references)
        for msg in validation_messages:
            if "error" in msg.lower():
                st.error(get_text(msg) if msg in TRANSLATIONS[st.session_state.current_language] else msg)
            else:
                st.warning(get_text(msg) if msg in TRANSLATIONS[st.session_state.current_language] else msg)
        
        if not is_valid:
            return [], io.BytesIO(), 0, 0, {}
        
        doi_list = []
        formatted_refs = []
        doi_found_count = 0
        doi_not_found_count = 0
        
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
        
        if valid_dois:
            self._process_doi_batch(valid_dois, reference_doi_map, references, 
                                  formatted_refs, doi_list, style_config,
                                  progress_container, status_container)
        
        doi_found_count = len([ref for ref in formatted_refs if not ref[1] and ref[2]])
        
        duplicates_info = self._find_duplicates(formatted_refs)
        
        txt_buffer = self._create_txt_file(doi_list)
        
        return formatted_refs, txt_buffer, doi_found_count, doi_not_found_count, duplicates_info
    
    def _process_doi_batch(self, valid_dois, reference_doi_map, references, 
                          formatted_refs, doi_list, style_config,
                          progress_container, status_container):
        """Пакетная обработка DOI"""
        status_container.info("Batch processing DOI...")
        
        self.progress_manager.start_processing(len(valid_dois))
        
        progress_bar = progress_container.progress(0)
        status_display = status_container.empty()
        
        metadata_results = self._extract_metadata_batch(valid_dois, progress_bar, status_display)
        
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
        
        progress_bar.progress(progress_ratio)
        
        progress_bar.markdown(f"""
            <style>
                .stProgress > div > div > div > div {{
                    background-color: {progress_color};
                }}
            </style>
        """, unsafe_allow_html=True)
        
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

# UI компоненты
class UIComponents:
    """Компоненты пользовательского интерфейса"""
    
    def __init__(self):
        self.user_prefs = UserPreferencesManager()
    
    def render_navigation_bar(self):
        """Рендер навигационной панели с этапами"""
        stages = [
            ('start', get_text('stage_start')),
            ('style', get_text('stage_style')),
            ('create', get_text('stage_create')),
            ('io', get_text('stage_io')),
            ('results', get_text('stage_results'))
        ]
        
        current_stage = st.session_state.current_stage
        
        # Определяем активные этапы
        active_stages = []
        if current_stage == 'start':
            active_stages = ['start']
        elif current_stage == 'style':
            active_stages = ['start', 'style']
        elif current_stage == 'create':
            active_stages = ['start', 'create']
        elif current_stage in ['io', 'results']:
            if st.session_state.selected_preset:
                active_stages = ['start', 'style', current_stage]
            else:
                active_stages = ['start', 'create', current_stage]
        
        # Рендер навигационной панели
        cols = st.columns(len(stages))
        for idx, (stage_id, stage_name) in enumerate(stages):
            with cols[idx]:
                if stage_id in active_stages:
                    # Активный этап
                    st.markdown(
                        f"""
                        <div style="
                            background-color: {Config.THEMES[st.session_state.current_theme]['primary']};
                            color: white;
                            padding: 8px;
                            border-radius: 5px;
                            text-align: center;
                            font-weight: bold;
                            margin-bottom: 10px;
                        ">
                            {stage_name}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                else:
                    # Неактивный этап
                    st.markdown(
                        f"""
                        <div style="
                            background-color: {Config.THEMES[st.session_state.current_theme]['secondaryBackground']};
                            color: {Config.THEMES[st.session_state.current_theme]['text']};
                            padding: 8px;
                            border-radius: 5px;
                            text-align: center;
                            opacity: 0.5;
                            margin-bottom: 10px;
                        ">
                            {stage_name}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
        
        # Кнопки навигации
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.session_state.current_stage != 'start':
                if st.button(get_text('back'), use_container_width=True, key="back_button"):
                    navigate_back()
        
        with col2:
            if st.button(get_text('clear_all'), use_container_width=True, key="clear_button"):
                clear_all()
        
        with col3:
            self._render_language_theme_selector()
    
    def _render_language_theme_selector(self):
        """Рендер выбора языка и темы"""
        with st.popover("⚙️"):
            col_lang, col_theme = st.columns(2)
            
            with col_lang:
                language = st.selectbox(
                    get_text('language'),
                    ['en', 'ru'],
                    format_func=lambda x: get_text('english') if x == 'en' else get_text('russian'),
                    index=0 if st.session_state.current_language == 'en' else 1,
                    key="language_selector"
                )
                
                if language != st.session_state.current_language:
                    st.session_state.current_language = language
                    self._save_user_preferences()
                    st.rerun()
            
            with col_theme:
                theme = st.selectbox(
                    get_text('theme'),
                    ['light', 'dark', 'library', 'barbie', 'neon'],
                    format_func=lambda x: get_text(x),
                    index=['light', 'dark', 'library', 'barbie', 'neon'].index(st.session_state.current_theme),
                    key="theme_selector"
                )
                
                if theme != st.session_state.current_theme:
                    st.session_state.current_theme = theme
                    self._save_user_preferences()
                    st.rerun()
    
    def _save_user_preferences(self):
        """Сохранение пользовательских предпочтений"""
        ip = self.user_prefs.get_user_ip()
        preferences = {
            'language': st.session_state.current_language,
            'theme': st.session_state.current_theme
        }
        self.user_prefs.save_preferences(ip, preferences)
    
    def load_user_preferences(self):
        """Загрузка пользовательских предпочтений"""
        ip = self.user_prefs.get_user_ip()
        prefs = self.user_prefs.get_preferences(ip)
        
        st.session_state.current_language = prefs['language']
        st.session_state.current_theme = prefs['theme']
    
    def apply_theme_styles(self):
        """Применение стилей темы"""
        theme = Config.THEMES[st.session_state.current_theme]
        
        st.markdown(f"""
            <style>
            .stApp {{
                background-color: {theme['background']};
                color: {theme['text']};
                font-family: {theme['font']};
            }}
            .main .block-container {{
                padding-top: 1rem;
                padding-bottom: 1rem;
            }}
            .stButton > button {{
                background-color: {theme['primary']};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 0.5rem 1rem;
                font-weight: bold;
            }}
            .stButton > button:hover {{
                background-color: {theme['accent']};
            }}
            .stSelectbox, .stTextInput, .stNumberInput, .stCheckbox, .stRadio, .stFileUploader, .stTextArea {{
                background-color: {theme['secondaryBackground']};
                color: {theme['text']};
                border: 1px solid {theme['border']};
                border-radius: 5px;
            }}
            .stTextArea textarea {{
                background-color: {theme['secondaryBackground']};
                color: {theme['text']};
            }}
            h1, h2, h3, h4 {{
                color: {theme['text']} !important;
            }}
            .card {{
                background-color: {theme['cardBackground']};
                border: 1px solid {theme['border']};
                border-radius: 10px;
                padding: 1rem;
                margin-bottom: 1rem;
            }}
            .compact-row {{
                margin-bottom: 0.3rem;
            }}
            .element-row {{
                padding: 0.2rem;
                margin: 0.1rem 0;
            }}
            .success-message {{
                color: {theme['success']};
                font-weight: bold;
            }}
            .error-message {{
                color: {theme['danger']};
                font-weight: bold;
            }}
            .warning-message {{
                color: {theme['warning']};
                font-weight: bold;
            }}
            </style>
        """, unsafe_allow_html=True)
    
    def render_stage_start(self):
        """Рендер этапа Start"""
        st.markdown(f"<h1>{get_text('start_title')}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p>{get_text('start_subtitle')}</p>", unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            if st.button(get_text('choose_preset'), use_container_width=True, key="choose_preset"):
                navigate_to('style')
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('<div class="card">', unsafe_allow_html=True)
            if st.button(get_text('create_new'), use_container_width=True, key="create_new"):
                navigate_to('create')
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown(f"<h4>{get_text('load_saved')}</h4>", unsafe_allow_html=True)
            
            uploaded_file = st.file_uploader(
                get_text('upload_style_file'),
                type=['json'],
                label_visibility="collapsed",
                key="style_uploader"
            )
            
            if uploaded_file is not None:
                try:
                    content = uploaded_file.read().decode('utf-8')
                    imported_style = json.loads(content)
                    
                    if 'style_config' in imported_style:
                        st.session_state.style_config = imported_style['style_config']
                    else:
                        st.session_state.style_config = imported_style
                    
                    st.session_state.selected_preset = None
                    st.success(get_text('style_loaded'))
                    
                    if st.button(get_text('proceed_to_io'), use_container_width=True, key="proceed_from_load"):
                        navigate_to('io')
                        
                except Exception as e:
                    st.error(f"{get_text('style_load_error')}: {str(e)}")
            
            if not uploaded_file:
                st.info(get_text('no_file_selected'))
            
            st.markdown('</div>', unsafe_allow_html=True)
    
    def render_stage_style(self):
        """Рендер этапа Style"""
        st.markdown(f"<h1>{get_text('style_title')}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p>{get_text('style_subtitle')}</p>", unsafe_allow_html=True)
        
        cols = st.columns(2)
        
        with cols[0]:
            # CTA Style
            st.markdown('<div class="card">', unsafe_allow_html=True)
            if st.button(get_text('cta_style'), use_container_width=True, key="cta_button"):
                st.session_state.selected_preset = 'cta'
                st.session_state.style_config = self._get_cta_style_config()
                navigate_to('io')
            st.markdown(f"<small>{get_text('style_description')} {get_text('cta_description')}</small>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # RSC Style
            st.markdown('<div class="card">', unsafe_allow_html=True)
            if st.button(get_text('rsc_style'), use_container_width=True, key="rsc_button"):
                st.session_state.selected_preset = 'rsc'
                st.session_state.style_config = self._get_rsc_style_config()
                navigate_to('io')
            st.markdown(f"<small>{get_text('style_description')} {get_text('rsc_description')}</small>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        with cols[1]:
            # ACS Style
            st.markdown('<div class="card">', unsafe_allow_html=True)
            if st.button(get_text('acs_style'), use_container_width=True, key="acs_button"):
                st.session_state.selected_preset = 'acs'
                st.session_state.style_config = self._get_acs_style_config()
                navigate_to('io')
            st.markdown(f"<small>{get_text('style_description')} {get_text('acs_description')}</small>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # GOST Style (только для русского языка)
            if st.session_state.current_language == 'ru':
                st.markdown('<div class="card">', unsafe_allow_html=True)
                if st.button(get_text('gost_style'), use_container_width=True, key="gost_button"):
                    st.session_state.selected_preset = 'gost'
                    st.session_state.style_config = self._get_gost_style_config()
                    navigate_to('io')
                st.markdown(f"<small>{get_text('style_description')} {get_text('gost_description')}</small>", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
    
    def _get_cta_style_config(self):
        """Конфигурация стиля CTA"""
        return {
            'author_format': "Smith AA",
            'author_separator': ", ",
            'et_al_limit': 0,
            'use_and_bool': False,
            'use_ampersand_bool': False,
            'doi_format': "doi:10.10/xxx",
            'doi_hyperlink': True,
            'page_format': "122–8",
            'final_punctuation': "",
            'numbering_style': "No numbering",
            'journal_style': "{J Abbr}",
            'elements': [
                ("Authors", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ". "}),
                ("Title", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ". "}),
                ("Journal", {'italic': True, 'bold': False, 'parentheses': False, 'separator': ". "}),
                ("Year", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ";"}),
                ("Volume", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ""}),
                ("Issue", {'italic': False, 'bold': False, 'parentheses': True, 'separator': ":"}),
                ("Pages", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ". "}),
                ("DOI", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ""})
            ],
            'cta_style': True,
            'acs_style': False,
            'rsc_style': False,
            'gost_style': False
        }
    
    def _get_rsc_style_config(self):
        """Конфигурация стиля RSC"""
        return {
            'author_format': "A.A. Smith",
            'author_separator': ", ",
            'et_al_limit': 0,
            'use_and_bool': True,
            'use_ampersand_bool': False,
            'doi_format': "10.10/xxx",
            'doi_hyperlink': True,
            'page_format': "122",
            'final_punctuation': ".",
            'numbering_style': "No numbering",
            'journal_style': "{J. Abbr.}",
            'elements': [
                ("Authors", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ", "}),
                ("Journal", {'italic': True, 'bold': False, 'parentheses': False, 'separator': ", "}),
                ("Year", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ", "}),
                ("Volume", {'italic': False, 'bold': True, 'parentheses': False, 'separator': ", "}),
                ("Pages", {'italic': False, 'bold': False, 'parentheses': False, 'separator': "."})
            ],
            'cta_style': False,
            'acs_style': False,
            'rsc_style': True,
            'gost_style': False
        }
    
    def _get_acs_style_config(self):
        """Конфигурация стиля ACS"""
        return {
            'author_format': "Smith, A.A.",
            'author_separator': "; ",
            'et_al_limit': 0,
            'use_and_bool': False,
            'use_ampersand_bool': False,
            'doi_format': "10.10/xxx",
            'doi_hyperlink': True,
            'page_format': "122–128",
            'final_punctuation': ".",
            'numbering_style': "No numbering",
            'journal_style': "{J. Abbr.}",
            'elements': [
                ("Authors", {'italic': False, 'bold': False, 'parentheses': False, 'separator': " "}),
                ("Title", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ". "}),
                ("Journal", {'italic': True, 'bold': False, 'parentheses': False, 'separator': " "}),
                ("Year", {'italic': False, 'bold': True, 'parentheses': False, 'separator': ", "}),
                ("Volume", {'italic': True, 'bold': False, 'parentheses': False, 'separator': ", "}),
                ("Pages", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ". "}),
                ("DOI", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ""})
            ],
            'cta_style': False,
            'acs_style': True,
            'rsc_style': False,
            'gost_style': False
        }
    
    def _get_gost_style_config(self):
        """Конфигурация стиля ГОСТ"""
        return {
            'author_format': "Smith AA",
            'author_separator': ", ",
            'et_al_limit': 0,
            'use_and_bool': False,
            'use_ampersand_bool': False,
            'doi_format': "https://dx.doi.org/10.10/xxx",
            'doi_hyperlink': True,
            'page_format': "122-128",
            'final_punctuation': "",
            'numbering_style': "No numbering",
            'journal_style': "{Full Journal Name}",
            'elements': [
                ("Authors", {'italic': False, 'bold': False, 'parentheses': False, 'separator': " "}),
                ("Title", {'italic': False, 'bold': False, 'parentheses': False, 'separator': " // "}),
                ("Journal", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ". – "}),
                ("Year", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ". – Vol. "}),
                ("Volume", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ", № "}),
                ("Issue", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ". – "}),
                ("Pages", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ". – "}),
                ("DOI", {'italic': False, 'bold': False, 'parentheses': False, 'separator': ""})
            ],
            'cta_style': False,
            'acs_style': False,
            'rsc_style': False,
            'gost_style': True
        }
    
    def render_stage_create(self):
        """Рендер этапа Create (компактный, без прокрутки)"""
        st.markdown(f"<h1>{get_text('create_title')}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p>{get_text('create_subtitle')}</p>", unsafe_allow_html=True)
        
        # Общие настройки
        st.markdown(f"<h3>{get_text('general_settings')}</h3>", unsafe_allow_html=True)
        
        # Компактный макет в 2 колонки
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown('<div class="compact-row">', unsafe_allow_html=True)
            numbering_style = st.selectbox(
                get_text('numbering_style'),
                Config.NUMBERING_STYLES,
                key="create_num",
                index=0
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('<div class="compact-row">', unsafe_allow_html=True)
            author_format = st.selectbox(
                get_text('author_format'),
                Config.AUTHOR_FORMATS,
                key="create_auth",
                index=0
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('<div class="compact-row">', unsafe_allow_html=True)
            col_sep_etal = st.columns(2)
            with col_sep_etal[0]:
                author_separator = st.selectbox(
                    get_text('author_separator'),
                    [", ", "; "],
                    key="create_sep",
                    index=0
                )
            with col_sep_etal[1]:
                et_al_limit = st.number_input(
                    get_text('et_al_limit'),
                    min_value=0,
                    max_value=10,
                    step=1,
                    key="create_etal",
                    value=0
                )
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('<div class="compact-row">', unsafe_allow_html=True)
            col_and_amp = st.columns(2)
            with col_and_amp[0]:
                use_and_bool = st.checkbox(
                    get_text('use_and'),
                    key="create_and",
                    value=False
                )
            with col_and_amp[1]:
                use_ampersand_bool = st.checkbox(
                    get_text('use_ampersand'),
                    key="create_amp",
                    value=False
                )
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown('<div class="compact-row">', unsafe_allow_html=True)
            journal_style = st.selectbox(
                get_text('journal_style'),
                Config.JOURNAL_STYLES,
                key="create_journal",
                index=0,
                format_func=lambda x: {
                    "{Full Journal Name}": get_text('full_journal_name'),
                    "{J. Abbr.}": get_text('journal_abbr_with_dots'),
                    "{J Abbr}": get_text('journal_abbr_no_dots')
                }[x]
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('<div class="compact-row">', unsafe_allow_html=True)
            page_format = st.selectbox(
                get_text('page_format'),
                Config.PAGE_FORMATS,
                key="create_page",
                index=3
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('<div class="compact-row">', unsafe_allow_html=True)
            doi_format = st.selectbox(
                get_text('doi_format'),
                Config.DOI_FORMATS,
                key="create_doi",
                index=0
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('<div class="compact-row">', unsafe_allow_html=True)
            doi_hyperlink = st.checkbox(
                get_text('doi_hyperlink'),
                key="create_doilink",
                value=True
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('<div class="compact-row">', unsafe_allow_html=True)
            final_punctuation = st.selectbox(
                get_text('final_punctuation'),
                ["", "."],
                key="create_punct",
                index=0
            )
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Конфигурация элементов (компактная таблица)
        st.markdown(f"<h3>{get_text('element_configuration')}</h3>", unsafe_allow_html=True)
        
        # Заголовок таблицы
        cols = st.columns([3, 1, 1, 1, 2])
        with cols[0]:
            st.markdown(f"<small><b>{get_text('element')}</b></small>", unsafe_allow_html=True)
        with cols[1]:
            st.markdown(f"<small><b>{get_text('italic')}</b></small>", unsafe_allow_html=True)
        with cols[2]:
            st.markdown(f"<small><b>{get_text('bold')}</b></small>", unsafe_allow_html=True)
        with cols[3]:
            st.markdown(f"<small><b>{get_text('parentheses')}</b></small>", unsafe_allow_html=True)
        with cols[4]:
            st.markdown(f"<small><b>{get_text('separator')}</b></small>", unsafe_allow_html=True)
        
        # 8 строк элементов (компактно)
        element_configs = []
        for i in range(8):
            cols = st.columns([3, 1, 1, 1, 2])
            with cols[0]:
                element = st.selectbox(
                    "",
                    Config.AVAILABLE_ELEMENTS,
                    key=f"create_el{i}",
                    label_visibility="collapsed",
                    index=0
                )
            with cols[1]:
                italic = st.checkbox("", key=f"create_it{i}", label_visibility="collapsed")
            with cols[2]:
                bold = st.checkbox("", key=f"create_bd{i}", label_visibility="collapsed")
            with cols[3]:
                parentheses = st.checkbox("", key=f"create_pr{i}", label_visibility="collapsed")
            with cols[4]:
                separator = st.text_input("", value=". ", key=f"create_sp{i}", label_visibility="collapsed")
            
            if element:
                element_configs.append((
                    element,
                    {
                        'italic': italic,
                        'bold': bold,
                        'parentheses': parentheses,
                        'separator': separator
                    }
                ))
        
        # Кнопки действий
        col_save, col_proceed = st.columns(2)
        
        with col_save:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            style_name = st.text_input(
                get_text('save_style_name'),
                value=st.session_state.custom_style_name,
                key="style_name_input"
            )
            
            if st.button(get_text('save_style'), use_container_width=True, key="save_style_button"):
                if style_name:
                    style_config = {
                        'author_format': author_format,
                        'author_separator': author_separator,
                        'et_al_limit': et_al_limit,
                        'use_and_bool': use_and_bool,
                        'use_ampersand_bool': use_ampersand_bool,
                        'doi_format': doi_format,
                        'doi_hyperlink': doi_hyperlink,
                        'page_format': page_format,
                        'final_punctuation': final_punctuation,
                        'numbering_style': numbering_style,
                        'journal_style': journal_style,
                        'elements': element_configs,
                        'cta_style': False,
                        'acs_style': False,
                        'rsc_style': False,
                        'gost_style': False
                    }
                    
                    export_data = {
                        'version': '1.0',
                        'style_name': style_name,
                        'export_date': str(datetime.now()),
                        'style_config': style_config
                    }
                    
                    json_data = json.dumps(export_data, indent=2, ensure_ascii=False)
                    st.download_button(
                        label=get_text('save_style'),
                        data=json_data.encode('utf-8'),
                        file_name=f"{style_name}.json",
                        mime="application/json",
                        use_container_width=True
                    )
                    
                    st.session_state.custom_style_name = style_name
                    st.session_state.style_config = style_config
                    st.success(get_text('style_saved'))
                else:
                    st.error("Please enter a style name")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col_proceed:
            if st.button(get_text('proceed_to_io'), use_container_width=True, key="proceed_from_create"):
                if element_configs:
                    st.session_state.style_config = {
                        'author_format': author_format,
                        'author_separator': author_separator,
                        'et_al_limit': et_al_limit,
                        'use_and_bool': use_and_bool,
                        'use_ampersand_bool': use_ampersand_bool,
                        'doi_format': doi_format,
                        'doi_hyperlink': doi_hyperlink,
                        'page_format': page_format,
                        'final_punctuation': final_punctuation,
                        'numbering_style': numbering_style,
                        'journal_style': journal_style,
                        'elements': element_configs,
                        'cta_style': False,
                        'acs_style': False,
                        'rsc_style': False,
                        'gost_style': False
                    }
                    st.session_state.selected_preset = None
                    navigate_to('io')
                else:
                    st.error(get_text('no_elements_error'))
    
    def render_stage_io(self):
        """Рендер этапа Input-Output"""
        st.markdown(f"<h1>{get_text('io_title')}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p>{get_text('io_subtitle')}</p>", unsafe_allow_html=True)
        
        # Выбор метода ввода
        st.markdown(f"<h4>{get_text('input_method')}</h4>", unsafe_allow_html=True)
        input_method = st.radio(
            "",
            ['upload_docx', 'paste_text'],
            format_func=lambda x: get_text(x),
            horizontal=True,
            key="io_input_method"
        )
        
        # Область ввода
        input_data = None
        
        if input_method == 'upload_docx':
            uploaded_file = st.file_uploader(
                get_text('upload_docx'),
                type=['docx'],
                label_visibility="collapsed",
                key="io_docx_uploader"
            )
            
            if uploaded_file:
                st.session_state.uploaded_file = uploaded_file
                try:
                    doc = Document(uploaded_file)
                    references = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
                    input_data = references
                    st.success(f"Found {len(references)} references in the document")
                except Exception as e:
                    st.error(f"Error reading DOCX file: {str(e)}")
            else:
                st.info(get_text('no_file'))
        
        else:  # paste_text
            references_input = st.text_area(
                get_text('references'),
                placeholder=get_text('enter_references'),
                height=100,
                label_visibility="collapsed",
                key="io_text_area"
            )
            
            if references_input:
                references = [ref.strip() for ref in references_input.split('\n') if ref.strip()]
                input_data = references
                st.success(f"Found {len(references)} references")
            else:
                st.info(get_text('no_input'))
        
        # Выбор формата вывода
        st.markdown(f"<h4>{get_text('output_format')}</h4>", unsafe_allow_html=True)
        output_options = st.multiselect(
            "",
            ['output_docx', 'output_txt', 'output_display'],
            default=['output_docx', 'output_display'],
            format_func=lambda x: get_text(x),
            key="io_output_format"
        )
        
        st.session_state.output_format = output_options
        
        # Кнопка обработки
        if st.button(get_text('process'), use_container_width=True, key="io_process_button"):
            if input_data:
                if len(input_data) > Config.MAX_REFERENCES:
                    st.error(get_text('too_many_references').format(Config.MAX_REFERENCES))
                elif not input_data:
                    st.error(get_text('no_references'))
                else:
                    st.session_state.processing_in_progress = True
                    st.session_state.references_input = input_data if isinstance(input_data, list) else input_data
                    
                    # Здесь будет обработка (упрощенно для примера)
                    with st.spinner(get_text('processing')):
                        time.sleep(2)  # Имитация обработки
                        
                        # Сохраняем результаты для следующего этапа
                        st.session_state.processed_results = {
                            'formatted_refs': [("Sample formatted reference 1", False, {})],
                            'txt_buffer': io.BytesIO(b"Sample DOI list"),
                            'doi_found_count': 5,
                            'doi_not_found_count': 2,
                            'duplicates_info': {}
                        }
                        
                        # Генерируем статистику
                        st.session_state.statistics = {
                            'journal_stats': [{'journal': 'Journal 1', 'count': 3, 'percentage': 60.0}],
                            'year_stats': [{'year': 2023, 'count': 5, 'percentage': 100.0}],
                            'author_stats': [{'author': 'Smith J.', 'count': 2, 'percentage': 40.0}],
                            'total_unique_dois': 5,
                            'needs_more_recent_references': False,
                            'has_frequent_author': False
                        }
                        
                        # Генерируем данные для скачивания
                        if 'output_docx' in output_options:
                            doc_buffer = io.BytesIO(b"Sample DOCX content")
                            st.session_state.download_data['docx'] = doc_buffer
                        
                        if 'output_txt' in output_options:
                            txt_buffer = io.BytesIO(b"Sample TXT content")
                            st.session_state.download_data['txt'] = txt_buffer
                        
                        navigate_to('results')
            else:
                st.error(get_text('no_input'))
    
    def render_stage_results(self):
        """Рендер этапа Results"""
        st.markdown(f"<h1>{get_text('results_title')}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p>{get_text('results_subtitle')}</p>", unsafe_allow_html=True)
        
        # Кнопки скачивания
        st.markdown(f"<h3>{get_text('download_results')}</h3>", unsafe_allow_html=True)
        
        if 'output_docx' in st.session_state.output_format and 'docx' in st.session_state.download_data:
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button(
                    label=get_text('download_docx'),
                    data=st.session_state.download_data['docx'],
                    file_name="formatted_references.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )
            
            with col2:
                if 'output_txt' in st.session_state.output_format and 'txt' in st.session_state.download_data:
                    st.download_button(
                        label=get_text('download_txt'),
                        data=st.session_state.download_data['txt'],
                        file_name="doi_list.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
        
        # Отображение в интерфейсе
        if 'output_display' in st.session_state.output_format:
            st.markdown(f"<h3>{get_text('view_in_interface')}</h3>", unsafe_allow_html=True)
            st.text_area(
                "",
                value="Sample formatted references will be displayed here...",
                height=200,
                disabled=True,
                key="results_display"
            )
        
        # Статистика
        if st.session_state.statistics:
            st.markdown(f"<h3>{get_text('statistics')}</h3>", unsafe_allow_html=True)
            
            col_stats1, col_stats2, col_stats3 = st.columns(3)
            
            with col_stats1:
                st.metric(get_text('total_references'), len(st.session_state.references_input))
            
            with col_stats2:
                if st.session_state.processed_results:
                    st.metric(get_text('doi_found'), st.session_state.processed_results['doi_found_count'])
            
            with col_stats3:
                if st.session_state.processed_results:
                    st.metric(get_text('doi_not_found'), st.session_state.processed_results['doi_not_found_count'])
            
            # Таблица частоты журналов
            st.markdown(f"<h4>{get_text('journal_frequency')}</h4>", unsafe_allow_html=True)
            if st.session_state.statistics['journal_stats']:
                journal_df = {
                    get_text('journal'): [s['journal'] for s in st.session_state.statistics['journal_stats']],
                    get_text('count'): [s['count'] for s in st.session_state.statistics['journal_stats']],
                    get_text('percentage'): [f"{s['percentage']}%" for s in st.session_state.statistics['journal_stats']]
                }
                st.dataframe(journal_df, use_container_width=True)
            
            # Распределение по годам
            st.markdown(f"<h4>{get_text('year_distribution')}</h4>", unsafe_allow_html=True)
            if st.session_state.statistics['year_stats']:
                year_df = {
                    get_text('year'): [s['year'] for s in st.session_state.statistics['year_stats']],
                    get_text('count'): [s['count'] for s in st.session_state.statistics['year_stats']],
                    get_text('percentage'): [f"{s['percentage']}%" for s in st.session_state.statistics['year_stats']]
                }
                st.dataframe(year_df, use_container_width=True)
                
                if st.session_state.statistics['needs_more_recent_references']:
                    st.warning(get_text('recent_references_warning'))
            
            # Распределение авторов
            st.markdown(f"<h4>{get_text('author_distribution')}</h4>", unsafe_allow_html=True)
            if st.session_state.statistics['author_stats']:
                author_df = {
                    get_text('author'): [s['author'] for s in st.session_state.statistics['author_stats']],
                    get_text('count'): [s['count'] for s in st.session_state.statistics['author_stats']],
                    get_text('percentage'): [f"{s['percentage']}%" for s in st.session_state.statistics['author_stats']]
                }
                st.dataframe(author_df, use_container_width=True)
                
                if st.session_state.statistics['has_frequent_author']:
                    st.warning(get_text('frequent_author_warning'))

# Основной класс приложения
class CitationStyleApp:
    """Основной класс приложения"""
    
    def __init__(self):
        self.ui = UIComponents()
        init_session_state()
    
    def run(self):
        """Запуск приложения"""
        st.set_page_config(layout="wide")
        
        # Загрузка пользовательских предпочтений
        self.ui.load_user_preferences()
        
        # Применение стилей темы
        self.ui.apply_theme_styles()
        
        # Рендер навигационной панели
        self.ui.render_navigation_bar()
        
        # Рендер текущего этапа
        current_stage = st.session_state.current_stage
        
        if current_stage == 'start':
            self.ui.render_stage_start()
        elif current_stage == 'style':
            self.ui.render_stage_style()
        elif current_stage == 'create':
            self.ui.render_stage_create()
        elif current_stage == 'io':
            self.ui.render_stage_io()
        elif current_stage == 'results':
            self.ui.render_stage_results()

# Вспомогательные функции (сохранены для обратной совместимости)
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
        'version': '1.0',
        'export_date': str(datetime.now()),
        'style_config': style_config
    }
    return json.dumps(export_data, indent=2, ensure_ascii=False).encode('utf-8')

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
        raise Exception(f"Error importing style: {str(e)}")

def apply_imported_style(imported_style):
    """Функция для применения импортированного стиля"""
    if imported_style:
        st.session_state.style_config = imported_style
        st.session_state.selected_preset = None

def main():
    """Основная функция"""
    app = CitationStyleApp()
    app.run()

if __name__ == "__main__":
    main()
