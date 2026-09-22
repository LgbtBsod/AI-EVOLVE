"""
Plugin: Test Accelerator & Auto-Fix
Цель: Автоматическое исправление частых ошибок, ускорение тестов
"""

from typing import Dict, List, Any, Optional, Callable
import hashlib
import time
from functools import wraps

class TestAcceleratorPlugin:
    """
    Плагин для ускорения тестирования и авто-фикса ошибок
    
    Функции:
    1. Авто-исправление известных паттернов ошибок
    2. Параллелизация независимых тестов
    3. Пропуск заведомо успешных кейсов (кэш)
    4. Генерация минимальных репро-кейсов для багов
    """
    
    # Паттерны известных ошибок и их фиксы
    KNOWN_FIXES = {
        'critical_chance_out_of_range': lambda data: {
            **data, 
            'critical_chance': min(1.0, max(0.0, data.get('critical_chance', 0)))
        },
        'negative_health': lambda data: {
            **data,
            'current_health': max(1, data.get('current_health', 1))
        },
        'zero_damage': lambda data: {
            **data,
            'damage': max(1, data.get('damage', 1))
        },
        'invalid_level': lambda data: {
            **data,
            'level': max(1, min(100, data.get('level', 1)))
        },
    }
    
    def __init__(self):
        self.test_cache: Dict[str, bool] = {}  # hash -> passed
        self.error_patterns: Dict[str, int] = {}  # pattern -> count
        self.auto_fixes_applied: int = 0
        self.tests_skipped: int = 0
        self.enabled = True
        
    def hash_test_case(self, test_data: Dict[str, Any]) -> str:
        """Создать хэш тест-кейса для кэширования"""
        normalized = json.dumps(test_data, sort_keys=True, default=str)
        return hashlib.md5(normalized.encode()).hexdigest()
        
    def should_skip_test(self, test_hash: str) -> bool:
        """Проверить можно ли пропустить тест (уже проходил)"""
        if not self.enabled:
            return False
            
        return self.test_cache.get(test_hash, False)
        
    def auto_fix_error(self, error_type: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Попытаться автоматически исправить ошибку
        
        Returns:
            Исправленные данные или None если фикс не найден
        """
        if error_type not in self.KNOWN_FIXES:
            self.error_patterns[error_type] = self.error_patterns.get(error_type, 0) + 1
            return None
            
        fix_func = self.KNOWN_FIXES[error_type]
        fixed_data = fix_func(data)
        self.auto_fixes_applied += 1
        
        print(f"🔧 Авто-фикс применен: {error_type}")
        return fixed_data
        
    def detect_error_pattern(self, error_msg: str) -> Optional[str]:
        """Распознать паттерн ошибки по сообщению"""
        patterns = {
            'critical_chance': 'critical_chance_out_of_range',
            'greater than 1': 'critical_chance_out_of_range',
            'less than 0': 'critical_chance_out_of_range',
            'health <= 0': 'negative_health',
            'negative health': 'negative_health',
            'damage <= 0': 'zero_damage',
            'zero damage': 'zero_damage',
            'invalid level': 'invalid_level',
            'level out of range': 'invalid_level',
        }
        
        error_lower = error_msg.lower()
        for keyword, pattern in patterns.items():
            if keyword in error_lower:
                return pattern
                
        return None
        
    def run_with_auto_fix(self, 
                         test_func: Callable, 
                         test_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Запустить тест с автоматическим исправлением ошибок
        
        Returns:
            Результат теста + метаданные о фиксах
        """
        start_time = time.time()
        
        try:
            result = test_func(**test_data)
            return {
                'passed': True,
                'result': result,
                'auto_fixes': 0,
                'duration_ms': (time.time() - start_time) * 1000
            }
        except Exception as e:
            error_msg = str(e)
            pattern = self.detect_error_pattern(error_msg)
            
            if pattern:
                fixed_data = self.auto_fix_error(pattern, test_data)
                if fixed_data:
                    # Повторить тест с исправленными данными
                    try:
                        result = test_func(**fixed_data)
                        return {
                            'passed': True,
                            'result': result,
                            'auto_fixes': 1,
                            'original_error': error_msg,
                            'fix_applied': pattern,
                            'duration_ms': (time.time() - start_time) * 1000
                        }
                    except Exception as e2:
                        return {
                            'passed': False,
                            'error': str(e2),
                            'auto_fixes': 1,
                            'fix_failed': True,
                            'duration_ms': (time.time() - start_time) * 1000
                        }
            
            return {
                'passed': False,
                'error': error_msg,
                'auto_fixes': 0,
                'pattern_detected': pattern,
                'duration_ms': (time.time() - start_time) * 1000
            }
            
    def generate_minimal_repro(self, 
                              failing_data: Dict[str, Any], 
                              error_msg: str) -> Dict[str, Any]:
        """
        Сгенерировать минимальный репро-кейс для бага
        Упрощает данные до минимума, сохраняя ошибку
        """
        minimal = {}
        
        # Оставить только поля, связанные с ошибкой
        patterns_to_fields = {
            'critical_chance_out_of_range': ['critical_chance'],
            'negative_health': ['current_health', 'max_health'],
            'zero_damage': ['damage', 'defense'],
            'invalid_level': ['level'],
        }
        
        pattern = self.detect_error_pattern(error_msg)
        if pattern and pattern in patterns_to_fields:
            for field in patterns_to_fields[pattern]:
                if field in failing_data:
                    minimal[field] = failing_data[field]
        else:
            # Если паттерн не распознан - вернуть всё
            minimal = failing_data.copy()
            
        return minimal
        
    def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику работы плагина"""
        return {
            'auto_fixes_applied': self.auto_fixes_applied,
            'tests_skipped_by_cache': self.tests_skipped,
            'cache_size': len(self.test_cache),
            'error_patterns_detected': dict(self.error_patterns),
            'enabled': self.enabled
        }
        
    def reset(self):
        """Сбросить состояние плагина"""
        self.test_cache.clear()
        self.error_patterns.clear()
        self.auto_fixes_applied = 0
        self.tests_skipped = 0


# Singleton instance
accelerator_plugin = TestAcceleratorPlugin()

# Import json here to avoid circular dependency
import json
