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
    
    # Настройки тем (5 тем)
    THEMES = {
        'light': {
            'primary': '#1f77b4',
            'secondary': '#2ca02c',
            'background': '#f8f9fa',
            'secondaryBackground': '#ffffff',
            'text': '#212529',
            'font': 'sans-serif',
            'border': '#dee2e6',
            'cardBackground': '#ffffff',
            'success': '#28a745',
            'warning': '#ffc107',
            'danger': '#dc3545'
        },
        'dark': {
            'primary': '#4ECDC4',
            'secondary': '#FF6B6B',
            'background': '#1a1d23',
            'secondaryBackground': '#2d323d',
            'text': '#e9ecef',
            'font': 'sans-serif',
            'border': '#495057',
            'cardBackground': '#2d323d',
            'success': '#20c997',
            'warning': '#fd7e14',
            'danger': '#e83e8c'
        },
        'library': {
            'primary': '#8B4513',
            'secondary': '#D2691E',
            'background': '#F5F5DC',
            'secondaryBackground': '#FAF0E6',
            'text': '#2F4F4F',
            'font': 'Georgia, serif',
            'border': '#DEB887',
            'cardBackground': '#FFEBCD',
            'success': '#228B22',
            'warning': '#B8860B',
            'danger': '#8B0000'
        },
        'barbie': {
            'primary': '#FF69B4',
            'secondary': '#FF1493',
            'background': '#FFF0F5',
            'secondaryBackground': '#FFE4E1',
            'text': '#8B008B',
            'font': 'Comic Sans MS, cursive',
            'border': '#FFB6C1',
            'cardBackground': '#FFE4E1',
            'success': '#DA70D6',
            'warning': '#FF00FF',
            'danger': '#C71585'
        },
        'neon': {
            'primary': '#00FFFF',
            'secondary': '#FF00FF',
            'background': '#0A0A0A',
            'secondaryBackground': '#1A1A1A',
            'text': '#FFFFFF',
            'font': 'Courier New, monospace',
            'border': '#00FF00',
            'cardBackground': '#222222',
            'success': '#00FF00',
            'warning': '#FFFF00',
            'danger': '#FF0000'
        }
    }

# Инициализация Crossref
works = Works()

