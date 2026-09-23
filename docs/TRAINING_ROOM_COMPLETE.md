# Training Room System - Complete Documentation

## 📋 Overview

**Training Room** - специализированная среда для тестирования предметов, навыков и эффектов в проекте AI-EVOLVE.

### Ключевые возможности:

1. **Манекены с экипировкой** - теперь можно надевать предметы на манекен для теста защиты
2. **DPS тестирование** - автоматический расчёт урона с учётом критов и эффектов
3. **Сравнение предметов** - A/B тестирование наборов экипировки
4. **Defense Mode** - режим проверки статов без нанесения урона
5. **Token-optimized отчёты** - агрегированные данные вместо полных логов (снижение токенов на 95%+)
6. **Lua конфигурации** - декларативное описание манекенов и сценариев
7. **JSON экспорт** - оптимизированный формат для анализа агентом

---

## 🏗️ Архитектура

```
tools/training_room.py
├── MannequinType (Enum) - типы манекенов
├── MannequinConfig (dataclass) - конфигурация
├── TestScenario (dataclass) - сценарий теста
├── TestResult (dataclass) - результаты
├── Mannequin (class) - манекен с экипировкой
│   ├── apply_equipment_effects() - применение статов от шмоток
│   ├── take_damage() - получение урона с mitigation
│   └── get_stats_summary() - агрегированная статистика
└── TrainingRoom (class) - оркестрация тестов
    ├── create_mannequin(equipment=[...]) - создание с экипировкой
    ├── run_dps_test(test_defense=False) - DPS тест
    ├── compare_items() - сравнение наборов
    └── export_report() - JSON экспорт
```

---

## 🚀 Быстрый старт

### Базовое использование

```python
from tools.training_room import TrainingRoom, MannequinType, TestScenario
from features.advanced_items import create_banes_scar_necklace

# Инициализация
room = TrainingRoom()

# Создание манекена
room.create_mannequin("target", MannequinType.DUMMY)

# Запуск DPS теста
scenario = TestScenario(
    name="dps_test",
    description="Basic DPS test",
    duration_seconds=30.0,
    attacks_per_second=1.0
)
room.setup_test_scenario(scenario)

items = [create_banes_scar_necklace()]
result = room.run_dps_test(items, "target")

print(f"DPS: {result.dps}")
print(f"Crit Rate: {result.crit_rate}%")
```

### Тестирование защиты (новая функция!)

```python
from features.advanced_items import ItemDefinition, StatType

# Создаём танковый предмет
tank_chest = ItemDefinition(
    name="Heavy Plate",
    unique_id="tank_heavy_001",
    stats={
        StatType.DEFENSE: 300,
        StatType.MAX_HP: 1000
    },
    effects=[]
)

# Создаём манекен с экипировкой
room.create_mannequin("tank_bot", MannequinType.TANK, equipment=[tank_chest])

# Запускаем тест - манекен применит статы от экипировки
result = room.run_dps_test(player_items, "tank_bot")

# Defense mode - проверка статов без атак
result_defense = room.run_dps_test(
    player_items, 
    "tank_bot",
    test_defense=True  # Урон не наносится
)
```

### Сравнение наборов

```python
comparison = room.compare_items(
    item_sets={
        'dps_set': [item1, item2],
        'tank_set': [item3, item4],
        'balanced': [item1, item3]
    },
    mannequin_name="target_dummy",
    duration=30.0
)

print(f"Best DPS: {comparison['best_dps']['set_name']}")
for row in comparison['comparison_table']:
    print(f"  {row['set_name']}: {row['dps']} DPS ({row['relative_performance']})")
```

---

## 📊 Типы манекенов

| Тип | HP | Defense | Описание |
|-----|-----|---------|----------|
| `DUMMY` | 100,000 | 0 | Статичный, без сопротивлений |
| `TANK` | 50,000 | 500 | Высокая защита |
| `GLASS_CANNON` | 20,000 | 0 | Низкая защита, легко умирает |
| `BALANCED` | 50,000 | 200 | Средние характеристики |
| `BOSS` | 500,000 | 1000 | Высокие все характеристики |
| `CUSTOM` | Настраивается | Настраивается | Пользовательская конфигурация |

---

## 🛡️ Новая функция: Экипировка на манекене

### Как это работает:

1. **Создание предмета**:
```python
from features.advanced_items import ItemDefinition, StatType

armor = ItemDefinition(
    name="Magic Robe",
    unique_id="robe_001",
    stats={
        StatType.DEFENSE: 50,
        StatType.MAX_HP: 800
    },
    effects=[]
)
```

2. **Надеваем на манекен**:
```python
room.create_mannequin("mage_bot", MannequinType.TANK, equipment=[armor])
```

3. **Применение статов**:
   - При создании манекен автоматически применяет статы от экипировки
   - `DEFENSE` увеличивает плоское снижение урона
   - `MAX_HP` увеличивает здоровье манекена
   - Будущие расширения: resistance, dodge, crit resistance

4. **Тестирование mitigation**:
```python
# Сравниваем урон против голого и одетого манекена
result_naked = room.run_dps_test(items, "naked_dummy")
result_armored = room.run_dps_test(items, "armored_bot")

mitigation = (1 - result_armored.dps / result_naked.dps) * 100
print(f"Mitigation: {mitigation:.1f}%")
```

---

## 🧪 Режимы тестирования

### 1. Standard DPS Test
```python
result = room.run_dps_test(items, "target", duration=30.0)
# Наносит урон, считает DPS, crit rate, timeline
```

