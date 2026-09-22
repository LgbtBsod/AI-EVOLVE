# Dev Probe - Модульная система анализа игр

## 📦 Архитектура

```
dev_probe/
├── core/                      # Ядро системы
│   ├── __init__.py
│   ├── snapshot_manager.py    # Управление снимками состояния
│   ├── event_tracker.py       # Отслеживание событий
│   ├── state_analyzer.py      # Анализ состояний и аномалий
│   └── logger_setup.py        # Настройка логирования
│
├── plugins/                   # Система плагинов
│   ├── __init__.py            # Базовые классы + готовые плагины
│   │   ├── DevProbePlugin     # Абстрактный базовый класс
│   │   ├── ToughnessPlugin    # Анализ стойкости
│   │   ├── EffectsPlugin      # Анализ эффектов
│   │   └── CombatPlugin       # Анализ боя
│   └── <custom_plugin>.py     # Пользовательские плагины
│
├── snapshots/                 # Сохраненные снимки (auto-generated)
├── reports/                   # Отчеты (auto-generated)
└── test_dev_probe_modules.py  # Тесты
```

## 🔌 Плагины

### ToughnessPlugin
Анализирует механику стойкости в стиле HSR/BNS:
- Считает количество пробитий (BREAK)
- Отслеживает урон по стойкости
- Определяет уникальные сущности с пробитой стойкостью

### EffectsPlugin  
Анализирует систему баффов/дебаффов:
- Подсчитывает примененные эффекты
- Анализирует теги (NEGATIVE, CC, DOT и др.)
- Считает длительность CC эффектов

### CombatPlugin
Анализирует боевую систему:
- Общий нанесенный урон
- Критические попадания и шанс крита
- Количество убийств

## 🚀 Использование

```python
from dev_probe.core import SnapshotManager, EventTracker, StateAnalyzer
from dev_probe.plugins import ToughnessPlugin, EffectsPlugin, CombatPlugin

# Инициализация
output_dir = Path("./dev_probe_output")
snapshot_mgr = SnapshotManager(output_dir)
event_tracker = EventTracker()
state_analyzer = StateAnalyzer()

# Инициализация плагинов
plugins = [
    ToughnessPlugin(),
    EffectsPlugin(),
    CombatPlugin(),
]

context = {"event_tracker": event_tracker}
for plugin in plugins:
    plugin.on_init(context)

# В игровом цикле
def game_loop():
    # Сделать снимок состояния
    state = get_game_state()  # Ваши данные
    snapshot = snapshot_mgr.take_snapshot(state, timestamp, frame)
    
    # Проанализировать на аномалии
    anomalies = state_analyzer.analyze_snapshot(snapshot)
    
    # Обработать плагинами
    for plugin in plugins:
        extra_data = plugin.on_snapshot(snapshot)
        if extra_data:
            snapshot.update(extra_data)

# Завершение
for plugin in plugins:
    report = plugin.on_finish()
    print(f"{plugin.name}: {report}")
```

## 🧪 Тесты

Все тесты проходят успешно:
```bash
cd AI-EVOLVE/tools/dev_probe
python test_dev_probe_modules.py
```

Результат: **6/6 тестов пройдено** ✓

## 🎯 EventType для отслеживания

```python
class EventType(Enum):
    COMBAT_START = "combat_start"
    COMBAT_END = "combat_end"
    DAMAGE_DEALT = "damage_dealt"
    DAMAGE_TAKEN = "damage_taken"
    EFFECT_APPLIED = "effect_applied"
    EFFECT_EXPIRED = "effect_expired"
    TOUGHNESS_DAMAGE = "toughness_damage"
    TOUGHNESS_BREAK = "toughness_break"
    TOUGHNESS_RECOVERED = "toughness_recovered"
    ENTITY_DIED = "entity_died"
    ENTITY_SPAWNED = "entity_spawned"
    ANOMALY_DETECTED = "anomaly_detected"
```

## 📊 Пример отчета плагина

```json
{
  "plugin": "toughness_analyzer",
  "total_breaks": 3,
  "unique_entities_broken": 2,
  "total_toughness_damage": 450,
  "break_events": [...]
}
```

## 🔧 Создание своего плагина

```python
from dev_probe.plugins import DevProbePlugin

class MyCustomPlugin(DevProbePlugin):
    name = "my_plugin"
    description = "Мой кастомный анализ"
    
    def on_init(self, context):
        # Регистрация обработчиков событий
        pass
    
    def on_snapshot(self, snapshot):
        # Анализ снапшота
        return {"my_data": ...}
    
    def on_event(self, event):
        # Обработка события
        pass
    
    def on_finish(self):
        # Финальный отчет
        return {"summary": ...}
```