# Полный словарь переводов (только русский и английский)
TRANSLATIONS = {
    'en': {
        'app_title': '🎨 Citation Style Constructor',
        'start_page_title': 'Start',
        'choose_preset_style': 'Choose Preset Style',
        'create_new_style': 'Create New Style',
        'load_saved_style': 'Load Saved Style',
        'style_page_title': 'Style Selection',
        'preset_styles': 'Preset Styles',
        'gost_style': 'GOST',
        'acs_style': 'ACS (MDPI)',
        'rsc_style': 'RSC',
        'cta_style': 'CTA',
        'create_page_title': 'Create New Style',
        'general_settings': 'General Settings',
        'element_configuration': 'Element Configuration',
        'numbering_style': 'Numbering:',
        'author_format': 'Authors:',
        'author_separator': 'Separator:',
        'et_al_limit': 'Et al after:',
        'use_and': "'and'",
        'use_ampersand': "'&'",
        'doi_format': 'DOI format:',
        'doi_hyperlink': 'DOI as hyperlink',
        'page_format': 'Pages:',
        'final_punctuation': 'Final punctuation:',
        'journal_style': 'Journal style:',
        'full_journal_name': 'Full Journal Name',
        'journal_abbr_with_dots': 'J. Abbr.',
        'journal_abbr_no_dots': 'J Abbr',
        'element': 'Element',
        'italic': 'Italic',
        'bold': 'Bold',
        'parentheses': 'Parentheses',
        'separator': 'Separator',
        'save_style': '💾 Save Style',
        'style_name': 'Style name:',
        'style_saved': 'Style saved successfully!',
        'io_page_title': 'Input & Output',
        'input_method': 'Input:',
        'output_method': 'Output:',
        'upload_docx': 'Upload DOCX File',
        'paste_text': 'Paste Text',
        'output_docx': 'DOCX',
        'output_txt': 'TXT',
        'output_interface': 'Interface',
        'references': 'References:',
        'enter_references': 'Enter references (one per line)',
        'process': '🚀 Process',
        'results_page_title': 'Results & Statistics',
        'download_results': 'Download Results',
        'statistics': 'Statistics',
        'journal_frequency': 'Journal Frequency',
        'year_distribution': 'Year Distribution',
        'author_distribution': 'Author Distribution',
        'total_references': 'Total References:',
        'doi_found': 'DOI Found:',
        'doi_not_found': 'DOI Not Found:',
        'back_button': '← Back',
        'clear_all_button': '🗑️ Clear All',
        'next_button': 'Next →',
        'prev_button': '← Previous',
        'apply_button': 'Apply Style',
        'continue_button': 'Continue to Input/Output',
        'theme_selector': 'Theme:',
        'language_selector': 'Language:',
        'theme_light': 'Light',
        'theme_dark': 'Dark',
        'theme_library': 'Library',
        'theme_barbie': 'Barbie',
        'theme_neon': 'Neon',
        'processing': '⏳ Processing...',
        'upload_file': 'Upload a file!',
        'enter_references_error': 'Enter references!',
        'no_style_selected': 'Please select a style!',
        'no_elements_selected': 'Please configure at least one element!',
        'validation_error_too_many_references': 'Too many references (maximum {} allowed)',
        'validation_warning_few_references': 'Few references for meaningful statistics',
        'select_docx_output': 'Select DOCX output to download!',
        'download_doi_txt': '📄 Download DOI List (TXT)',
        'download_ref_docx': '📋 Download References (DOCX)',
        'duplicate_reference': '🔄 Repeated Reference (See #{})',
        'cache_initialized': 'Cache initialized successfully',
        'cache_cleared': 'Cache cleared successfully',
        'style_preset_info': 'Select one of the preset citation styles',
        'create_style_info': 'Create your own custom citation style',
        'load_style_info': 'Load a previously saved style',
        'step_active': 'Active',
        'step_completed': 'Completed',
        'step_pending': 'Pending'
    },
    'ru': {
        'app_title': '🎨 Конструктор стилей цитирования',
        'start_page_title': 'Старт',
        'choose_preset_style': 'Выбрать готовый стиль',
        'create_new_style': 'Создать новый стиль',
        'load_saved_style': 'Загрузить сохраненный стиль',
        'style_page_title': 'Выбор стиля',
        'preset_styles': 'Готовые стили',
        'gost_style': 'ГОСТ',
        'acs_style': 'ACS (MDPI)',
        'rsc_style': 'RSC',
        'cta_style': 'CTA',
        'create_page_title': 'Создание стиля',
        'general_settings': 'Общие настройки',
        'element_configuration': 'Конфигурация элементов',
        'numbering_style': 'Нумерация:',
        'author_format': 'Авторы:',
        'author_separator': 'Разделитель:',
        'et_al_limit': 'Et al после:',
        'use_and': "'и'",
        'use_ampersand': "'&'",
        'doi_format': 'Формат DOI:',
        'doi_hyperlink': 'DOI как ссылка',
        'page_format': 'Страницы:',
        'final_punctuation': 'Конечная пунктуация:',
        'journal_style': 'Стиль журнала:',
        'full_journal_name': 'Полное название журнала',
        'journal_abbr_with_dots': 'J. Abbr.',
        'journal_abbr_no_dots': 'J Abbr',
        'element': 'Элемент',
        'italic': 'Курсив',
        'bold': 'Жирный',
        'parentheses': 'Скобки',
        'separator': 'Разделитель',
        'save_style': '💾 Сохранить стиль',
        'style_name': 'Имя стиля:',
        'style_saved': 'Стиль сохранен успешно!',
        'io_page_title': 'Ввод и вывод',
        'input_method': 'Ввод:',
        'output_method': 'Вывод:',
        'upload_docx': 'Загрузить DOCX файл',
        'paste_text': 'Вставить текст',
        'output_docx': 'DOCX',
        'output_txt': 'TXT',
        'output_interface': 'Интерфейс',
        'references': 'Ссылки:',
        'enter_references': 'Введите ссылки (по одной на строку)',
        'process': '🚀 Обработать',
        'results_page_title': 'Результаты и статистика',
        'download_results': 'Скачать результаты',
        'statistics': 'Статистика',
        'journal_frequency': 'Частота журналов',
        'year_distribution': 'Распределение по годам',
        'author_distribution': 'Распределение авторов',
        'total_references': 'Всего ссылок:',
        'doi_found': 'DOI найдено:',
        'doi_not_found': 'DOI не найдено:',
        'back_button': '← Назад',
        'clear_all_button': '🗑️ Очистить всё',
        'next_button': 'Далее →',
        'prev_button': '← Назад',
        'apply_button': 'Применить стиль',
        'continue_button': 'Продолжить к Вводу/Выводу',
        'theme_selector': 'Тема:',
        'language_selector': 'Язык:',
        'theme_light': 'Светлая',
        'theme_dark': 'Тёмная',
        'theme_library': 'Библиотечная',
        'theme_barbie': 'Барби',
        'theme_neon': 'Неоновая',
        'processing': '⏳ Обработка...',
        'upload_file': 'Загрузите файл!',
        'enter_references_error': 'Введите ссылки!',
        'no_style_selected': 'Пожалуйста, выберите стиль!',
        'no_elements_selected': 'Пожалуйста, настройте хотя бы один элемент!',
        'validation_error_too_many_references': 'Слишком много ссылок (максимум {} разрешено)',
        'validation_warning_few_references': 'Мало ссылок для значимой статистики',
        'select_docx_output': 'Выберите DOCX для скачивания!',
        'download_doi_txt': '📄 Скачать список DOI (TXT)',
        'download_ref_docx': '📋 Скачать ссылки (DOCX)',
        'duplicate_reference': '🔄 Повторная ссылка (См. #{})',
        'cache_initialized': 'Кэш инициализирован успешно',
        'cache_cleared': 'Кэш очищен успешно',
        'style_preset_info': 'Выберите один из готовых стилей цитирования',
        'create_style_info': 'Создайте свой собственный стиль цитирования',
        'load_style_info': 'Загрузите ранее сохраненный стиль',
        'step_active': 'Активно',
        'step_completed': 'Завершено',
        'step_pending': 'Ожидание'
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
            errors.append(get_text('no_elements_selected'))
        
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
        'current_page': 'start',
        'previous_pages': [],
        'selected_preset_style': None,
        'custom_style_created': False,
        
        # Язык и тема
        'current_language': 'en',
        'current_theme': 'light',
        
        # Стиль
        'num': "No numbering",
        'auth': "AA Smith",
        'sep': ", ",
        'etal': 0,
        'use_and_checkbox': False,
        'use_ampersand_checkbox': False,
        'doi': "10.10/xxx",
        'doilink': True,
        'page': "122–128",
        'punct': "",
        'journal_style': '{Full Journal Name}',
        
        # Стили пресеты
        'gost_style': False,
        'acs_style': False,
        'rsc_style': False,
        'cta_style': False,
        
        # Элементы конфигурации
        'el0': "", 'el1': "", 'el2': "", 'el3': "", 'el4': "", 'el5': "", 'el6': "", 'el7': "",
        'it0': False, 'it1': False, 'it2': False, 'it3': False, 'it4': False, 'it5': False, 'it6': False, 'it7': False,
        'bd0': False, 'bd1': False, 'bd2': False, 'bd3': False, 'bd4': False, 'bd5': False, 'bd6': False, 'bd7': False,
        'pr0': False, 'pr1': False, 'pr2': False, 'pr3': False, 'pr4': False, 'pr5': False, 'pr6': False, 'pr7': False,
        'sp0': ". ", 'sp1': ". ", 'sp2': ". ", 'sp3': ". ", 'sp4': ". ", 'sp5': ". ", 'sp6': ". ", 'sp7': ". ",
        
        # Ввод/вывод
        'input_method': 'paste_text',
        'output_method': 'docx',
        'uploaded_file': None,
        'references_text': "",
        'processed_results': None,
        'statistics': None,
        'download_data': {},
        
        # Сохраненные стили
        'saved_styles': {},
        'last_style_update': 0,
        
        # Системные флаги
        'user_prefs_loaded': False,
        'cache_initialized': False,
        'style_import_processed': False,
        'last_imported_file_hash': None,
    }
    
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

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
            
            if i < len(metadata['authors']):
                if i < len(metadata['authors']) - 2:
                    authors_str += "; "
                elif i == len(metadata['authors']) - 2:
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
        status_container.info(get_text('processing'))
        
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

# UI компоненты для нового дизайна
class NewUIComponents:
    """Компоненты пользовательского интерфейса нового дизайна"""
    
    def __init__(self):
        self.user_prefs = UserPreferencesManager()
    
    def apply_theme_styles(self):
        """Применение стилей выбранной темы"""
        theme = Config.THEMES[st.session_state.current_theme]
        
        st.markdown(f"""
            <style>
            /* Основные стили */
            .block-container {{
                padding: 1rem;
                background-color: {theme['background']};
                color: {theme['text']};
                font-family: {theme['font']};
            }}
            
            /* Заголовки */
            h1, h2, h3, h4, h5, h6 {{
                color: {theme['text']} !important;
                font-family: {theme['font']};
            }}
            
            h1 {{ font-size: 1.5rem; margin-bottom: 1rem; }}
            h2 {{ font-size: 1.3rem; margin-bottom: 0.8rem; }}
            h3 {{ font-size: 1.1rem; margin-bottom: 0.6rem; }}
            
            /* Текст */
            p, div, span, label {{
                color: {theme['text']};
                font-family: {theme['font']};
            }}
            
            /* Кнопки */
            .stButton > button {{
                background-color: {theme['primary']};
                color: white;
                border: none;
                padding: 0.5rem 1rem;
                border-radius: 0.3rem;
                font-family: {theme['font']};
                font-weight: 500;
                transition: all 0.3s ease;
            }}
            
            .stButton > button:hover {{
                background-color: {theme['secondary']};
                transform: translateY(-1px);
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            }}
            
            /* Карточки */
            .card {{
                background-color: {theme['cardBackground']};
                border: 1px solid {theme['border']};
                border-radius: 0.5rem;
                padding: 1rem;
                margin-bottom: 1rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            
            /* Прогресс-шаги */
            .step-container {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 2rem;
                position: relative;
            }}
            
            .step-container::before {{
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
                display: flex;
                flex-direction: column;
                align-items: center;
                position: relative;
                z-index: 2;
                flex: 1;
            }}
            
            .step-circle {{
                width: 40px;
                height: 40px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                margin-bottom: 0.5rem;
                border: 2px solid {theme['border']};
            }}
            
            .step-active .step-circle {{
                background-color: {theme['primary']};
                color: white;
                border-color: {theme['primary']};
            }}
            
            .step-completed .step-circle {{
                background-color: {theme['success']};
                color: white;
                border-color: {theme['success']};
            }}
            
            .step-pending .step-circle {{
                background-color: {theme['secondaryBackground']};
                color: {theme['text']};
                border-color: {theme['border']};
            }}
            
            .step-label {{
                font-size: 0.8rem;
                text-align: center;
                color: {theme['text']};
            }}
            
            .step-active .step-label {{
                font-weight: bold;
                color: {theme['primary']};
            }}
            
            .step-completed .step-label {{
                color: {theme['success']};
            }}
            
            /* Компактные формы */
            .compact-form {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 0.8rem;
                margin-bottom: 1rem;
            }}
            
            .compact-form-item {{
                display: flex;
                flex-direction: column;
            }}
            
            .compact-form-item label {{
                font-size: 0.85rem;
                margin-bottom: 0.3rem;
                color: {theme['text']};
                font-weight: 500;
            }}
            
            /* Элементы конфигурации - компактные */
            .element-grid {{
                display: grid;
                grid-template-columns: 1fr auto auto auto 1fr;
                gap: 0.3rem;
                align-items: center;
                margin-bottom: 0.3rem;
            }}
            
            .element-grid-header {{
                font-size: 0.8rem;
                font-weight: bold;
                color: {theme['text']};
                margin-bottom: 0.5rem;
            }}
            
            /* Таблицы статистики */
            .stats-table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 1rem;
            }}
            
            .stats-table th, .stats-table td {{
                padding: 0.5rem;
                border: 1px solid {theme['border']};
                text-align: left;
                font-size: 0.85rem;
            }}
            
            .stats-table th {{
                background-color: {theme['secondaryBackground']};
                font-weight: bold;
            }}
            
            .stats-table tr:nth-child(even) {{
                background-color: {theme['cardBackground']};
            }}
            
            /* Уведомления */
            .stAlert {{
                border: 1px solid {theme['border']};
                border-radius: 0.3rem;
                padding: 0.75rem;
                margin-bottom: 1rem;
            }}
            
            /* Навигация */
            .nav-buttons {{
                display: flex;
                justify-content: space-between;
                margin-top: 2rem;
                padding-top: 1rem;
                border-top: 1px solid {theme['border']};
            }}
            
            /* Компактные выпадающие списки */
            .stSelectbox > div > div {{
                padding: 0.3rem !important;
                font-size: 0.85rem !important;
            }}
            
            /* Компактные чекбоксы */
            .stCheckbox > label {{
                font-size: 0.85rem !important;
                padding: 0.2rem !important;
            }}
            
            /* Компактные поля ввода */
            .stTextInput > div > div > input {{
                padding: 0.3rem !important;
                font-size: 0.85rem !important;
            }}
            
            /* Компактные числовые поля */
            .stNumberInput > div > div > input {{
                padding: 0.3rem !important;
                font-size: 0.85rem !important;
            }}
            
            /* Адаптивность */
            @media (max-width: 768px) {{
                .compact-form {{
                    grid-template-columns: 1fr;
                }}
                
                .element-grid {{
                    grid-template-columns: 1fr;
                    gap: 0.5rem;
                }}
                
                .step-container {{
                    flex-wrap: wrap;
                }}
                
                .step {{
                    flex: 0 0 33.333%;
                    margin-bottom: 1rem;
                }}
            }}
            </style>
        """, unsafe_allow_html=True)
    
    def render_header(self):
        """Рендер заголовка приложения с языком и темой"""
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            st.title(get_text('app_title'))
        
        with col2:
            # Выбор языка
            lang_options = [('English', 'en'), ('Русский', 'ru')]
            selected_lang = st.selectbox(
                get_text('language_selector'),
                options=lang_options,
                format_func=lambda x: x[0],
                index=0 if st.session_state.current_language == 'en' else 1,
                key="language_select"
            )
            
            if selected_lang[1] != st.session_state.current_language:
                st.session_state.current_language = selected_lang[1]
                self.user_prefs.save_preferences(
                    self.user_prefs.get_user_ip(),
                    {'language': selected_lang[1], 'theme': st.session_state.current_theme}
                )
                st.rerun()
        
        with col3:
            # Выбор темы
            theme_options = [
                (get_text('theme_light'), 'light'),
                (get_text('theme_dark'), 'dark'),
                (get_text('theme_library'), 'library'),
                (get_text('theme_barbie'), 'barbie'),
                (get_text('theme_neon'), 'neon')
            ]
            selected_theme = st.selectbox(
                get_text('theme_selector'),
                options=theme_options,
                format_func=lambda x: x[0],
                index=['light', 'dark', 'library', 'barbie', 'neon'].index(st.session_state.current_theme),
                key="theme_select"
            )
            
            if selected_theme[1] != st.session_state.current_theme:
                st.session_state.current_theme = selected_theme[1]
                self.user_prefs.save_preferences(
                    self.user_prefs.get_user_ip(),
                    {'language': st.session_state.current_language, 'theme': selected_theme[1]}
                )
                st.rerun()
    
    def render_step_indicator(self):
        """Рендер индикатора шагов"""
        steps = ['start', 'style', 'create', 'io', 'results']
        step_labels = {
            'start': get_text('start_page_title'),
            'style': get_text('style_page_title'),
            'create': get_text('create_page_title'),
            'io': get_text('io_page_title'),
            'results': get_text('results_page_title')
        }
        
        current_page = st.session_state.current_page
        current_index = steps.index(current_page) if current_page in steps else 0
        
        html_steps = ""
        for i, step in enumerate(steps):
            status_class = ""
            if i == current_index:
                status_class = "step-active"
            elif i < current_index:
                status_class = "step-completed"
            else:
                status_class = "step-pending"
            
            html_steps += f"""
                <div class="step {status_class}">
                    <div class="step-circle">{i+1}</div>
                    <div class="step-label">{step_labels[step]}</div>
                </div>
            """
        
        st.markdown(f"""
            <div class="step-container">
                {html_steps}
            </div>
        """, unsafe_allow_html=True)
    
    def render_start_page(self):
        """Рендер стартовой страницы"""
        st.markdown(f"""
            <div class="card">
                <h3>{get_text('start_page_title')}</h3>
                <p>Выберите способ создания стиля цитирования:</p>
            </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"""
                <div class="card" style="text-align: center; cursor: pointer;" 
                     onclick="this.style.boxShadow='0 0 10px {Config.THEMES[st.session_state.current_theme]['primary']}'; setTimeout(() => {{window.parent.document.getElementById('choose-preset-btn').click()}}, 100)">
                    <h4>📋 {get_text('choose_preset_style')}</h4>
                    <p style="font-size: 0.9rem; color: {Config.THEMES[st.session_state.current_theme]['text']}80;">
                        {get_text('style_preset_info')}
                    </p>
                </div>
            """, unsafe_allow_html=True)
            
            if st.button(get_text('choose_preset_style'), key='choose-preset-btn', use_container_width=True):
                st.session_state.previous_pages.append('start')
                st.session_state.current_page = 'style'
                st.rerun()
        
        with col2:
            st.markdown(f"""
                <div class="card" style="text-align: center; cursor: pointer;"
                     onclick="this.style.boxShadow='0 0 10px {Config.THEMES[st.session_state.current_theme]['primary']}'; setTimeout(() => {{window.parent.document.getElementById('create-new-btn').click()}}, 100)">
                    <h4>✨ {get_text('create_new_style')}</h4>
                    <p style="font-size: 0.9rem; color: {Config.THEMES[st.session_state.current_theme]['text']}80;">
                        {get_text('create_style_info')}
                    </p>
                </div>
            """, unsafe_allow_html=True)
            
            if st.button(get_text('create_new_style'), key='create-new-btn', use_container_width=True):
                st.session_state.previous_pages.append('start')
                st.session_state.current_page = 'create'
                st.rerun()
        
        with col3:
            st.markdown(f"""
                <div class="card" style="text-align: center;">
                    <h4>📂 {get_text('load_saved_style')}</h4>
                    <p style="font-size: 0.9rem; color: {Config.THEMES[st.session_state.current_theme]['text']}80;">
                        {get_text('load_style_info')}
                    </p>
                </div>
            """, unsafe_allow_html=True)
            
            uploaded_file = st.file_uploader(
                "Выберите файл стиля",
                type=['json'],
                key="style_uploader",
                label_visibility="collapsed"
            )
            
            if uploaded_file is not None:
                try:
                    style_data = json.loads(uploaded_file.getvalue().decode('utf-8'))
                    self._apply_uploaded_style(style_data)
                    st.success(get_text('style_saved'))
                    st.session_state.previous_pages.append('start')
                    st.session_state.current_page = 'create'
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка загрузки стиля: {str(e)}")
    
    def render_style_page(self):
        """Рендер страницы выбора готового стиля"""
        st.markdown(f"""
            <div class="card">
                <h3>{get_text('style_page_title')}</h3>
                <p>Выберите один из готовых стилей цитирования:</p>
            </div>
        """, unsafe_allow_html=True)
        
        cols = st.columns(4)
        
        styles = [
            ('gost_style', get_text('gost_style'), '🇷🇺'),
            ('acs_style', get_text('acs_style'), '🔬'),
            ('rsc_style', get_text('rsc_style'), '⚗️'),
            ('cta_style', get_text('cta_style'), '📊')
        ]
        
        for idx, (style_key, style_name, emoji) in enumerate(styles):
            with cols[idx]:
                if st.button(f"{emoji} {style_name}", use_container_width=True, key=f"style_{style_key}"):
                    # Сброс предыдущих стилей
                    for key in ['gost_style', 'acs_style', 'rsc_style', 'cta_style']:
                        st.session_state[key] = False
                    
                    # Установка выбранного стиля
                    st.session_state[style_key] = True
                    st.session_state.selected_preset_style = style_key
                    
                    # Переход к следующей странице
                    st.session_state.previous_pages.append('style')
                    st.session_state.current_page = 'io'
                    st.rerun()
        
        # Кнопки навигации
        col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
        with col_nav1:
            if st.button(get_text('back_button'), use_container_width=True, key="style_back"):
                if st.session_state.previous_pages:
                    st.session_state.current_page = st.session_state.previous_pages.pop()
                    st.rerun()
        
        with col_nav3:
            if st.button(get_text('next_button'), use_container_width=True, key="style_next"):
                if st.session_state.selected_preset_style:
                    st.session_state.previous_pages.append('style')
                    st.session_state.current_page = 'io'
                    st.rerun()
                else:
                    st.warning(get_text('no_style_selected'))
    
    def render_create_page(self):
        """Рендер страницы создания стиля"""
        st.markdown(f"""
            <div class="card">
                <h3>{get_text('create_page_title')}</h3>
                <p>Настройте параметры вашего стиля цитирования:</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Общие настройки - компактная форма
        st.markdown(f"<h4>{get_text('general_settings')}</h4>", unsafe_allow_html=True)
        
        # Используем компактную сетку для настроек
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.session_state.num = st.selectbox(
                get_text('numbering_style'),
                Config.NUMBERING_STYLES,
                index=Config.NUMBERING_STYLES.index(st.session_state.num),
                key="create_num"
            )
            
            st.session_state.auth = st.selectbox(
                get_text('author_format'),
                Config.AUTHOR_FORMATS,
                index=Config.AUTHOR_FORMATS.index(st.session_state.auth),
                key="create_auth"
            )
            
            st.session_state.sep = st.selectbox(
                get_text('author_separator'),
                [", ", "; "],
                index=[", ", "; "].index(st.session_state.sep),
                key="create_sep"
            )
        
        with col2:
            st.session_state.etal = st.number_input(
                get_text('et_al_limit'),
                min_value=0,
                value=st.session_state.etal,
                key="create_etal"
            )
            
            col_and, col_amp = st.columns(2)
            with col_and:
                st.session_state.use_and_checkbox = st.checkbox(
                    get_text('use_and'),
                    value=st.session_state.use_and_checkbox,
                    key="create_and",
                    disabled=st.session_state.use_ampersand_checkbox
                )
            with col_amp:
                st.session_state.use_ampersand_checkbox = st.checkbox(
                    get_text('use_ampersand'),
                    value=st.session_state.use_ampersand_checkbox,
                    key="create_amp",
                    disabled=st.session_state.use_and_checkbox
                )
            
            st.session_state.journal_style = st.selectbox(
                get_text('journal_style'),
                Config.JOURNAL_STYLES,
                index=Config.JOURNAL_STYLES.index(st.session_state.journal_style),
                format_func=lambda x: {
                    "{Full Journal Name}": get_text('full_journal_name'),
                    "{J. Abbr.}": get_text('journal_abbr_with_dots'),
                    "{J Abbr}": get_text('journal_abbr_no_dots')
                }[x],
                key="create_journal"
            )
        
        with col3:
            current_page = st.session_state.page
            page_index = 3
            if current_page in Config.PAGE_FORMATS:
                page_index = Config.PAGE_FORMATS.index(current_page)
            
            st.session_state.page = st.selectbox(
                get_text('page_format'),
                Config.PAGE_FORMATS,
                index=page_index,
                key="create_page"
            )
            
            st.session_state.doi = st.selectbox(
                get_text('doi_format'),
                Config.DOI_FORMATS,
                index=Config.DOI_FORMATS.index(st.session_state.doi),
                key="create_doi"
            )
            
            st.session_state.doilink = st.checkbox(
                get_text('doi_hyperlink'),
                value=st.session_state.doilink,
                key="create_doilink"
            )
            
            st.session_state.punct = st.selectbox(
                get_text('final_punctuation'),
                ["", "."],
                index=["", "."].index(st.session_state.punct),
                key="create_punct"
            )
        
        # Конфигурация элементов - компактная форма
        st.markdown(f"<h4>{get_text('element_configuration')}</h4>", unsafe_allow_html=True)
        
        # Заголовки столбцов
        col_headers = st.columns([2, 1, 1, 1, 2])
        with col_headers[0]:
            st.markdown(f"<div class='element-grid-header'>{get_text('element')}</div>", unsafe_allow_html=True)
        with col_headers[1]:
            st.markdown(f"<div class='element-grid-header'>{get_text('italic')}</div>", unsafe_allow_html=True)
        with col_headers[2]:
            st.markdown(f"<div class='element-grid-header'>{get_text('bold')}</div>", unsafe_allow_html=True)
        with col_headers[3]:
            st.markdown(f"<div class='element-grid-header'>{get_text('parentheses')}</div>", unsafe_allow_html=True)
        with col_headers[4]:
            st.markdown(f"<div class='element-grid-header'>{get_text('separator')}</div>", unsafe_allow_html=True)
        
        # Элементы конфигурации
        for i in range(8):
            cols = st.columns([2, 1, 1, 1, 2])
            
            with cols[0]:
                st.session_state[f"el{i}"] = st.selectbox(
                    "",
                    Config.AVAILABLE_ELEMENTS,
                    index=Config.AVAILABLE_ELEMENTS.index(st.session_state[f"el{i}"]) if st.session_state[f"el{i}"] in Config.AVAILABLE_ELEMENTS else 0,
                    key=f"create_el{i}",
                    label_visibility="collapsed"
                )
            
            with cols[1]:
                st.session_state[f"it{i}"] = st.checkbox(
                    "",
                    value=st.session_state[f"it{i}"],
                    key=f"create_it{i}",
                    label_visibility="collapsed"
                )
            
            with cols[2]:
                st.session_state[f"bd{i}"] = st.checkbox(
                    "",
                    value=st.session_state[f"bd{i}"],
                    key=f"create_bd{i}",
                    label_visibility="collapsed"
                )
            
            with cols[3]:
                st.session_state[f"pr{i}"] = st.checkbox(
                    "",
                    value=st.session_state[f"pr{i}"],
                    key=f"create_pr{i}",
                    label_visibility="collapsed"
                )
            
            with cols[4]:
                st.session_state[f"sp{i}"] = st.text_input(
                    "",
                    value=st.session_state[f"sp{i}"],
                    key=f"create_sp{i}",
                    label_visibility="collapsed"
                )
        
        # Сохранение стиля и навигация
        col_save, col_nav1, col_nav2, col_nav3 = st.columns([2, 1, 1, 1])
        
        with col_save:
            style_name = st.text_input(
                get_text('style_name'),
                value="my_style",
                key="style_name_input"
            )
            
            if st.button(get_text('save_style'), use_container_width=True, key="save_style_btn"):
                style_config = self._get_style_config()
                style_data = {
                    'name': style_name,
                    'config': style_config,
                    'created': datetime.now().isoformat()
                }
                
                # Сохранение в session_state
                if 'saved_styles' not in st.session_state:
                    st.session_state.saved_styles = {}
                st.session_state.saved_styles[style_name] = style_data
                
                # Предложение скачать
                json_data = json.dumps(style_data, indent=2, ensure_ascii=False)
                st.download_button(
                    label="📥 Download Style",
                    data=json_data.encode('utf-8'),
                    file_name=f"{style_name}.json",
                    mime="application/json"
                )
                
                st.success(get_text('style_saved'))
        
        with col_nav1:
            if st.button(get_text('back_button'), use_container_width=True, key="create_back"):
                if st.session_state.previous_pages:
                    st.session_state.current_page = st.session_state.previous_pages.pop()
                    st.rerun()
        
        with col_nav2:
            if st.button(get_text('clear_all_button'), use_container_width=True, key="create_clear"):
                self._reset_create_page()
                st.rerun()
        
        with col_nav3:
            if st.button(get_text('continue_button'), use_container_width=True, key="create_continue"):
                # Проверка, что хотя бы один элемент выбран
                has_elements = any(st.session_state[f"el{i}"] for i in range(8))
                if has_elements:
                    st.session_state.previous_pages.append('create')
                    st.session_state.current_page = 'io'
                    st.session_state.custom_style_created = True
                    st.rerun()
                else:
                    st.warning(get_text('no_elements_selected'))
    
    def render_io_page(self):
        """Рендер страницы ввода/вывода"""
        st.markdown(f"""
            <div class="card">
                <h3>{get_text('io_page_title')}</h3>
                <p>Настройте параметры ввода и вывода данных:</p>
            </div>
        """, unsafe_allow_html=True)
        
        col_input, col_output = st.columns(2)
        
        with col_input:
            st.markdown(f"<h4>{get_text('input_method')}</h4>", unsafe_allow_html=True)
            
            input_method = st.radio(
                "",
                ['upload_docx', 'paste_text'],
                format_func=lambda x: get_text(x),
                index=0 if st.session_state.input_method == 'upload_docx' else 1,
                key="io_input_method",
                horizontal=True
            )
            
            st.session_state.input_method = input_method
            
            if input_method == 'upload_docx':
                uploaded_file = st.file_uploader(
                    get_text('upload_docx'),
                    type=['docx'],
                    key="io_file_uploader"
                )
                if uploaded_file:
                    st.session_state.uploaded_file = uploaded_file
            else:
                references_text = st.text_area(
                    get_text('references'),
                    placeholder=get_text('enter_references'),
                    height=150,
                    key="io_references_text"
                )
                st.session_state.references_text = references_text
        
        with col_output:
            st.markdown(f"<h4>{get_text('output_method')}</h4>", unsafe_allow_html=True)
            
            output_method = st.radio(
                "",
                ['docx', 'txt', 'interface'],
                format_func=lambda x: get_text(f'output_{x}'),
                index=['docx', 'txt', 'interface'].index(st.session_state.output_method),
                key="io_output_method",
                horizontal=True
            )
            
            st.session_state.output_method = output_method
            
            if output_method == 'interface':
                st.info("Результаты будут отображены в интерфейсе")
        
        # Кнопка обработки
        col_process, col_nav1, col_nav2 = st.columns([2, 1, 1])
        
        with col_process:
            if st.button(get_text('process'), use_container_width=True, key="io_process"):
                self._process_io_data()
        
        with col_nav1:
            if st.button(get_text('back_button'), use_container_width=True, key="io_back"):
                if st.session_state.previous_pages:
                    st.session_state.current_page = st.session_state.previous_pages.pop()
                    st.rerun()
        
        with col_nav2:
            if st.button(get_text('clear_all_button'), use_container_width=True, key="io_clear"):
                self._reset_io_page()
                st.rerun()
    
    def render_results_page(self):
        """Рендер страницы результатов"""
        st.markdown(f"""
            <div class="card">
                <h3>{get_text('results_page_title')}</h3>
                <p>Результаты обработки и статистика:</p>
            </div>
        """, unsafe_allow_html=True)
        
        if st.session_state.processed_results:
            formatted_refs, txt_buffer, doi_found_count, doi_not_found_count, duplicates_info = st.session_state.processed_results
            
            # Скачивание результатов
            st.markdown(f"<h4>{get_text('download_results')}</h4>", unsafe_allow_html=True)
            
            col_dl1, col_dl2 = st.columns(2)
            
            with col_dl1:
                st.download_button(
                    label=get_text('download_doi_txt'),
                    data=txt_buffer,
                    file_name='doi_list.txt',
                    mime='text/plain',
                    use_container_width=True
                )
            
            with col_dl2:
                if st.session_state.output_method == 'docx':
                    # Генерация DOCX
                    style_config = self._get_style_config()
                    statistics = generate_statistics(formatted_refs)
                    docx_buffer = DocumentGenerator.generate_document(
                        formatted_refs, statistics, style_config, duplicates_info
                    )
                    
                    st.download_button(
                        label=get_text('download_ref_docx'),
                        data=docx_buffer,
                        file_name='formatted_references.docx',
                        mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        use_container_width=True
                    )
            
            # Статистика
            st.markdown(f"<h4>{get_text('statistics')}</h4>", unsafe_allow_html=True)
            
            # Основная статистика
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            
            with col_stat1:
                st.metric(
                    get_text('total_references'),
                    len(formatted_refs)
                )
            
            with col_stat2:
                st.metric(
                    get_text('doi_found'),
                    doi_found_count
                )
            
            with col_stat3:
                st.metric(
                    get_text('doi_not_found'),
                    doi_not_found_count
                )
            
            # Подробная статистика
            if st.session_state.statistics:
                statistics = st.session_state.statistics
                
                # Частота журналов
                st.markdown(f"<h5>{get_text('journal_frequency')}</h5>", unsafe_allow_html=True)
                if statistics['journal_stats']:
                    journal_df = pd.DataFrame(statistics['journal_stats'])
                    st.dataframe(journal_df, use_container_width=True)
                
                # Распределение по годам
                st.markdown(f"<h5>{get_text('year_distribution')}</h5>", unsafe_allow_html=True)
                if statistics['year_stats']:
                    year_df = pd.DataFrame(statistics['year_stats'])
                    st.dataframe(year_df, use_container_width=True)
                
                # Распределение авторов
                st.markdown(f"<h5>{get_text('author_distribution')}</h5>", unsafe_allow_html=True)
                if statistics['author_stats']:
                    author_df = pd.DataFrame(statistics['author_stats'])
                    st.dataframe(author_df, use_container_width=True)
        
        # Кнопки навигации
        col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
        
        with col_nav1:
            if st.button(get_text('back_button'), use_container_width=True, key="results_back"):
                if st.session_state.previous_pages:
                    st.session_state.current_page = st.session_state.previous_pages.pop()
                    st.rerun()
        
        with col_nav3:
            if st.button(get_text('clear_all_button'), use_container_width=True, key="results_clear"):
                self._reset_all()
                st.session_state.current_page = 'start'
                st.rerun()
    
    def _get_style_config(self):
        """Получение конфигурации стиля"""
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
    
    def _apply_uploaded_style(self, style_data):
        """Применение загруженного стиля"""
        if 'config' in style_data:
            config = style_data['config']
            
            # Применение общих настроек
            if 'author_format' in config:
                st.session_state.auth = config['author_format']
            if 'author_separator' in config:
                st.session_state.sep = config['author_separator']
            if 'et_al_limit' in config:
                st.session_state.etal = config['et_al_limit'] or 0
            if 'use_and_bool' in config:
                st.session_state.use_and_checkbox = config['use_and_bool']
            if 'use_ampersand_bool' in config:
                st.session_state.use_ampersand_checkbox = config['use_ampersand_bool']
            if 'doi_format' in config:
                st.session_state.doi = config['doi_format']
            if 'doi_hyperlink' in config:
                st.session_state.doilink = config['doi_hyperlink']
            if 'page_format' in config:
                st.session_state.page = config['page_format']
            if 'final_punctuation' in config:
                st.session_state.punct = config['final_punctuation']
            if 'numbering_style' in config:
                st.session_state.num = config['numbering_style']
            if 'journal_style' in config:
                st.session_state.journal_style = config['journal_style']
            
            # Применение элементов
            elements = config.get('elements', [])
            for i in range(8):
                if i < len(elements):
                    element, element_config = elements[i]
                    st.session_state[f"el{i}"] = element
                    st.session_state[f"it{i}"] = element_config.get('italic', False)
                    st.session_state[f"bd{i}"] = element_config.get('bold', False)
                    st.session_state[f"pr{i}"] = element_config.get('parentheses', False)
                    st.session_state[f"sp{i}"] = element_config.get('separator', ". ")
                else:
                    st.session_state[f"el{i}"] = ""
                    st.session_state[f"it{i}"] = False
                    st.session_state[f"bd{i}"] = False
                    st.session_state[f"pr{i}"] = False
                    st.session_state[f"sp{i}"] = ". "
    
    def _process_io_data(self):
        """Обработка данных ввода/вывода"""
        processor = ReferenceProcessor()
        style_config = self._get_style_config()
        
        # Получение ссылок
        references = []
        if st.session_state.input_method == 'upload_docx' and st.session_state.uploaded_file:
            doc = Document(st.session_state.uploaded_file)
            references = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
        elif st.session_state.input_method == 'paste_text' and st.session_state.references_text:
            references = [ref.strip() for ref in st.session_state.references_text.split('\n') if ref.strip()]
        
        if not references:
            st.error(get_text('enter_references_error'))
            return
        
        # Обработка
        progress_container = st.empty()
        status_container = st.empty()
        
        with st.spinner(get_text('processing')):
            try:
                results = processor.process_references(
                    references, style_config, progress_container, status_container
                )
                
                st.session_state.processed_results = results
                st.session_state.statistics = generate_statistics(results[0])
                st.session_state.previous_pages.append('io')
                st.session_state.current_page = 'results'
                st.rerun()
                
            except Exception as e:
                st.error(f"Ошибка обработки: {str(e)}")
    
    def _reset_create_page(self):
        """Сброс страницы создания стиля"""
        st.session_state.num = "No numbering"
        st.session_state.auth = "AA Smith"
        st.session_state.sep = ", "
        st.session_state.etal = 0
        st.session_state.use_and_checkbox = False
        st.session_state.use_ampersand_checkbox = False
        st.session_state.doi = "10.10/xxx"
        st.session_state.doilink = True
        st.session_state.page = "122–128"
        st.session_state.punct = ""
        st.session_state.journal_style = '{Full Journal Name}'
        
        for i in range(8):
            st.session_state[f"el{i}"] = ""
            st.session_state[f"it{i}"] = False
            st.session_state[f"bd{i}"] = False
            st.session_state[f"pr{i}"] = False
            st.session_state[f"sp{i}"] = ". "
    
    def _reset_io_page(self):
        """Сброс страницы ввода/вывода"""
        st.session_state.input_method = 'paste_text'
        st.session_state.output_method = 'docx'
        st.session_state.uploaded_file = None
        st.session_state.references_text = ""
        st.session_state.processed_results = None
        st.session_state.statistics = None
    
    def _reset_all(self):
        """Полный сброс"""
        self._reset_create_page()
        self._reset_io_page()
        st.session_state.current_page = 'start'
        st.session_state.previous_pages = []
        st.session_state.selected_preset_style = None
        st.session_state.custom_style_created = False

# Основной класс приложения
class CitationStyleApp:
    """Основной класс приложения нового дизайна"""
    
    def __init__(self):
        self.ui = NewUIComponents()
        init_session_state()
    
    def run(self):
        """Запуск приложения"""
        st.set_page_config(layout="wide", page_title=get_text('app_title'))
        
        # Загрузка пользовательских предпочтений
        if not st.session_state.user_prefs_loaded:
            ip = self.ui.user_prefs.get_user_ip()
            prefs = self.ui.user_prefs.get_preferences(ip)
            
            st.session_state.current_language = prefs.get('language', 'en')
            st.session_state.current_theme = prefs.get('theme', 'light')
            st.session_state.user_prefs_loaded = True
        
        # Применение стилей темы
        self.ui.apply_theme_styles()
        
        # Рендер заголовка
        self.ui.render_header()
        
        # Рендер индикатора шагов
        self.ui.render_step_indicator()
        
        # Рендер текущей страницы
        current_page = st.session_state.current_page
        
        if current_page == 'start':
            self.ui.render_start_page()
        elif current_page == 'style':
            self.ui.render_style_page()
        elif current_page == 'create':
            self.ui.render_create_page()
        elif current_page == 'io':
            self.ui.render_io_page()
        elif current_page == 'results':
            self.ui.render_results_page()

# Вспомогательные функции (оставлены без изменений)
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

# Импорт pandas для отображения статистики
try:
    import pandas as pd
except ImportError:
    pd = None
    st.warning("Для отображения статистики установите pandas: pip install pandas")

def main():
    """Основная функция"""
    app = CitationStyleApp()
    app.run()

if __name__ == "__main__":
    main()
