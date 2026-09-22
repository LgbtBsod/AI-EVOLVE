# Dev Probe - Модульная система анализа игр + AI Assistant Toolkit

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
│   │   ├── CombatPlugin       # Анализ боя
│   │   └── AdvancedMechanicsPlugin  # Анализ продвинутых механик
│   └── <custom_plugin>.py     # Пользовательские плагины
│
├── ai_assistant_toolkit.py    # НОВЫЙ! Инструменты для AI-агентов
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

### AdvancedMechanicsPlugin (НОВЫЙ!)
Анализирует продвинутые игровые механики:
- Комбо-системы (максимальное комбо, сбросы комбо)
- Уклонения/парирования/блоки
- Управление ресурсами (мана, энергия, ярость, выносливость)
- Детекция аномалий (невозможные комбо, спам уклонений, истощение ресурсов)

## 🚀 Использование

```python
from dev_probe.core import SnapshotManager, EventTracker, StateAnalyzer
from dev_probe.plugins import ToughnessPlugin, EffectsPlugin, CombatPlugin, AdvancedMechanicsPlugin

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
    AdvancedMechanicsPlugin(),  # Новый плагин!
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

Результат: **7/7 тестов пройдено** ✓

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
    DODGE_PERFORMED = "dodge_performed"        # НОВОЕ!
    PARRY_PERFORMED = "parry_performed"        # НОВОЕ!
    BLOCK_PERFORMED = "block_performed"        # НОВОЕ!
    COMBO_STARTED = "combo_started"            # НОВОЕ!
    COMBO_FINISHED = "combo_finished"          # НОВОЕ!
    RESOURCE_CHANGED = "resource_changed"      # НОВОЕ!
    SKILL_USED = "skill_used"                  # НОВОЕ!
    ITEM_USED = "item_used"                    # НОВОЕ!
    QUEST_STARTED = "quest_started"            # НОВОЕ!
    QUEST_COMPLETED = "quest_completed"        # НОВОЕ!
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

## 🆕 Что нового в этой версии

- **AI Assistant Toolkit**: Полностью новый модуль для ускорения работы AI-агентов
  - `TokenBudget`: Трекер токенов для оптимизации отчетов
  - `IssueReport`: Структурированные отчеты о проблемах с приоритетами
  - `TrendAnalysis`: Предиктивная аналитика с детекцией аномалий
  - `analyze_test_results`: Автоматический анализ тестов и выявление регрессий
  - `detect_anomalies_in_metrics`: Статистическая детекция аномалий (z-score)
  - `generate_compact_report`: Сжатые отчеты для экономии токенов
  - Кэширование данных с TTL для ускорения повторных запросов

- **AdvancedMechanicsPlugin**: Анализ продвинутых механик
  - Комбо-системы (максимальное комбо, сбросы комбо)
  - Уклонения/парирования/блоки
  - Управление ресурсами (мана, энергия, ярость, выносливость)
  - Детекция аномалий (невозможные комбо, спам уклонений, истощение ресурсов)

- **Новые типы событий**: Добавлено 10 новых типов событий для отслеживания уклонений, комбо, ресурсов и квестов

- **Улучшенная архитектура**: Модульная система плагинов позволяет легко добавлять новые анализаторы

- **Расширенное тестирование**: Добавлены тесты для нового плагина

## 🚀 Использование AI Assistant Toolkit

```python
from ai_assistant_toolkit import AIAssistantToolkit, PriorityLevel

# Инициализация
toolkit = AIAssistantToolkit(output_dir=Path("./ai_reports"))

# Пример 1: Анализ результатов тестов
test_output = """
tests/test_combat.py::test_damage PASSED
tests/test_toughness.py::test_break FAILED
"""
result = toolkit.analyze_test_results(test_output)
print(f"Tests: {result['passed']}/{result['total']} passed")

# Пример 2: Отслеживание трендов метрик
for i in range(10):
    trend = toolkit.track_trend("avg_damage", 100 + i * 5)
    if trend.anomaly_detected:
        print(f"⚠️ Аномалия detected! Prediction: {trend.prediction_next}")

# Пример 3: Детекция аномалий в метриках
metrics = {
    "damage_per_second": [100, 105, 98, 102, 500, 103],  # 500 - аномалия
}
anomalies = toolkit.detect_anomalies_in_metrics(metrics, sensitivity=2.0)
for a in anomalies:
    print(f"[{a.priority.value}] {a.title}: {a.description}")

# Пример 4: Добавление проблем с приоритетами
toolkit.add_issue(
    title="Toughness cap exceeded",
    priority=PriorityLevel.HIGH,
    category="toughness",
    description="Max toughness > 20% HP after 5 breaks",
    recommendation="Check toughness scaling formula",
    related_files=["src/systems/combat/components/toughness_component.py"]
)

# Пример 5: Генерация компактного отчета (для экономии токенов)
compact_report = toolkit.generate_compact_report(
    toolkit.issues,
    include_details=False,  # Ultra-compact режим
    max_issues=5
)
print(compact_report)

# Пример 6: Быстрая сводка
summary = toolkit.generate_quick_summary()
print(summary)

# Пример 7: Экспорт полного отчета
report_path = toolkit.export_report("session_report.json")
print(f"Report saved to: {report_path}")
```

## 💡 Советы по экономии токенов

1. **Используйте `generate_compact_report`** с `include_details=False` для быстрых проверок
2. **Кэшируйте результаты** через `set_cached()` для повторного использования
3. **Приоритизируйте проблемы** через `prioritize_issues()` - обрабатывайте сначала critical/high
4. **Используйте тренды** для предсказания проблем до их возникновения
5. **Экспортируйте отчеты в файлы** вместо передачи в контексте LLM
