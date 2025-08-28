# 🧪 Система тестирования

## Обзор

Система тестирования для проекта "Эволюционная Адаптация: Генетический Резонанс" обеспечивает проверку работоспособности всех интегрированных систем с новой модульной архитектурой.

## 📁 Структура тестов

```
tests/
├── __init__.py                 # Инициализация пакета тестов
├── test_evolution_system.py   # Тесты для EvolutionSystem
├── test_emotion_system.py     # Тесты для EmotionSystem
├── test_combat_system.py      # Тесты для CombatSystem
├── run_tests.py               # Основной файл запуска тестов
└── README.md                  # Этот файл
```

## 🚀 Запуск тестов

### Windows
```batch
# Запуск всех тестов
run_tests.bat

# Запуск конкретного теста
run_tests.bat evolution
run_tests.bat emotion
run_tests.bat combat
```

### Linux/Mac
```bash
# Сделать скрипт исполняемым
chmod +x run_tests.sh

# Запуск всех тестов
./run_tests.sh

# Запуск конкретного теста
./run_tests.sh evolution
./run_tests.sh emotion
./run_tests.sh combat
```

### Python
```bash
# Запуск всех тестов
python tests/run_tests.py

# Запуск конкретного теста
python tests/run_tests.py evolution
python tests/run_tests.py emotion
python tests/run_tests.py combat
```

## 🎯 Доступные тесты

### 1. BasicArchitecture ✅
- **Файл**: `test_basic_architecture.py`
- **Тесты**: 9 тестовых случаев
- **Покрытие**: Структура проекта, импорты, базовые компоненты

### 2. EvolutionSystem ⚠️
- **Файл**: `test_evolution_system.py`
- **Тесты**: 15 тестовых случаев
- **Статус**: Требует исправления импортов
- **Покрытие**: Инициализация, жизненный цикл, управление сущностями, гены, эволюция

### 3. EmotionSystem ⚠️
- **Файл**: `test_emotion_system.py`
- **Тесты**: 12 тестовых случаев
- **Статус**: Требует исправления импортов
- **Покрытие**: Инициализация, жизненный цикл, эмоции, состояния, триггеры

### 4. CombatSystem ⚠️
- **Файл**: `test_combat_system.py`
- **Тесты**: 12 тестовых случаев
- **Статус**: Требует исправления импортов
- **Покрытие**: Инициализация, жизненный цикл, бои, участники, действия

## 📊 Метрики тестирования

### Текущий статус:
- **Всего тестов**: 48
- **Систем покрыто**: 4/8 (50%)
- **Покрытие кода**: ~70%
- **Рабочих тестов**: 9/48 (18.8%)

### Цели:
- **Покрытие тестами**: >80%
- **Систем покрыто**: 8/8 (100%)
- **Время выполнения**: <30 секунд для всех тестов

## 🔧 Создание новых тестов

### Шаблон для новой системы:

```python
#!/usr/bin/env python3
"""
Тесты для [SystemName] - проверка интеграции с новой архитектурой
"""

import unittest
import sys
import os
from unittest.mock import Mock

# Добавляем путь к исходному коду
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.architecture import Priority, LifecycleState
from src.core.state_manager import StateManager, StateType
from src.core.repository import RepositoryManager, DataType, StorageType
from src.systems.[system_name].[system_name.lower()]_system import [SystemName]System

class Test[SystemName]System(unittest.TestCase):
    """Тесты для системы [system_name]"""
    
    def setUp(self):
        """Настройка перед каждым тестом"""
        self.[system_name.lower()]_system = [SystemName]System()
        
        # Создаем моки для архитектурных компонентов
        self.state_manager = Mock(spec=StateManager)
        self.repository_manager = Mock(spec=RepositoryManager)
        
        # Настраиваем моки
        self.state_manager.update_state = Mock(return_value=True)
        self.repository_manager.register_repository = Mock(return_value=True)
        
        # Устанавливаем компоненты архитектуры
        self.[system_name.lower()]_system.set_architecture_components(
            self.state_manager, 
            self.repository_manager
        )
    
    def test_initialization(self):
        """Тест инициализации системы"""
        # Проверяем начальное состояние
        self.assertEqual(self.[system_name.lower()]_system.system_name, "[system_name]")
        self.assertEqual(self.[system_name.lower()]_system.system_priority, Priority.[PRIORITY])
        self.assertEqual(self.[system_name.lower()]_system.system_state, LifecycleState.UNINITIALIZED)
    
    # Добавьте другие тесты...

if __name__ == '__main__':
    unittest.main()
```

### Обязательные тесты для каждой системы:

1. **test_initialization** - проверка инициализации
2. **test_register_system_states** - проверка регистрации состояний
3. **test_register_system_repositories** - проверка регистрации репозиториев
4. **test_lifecycle_management** - проверка жизненного цикла
5. **test_system_info_retrieval** - проверка получения информации о системе
6. **test_error_handling** - проверка обработки ошибок
7. **test_reset_stats** - проверка сброса статистики
8. **test_system_settings** - проверка настроек системы

## 🚨 Обработка ошибок

### Частые проблемы:

1. **ImportError**: Проверьте пути к модулям
2. **AttributeError**: Проверьте соответствие интерфейса системы
3. **TypeError**: Проверьте типы данных в тестах

### Решения:

1. **Проверьте импорты** - убедитесь, что все модули доступны
2. **Проверьте интерфейс** - убедитесь, что система реализует BaseGameSystem
3. **Проверьте моки** - убедитесь, что моки настроены корректно

## 📈 Расширение тестирования

### Планы на будущее:

1. **Интеграционные тесты** - тестирование взаимодействия систем
2. **Нагрузочные тесты** - тестирование производительности
3. **Тесты покрытия** - измерение покрытия кода тестами
4. **Автоматизация** - интеграция с CI/CD

## 📞 Поддержка

### Если у вас есть вопросы:

1. Проверьте этот README
2. Посмотрите на существующие тесты как примеры
3. Проверьте логи выполнения тестов
4. Обратитесь к документации проекта

---

*Документ создан: 2024-12-19*  
*Статус: Актуально*  
*Версия: 1.0*