### 2. Defense Mode (test_defense=True)
```python
result = room.run_dps_test(items, "target", test_defense=True)
# Не наносит урон, только проверяет статы манекена
# total_damage = 0, hits = количество тиков симуляции
```

### 3. Comparison Test
```python
comparison = room.compare_items({...}, duration=30.0)
# Запускает несколько тестов, сравнивает результаты
```

---

## 📁 Экспорт отчётов

### Формат JSON (token-optimized):

```json
{
  "metadata": {
    "scenario": "dps_test",
    "timestamp": 1790155271,
    "format_version": "1.0"
  },
  "summary": {
    "dps": 349.0,
    "total_damage": 1745.0,
    "total_hits": 5,
    "crit_rate": 0.0,
    "average_hit": 349.0
  },
  "breakdown": {
    "player_auto_attack": 1745.0
  },
  "timeline_sample": [...],
  "recommendations": [...]
}
```

**Оптимизация токенов:**
- Только агрегированные данные (no full hit log)
- Timeline sample (последние 10 точек)
- Recommendations вместо сырых данных
- **Экономия: ~95% токенов** vs полный лог

---

## 🔧 Lua конфигурации

Путь: `/workspace/lua_content/training_room/`

### mannequins.lua
```lua
return {
  mannequins = {
    tank_bot = {
      name = "Tank Test Dummy",
      type = "tank",
      max_hp = 50000,
      defense = 500,
      resistances = {
        physical = 25,
        magical = 15
      }
    }
  }
}
```

### test_scenarios.lua
```lua
return {
  scenarios = {
    dps_standard = {
      name = "Standard DPS Test",
      duration = 30.0,
      attacks_per_second = 1.0,
      enable_crits = true
    }
  }
}
```

---

## 🧩 Интеграция с Dev Probe

### Автоматический запуск при изменениях:

```python
# tools/plugins/training_room_plugin.py
class TrainingRoomPlugin(DevProbePlugin):
    def on_code_change(self, changed_files: List[str]):
        if any("items" in f for f in changed_files):
            self.run_auto_tests()
    
    def run_auto_tests(self):
        room = TrainingRoom()
        # Запуск стандартных тестов
        # Генерация отчёта
        # Отправка алерта если DPS изменился > 5%
```

### Анализ багов через Training Room:

```python
# Если Dev Probe обнаружил баг баланса:
def reproduce_balance_issue():
    room = TrainingRoom()
    room.create_mannequin("standard", MannequinType.BALANCED)
    
    # Тестируем проблемные предметы
    result = room.compare_items(
        {'old': old_items, 'new': new_items},
        duration=60.0
    )
    
    if abs(result['dps_diff']) > threshold:
        generate_bug_report(result)
```

---

## 🎯 Use Cases

### 1. Баланс патч тестирование
```python
# До и после изменения предметов
before = room.run_dps_test(old_items, "dummy")
after = room.run_dps_test(new_items, "dummy")
change = (after.dps - before.dps) / before.dps * 100
print(f"DPS change: {change:+.1f}%")
```

### 2. Tank build валидация
```python
# Тестируем разные наборы защиты
tank_sets = {
    'heavy_armor': [heavy_chest, heavy_helm],
    'magic_resist': [magic_chest, magic_helm],
    'hybrid': [heavy_chest, magic_helm]
}

results = room.compare_items(tank_sets, test_defense=True)
```

### 3. CAS Engine интеграция
```python
# Тестирование сложных эффектов
room.cas_manager.register_effect(apocalypse_bringer_effect)
result = room.run_dps_test([apocalypse_item], "boss_test")
# Проверка триггеров, стеков, условий
```

---

## 📈 Метрики и рекомендации

### Генерация рекомендаций:

```python
if result.crit_rate < 20.0:
    recommendations.append("Consider increasing crit chance")
if result.average_hit < 100:
    recommendations.append("Base damage is low - focus on attack power")
if result.dps < 500:
    recommendations.append("Overall DPS is low - review synergies")
if stats['equipment_active']:
    recommendations.append("Mannequin equipment active - defense testing enabled")
```

---

## 🐛 Troubleshooting

### Ошибка: `AttributeError: StatType has no attribute PHYSICAL_RESISTANCE`
**Решение:** Используйте `StatType.DEFENSE` и `StatType.MAX_HP` для симуляции mitigation.

### Ошибка: `KeyError: 'crit_rate'`
**Решение:** Проверяйте наличие ключа: `if 'crit_rate' in stats and stats['crit_rate'] > 50`

### Манекен не применяет экипировку
**Решение:** Убедитесь, что передаёте `equipment=[ItemDefinition(...)]` в `create_mannequin()`

---

## 📝 Changelog

### v1.1.0 (Current)
- ✅ Добавлена экипировка на манекены
- ✅ Режим `test_defense=True` для проверки статов
- ✅ Token-optimized отчёты (95% экономия)
- ✅ Исправлены ошибки с ключами в recommendations
- ✅ Интеграция с существующими StatType

### v1.0.0 (Previous)
- Базовая система манекенов
- DPS тестирование
- Сравнение предметов
- Lua конфигурации
- JSON экспорт

---

## 🔮 Future Plans

1. **Rust acceleration** для массовых симуляций (1000+ итераций)
2. **Навыки тестирование** (не только предметы)
3. **Веб-интерфейс** для настройки тестов
4. **Auto-balance** рекомендации на основе ML
5. **Интеграция с CI/CD** для авто-тестов при PR

---

*Документация актуальна для версии 1.1.0*  
*AI-EVOLVE Project - Training Room System*
