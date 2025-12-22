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
            'toolbar': '#e9ecef'
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
            'toolbar': '#343a40'
        }
    }
    
    # Интерфейсные константы
    UI_MODES = ['toolbar_mode', 'timeline_mode']
    UI_MODE_NAMES = {
        'en': {
            'toolbar_mode': 'Toolbar Mode',
            'timeline_mode': 'Timeline Mode'
        },
        'ru': {
            'toolbar_mode': 'Режим панели',
            'timeline_mode': 'Режим таймлайна'
        }
    }

# Инициализация Crossref
works = Works()

# Полный словарь переводов (только русский и английский)
TRANSLATIONS = {
    'en': {
        # Основные
        'header': '🎨 Citation Style Constructor',
        'general_settings': '⚙️ General Settings',
        'element_config': '📑 Element Configuration',
        'style_preview': '👀 Style Preview',
        'data_input': '📁 Data Input',
        'data_output': '📤 Data Output',
        
        # Настройки
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
        
        # Элементы
        'element': 'Element',
        'italic': 'Italic',
        'bold': 'Bold',
        'parentheses': 'Parentheses',
        'separator': 'Separator',
        
        # Ввод/вывод
        'input_method': 'Input:',
        'output_method': 'Output:',
        'select_docx': 'Select DOCX',
        'enter_references': 'Enter references (one per line)',
        'references': 'References:',
        'results': 'Results:',
        'process': '🚀 Process',
        'example': 'Example:',
        
        # Ошибки и уведомления
        'error_select_element': 'Select at least one element!',
        'processing': '⏳ Processing...',
        'upload_file': 'Upload a file!',
        'enter_references_error': 'Enter references!',
        'select_docx_output': 'Select DOCX output to download!',
        'found_references': 'Found {} references.',
        'found_references_text': 'Found {} references in text.',
        'statistics': 'Statistics: {} DOI found, {} not found.',
        
        # Язык и тема
        'language': 'Language:',
        'theme_selector': 'Theme:',
        'light_theme': 'Light',
        'dark_theme': 'Dark',
        
        # Стили
        'gost_style': 'Apply GOST Style',
        'style_presets': 'Style Presets',
        'gost_button': 'GOST',
        'acs_button': 'ACS (MDPI)',
        'rsc_button': 'RSC',
        'cta_button': 'CTA',
        'style_preset_tooltip': 'Here are some styles maintained by individual publishers. For major publishers (Elsevier, Springer Nature, Wiley), styles vary from journal to journal. To create (or reformat) references for a specific journal, use the Citation Style Constructor.',
        
        # Управление стилями
        'export_style': '📤 Export Style',
        'import_style': '📥 Import Style',
        'export_file_name': 'File name:',
        'import_file': 'Select style file:',
        'export_success': 'Style exported successfully!',
        'import_success': 'Style imported successfully!',
        'import_error': 'Error importing style file!',
        
        # Прогресс
        'processing_status': 'Processing references...',
        'current_reference': 'Current: {}',
        'processed_stats': 'Processed: {}/{} | Found: {} | Errors: {}',
        'time_remaining': 'Estimated time remaining: {}',
        'duplicate_reference': '🔄 Repeated Reference (See #{})',
        'batch_processing': 'Batch processing DOI...',
        'extracting_metadata': 'Extracting metadata...',
        'checking_duplicates': 'Checking for duplicates...',
        'retrying_failed': 'Retrying failed DOI requests...',
        'bibliographic_search': 'Searching by bibliographic data...',
        
        # Руководство
        'short_guide_title': 'A short guide for the conversion of doi-based references',
        'step_1': '❶ Select a ready reference style (ACS(MDPI), RSC, or CTA), or create your own style by selecting the sequence, design, and punctuation of the element configurations',
        'step_1_note': '(!) The punctuation boxes enable various items to be included between element configurations (simple punctuation, Vol., Issue…)',
        'step_2': '❷ Then, use the Style Presets to change certain element configurations for each reformatted reference.',
        'step_3': '❸ The Style Preview function enables users to visualize the final form of their reference style',
        'step_4': '❹ If the final style is appropriate, select the Docx or Text option in the Data Input section and upload the corresponding information (reference list). Then, in the Data Output section, select the required options and press "Process" to initiate reformatting.',
        'step_5': '❺ After processing is complete, download the reformatted references in your preferred format.',
        'step_5_note': '(!) Outputting the Docx file is recommended, as it preserves formatting (e.g., bold, italic, and hyperlinks) and includes additional stats at the end of the document.',
        'step_6': '❻ After creating your final version of the style, save it so that you can upload it again in the next session. Use the Style Management section for this purpose.',
        
        # Валидация
        'validation_error_no_elements': 'Please configure at least one element or select a preset style!',
        'validation_error_too_many_references': 'Too many references (maximum {} allowed)',
        'validation_warning_few_references': 'Few references for meaningful statistics',
        
        # Кэш
        'cache_initialized': 'Cache initialized successfully',
        'cache_cleared': 'Cache cleared successfully',
        
        # Вид
        'mobile_view': 'Mobile View',
        'desktop_view': 'Desktop View',
        'ui_mode': 'Interface Mode:',
        
        # Новые для таймлайн режима
        'timeline_editor': 'Timeline Editor',
        'style_sequencer': 'Style Sequencer',
        'element_track': 'Element Track',
        'drag_to_reorder': 'Drag to reorder',
        'add_element': '+ Add Element',
        'properties_panel': 'Properties Panel',
        'preview_monitor': 'Preview Monitor',
        'media_pool': 'Media Pool',
        'import_references': 'Import References',
        'render_output': 'Render Output',
        'track_authors': 'Authors Track',
        'track_title': 'Title Track',
        'track_journal': 'Journal Track',
        'track_year': 'Year Track',
        'track_volume': 'Volume Track',
        'track_pages': 'Pages Track',
        'track_doi': 'DOI Track',
        'empty_timeline': 'Drag elements here to build your citation style',
        
        # Новые для toolbar режима
        'quick_styles': 'Quick Styles',
        'tools': 'Tools',
        'style_builder': 'Style Builder',
        'format_options': 'Format Options',
        'upload_process': 'Upload & Process',
        'download_section': 'Download',
        'card_style': 'Style',
        'card_input': 'Input',
        'card_output': 'Output',
        
        # Кнопки
        'clear_button': '🗑️ Clear',
        'back_button': '↩️ Back',
        'save_button': '💾 Save',
        'load_button': '📂 Load',
        'reset_button': '🔄 Reset',
        'help_button': '❓ Help'
    },
    'ru': {
        # Основные
        'header': '🎨 Конструктор стилей цитирования',
        'general_settings': '⚙️ Настройки',
        'element_config': '📑 Конфигурация элементов',
        'style_preview': '👀 Предпросмотр',
        'data_input': '📁 Ввод',
        'data_output': '📤 Вывод',
        
        # Настройки
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
        
        # Элементы
        'element': 'Элемент',
        'italic': 'Курсив',
        'bold': 'Жирный',
        'parentheses': 'Скобки',
        'separator': 'Разделитель',
        
        # Ввод/вывод
        'input_method': 'Ввод:',
        'output_method': 'Вывод:',
        'select_docx': 'Выберите DOCX',
        'enter_references': 'Введите ссылки (по одной на строку)',
        'references': 'Ссылки:',
        'results': 'Результаты:',
        'process': '🚀 Обработать',
        'example': 'Пример:',
        
        # Ошибки и уведомления
        'error_select_element': 'Выберите хотя бы один элемент!',
        'processing': '⏳ Обработка...',
        'upload_file': 'Загрузите файл!',
        'enter_references_error': 'Введите ссылки!',
        'select_docx_output': 'Выберите DOCX для скачивания!',
        'found_references': 'Найдено {} ссылок.',
        'found_references_text': 'Найдено {} ссылок в тексте.',
        'statistics': 'Статистика: {} DOI найдено, {} не найдено.',
        
        # Язык и тема
        'language': 'Язык:',
        'theme_selector': 'Тема:',
        'light_theme': 'Светлая',
        'dark_theme': 'Тёмная',
        
        # Стили
        'gost_style': 'Применить стиль ГОСТ',
        'style_presets': 'Готовые стили',
        'gost_button': 'ГОСТ',
        'acs_button': 'ACS (MDPI)',
        'rsc_button': 'RSC',
        'cta_button': 'CTA',
        'style_preset_tooltip': 'Здесь указаны некоторые стили, которые сохраняются в пределах одного издательства. Для ряда крупных издательств (Esevier, Springer Nature, Wiley) стиль отличается от журнала к журналу. Для формирования (или переформатирования) ссылок для конкретного журнала предлагаем воспользоваться конструктором ссылок.',
        
        # Управление стилями
        'export_style': '📤 Экспорт стиля',
        'import_style': '📥 Импорт стиля',
        'export_file_name': 'Имя файла:',
        'import_file': 'Выберите файл стиля:',
        'export_success': 'Стиль экспортирован успешно!',
        'import_success': 'Стиль импортирован успешно!',
        'import_error': 'Ошибка импорта файла стиля!',
        
        # Прогресс
        'processing_status': 'Обработка ссылок...',
        'current_reference': 'Текущая: {}',
        'processed_stats': 'Обработано: {}/{} | Найдено: {} | Ошибки: {}',
        'time_remaining': 'Примерное время до завершения: {}',
        'duplicate_reference': '🔄 Повторная ссылка (См. #{})',
        'batch_processing': 'Пакетная обработка DOI...',
        'extracting_metadata': 'Извлечение метаданных...',
        'checking_duplicates': 'Проверка на дубликаты...',
        'retrying_failed': 'Повторная попытка для неудачных DOI...',
        'bibliographic_search': 'Поиск по библиографическим данным...',
        
        # Руководство
        'short_guide_title': 'Краткое руководство для конвертации ссылок, имеющих doi',
        'step_1': '❶ Выберите готовый стиль ссылок (ГОСТ, ACS(MDPI), RSC или CTA) или создайте свой собственный стиль, выбрав последовательность, оформление и пунктуацию конфигураций элементов',
        'step_1_note': '(!) Поля пунктуации позволяют включать различные элементы между конфигурациями (простая пунктуация, Том, Выпуск…)',
        'step_2': '❷ Затем используйте готовые стили, чтобы изменить определенные конфигурации элементов для каждой переформатированной ссылки.',
        'step_3': '❸ Функция предпросмотра стиля позволяет визуализировать окончательную форму вашего стиля ссылок',
        'step_4': '❹ Если окончательный стиль подходит, выберите опцию Docx или Текст в разделе ввода данных и загрузите соответствующую информацию (список литературы). Затем в разделе вывода данных выберите нужные опции и нажмите "Обработать" для начала переформатирования.',
        'step_5': '❺ После завершения обработки загрузите переформатированные ссылки в предпочитаемом формате.',
        'step_5_note': '(!) Рекомендуется выводить файл Docx, так как он сохраняет форматирование (например, жирный шрифт, курсив и гиперссылки) и включает дополнительную статистику в конце документа.',
        'step_6': '❻ После создания окончательной версии стиля сохраните его, чтобы можно было снова загрузить в следующей сессии. Для этого используйте раздел Style Management.',
        
        # Валидация
        'validation_error_no_elements': 'Пожалуйста, настройте хотя бы один элемент или выберите готовый стиль!',
        'validation_error_too_many_references': 'Слишком много ссылок (максимум {} разрешено)',
        'validation_warning_few_references': 'Мало ссылок для значимой статистики',
        
        # Кэш
        'cache_initialized': 'Кэш инициализирован успешно',
        'cache_cleared': 'Кэш очищен успешно',
        
        # Вид
        'mobile_view': 'Мобильный вид',
        'desktop_view': 'Десктопный вид',
        'ui_mode': 'Режим интерфейса:',
        
        # Новые для таймлайн режима
        'timeline_editor': 'Таймлайн редактор',
        'style_sequencer': 'Секвенсер стилей',
        'element_track': 'Дорожка элемента',
        'drag_to_reorder': 'Перетащите для изменения порядка',
        'add_element': '+ Добавить элемент',
        'properties_panel': 'Панель свойств',
        'preview_monitor': 'Монитор предпросмотра',
        'media_pool': 'Медиапул',
        'import_references': 'Импорт ссылок',
        'render_output': 'Рендер вывода',
        'track_authors': 'Дорожка авторов',
        'track_title': 'Дорожка заголовка',
        'track_journal': 'Дорожка журнала',
        'track_year': 'Дорожка года',
        'track_volume': 'Дорожка тома',
        'track_pages': 'Дорожка страниц',
        'track_doi': 'Дорожка DOI',
        'empty_timeline': 'Перетащите элементы сюда для построения стиля цитирования',
        
        # Новые для toolbar режима
        'quick_styles': 'Быстрые стили',
        'tools': 'Инструменты',
        'style_builder': 'Конструктор стилей',
        'format_options': 'Опции форматирования',
        'upload_process': 'Загрузить и обработать',
        'download_section': 'Скачивание',
        'card_style': 'Стиль',
        'card_input': 'Ввод',
        'card_output': 'Вывод',
        
        # Кнопки
        'clear_button': '🗑️ Очистить',
        'back_button': '↩️ Назад',
        'save_button': '💾 Сохранить',
        'load_button': '📂 Загрузить',
        'reset_button': '🔄 Сбросить',
        'help_button': '❓ Помощь'
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
                    ui_mode TEXT DEFAULT 'toolbar_mode',
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
                    'SELECT language, theme, mobile_view, ui_mode FROM user_preferences WHERE ip_address = ?',
                    (ip,)
                ).fetchone()
                
                if result:
                    return {
                        'language': result[0],
                        'theme': result[1],
                        'mobile_view': bool(result[2]),
                        'ui_mode': result[3] if result[3] else 'toolbar_mode'
                    }
        except Exception as e:
            logger.error(f"Error getting preferences for {ip}: {e}")
        
        return {
            'language': 'en',
            'theme': 'light',
            'mobile_view': False,
            'ui_mode': 'toolbar_mode'
        }
    
    def save_preferences(self, ip: str, preferences: Dict[str, Any]):
        """Сохранение предпочтений пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO user_preferences 
                    (ip_address, language, theme, mobile_view, ui_mode, updated_at) 
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    ip,
                    preferences.get('language', 'en'),
                    preferences.get('theme', 'light'),
                    int(preferences.get('mobile_view', False)),
                    preferences.get('ui_mode', 'toolbar_mode')
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
        'current_language': 'en',
        'current_theme': 'light',
        'mobile_view': False,
        'ui_mode': 'toolbar_mode',
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
        'timeline_elements': [],
        'dragged_element': None,
        'active_element_index': -1,
        'show_timeline_help': True,
    }
    
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default
    
    # Инициализация элементов конфигурации
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

# UI компоненты
class UIComponents:
    """Компоненты пользовательского интерфейса"""
    
    def __init__(self):
        self.user_prefs = UserPreferencesManager()
    
    def render_header(self):
        """Рендер заголовка и контролов с выпадающим меню"""
        if st.session_state.ui_mode == 'toolbar_mode':
            self._render_toolbar_header()
        else:
            self._render_timeline_header()
    
    def _render_toolbar_header(self):
        """Рендер заголовка для toolbar режима"""
        col_title, col_controls = st.columns([2, 3])
        
        with col_title:
            st.markdown(f"<h1 style='margin-bottom: 0.2rem;'>🎨 {get_text('header')}</h1>", unsafe_allow_html=True)
        
        with col_controls:
            # Панель инструментов
            toolbar_cols = st.columns([1, 1, 1, 1, 1, 1])
            
            with toolbar_cols[0]:
                # Переключатель режимов
                self._render_ui_mode_selector()
            
            with toolbar_cols[1]:
                # Язык
                self._render_language_selector()
            
            with toolbar_cols[2]:
                # Тема
                self._render_theme_selector()
            
            with toolbar_cols[3]:
                # Вид
                self._render_view_selector()
            
            with toolbar_cols[4]:
                # Кнопка Help
                if st.button("❓", help=get_text('help_button'), key="help_button", use_container_width=True):
                    st.info(get_text('short_guide_title'))
            
            with toolbar_cols[5]:
                # Выпадающее меню
                with st.popover("⚙️"):
                    st.markdown("**Actions**")
                    self._render_clear_button()
                    st.markdown("---")
                    self._render_back_button()
                    self._render_reset_button()
    
    def _render_timeline_header(self):
        """Рендер заголовка для timeline режима"""
        col_title, col_controls = st.columns([2, 3])
        
        with col_title:
            st.markdown(f"<h1 style='margin-bottom: 0.2rem;'>🎬 {get_text('timeline_editor')}</h1>", unsafe_allow_html=True)
        
        with col_controls:
            # Панель инструментов для таймлайна
            toolbar_cols = st.columns([1, 1, 1, 1, 1, 1])
            
            with toolbar_cols[0]:
                # Переключатель режимов
                self._render_ui_mode_selector()
            
            with toolbar_cols[1]:
                # Язык
                self._render_language_selector()
            
            with toolbar_cols[2]:
                # Тема
                self._render_theme_selector()
            
            with toolbar_cols[3]:
                # Вид
                self._render_view_selector()
            
            with toolbar_cols[4]:
                # Кнопка Save
                if st.button("💾", help=get_text('save_button'), key="save_btn", use_container_width=True):
                    st.success("Style saved")
            
            with toolbar_cols[5]:
                # Выпадающее меню
                with st.popover("⚙️"):
                    st.markdown("**Timeline Tools**")
                    self._render_clear_button()
                    st.markdown("---")
                    self._render_back_button()
                    self._render_reset_button()
    
    def _render_ui_mode_selector(self):
        """Рендер переключателя режимов интерфейса"""
        modes = [
            (Config.UI_MODE_NAMES[st.session_state.current_language]['toolbar_mode'], 'toolbar_mode'),
            (Config.UI_MODE_NAMES[st.session_state.current_language]['timeline_mode'], 'timeline_mode')
        ]
        
        current_mode = st.session_state.ui_mode
        mode_index = 0 if current_mode == 'toolbar_mode' else 1
        
        selected_mode = st.selectbox(
            get_text('ui_mode'),
            modes,
            format_func=lambda x: x[0],
            index=mode_index,
            key="ui_mode_selector",
            label_visibility="collapsed"
        )
        
        if selected_mode[1] != st.session_state.ui_mode:
            self._save_current_state()
            st.session_state.ui_mode = selected_mode[1]
            self._save_user_preferences()
            st.rerun()
    
    def _render_language_selector(self):
        """Рендер селектора языка"""
        languages = [
            ('English', 'en'),
            ('Русский', 'ru')
        ]
        
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
            self._save_current_state()
            st.session_state.current_language = selected_language[1]
            self._save_user_preferences()
            st.rerun()
    
    def _render_theme_selector(self):
        """Рендер селектора темы"""
        themes = [
            (get_text('light_theme'), 'light'),
            (get_text('dark_theme'), 'dark')
        ]
        
        selected_theme = st.selectbox(
            get_text('theme_selector'),
            themes,
            format_func=lambda x: x[0],
            index=0 if st.session_state.current_theme == 'light' else 1,
            key="theme_selector",
            label_visibility="collapsed"
        )
        
        if selected_theme[1] != st.session_state.current_theme:
            self._save_current_state()
            st.session_state.current_theme = selected_theme[1]
            self._save_user_preferences()
            st.rerun()
    
    def _render_view_selector(self):
        """Рендер переключателя вида"""
        mobile_view = st.session_state.mobile_view
        view_label = get_text('mobile_view') if mobile_view else get_text('desktop_view')
        
        view_btn = st.button(view_label, key="view_selector", use_container_width=True)
        if view_btn:
            self._save_current_state()
            st.session_state.mobile_view = not st.session_state.mobile_view
            self._save_user_preferences()
            st.rerun()
    
    def _render_clear_button(self):
        """Рендер кнопки Clear с иконкой"""
        if st.button(get_text('clear_button'), help="Clear all settings", key="clear_button", use_container_width=True):
            self._clear_all_settings()

    def _render_back_button(self):
        """Рендер кнопки Back с иконкой"""
        if st.session_state.previous_states:
            if st.button(get_text('back_button'), help="Back to previous state", key="back_button", use_container_width=True):
                self._restore_previous_state()
    
    def _render_reset_button(self):
        """Рендер кнопки Reset с иконкой"""
        if st.button(get_text('reset_button'), help="Reset to defaults", key="reset_button", use_container_width=True):
            self._reset_to_defaults()
    
    def _save_current_state(self):
        """Сохранение текущего состояния для кнопки Back"""
        if 'previous_states' not in st.session_state:
            st.session_state.previous_states = []
        
        # Сохраняем только основные настройки для экономии памяти
        current_state = {
            'current_language': st.session_state.current_language,
            'current_theme': st.session_state.current_theme,
            'mobile_view': st.session_state.mobile_view,
            'ui_mode': st.session_state.ui_mode,
            'num': st.session_state.num,
            'auth': st.session_state.auth,
            'sep': st.session_state.sep,
            'etal': st.session_state.etal,
            'doi': st.session_state.doi,
            'doilink': st.session_state.doilink,
            'page': st.session_state.page,
            'punct': st.session_state.punct,
            'journal_style': st.session_state.journal_style,
            'use_and_checkbox': st.session_state.use_and_checkbox,
            'use_ampersand_checkbox': st.session_state.use_ampersand_checkbox,
            'gost_style': st.session_state.gost_style,
            'acs_style': st.session_state.acs_style,
            'rsc_style': st.session_state.rsc_style,
            'cta_style': st.session_state.cta_style,
            'timestamp': time.time(),
            'timeline_elements': st.session_state.get('timeline_elements', []).copy(),
            'active_element_index': st.session_state.get('active_element_index', -1)
        }
        
        # Сохраняем элементы конфигурации
        for i in range(8):
            for prop in ['el', 'it', 'bd', 'pr', 'sp']:
                key = f"{prop}{i}"
                current_state[key] = st.session_state[key]
        
        # Добавляем в стек и ограничиваем размер
        st.session_state.previous_states.append(current_state)
        if len(st.session_state.previous_states) > st.session_state.max_undo_steps:
            st.session_state.previous_states.pop(0)
    
    def _clear_all_settings(self):
        """Очистка всех настроек"""
        self._save_current_state()
        
        # Сброс основных настроек
        st.session_state.num = "No numbering"
        st.session_state.auth = "AA Smith"
        st.session_state.sep = ", "
        st.session_state.etal = 0
        st.session_state.doi = "10.10/xxx"
        st.session_state.doilink = True
        st.session_state.page = "122–128"
        st.session_state.punct = ""
        st.session_state.journal_style = '{Full Journal Name}'
        st.session_state.use_and_checkbox = False
        st.session_state.use_ampersand_checkbox = False
        
        # Сброс стилей
        st.session_state.gost_style = False
        st.session_state.acs_style = False
        st.session_state.rsc_style = False
        st.session_state.cta_style = False
        
        # Сброс элементов конфигурации
        for i in range(8):
            st.session_state[f"el{i}"] = ""
            st.session_state[f"it{i}"] = False
            st.session_state[f"bd{i}"] = False
            st.session_state[f"pr{i}"] = False
            st.session_state[f"sp{i}"] = ". "
        
        # Сброс данных
        st.session_state.output_text_value = ""
        st.session_state.show_results = False
        st.session_state.download_data = {}
        
        # Сброс таймлайн
        st.session_state.timeline_elements = []
        st.session_state.active_element_index = -1
        
        st.rerun()
    
    def _reset_to_defaults(self):
        """Сброс к значениям по умолчанию"""
        self._save_current_state()
        
        # Сброс только основных настроек, не затрагивая данные
        st.session_state.num = "No numbering"
        st.session_state.auth = "AA Smith"
        st.session_state.sep = ", "
        st.session_state.etal = 0
        st.session_state.doi = "10.10/xxx"
        st.session_state.doilink = True
        st.session_state.page = "122–128"
        st.session_state.punct = ""
        st.session_state.journal_style = '{Full Journal Name}'
        st.session_state.use_and_checkbox = False
        st.session_state.use_ampersand_checkbox = False
        
        # Сброс стилей
        st.session_state.gost_style = False
        st.session_state.acs_style = False
        st.session_state.rsc_style = False
        st.session_state.cta_style = False
        
        st.rerun()
    
    def _restore_previous_state(self):
        """Восстановление предыдущего состояния"""
        if not st.session_state.previous_states:
            st.warning("No previous state to restore")
            return
        
        previous_state = st.session_state.previous_states.pop()
        
        # Восстанавливаем основные настройки
        for key, value in previous_state.items():
            if key in st.session_state and key != 'timestamp':
                st.session_state[key] = value
        
        st.rerun()
    
    def _save_user_preferences(self):
        """Сохранение пользовательских предпочтений"""
        ip = self.user_prefs.get_user_ip()
        preferences = {
            'language': st.session_state.current_language,
            'theme': st.session_state.current_theme,
            'mobile_view': st.session_state.mobile_view,
            'ui_mode': st.session_state.ui_mode
        }
        self.user_prefs.save_preferences(ip, preferences)
    
    def load_user_preferences(self):
        """Загрузка пользовательских предпочтений"""
        if not st.session_state.user_prefs_loaded:
            ip = self.user_prefs.get_user_ip()
            prefs = self.user_prefs.get_preferences(ip)
            
            st.session_state.current_language = prefs['language']
            st.session_state.current_theme = prefs['theme'] 
            st.session_state.mobile_view = prefs['mobile_view']
            st.session_state.ui_mode = prefs['ui_mode']
            st.session_state.user_prefs_loaded = True
    
    def apply_theme_styles(self):
        """Применение стилей темы"""
        theme = Config.THEMES[st.session_state.current_theme]
        
        st.markdown(f"""
            <style>
            .block-container {{
                padding: 0.2rem;
                background-color: {theme['background']};
                color: {theme['text']};
                font-family: {theme['font']};
            }}
            
            /* Общие стили */
            .stSelectbox, .stTextInput, .stNumberInput, .stCheckbox, .stRadio, .stFileUploader, .stTextArea {{
                margin-bottom: 0.02rem;
                background-color: {theme['secondaryBackground']};
                border: 1px solid {theme['border']};
                border-radius: 0.25rem;
            }}
            
            .stTextArea {{ 
                height: 40px !important; 
                font-size: 0.7rem; 
                background-color: {theme['secondaryBackground']};
                color: {theme['text']};
            }}
            
            .stButton > button {{ 
                width: 100%; 
                padding: 0.05rem; 
                font-size: 0.7rem; 
                margin: 0.02rem; 
                background-color: {theme['primary']};
                color: white;
                border: none;
                border-radius: 0.25rem;
                transition: all 0.2s;
            }}
            
            .stButton > button:hover {{
                background-color: {theme['accent']};
                transform: translateY(-1px);
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            
            h1, h2, h3, h4, h5, h6 {{
                color: {theme['text']} !important;
            }}
            
            h1 {{ font-size: 1.0rem; margin-bottom: 0.05rem; }}
            h2 {{ font-size: 0.9rem; margin-bottom: 0.05rem; }}
            h3 {{ font-size: 0.8rem; margin-bottom: 0.02rem; }}
            
            label {{ 
                font-size: 0.65rem !important; 
                color: {theme['text']} !important;
            }}
            
            .stMarkdown {{ 
                font-size: 0.65rem; 
                color: {theme['text']};
            }}
            
            .stCheckbox > label {{ 
                font-size: 0.6rem; 
                color: {theme['text']};
            }}
            
            .stRadio > label {{ 
                font-size: 0.65rem; 
                color: {theme['text']};
            }}
            
            .stDownloadButton > button {{ 
                font-size: 0.7rem; 
                padding: 0.05rem; 
                margin: 0.02rem; 
                background-color: {theme['primary']};
                color: white;
                border: none;
                border-radius: 0.25rem;
            }}
            
            /* Карточные стили для toolbar режима */
            .card {{
                background-color: {theme['cardBackground']};
                padding: 0.5rem;
                border-radius: 0.5rem;
                border: 1px solid {theme['border']};
                margin-bottom: 0.5rem;
                transition: all 0.3s ease;
            }}
            
            .card:hover {{
                border-color: {theme['primary']};
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }}
            
            .card-header {{
                font-weight: bold;
                font-size: 0.8rem;
                margin-bottom: 0.3rem;
                color: {theme['primary']};
                border-bottom: 1px solid {theme['border']};
                padding-bottom: 0.2rem;
            }}
            
            .card-content {{
                font-size: 0.7rem;
                line-height: 1.2;
            }}
            
            /* Стили для таймлайн режима */
            .timeline-container {{
                background-color: {theme['secondaryBackground']};
                border-radius: 0.5rem;
                padding: 0.5rem;
                margin-bottom: 0.5rem;
                border: 1px solid {theme['border']};
            }}
            
            .timeline-track {{
                background-color: {theme['cardBackground']};
                border-radius: 0.25rem;
                padding: 0.3rem;
                margin-bottom: 0.2rem;
                border: 1px solid {theme['border']};
                cursor: grab;
                transition: all 0.2s;
            }}
            
            .timeline-track:hover {{
                background-color: {theme['primary']}20;
                border-color: {theme['primary']};
                transform: translateX(2px);
            }}
            
            .timeline-track.dragging {{
                opacity: 0.5;
                border-style: dashed;
            }}
            
            .timeline-track.active {{
                background-color: {theme['primary']}30;
                border-color: {theme['primary']};
                box-shadow: 0 0 0 2px {theme['primary']}40;
            }}
            
            .timeline-properties {{
                background-color: {theme['cardBackground']};
                border-radius: 0.25rem;
                padding: 0.5rem;
                border: 1px solid {theme['primary']};
            }}
            
            .timeline-preview {{
                background-color: {theme['background']};
                border-radius: 0.25rem;
                padding: 0.5rem;
                font-family: monospace;
                border: 1px solid {theme['border']};
                min-height: 80px;
            }}
            
            .toolbar {{
                background-color: {theme['toolbar']};
                border-radius: 0.5rem;
                padding: 0.3rem;
                margin-bottom: 0.5rem;
                border: 1px solid {theme['border']};
            }}
            
            .toolbar-button {{
                background-color: {theme['secondaryBackground']};
                border: 1px solid {theme['border']};
                border-radius: 0.25rem;
                padding: 0.2rem 0.5rem;
                margin: 0.1rem;
                cursor: pointer;
                transition: all 0.2s;
                display: inline-block;
            }}
            
            .toolbar-button:hover {{
                background-color: {theme['primary']}20;
                border-color: {theme['primary']};
            }}
            
            .element-row {{ margin: 0.01rem; padding: 0.01rem; }}
            .processing-header {{ font-size: 0.8rem; font-weight: bold; margin-bottom: 0.1rem; }}
            .processing-status {{ font-size: 0.7rem; margin-bottom: 0.05rem; }}
            .compact-row {{ margin-bottom: 0.1rem; }}
            .guide-text {{ font-size: 0.55rem !important; line-height: 1.1; margin-bottom: 0.1rem; }}
            .guide-title {{ font-size: 0.7rem !important; font-weight: bold; margin-bottom: 0.1rem; }}
            .guide-step {{ font-size: 0.55rem !important; line-height: 1.1; margin-bottom: 0.1rem; }}
            .guide-note {{ font-size: 0.55rem !important; font-style: italic; line-height: 1.1; margin-bottom: 0.1rem; margin-left: 0.5rem; }}
            
            /* Мобильные стили */
            @media (max-width: 768px) {{
                .block-container {{ padding: 0.1rem; }}
                .stSelectbox, .stTextInput, .stNumberInput {{ 
                    font-size: 0.8rem !important;
                    margin-bottom: 0.1rem;
                }}
                .stButton > button {{
                    font-size: 0.8rem !important;
                    padding: 0.3rem !important;
                    margin: 0.1rem !important;
                }}
                .stCheckbox > label {{
                    font-size: 0.7rem !important;
                }}
                h1 {{ font-size: 1.1rem !important; }}
                h2 {{ font-size: 1.0rem !important; }}
                h3 {{ font-size: 0.9rem !important; }}
                
                .card {{
                    padding: 0.3rem;
                    margin-bottom: 0.3rem;
                }}
                
                .timeline-container {{
                    padding: 0.3rem;
                }}
            }}
            
            /* Десктоп стили */
            @media (min-width: 769px) {{
                .mobile-only {{ display: none; }}
            }}
            
            /* Мобильные только */
            @media (max-width: 768px) {{
                .desktop-only {{ display: none; }}
            }}
            
            /* Стили для разделителей */
            .separator-demo {{
                color: {theme['primary']};
                font-weight: bold;
                padding: 0 0.2rem;
            }}
            
            /* Стили для превью в таймлайне */
            .preview-reference {{
                font-family: 'Courier New', monospace;
                font-size: 0.7rem;
                line-height: 1.3;
                padding: 0.3rem;
                background-color: {theme['cardBackground']};
                border-radius: 0.25rem;
                border-left: 3px solid {theme['primary']};
            }}
            
            /* Стили для элемента в перетаскивании */
            .draggable-element {{
                padding: 0.3rem 0.5rem;
                background-color: {theme['secondaryBackground']};
                border: 1px dashed {theme['border']};
                border-radius: 0.25rem;
                margin: 0.1rem;
                cursor: move;
                transition: all 0.2s;
            }}
            
            .draggable-element:hover {{
                background-color: {theme['primary']}15;
                border-color: {theme['primary']};
            }}
            
            /* Стили для активных кнопок */
            .active-button {{
                background-color: {theme['primary']} !important;
                color: white !important;
                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            }}
            
            /* Анимации */
            @keyframes pulse {{
                0% {{ opacity: 1; }}
                50% {{ opacity: 0.7; }}
                100% {{ opacity: 1; }}
            }}
            
            .pulse {{
                animation: pulse 2s infinite;
            }}
            
            /* Стили для полосы прокрутки */
            ::-webkit-scrollbar {{
                width: 8px;
                height: 8px;
            }}
            
            ::-webkit-scrollbar-track {{
                background: {theme['background']};
                border-radius: 4px;
            }}
            
            ::-webkit-scrollbar-thumb {{
                background: {theme['primary']};
                border-radius: 4px;
            }}
            
            ::-webkit-scrollbar-thumb:hover {{
                background: {theme['accent']};
            }}
            </style>
        """, unsafe_allow_html=True)

    def render_toolbar_interface(self):
        """Рендер интерфейса в режиме панели инструментов"""
        # Верхняя панель инструментов
        st.markdown("<div class='toolbar'>", unsafe_allow_html=True)
        col_tools = st.columns(6)
        
        with col_tools[0]:
            st.markdown(f"**{get_text('quick_styles')}**")
        
        with col_tools[1]:
            self.render_style_presets_toolbar()
        
        with col_tools[2]:
            st.markdown(f"**{get_text('tools')}**")
        
        with col_tools[3]:
            if st.button("📋", help="Copy style", use_container_width=True, key="copy_style"):
                st.info("Style copied to clipboard")
        
        with col_tools[4]:
            if st.button("📊", help="Show statistics", use_container_width=True, key="show_stats"):
                st.session_state.show_stats = not st.session_state.get('show_stats', False)
        
        with col_tools[5]:
            if st.button("🎯", help="Auto-format", use_container_width=True, key="auto_format"):
                st.info("Auto-formatting applied")
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Основной контент в колонках
        if st.session_state.mobile_view:
            # Мобильный вид
            self._render_toolbar_mobile()
        else:
            # Десктоп вид
            self._render_toolbar_desktop()
    
    def _render_toolbar_mobile(self):
        """Рендер toolbar режима для мобильных"""
        # Карточка стилей
        with st.container():
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown(f"<div class='card-header'>{get_text('card_style')}</div>", unsafe_allow_html=True)
            self.render_general_settings_compact()
            st.markdown("</div>", unsafe_allow_html=True)
        
        # Карточка конструктора
        with st.container():
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown(f"<div class='card-header'>{get_text('style_builder')}</div>", unsafe_allow_html=True)
            element_configs = self.render_element_configuration_compact()
            st.markdown("</div>", unsafe_allow_html=True)
        
        # Карточка ввода
        with st.container():
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown(f"<div class='card-header'>{get_text('card_input')}</div>", unsafe_allow_html=True)
            input_data = self.render_data_input_compact()
            st.markdown("</div>", unsafe_allow_html=True)
        
        # Карточка вывода
        with st.container():
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown(f"<div class='card-header'>{get_text('card_output')}</div>", unsafe_allow_html=True)
            output_method = self.render_data_output_compact()
            st.markdown("</div>", unsafe_allow_html=True)
        
        # Кнопка обработки
        if st.button(get_text('process'), use_container_width=True, type="primary", key="process_main"):
            style_config = self._get_style_config_from_elements(element_configs)
            self._trigger_processing(input_data, style_config, output_method)
        
        # Предпросмотр
        if st.session_state.get('show_preview', True):
            with st.container():
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"<div class='card-header'>{get_text('style_preview')}</div>", unsafe_allow_html=True)
                self.render_style_preview_compact(style_config)
                st.markdown("</div>", unsafe_allow_html=True)
    
    def _render_toolbar_desktop(self):
        """Рендер toolbar режима для десктопа"""
        col1, col2, col3 = st.columns([1.2, 1, 1])
        
        with col1:
            # Левая колонка: Настройки и конструктор
            with st.container():
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"<div class='card-header'>⚙️ {get_text('general_settings')}</div>", unsafe_allow_html=True)
                self.render_general_settings_compact()
                st.markdown("</div>", unsafe_allow_html=True)
            
            with st.container():
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"<div class='card-header'>📑 {get_text('element_config')}</div>", unsafe_allow_html=True)
                element_configs = self.render_element_configuration_compact()
                st.markdown("</div>", unsafe_allow_html=True)
        
        with col2:
            # Центральная колонка: Ввод и предпросмотр
            with st.container():
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"<div class='card-header'>📁 {get_text('data_input')}</div>", unsafe_allow_html=True)
                input_data = self.render_data_input_compact()
                st.markdown("</div>", unsafe_allow_html=True)
            
            with st.container():
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"<div class='card-header'>👀 {get_text('style_preview')}</div>", unsafe_allow_html=True)
                style_config = self._get_style_config_from_elements(element_configs)
                self.render_style_preview_compact(style_config)
                st.markdown("</div>", unsafe_allow_html=True)
        
        with col3:
            # Правая колонка: Вывод и обработка
            with st.container():
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"<div class='card-header'>📤 {get_text('data_output')}</div>", unsafe_allow_html=True)
                output_method = self.render_data_output_compact()
                st.markdown("</div>", unsafe_allow_html=True)
            
            # Большая кнопка обработки
            if st.button(get_text('process'), use_container_width=True, type="primary", key="process_main"):
                self._trigger_processing(input_data, style_config, output_method)
            
            # Кнопки скачивания
            self._render_download_buttons_compact(output_method)
            
            # Управление стилями
            with st.expander("💾 Style Management", expanded=False):
                self._render_style_management_compact(style_config)
    
    def render_timeline_interface(self):
        """Рендер интерфейса в режиме таймлайна"""
        # Основной макет таймлайна
        col_timeline, col_properties = st.columns([2, 1])
        
        with col_timeline:
            # Секвенсер стилей
            st.markdown(f"<h3>🎬 {get_text('style_sequencer')}</h3>", unsafe_allow_html=True)
            self._render_timeline_sequencer()
            
            # Панель элементов для перетаскивания
            st.markdown(f"<h4>{get_text('add_element')}</h4>", unsafe_allow_html=True)
            self._render_draggable_elements()
            
            # Медиапул
            st.markdown(f"<h3>📁 {get_text('media_pool')}</h3>", unsafe_allow_html=True)
            input_data = self.render_data_input_compact()
        
        with col_properties:
            # Панель свойств
            st.markdown(f"<h3>⚙️ {get_text('properties_panel')}</h3>", unsafe_allow_html=True)
            self._render_timeline_properties()
            
            # Монитор предпросмотра
            st.markdown(f"<h3>👁️ {get_text('preview_monitor')}</h3>", unsafe_allow_html=True)
            style_config = self._get_timeline_style_config()
            self._render_timeline_preview(style_config)
            
            # Кнопки управления
            col_buttons = st.columns(2)
            with col_buttons[0]:
                if st.button(get_text('import_references'), use_container_width=True, key="timeline_import"):
                    st.info("Import started")
            
            with col_buttons[1]:
                if st.button(get_text('render_output'), use_container_width=True, type="primary", key="timeline_render"):
                    output_method = "DOCX"  # По умолчанию DOCX для таймлайна
                    self._trigger_processing(input_data, style_config, output_method)
    
    def _render_timeline_sequencer(self):
        """Рендер секвенсера таймлайна"""
        st.markdown(f"<div class='timeline-container'>", unsafe_allow_html=True)
        
        # Получаем элементы из таймлайна или из обычной конфигурации
        timeline_elements = st.session_state.get('timeline_elements', [])
        
        if not timeline_elements:
            # Если таймлайн пустой, показываем подсказку
            st.markdown(f"""
                <div style='text-align: center; padding: 2rem; color: var(--text-color-secondary);'>
                    <div style='font-size: 2rem; margin-bottom: 1rem;'>⬇️</div>
                    <div>{get_text('empty_timeline')}</div>
                    <div style='font-size: 0.8rem; margin-top: 0.5rem;'>{get_text('drag_to_reorder')}</div>
                </div>
            """, unsafe_allow_html=True)
        else:
            # Отображаем элементы таймлайна
            for i, element_data in enumerate(timeline_elements):
                element_name = element_data.get('element', '')
                element_config = element_data.get('config', {})
                
                # Определяем классы для трека
                track_class = "timeline-track"
                if i == st.session_state.get('active_element_index', -1):
                    track_class += " active"
                if st.session_state.get('dragged_element') == i:
                    track_class += " dragging"
                
                # Отображаем трек
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    track_html = f"""
                        <div class='{track_class}' onclick='window.timelineSelectElement({i})'>
                            <div style='font-weight: bold;'>{element_name}</div>
                            <div style='font-size: 0.7rem; opacity: 0.8;'>
                                {self._format_element_config_preview(element_config)}
                            </div>
                        </div>
                    """
                    st.markdown(track_html, unsafe_allow_html=True)
                
                with col2:
                    # Кнопки управления треком
                    if st.button("↑", key=f"move_up_{i}", use_container_width=True):
                        self._move_timeline_element(i, -1)
                
                with col3:
                    if st.button("✕", key=f"remove_{i}", use_container_width=True):
                        self._remove_timeline_element(i)
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # JavaScript для обработки кликов
        st.markdown("""
            <script>
            function timelineSelectElement(index) {
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: {index: index, type: 'timeline_select'}
                }, '*');
            }
            </script>
        """, unsafe_allow_html=True)
    
    def _render_draggable_elements(self):
        """Рендер перетаскиваемых элементов"""
        elements = ["Authors", "Title", "Journal", "Year", "Volume", "Issue", "Pages", "DOI"]
        
        cols = st.columns(4)
        for i, element in enumerate(elements):
            with cols[i % 4]:
                if st.button(element, key=f"drag_{element}", use_container_width=True):
                    self._add_to_timeline(element)
        
        st.markdown(f"<div style='font-size: 0.7rem; text-align: center; margin-top: 0.5rem;'>{get_text('drag_to_reorder')}</div>", unsafe_allow_html=True)
    
    def _render_timeline_properties(self):
        """Рендер панели свойств для выбранного элемента"""
        active_index = st.session_state.get('active_element_index', -1)
        timeline_elements = st.session_state.get('timeline_elements', [])
        
        if active_index >= 0 and active_index < len(timeline_elements):
            element_data = timeline_elements[active_index]
            element_name = element_data.get('element', '')
            element_config = element_data.get('config', {})
            
            st.markdown(f"<div class='timeline-properties'>", unsafe_allow_html=True)
            st.markdown(f"**{element_name}**")
            
            # Настройки форматирования
            col1, col2 = st.columns(2)
            with col1:
                italic = st.checkbox(get_text('italic'), value=element_config.get('italic', False),
                                   key=f"timeline_italic_{active_index}")
            with col2:
                bold = st.checkbox(get_text('bold'), value=element_config.get('bold', False),
                                 key=f"timeline_bold_{active_index}")
            
            parentheses = st.checkbox(get_text('parentheses'), value=element_config.get('parentheses', False),
                                    key=f"timeline_parentheses_{active_index}")
            
            separator = st.text_input(get_text('separator'), value=element_config.get('separator', '. '),
                                    key=f"timeline_separator_{active_index}")
            
            # Обновляем конфигурацию
            if st.button("💾 Update", key=f"update_{active_index}", use_container_width=True):
                timeline_elements[active_index]['config'] = {
                    'italic': italic,
                    'bold': bold,
                    'parentheses': parentheses,
                    'separator': separator
                }
                st.session_state.timeline_elements = timeline_elements
                st.success("Updated!")
                st.rerun()
            
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Select an element from the timeline to edit its properties")
    
    def _render_timeline_preview(self, style_config):
        """Рендер предпросмотра для таймлайна"""
        st.markdown("<div class='timeline-preview'>", unsafe_allow_html=True)
        
        # Интерактивный предпросмотр
        current_time = time.time()
        if current_time - st.session_state.get('last_style_update', 0) > 1:
            st.session_state.last_style_update = current_time
            
            preview_metadata = self._get_preview_metadata(style_config)
            if preview_metadata:
                preview_ref, _ = format_reference(preview_metadata, style_config, for_preview=True)
                preview_with_numbering = self._add_numbering(preview_ref, style_config)
                
                # Форматирование HTML для предпросмотра
                preview_html = self._format_preview_html(preview_with_numbering, style_config)
                st.markdown(f"<div class='preview-reference'>{preview_html}</div>", unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    def _format_element_config_preview(self, config):
        """Форматирование предпросмотра конфигурации элемента"""
        parts = []
        if config.get('italic'):
            parts.append("I")
        if config.get('bold'):
            parts.append("B")
        if config.get('parentheses'):
            parts.append("()")
        
        separator = config.get('separator', '. ')
        if separator:
            parts.append(f"sep: '{separator}'")
        
        return " | ".join(parts) if parts else "Default"
    
    def _add_to_timeline(self, element_name):
        """Добавление элемента в таймлайн"""
        timeline_elements = st.session_state.get('timeline_elements', [])
        
        # Проверяем, нет ли уже такого элемента
        for elem in timeline_elements:
            if elem.get('element') == element_name:
                st.warning(f"Element '{element_name}' already in timeline")
                return
        
        # Добавляем новый элемент
        timeline_elements.append({
            'element': element_name,
            'config': {
                'italic': False,
                'bold': False,
                'parentheses': False,
                'separator': '. '
            }
        })
        
        st.session_state.timeline_elements = timeline_elements
        st.session_state.active_element_index = len(timeline_elements) - 1
        st.rerun()
    
    def _remove_timeline_element(self, index):
        """Удаление элемента из таймлайна"""
        timeline_elements = st.session_state.get('timeline_elements', [])
        if 0 <= index < len(timeline_elements):
            timeline_elements.pop(index)
            st.session_state.timeline_elements = timeline_elements
            
            # Обновляем активный индекс
            if st.session_state.active_element_index == index:
                st.session_state.active_element_index = -1
            elif st.session_state.active_element_index > index:
                st.session_state.active_element_index -= 1
            
            st.rerun()
    
    def _move_timeline_element(self, index, direction):
        """Перемещение элемента в таймлайне"""
        timeline_elements = st.session_state.get('timeline_elements', [])
        new_index = index + direction
        
        if 0 <= new_index < len(timeline_elements):
            # Меняем элементы местами
            timeline_elements[index], timeline_elements[new_index] = timeline_elements[new_index], timeline_elements[index]
            st.session_state.timeline_elements = timeline_elements
            
            # Обновляем активный индекс
            if st.session_state.active_element_index == index:
                st.session_state.active_element_index = new_index
            elif st.session_state.active_element_index == new_index:
                st.session_state.active_element_index = index
            
            st.rerun()
    
    def _get_timeline_style_config(self):
        """Получение конфигурации стиля из таймлайна"""
        timeline_elements = st.session_state.get('timeline_elements', [])
        
        # Преобразуем элементы таймлайна в формат обычной конфигурации
        elements = []
        for elem in timeline_elements:
            elements.append((
                elem['element'],
                {
                    'italic': elem['config'].get('italic', False),
                    'bold': elem['config'].get('bold', False),
                    'parentheses': elem['config'].get('parentheses', False),
                    'separator': elem['config'].get('separator', '. ')
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
            'gost_style': st.session_state.get('gost_style', False),
            'acs_style': st.session_state.get('acs_style', False),
            'rsc_style': st.session_state.get('rsc_style', False),
            'cta_style': st.session_state.get('cta_style', False)
        }
    
    def render_style_presets_toolbar(self):
        """Рендер пресетов стилей для toolbar режима"""
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.session_state.current_language == 'ru':
                if st.button(get_text('gost_button'), use_container_width=True, key="gost_toolbar"):
                    self._apply_gost_style()
        
        with col2:
            if st.button(get_text('acs_button'), use_container_width=True, key="acs_toolbar"):
                self._apply_acs_style()
        
        with col3:
            if st.button(get_text('rsc_button'), use_container_width=True, key="rsc_toolbar"):
                self._apply_rsc_style()
        
        with col4:
            if st.button(get_text('cta_button'), use_container_width=True, key="cta_toolbar"):
                self._apply_cta_style()
    
    def _apply_gost_style(self):
        """Применение стиля ГОСТ (только для русского языка)"""
        def apply_gost_callback():
            self._save_current_state()
            st.session_state.num = "No numbering"
            st.session_state.auth = "Smith AA"
            st.session_state.sep = ", "
            st.session_state.etal = 0
            st.session_state.use_and_checkbox = False
            st.session_state.use_ampersand_checkbox = False
            st.session_state.doi = "https://dx.doi.org/10.10/xxx"
            st.session_state.doilink = True
            st.session_state.page = "122-128"
            st.session_state.punct = ""
            st.session_state.journal_style = "{Full Journal Name}"
            
            # Для таймлайна
            st.session_state.timeline_elements = [
                {
                    'element': 'Authors',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ' '}
                },
                {
                    'element': 'Title',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ' // '}
                },
                {
                    'element': 'Journal',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. – '}
                },
                {
                    'element': 'Year',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. – Vol. '}
                },
                {
                    'element': 'Volume',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '}
                },
                {
                    'element': 'Issue',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ''}
                },
                {
                    'element': 'Pages',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. – '}
                },
                {
                    'element': 'DOI',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. – '}
                }
            ]
            
            st.session_state.gost_style = True
            st.session_state.acs_style = False
            st.session_state.rsc_style = False
            st.session_state.cta_style = False
            st.session_state.style_applied = True
        
        apply_gost_callback()
        st.rerun()
    
    def _apply_acs_style(self):
        """Применение стиля ACS"""
        def apply_acs_callback():
            self._save_current_state()
            st.session_state.num = "No numbering"
            st.session_state.auth = "Smith, A.A."
            st.session_state.sep = "; "
            st.session_state.etal = 0
            st.session_state.use_and_checkbox = False
            st.session_state.use_ampersand_checkbox = False
            st.session_state.doi = "10.10/xxx"
            st.session_state.doilink = True
            st.session_state.page = "122–128"
            st.session_state.punct = "."
            st.session_state.journal_style = "{J. Abbr.}"
            
            # Для таймлайна
            st.session_state.timeline_elements = [
                {
                    'element': 'Authors',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ' '}
                },
                {
                    'element': 'Title',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '}
                },
                {
                    'element': 'Journal',
                    'config': {'italic': True, 'bold': False, 'parentheses': False, 'separator': ' '}
                },
                {
                    'element': 'Year',
                    'config': {'italic': False, 'bold': True, 'parentheses': False, 'separator': ', '}
                },
                {
                    'element': 'Volume',
                    'config': {'italic': True, 'bold': False, 'parentheses': False, 'separator': ', '}
                },
                {
                    'element': 'Pages',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '}
                },
                {
                    'element': 'DOI',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ''}
                }
            ]
            
            st.session_state.gost_style = False
            st.session_state.acs_style = True
            st.session_state.rsc_style = False
            st.session_state.cta_style = False
            st.session_state.style_applied = True
        
        apply_acs_callback()
        st.rerun()
    
    def _apply_rsc_style(self):
        """Применение стиля RSC"""
        def apply_rsc_callback():
            self._save_current_state()
            st.session_state.num = "No numbering"
            st.session_state.auth = "A.A. Smith"
            st.session_state.sep = ", "
            st.session_state.etal = 0
            st.session_state.use_and_checkbox = True
            st.session_state.use_ampersand_checkbox = False
            st.session_state.doi = "10.10/xxx"
            st.session_state.doilink = True
            st.session_state.page = "122"
            st.session_state.punct = "."
            st.session_state.journal_style = "{J. Abbr.}"
            
            # Для таймлайна
            st.session_state.timeline_elements = [
                {
                    'element': 'Authors',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '}
                },
                {
                    'element': 'Journal',
                    'config': {'italic': True, 'bold': False, 'parentheses': False, 'separator': ', '}
                },
                {
                    'element': 'Year',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ', '}
                },
                {
                    'element': 'Volume',
                    'config': {'italic': False, 'bold': True, 'parentheses': False, 'separator': ', '}
                },
                {
                    'element': 'Pages',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '.'}
                }
            ]
            
            st.session_state.gost_style = False
            st.session_state.acs_style = False
            st.session_state.rsc_style = True
            st.session_state.cta_style = False
            st.session_state.style_applied = True
        
        apply_rsc_callback()
        st.rerun()
    
    def _apply_cta_style(self):
        """Применение стиля CTA"""
        def apply_cta_callback():
            self._save_current_state()
            st.session_state.num = "No numbering"
            st.session_state.auth = "Smith AA"
            st.session_state.sep = ", "
            st.session_state.etal = 0
            st.session_state.use_and_checkbox = False
            st.session_state.use_ampersand_checkbox = False
            st.session_state.doi = "doi:10.10/xxx"
            st.session_state.doilink = True
            st.session_state.page = "122–8"
            st.session_state.punct = ""
            st.session_state.journal_style = "{J Abbr}"
            
            # Для таймлайна
            st.session_state.timeline_elements = [
                {
                    'element': 'Authors',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '}
                },
                {
                    'element': 'Title',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '}
                },
                {
                    'element': 'Journal',
                    'config': {'italic': True, 'bold': False, 'parentheses': False, 'separator': '. '}
                },
                {
                    'element': 'Year',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ';'}
                },
                {
                    'element': 'Volume',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ''}
                },
                {
                    'element': 'Issue',
                    'config': {'italic': False, 'bold': False, 'parentheses': True, 'separator': ':'}
                },
                {
                    'element': 'Pages',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': '. '}
                },
                {
                    'element': 'DOI',
                    'config': {'italic': False, 'bold': False, 'parentheses': False, 'separator': ''}
                }
            ]
            
            st.session_state.gost_style = False
            st.session_state.acs_style = False
            st.session_state.rsc_style = False
            st.session_state.cta_style = True
            st.session_state.style_applied = True
        
        apply_cta_callback()
        st.rerun()
    
    def render_general_settings_compact(self):
        """Компактный рендер общих настроек"""
        if st.session_state.mobile_view:
            # Мобильный вид
            numbering_style = st.selectbox(
                get_text('numbering_style'), 
                Config.NUMBERING_STYLES, 
                key="num", 
                index=Config.NUMBERING_STYLES.index(st.session_state.num)
            )
            
            author_format = st.selectbox(
                get_text('author_format'), 
                Config.AUTHOR_FORMATS, 
                key="auth", 
                index=Config.AUTHOR_FORMATS.index(st.session_state.auth)
            )
            
            col_sep_etal = st.columns(2)
            with col_sep_etal[0]:
                author_separator = st.selectbox(
                    get_text('author_separator'), 
                    [", ", "; "], 
                    key="sep", 
                    index=[", ", "; "].index(st.session_state.sep)
                )
            with col_sep_etal[1]:
                et_al_limit = st.number_input(
                    get_text('et_al_limit'), 
                    min_value=0, 
                    step=1, 
                    key="etal", 
                    value=st.session_state.etal
                )
        else:
            # Десктоп вид
            col1, col2 = st.columns(2)
            with col1:
                numbering_style = st.selectbox(
                    get_text('numbering_style'), 
                    Config.NUMBERING_STYLES, 
                    key="num", 
                    index=Config.NUMBERING_STYLES.index(st.session_state.num)
                )
            
            with col2:
                author_format = st.selectbox(
                    get_text('author_format'), 
                    Config.AUTHOR_FORMATS, 
                    key="auth", 
                    index=Config.AUTHOR_FORMATS.index(st.session_state.auth)
                )
            
            col_sep, col_etal = st.columns(2)
            with col_sep:
                author_separator = st.selectbox(
                    get_text('author_separator'), 
                    [", ", "; "], 
                    key="sep", 
                    index=[", ", "; "].index(st.session_state.sep)
                )
            
            with col_etal:
                et_al_limit = st.number_input(
                    get_text('et_al_limit'), 
                    min_value=0, 
                    step=1, 
                    key="etal", 
                    value=st.session_state.etal
                )
        
        # Общие для обоих видов
        col_and, col_amp = st.columns(2)
        with col_and:
            use_and_checkbox = st.checkbox(
                get_text('use_and'), 
                key="use_and_checkbox", 
                value=st.session_state.use_and_checkbox,
                disabled=st.session_state.use_ampersand_checkbox
            )
        with col_amp:
            use_ampersand_checkbox = st.checkbox(
                get_text('use_ampersand'), 
                key="use_ampersand_checkbox", 
                value=st.session_state.use_ampersand_checkbox,
                disabled=st.session_state.use_and_checkbox
            )
        
        # Стиль журнала
        journal_style = st.selectbox(
            get_text('journal_style'),
            Config.JOURNAL_STYLES,
            key="journal_style",
            index=Config.JOURNAL_STYLES.index(st.session_state.journal_style),
            format_func=lambda x: {
                "{Full Journal Name}": get_text('full_journal_name'),
                "{J. Abbr.}": get_text('journal_abbr_with_dots'),
                "{J Abbr}": get_text('journal_abbr_no_dots')
            }[x]
        )
        
        # Настройки страниц
        current_page = st.session_state.page
        page_index = 3
        if current_page in Config.PAGE_FORMATS:
            page_index = Config.PAGE_FORMATS.index(current_page)
        
        page_format = st.selectbox(
            get_text('page_format'), 
            Config.PAGE_FORMATS, 
            key="page", 
            index=page_index
        )
        
        # Настройки DOI
        col_doi_format, col_doi_link = st.columns(2)
        with col_doi_format:
            doi_format = st.selectbox(
                get_text('doi_format'), 
                Config.DOI_FORMATS, 
                key="doi", 
                index=Config.DOI_FORMATS.index(st.session_state.doi)
            )
        with col_doi_link:
            doi_hyperlink = st.checkbox(
                get_text('doi_hyperlink'), 
                key="doilink", 
                value=st.session_state.doilink
            )
        
        # Конечная пунктуация
        final_punctuation = st.selectbox(
            get_text('final_punctuation'), 
            ["", "."], 
            key="punct", 
            index=["", "."].index(st.session_state.punct)
        )
    
    def render_element_configuration_compact(self):
        """Компактный рендер конфигурации элементов"""
        element_configs = []
        used_elements = set()
        
        st.markdown(
            f"<small>{get_text('element')} | {get_text('italic')} | {get_text('bold')} | {get_text('parentheses')} | {get_text('separator')}</small>", 
            unsafe_allow_html=True
        )
        
        for i in range(8):
            if st.session_state.mobile_view:
                # Мобильный вид
                element = st.selectbox(
                    f"E{i+1}", 
                    Config.AVAILABLE_ELEMENTS, 
                    key=f"el{i}", 
                    index=Config.AVAILABLE_ELEMENTS.index(st.session_state[f"el{i}"]) if st.session_state[f"el{i}"] in Config.AVAILABLE_ELEMENTS else 0,
                    label_visibility="collapsed"
                )
                
                col_mobile = st.columns(4)
                with col_mobile[0]:
                    italic = st.checkbox(
                        "", 
                        key=f"it{i}", 
                        help=get_text('italic'), 
                        value=st.session_state[f"it{i}"]
                    )
                with col_mobile[1]:
                    bold = st.checkbox(
                        "", 
                        key=f"bd{i}", 
                        help=get_text('bold'), 
                        value=st.session_state[f"bd{i}"]
                    )
                with col_mobile[2]:
                    parentheses = st.checkbox(
                        "", 
                        key=f"pr{i}", 
                        help=get_text('parentheses'), 
                        value=st.session_state[f"pr{i}"]
                    )
                with col_mobile[3]:
                    separator = st.text_input(
                        "", 
                        value=st.session_state[f"sp{i}"], 
                        key=f"sp{i}", 
                        label_visibility="collapsed",
                        placeholder="sep"
                    )
            else:
                # Десктоп вид
                cols = st.columns([2, 1, 1, 1, 2])
                
                with cols[0]:
                    element = st.selectbox(
                        "", 
                        Config.AVAILABLE_ELEMENTS, 
                        key=f"el{i}", 
                        label_visibility="collapsed",
                        index=Config.AVAILABLE_ELEMENTS.index(st.session_state[f"el{i}"]) if st.session_state[f"el{i}"] in Config.AVAILABLE_ELEMENTS else 0
                    )
                
                with cols[1]:
                    italic = st.checkbox(
                        "", 
                        key=f"it{i}", 
                        help=get_text('italic'), 
                        value=st.session_state[f"it{i}"]
                    )
                
                with cols[2]:
                    bold = st.checkbox(
                        "", 
                        key=f"bd{i}", 
                        help=get_text('bold'), 
                        value=st.session_state[f"bd{i}"]
                    )
                
                with cols[3]:
                    parentheses = st.checkbox(
                        "", 
                        key=f"pr{i}", 
                        help=get_text('parentheses'), 
                        value=st.session_state[f"pr{i}"]
                    )
                
                with cols[4]:
                    separator = st.text_input(
                        "", 
                        value=st.session_state[f"sp{i}"], 
                        key=f"sp{i}", 
                        label_visibility="collapsed",
                        placeholder="separator"
                    )
            
            if element and element not in used_elements:
                element_configs.append((
                    element, 
                    {
                        'italic': italic, 
                        'bold': bold, 
                        'parentheses': parentheses, 
                        'separator': separator
                    }
                ))
                used_elements.add(element)
        
        return element_configs
    
    def render_style_preview_compact(self, style_config: Dict):
        """Компактный рендер предпросмотра стиля"""
        # Интерактивный предпросмотр
        current_time = time.time()
        if current_time - st.session_state.get('last_style_update', 0) > 1:
            st.session_state.last_style_update = current_time
            
            preview_metadata = self._get_preview_metadata(style_config)
            if preview_metadata:
                preview_ref, _ = format_reference(preview_metadata, style_config, for_preview=True)
                preview_with_numbering = self._add_numbering(preview_ref, style_config)
                
                # Форматирование HTML для предпросмотра
                preview_html = self._format_preview_html(preview_with_numbering, style_config)
                st.markdown(f"<div class='preview-reference'>{preview_html}</div>", unsafe_allow_html=True)
    
    def render_data_input_compact(self):
        """Компактный рендер ввода данных"""
        input_method = st.radio(
            get_text('input_method'), 
            ['DOCX', 'Text' if st.session_state.current_language == 'en' else 'Текст'], 
            horizontal=True, 
            key="input_method_compact"
        )
        
        if input_method == 'DOCX':
            uploaded_file = st.file_uploader(
                get_text('select_docx'), 
                type=['docx'], 
                label_visibility="collapsed", 
                key="docx_uploader_compact"
            )
            return uploaded_file
        else:
            references_input = st.text_area(
                get_text('references'), 
                placeholder=get_text('enter_references'), 
                height=40, 
                label_visibility="collapsed", 
                key="references_input_compact"
            )
            return references_input
    
    def render_data_output_compact(self):
        """Компактный рендер вывода данных"""
        output_method = st.radio(
            get_text('output_method'), 
            ['DOCX', 'Text' if st.session_state.current_language == 'en' else 'Текст'], 
            horizontal=True, 
            key="output_method_compact"
        )
        
        if output_method == 'Text' if st.session_state.current_language == 'en' else 'Текст':
            output_text_value = st.session_state.output_text_value if st.session_state.show_results else ""
            st.text_area(
                get_text('results'), 
                value=output_text_value, 
                height=40, 
                disabled=True, 
                label_visibility="collapsed", 
                key="output_text_compact"
            )
        
        return output_method
    
    def _get_style_config_from_elements(self, element_configs):
        """Получение конфигурации стиля из элементов"""
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
    
    def _trigger_processing(self, input_data, style_config, output_method):
        """Триггер обработки данных"""
        # Этот метод будет вызываться из основного класса приложения
        st.session_state.process_triggered = True
        st.session_state.process_data = {
            'input_data': input_data,
            'style_config': style_config,
            'output_method': output_method
        }
    
    def _render_download_buttons_compact(self, output_method):
        """Компактный рендер кнопок скачивания"""
        if st.session_state.download_data:
            if st.session_state.mobile_view:
                # Мобильный вид
                st.download_button(
                    label="📄 DOI (TXT)",
                    data=st.session_state.download_data['txt_bytes'],
                    file_name='doi_list.txt',
                    mime='text/plain',
                    key="doi_download_compact",
                    use_container_width=True
                )
                
                if output_method == 'DOCX' and st.session_state.download_data.get('output_doc_buffer'):
                    st.download_button(
                        label="📋 References (DOCX)",
                        data=st.session_state.download_data['output_doc_buffer'],
                        file_name='Reformatted references.docx',
                        mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        key="docx_download_compact",
                        use_container_width=True
                    )
            else:
                # Десктоп вид
                col_download = st.columns(2)
                with col_download[0]:
                    st.download_button(
                        label="📄 TXT",
                        data=st.session_state.download_data['txt_bytes'],
                        file_name='doi_list.txt',
                        mime='text/plain',
                        key="doi_download_compact",
                        use_container_width=True
                    )
                
                with col_download[1]:
                    if output_method == 'DOCX' and st.session_state.download_data.get('output_doc_buffer'):
                        st.download_button(
                            label="📋 DOCX",
                            data=st.session_state.download_data['output_doc_buffer'],
                            file_name='references.docx',
                            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            key="docx_download_compact",
                            use_container_width=True
                        )
    
    def _render_style_management_compact(self, style_config):
        """Компактный рендер управления стилями"""
        # Экспорт стиля
        export_file_name = st.text_input(
            get_text('export_file_name'), 
            value="my_citation_style", 
            placeholder="Enter file name", 
            key="export_name_compact"
        )
        
        export_data = self._export_style(style_config, export_file_name)
        if export_data:
            st.download_button(
                label=get_text('export_style'),
                data=export_data,
                file_name=f"{export_file_name}.json",
                mime="application/json",
                use_container_width=True,
                key="export_button_compact"
            )
        
        # Импорт стиля
        imported_file = st.file_uploader(
            get_text('import_file'), 
            type=['json'], 
            label_visibility="collapsed", 
            key="style_importer_compact"
        )
        
        if imported_file is not None:
            current_file_hash = hashlib.md5(imported_file.getvalue()).hexdigest()
            
            if (st.session_state.last_imported_file_hash != current_file_hash or 
                not st.session_state.style_import_processed):
                
                imported_style = self._import_style(imported_file)
                if imported_style:
                    st.session_state.last_imported_file_hash = current_file_hash
                    st.session_state.imported_style = imported_style
                    st.session_state.apply_imported_style = True
                    st.session_state.style_import_processed = False
                    
                    st.success(get_text('import_success'))
                    st.rerun()
    
    def _export_style(self, style_config, file_name):
        """Экспорт стиля"""
        try:
            export_data = {
                'version': '2.0',
                'export_date': str(datetime.now()),
                'ui_mode': st.session_state.ui_mode,
                'style_config': style_config,
                'timeline_elements': st.session_state.get('timeline_elements', [])
            }
            json_data = json.dumps(export_data, indent=2, ensure_ascii=False)
            return json_data.encode('utf-8')
        except Exception as e:
            st.error(f"Export error: {str(e)}")
            return None
    
    def _import_style(self, uploaded_file):
        """Импорт стиля"""
        try:
            uploaded_file.seek(0)
            content = uploaded_file.read().decode('utf-8')
            import_data = json.loads(content)
        
            # Поддержка разных версий
            if import_data.get('version') == '2.0':
                # Новая версия с поддержкой таймлайна
                return import_data
            elif 'style_config' in import_data:
                # Старая версия
                return import_data['style_config']
            else:
                return import_data
            
        except Exception as e:
            st.error(f"{get_text('import_error')}: {str(e)}")
            return None
    
    def _get_preview_metadata(self, style_config: Dict) -> Optional[Dict]:
        """Получение метаданных для предпросмотра"""
        if style_config.get('gost_style', False):
            return {
                'authors': [{'given': 'John A.', 'family': 'Smith'}, {'given': 'Alice B.', 'family': 'Doe'}],
                'title': 'Article Title',
                'journal': 'Journal of the American Chemical Society',
                'year': 2020,
                'volume': '15',
                'issue': '3',
                'pages': '122-128',
                'article_number': '',
                'doi': '10.1000/xyz123'
            }
        elif style_config.get('acs_style', False):
            return {
                'authors': [{'given': 'John A.', 'family': 'Smith'}, {'given': 'Alice B.', 'family': 'Doe'}],
                'title': 'Article Title',
                'journal': 'Journal of the American Chemical Society',
                'year': 2020,
                'volume': '15',
                'issue': '3',
                'pages': '122-128',
                'article_number': '',
                'doi': '10.1000/xyz123'
            }
        elif style_config.get('rsc_style', False):
            return {
                'authors': [{'given': 'John A.', 'family': 'Smith'}, {'given': 'Alice B.', 'family': 'Doe'}],
                'title': 'Article Title',
                'journal': 'Chemical Communications',
                'year': 2020,
                'volume': '15',
                'issue': '3',
                'pages': '122-128',
                'article_number': '',
                'doi': '10.1000/xyz123'
            }
        elif style_config.get('cta_style', False):
            return {
                'authors': [
                    {'given': 'Fei', 'family': 'He'}, 
                    {'given': 'Feng', 'family': 'Ma'},
                    {'given': 'Juan', 'family': 'Li'},
                    {'given': 'Tao', 'family': 'Li'},
                    {'given': 'Guangshe', 'family': 'Li'}
                ],
                'title': 'Effect of calcination temperature on the structural properties and photocatalytic activities of solvothermal synthesized TiO2 hollow nanoparticles',
                'journal': 'Ceramics International',
                'year': 2014,
                'volume': '40',
                'issue': '5',
                'pages': '6441-6446',
                'article_number': '',
                'doi': '10.1016/j.ceramint.2013.11.094'
            }
        elif style_config.get('elements') or st.session_state.get('timeline_elements'):
            return {
                'authors': [{'given': 'John A.', 'family': 'Smith'}, {'given': 'Alice B.', 'family': 'Doe'}],
                'title': 'Article Title',
                'journal': 'Journal of the American Chemical Society',
                'year': 2020,
                'volume': '15',
                'issue': '3',
                'pages': '122-128',
                'article_number': 'e12345',
                'doi': '10.1000/xyz123'
            }
        else:
            return None
    
    def _add_numbering(self, preview_ref: str, style_config: Dict) -> str:
        """Добавление нумерации к предпросмотру"""
        numbering = style_config['numbering_style']
        if numbering == "No numbering":
            return preview_ref
        elif numbering == "1":
            return f"1 {preview_ref}"
        elif numbering == "1.":
            return f"1. {preview_ref}"
        elif numbering == "1)":
            return f"1) {preview_ref}"
        elif numbering == "(1)":
            return f"(1) {preview_ref}"
        elif numbering == "[1]":
            return f"[1] {preview_ref}"
        else:
            return f"1. {preview_ref}"
    
    def _format_preview_html(self, preview_text: str, style_config: Dict) -> str:
        """Форматирование HTML для предпросмотра"""
        preview_html = preview_text
        
        if style_config.get('acs_style', False):
            preview_html = preview_html.replace("J. Am. Chem. Soc.", "<i>J. Am. Chem. Soc.</i>")
            preview_html = preview_html.replace("2020", "<b>2020</b>")
            preview_html = preview_html.replace("15", "<i>15</i>")
        elif style_config.get('rsc_style', False):
            preview_html = preview_html.replace("Chem. Commun.", "<i>Chem. Commun.</i>")
            preview_html = preview_html.replace("15", "<b>15</b>")
        
        return preview_html

# Основной класс приложения
class CitationStyleApp:
    """Основной класс приложения"""
    
    def __init__(self):
        self.processor = ReferenceProcessor()
        self.validator = StyleValidator()
        self.ui = UIComponents()
        init_session_state()
    
    def run(self):
        """Запуск приложения"""
        st.set_page_config(layout="wide", page_title="Citation Style Constructor")
    
        # Загрузка пользовательских предпочтений
        self.ui.load_user_preferences()
    
        # Обработка импортированного стиля (если есть)
        self._handle_imported_style()
    
        # Применение стилей темы
        self.ui.apply_theme_styles()
        
        # Рендер заголовка и контролов
        self.ui.render_header()
        
        # Рендер основного интерфейса в зависимости от режима
        if st.session_state.ui_mode == 'toolbar_mode':
            self.ui.render_toolbar_interface()
        else:
            self.ui.render_timeline_interface()
        
        # Обработка триггера обработки
        self._handle_processing_trigger()
    
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
        """Обработка данных"""
        # Валидация стиля
        is_valid, validation_messages = self.validator.validate_style_config(style_config)
        for msg in validation_messages:
            if "error" in msg.lower():
                st.error(msg)
                return
            else:
                st.warning(msg)
        
        if not is_valid:
            st.error(get_text('validation_error_no_elements'))
            return
        
        # Обработка в зависимости от типа ввода
        try:
            if isinstance(input_data, str):  # Текстовый ввод
                self._process_text_input(input_data, style_config, output_method)
            else:  # DOCX ввод
                self._process_docx_input(input_data, style_config, output_method)
        except Exception as e:
            logger.error(f"Processing error: {e}")
            st.error(f"Processing error: {str(e)}")
    
    def _process_text_input(self, references_input, style_config, output_method):
        """Обработка текстового ввода"""
        if not references_input.strip():
            st.error(get_text('enter_references_error'))
            return
        
        references = [ref.strip() for ref in references_input.split('\n') if ref.strip()]
        st.write(f"**{get_text('found_references_text').format(len(references))}**")
        
        # Создаем контейнеры для прогресса
        progress_container = st.empty()
        status_container = st.empty()
        
        with st.spinner(get_text('processing')):
            formatted_refs, txt_bytes, doi_found_count, doi_not_found_count, duplicates_info = (
                self.processor.process_references(references, style_config, progress_container, status_container)
            )
            
            statistics = generate_statistics(formatted_refs)
            output_doc_buffer = DocumentGenerator.generate_document(
                formatted_refs, statistics, style_config, duplicates_info
            )
            
            self._handle_output(formatted_refs, txt_bytes, output_doc_buffer, 
                              doi_found_count, doi_not_found_count, output_method)
    
    def _process_docx_input(self, uploaded_file, style_config, output_method):
        """Обработка DOCX ввода"""
        if not uploaded_file:
            st.error(get_text('upload_file'))
            return
        
        # Создаем контейнеры для прогресса
        progress_container = st.empty()
        status_container = st.empty()
        
        with st.spinner(get_text('processing')):
            doc = Document(uploaded_file)
            references = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
            st.write(f"**{get_text('found_references').format(len(references))}**")
            
            formatted_refs, txt_bytes, output_doc_buffer, doi_found_count, doi_not_found_count, statistics = (
                self._process_docx_references(references, style_config, progress_container, status_container)
            )
            
            self._handle_output(formatted_refs, txt_bytes, output_doc_buffer,
                              doi_found_count, doi_not_found_count, output_method)
    
    def _process_docx_references(self, references, style_config, progress_container, status_container):
        """Обработка ссылок из DOCX"""
        formatted_refs, txt_bytes, doi_found_count, doi_not_found_count, duplicates_info = (
            self.processor.process_references(references, style_config, progress_container, status_container)
        )
        
        statistics = generate_statistics(formatted_refs)
        output_doc_buffer = DocumentGenerator.generate_document(
            formatted_refs, statistics, style_config, duplicates_info
        )
        
        return formatted_refs, txt_bytes, output_doc_buffer, doi_found_count, doi_not_found_count, statistics
    
    def _handle_output(self, formatted_refs, txt_bytes, output_doc_buffer, 
                      doi_found_count, doi_not_found_count, output_method):
        """Обработка вывода"""
        # Статистика
        st.write(f"**{get_text('statistics').format(doi_found_count, doi_not_found_count)}**")
        
        # Подготовка текстового вывода
        if output_method == 'Text' if st.session_state.current_language == 'en' else 'Текст':
            output_text_value = self._format_text_output(formatted_refs, st.session_state.num)
            st.session_state.output_text_value = output_text_value
            st.session_state.show_results = True
        else:
            st.session_state.output_text_value = ""
            st.session_state.show_results = False
        
        # Сохранение данных для скачивания
        st.session_state.download_data = {
            'txt_bytes': txt_bytes,
            'output_doc_buffer': output_doc_buffer
        }
        
        st.rerun()
    
    def _format_text_output(self, formatted_refs, numbering_style):
        """Форматирование текстового вывода"""
        output_text_value = ""
        for i, (elements, is_error, metadata) in enumerate(formatted_refs):
            prefix = self._get_numbering_prefix(i, numbering_style)
            
            if is_error:
                output_text_value += f"{prefix}{elements}\n"
            else:
                if isinstance(elements, str):
                    output_text_value += f"{prefix}{elements}\n"
                else:
                    ref_str = ""
                    for j, element_data in enumerate(elements):
                        if len(element_data) == 6:
                            value, _, _, separator, _, _ = element_data
                            ref_str += value
                            if separator and j < len(elements) - 1:
                                ref_str += separator
                        else:
                            ref_str += str(element_data)
                    
                    output_text_value += f"{prefix}{ref_str}\n"
        
        return output_text_value
    
    def _get_numbering_prefix(self, index, numbering_style):
        """Получение префикса нумерации"""
        if numbering_style == "No numbering":
            return ""
        elif numbering_style == "1":
            return f"{index + 1} "
        elif numbering_style == "1.":
            return f"{index + 1}. "
        elif numbering_style == "1)":
            return f"{index + 1}) "
        elif numbering_style == "(1)":
            return f"({index + 1}) "
        elif numbering_style == "[1]":
            return f"[{index + 1}] "
        else:
            return f"{index + 1}. "
    
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
                    st.session_state.gost_style = style_cfg['gost_style']
                if 'acs_style' in style_cfg:
                    st.session_state.acs_style = style_cfg['acs_style']
                if 'rsc_style' in style_cfg:
                    st.session_state.rsc_style = style_cfg['rsc_style']
                if 'cta_style' in style_cfg:
                    st.session_state.cta_style = style_cfg['cta_style']
                
                # Режим интерфейса
                if 'ui_mode' in imported_style:
                    st.session_state.ui_mode = imported_style['ui_mode']
                
                # Элементы таймлайна
                if 'timeline_elements' in imported_style:
                    st.session_state.timeline_elements = imported_style['timeline_elements']
                
                # Обычные элементы
                if 'elements' in style_cfg:
                    elements = style_cfg['elements']
                    # Очищаем существующие элементы
                    for i in range(8):
                        st.session_state[f"el{i}"] = ""
                        st.session_state[f"it{i}"] = False
                        st.session_state[f"bd{i}"] = False
                        st.session_state[f"pr{i}"] = False
                        st.session_state[f"sp{i}"] = ". "
                    
                    # Устанавливаем новые элементы
                    for i, (element, config) in enumerate(elements):
                        if i < 8:
                            st.session_state[f"el{i}"] = element
                            st.session_state[f"it{i}"] = config.get('italic', False)
                            st.session_state[f"bd{i}"] = config.get('bold', False)
                            st.session_state[f"pr{i}"] = config.get('parentheses', False)
                            st.session_state[f"sp{i}"] = config.get('separator', ". ")
            
            st.session_state.style_applied = True
            st.session_state.style_import_processed = True
        
        apply_style_callback()

# Вспомогательные функции
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
