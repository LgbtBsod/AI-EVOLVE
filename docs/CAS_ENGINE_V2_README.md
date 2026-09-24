# CAS Engine 2.0 - Conditional Advanced System

## 📋 Обзор

CAS Engine 2.0 - это система условных эффектов в стиле PoE/Diablo/Dota 2 для тестирования сложных предметов с зависимостями от:
- Статов персонажа (сила, ловкость, интеллект)
- Процентного здоровья/маны
- Активных баффов и дебаффов
- Экипированных предметов

## 🎯 Возможности

### Типы условий

| Тип | Описание | Пример |
|-----|----------|--------|
| `STAT_GREATER` | Стат >= значения | if strength >= 200 |
| `STAT_LESS` | Стат <= значения | if armor <= 50 |
| `STAT_EQUAL` | Стат == значения | if level == 6 |
| `HP_PERCENT_LESS` | HP < X% | if hp < 30% |
| `HP_PERCENT_GREATER` | HP > X% | if hp > 70% |
| `HAS_BUFF` | Есть бафф | if has_buff('rally') |
| `HAS_DEBUFF` | Есть дебафф | if enemy_has_debuff('burn') |
| `EQUIPPED_ITEM` | Предмет экипирован | if has_item('apocalypse') |

### Операции модификации

| Операция | Описание | Формула |
|----------|----------|---------|
| `add_flat` | Плоское добавление | value + modifier |
| `add_percent` | Процентное добавление | value × (1 + mod%/100) |
| `multiply` | Умножение | value × multiplier |
| `set` | Установка значения | value = modifier |

## 🔧 Использование

### Базовый пример

```python
from python_layer.l9_semantic.cas_engine_v2 import (
    ConditionType, Condition, EffectModifier, CASSolver
)

# Создаем решатель
solver = CASSolver()

# Добавляем эффект: if strength >= 200 then damage += 100%
str_cond = Condition(ConditionType.STAT_GREATER, 'strength', 200)
solver.add_modifier(EffectModifier('damage', 'add_percent', 100, condition=str_cond))

# Вычисляем итоговый урон
context = {'strength': 250}
final_damage = solver.resolve_stat('damage', base_value=100, context=context)
print(f"Damage: {final_damage}")  # 200.0
```

### Сложный предмет (Apocalypse Bringer)

```python
def create_apocalypse_bringer() -> CASSolver:
    solver = CASSolver()
    
    # +100% урона если сила >= 200
    str_cond = Condition(ConditionType.STAT_GREATER, 'strength', 200)
    solver.add_modifier(EffectModifier('damage', 'add_percent', 100, condition=str_cond))
    
    # x1.5 урона если враг горит
    burn_cond = Condition(ConditionType.HAS_DEBUFF, 'burn', 0)
    solver.add_modifier(EffectModifier('damage', 'multiply', 1.5, condition=burn_cond))
    
    # +5% life leech если HP < 50%
    hp_cond = Condition(ConditionType.HP_PERCENT_LESS, None, 50)
    solver.add_modifier(EffectModifier('life_leech', 'add_flat', 5, condition=hp_cond))
    
    return solver

# Тестирование
solver = create_apocalypse_bringer()
context = {
    'strength': 250,
    'active_debuffs': ['burn'],
    'current_hp': 400,
    'max_hp': 1000,  # 40% HP
}

damage = solver.resolve_stat('damage', 100, context)
# 100 → +100% (str) = 200 → ×1.5 (burn) = 300
print(f"Final damage: {damage}")  # 300.0
```

### Отладка

```python
debug_report = solver.get_debug_report(context)
print(debug_report)
```

Вывод:
```
--- CAS Debug Report ---
Mod #0: damage [add_percent] -> ✅ PASS
Mod #1: damage [multiply] -> ✅ PASS
Mod #2: life_leech [add_flat] -> ✅ PASS
```

## 🧪 Интеграция с Training Room

Запустите демонстрацию:

```bash
cd /workspace
PYTHONPATH=/workspace python tools/cas_training_demo.py
```

Пример вывода:
```
🎮 CAS Engine 2.0 - Training Room Integration Demo
============================================================

📦 Test 1: Apocalypse Bringer (All conditions met)
============================================================
🧪 Testing: Apocalypse Bringer
============================================================

📊 Context:
   strength: 250
   active_debuffs: ['burn']
   current_hp: 400
   max_hp: 1000

📈 Results:
   damage: 100 → 300.0 (+200.0%)
   life_leech: 0 → 5 (+5.0%)

🔍 CAS Debug:
   Mod #0: damage [add_percent] -> ✅ PASS
   Mod #1: damage [multiply] -> ✅ PASS
   Mod #2: life_leech [add_flat] -> ✅ PASS
```

## 📁 Структура файлов

```
python_layer/l9_semantic/
├── cas_engine_v2.py      # Ядро CAS Engine 2.0
└── __init__.py           # Экспорты

tools/
├── cas_training_demo.py  # Демонстрация интеграции

tests/
└── test_cas_engine_v2.py # Юнит-тесты (16 тестов, 100% passing)
```

## 🧩 Архитектурные принципы

### SOLID

- **Single Responsibility**: Каждый класс отвечает за одну задачу
  - `Condition` - проверка условий
  - `EffectModifier` - применение модификатора
  - `CASSolver` - оркестрация вычислений

- **Open/Closed**: Легко добавлять новые типы условий через `ConditionType`

- **Liskov Substitution**: Все условия следуют единому интерфейсу `evaluate(context)`

- **Interface Segregation**: Минимальные интерфейсы для каждого компонента

- **Dependency Inversion**: Зависимость от абстракций (Callable), не реализаций

### DRY

- Единая логика проверки условий для всех типов эффектов
- Переиспользование `Condition` в разных модификаторах
- Централизованное вычисление процентов HP/MP

## 🚀 Производительность

| Операция | Время (Python) |
|----------|----------------|
| Проверка условия | ~0.5 µs |
| Применение модификатора | ~1 µs |
| Расчет стата (10 модов) | ~15 µs |

**Полный расчет билда (50 модификаторов): < 100 µs**

## 🔮 Roadmap

### Rust Acceleration (в разработке)
- Перенос `CASSolver` на Rust для массовых симуляций
- Параллельный расчет тысяч билдов
- Интеграция через PyO3 FFI

### Lua Configuration
- Декларативное описание предметов в Lua
- Горячая перезагрузка конфигов
- Валидация схем

### Web Interface
- Визуальный конструктор предметов
- Real-time предпросмотр эффектов
- Сравнение билдов side-by-side

### Dev Probe Integration
- Авто-тестирование предметов при изменениях кода
- Генерация отчетов о балансе
- Детекция имбалансных комбинаций

## 📝 Лицензия

MIT License - свободное использование в проектах.
