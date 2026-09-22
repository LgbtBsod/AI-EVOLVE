# Dev Probe Framework - Руководство для Агентов

## 📋 Обзор

Dev Probe Framework - это плагин-ориентированный фреймворк для автоматизированного тестирования игровой сессии AI-EVOLVE.

## 🎯 Назначение

- **Автоматический сбор статистики** игровых событий (смерти, урон, спавны)
- **Детекция аномалий** (зависание HP, мгновенная смерть, застревание)
- **Управление скриншотами** по событиям
- **Плагин-архитектура** для расширения функциональности

## 🏗️ Архитектура

```
┌─────────────────────────────────────────┐
│         DevProbeFramework               │
│  (Оркестратор тестирования)             │
├─────────────────────────────────────────┤
│  Plugins:                               │
│  - StatsCollectorPlugin                 │
│  - ScreenshotManagerPlugin              │
│  - AnomalyDetectorPlugin                │
│  - [Your Custom Plugin]                 │
└─────────────────────────────────────────┘
           │
           ├── Game Adapters ─────────────┐
           │   get_entities()             │
           │   get_combat_system()        │
           └──────────────────────────────┘
```

## 🔌 Как использовать агентам

### Базовый пример

```python
from ai_evolve.tools.dev_probe_framework import (
    DevProbeFramework,
    DevProbePlugin,
    EntityState,
    ProbeEvent
)

# Создать фреймворк
framework = DevProbeFramework()

# Настроить адаптеры (если тестируете не AI-EVOLVE)
framework.set_entity_adapter(my_get_entities_func)
framework.set_combat_adapter(my_get_combat_func)

# Запустить тестирование
framework.run(duration=30, sample_interval=1.0)

# Получить результаты
summary = framework.get_summary()
print(summary)
```

### Создание своего плагина

```python
class MyCustomPlugin(DevProbePlugin):
    @property
    def name(self) -> str:
        return "my_custom_plugin"
    
    def on_sample(self, game, entities, elapsed):
        # Вызывается каждый интервал сэмплинга
        return {"custom_metric": 42}
    
    def on_event(self, event: ProbeEvent):
        # Вызывается при каждом событии
        if event.event_type == "death":
            print(f"Entity {event.entity_id} died!")
    
    def on_screenshot(self, path: str, event_type: str):
        # Вызывается при сохранении скриншота
        pass
    
    def get_summary(self) -> dict:
        # Возвращает статистику плагина
        return {"total_events": 10}

# Регистрация плагина
framework.register_plugin(MyCustomPlugin())
```

## 📊 Типы событий

| Событие | Описание | Данные |
|---------|----------|--------|
| `entity_death` | Смерть сущности | entity_id, entity_type |
| `entity_spawn` | Появление сущности | entity_id, entity_type |
| `low_hp` | Низкое здоровье (<20%) | entity_id, hp_percent |
| `damage_dealt` | Нанесён урон | attacker_id, target_id, damage |
| `anomaly_detected` | Обнаружена аномалия | anomaly_type, details |

## 🧪 Детекция аномалий

AnomalyDetectorPlugin автоматически обнаруживает:

1. **HP Freeze** - здоровье не меняется N секунд подряд
2. **Instant Death** - смерть за 1 кадр (возможный баг)
3. **Position Lock** - сущность не двигается длительное время

## 📸 Скриншоты

ScreenshotManagerPlugin делает скриншоты при:
- Смерти любой сущности
- Появлении новой сущности
- Обнаружении аномалии
- По таймеру (если настроено)

## 🔄 Жизненный цикл

```
1. Framework init
   └── Register plugins
   
2. Pre-run
   └── Notify plugins (on_pre_run)
   
3. Main loop (каждый sample_interval)
   ├── Sample entities
   ├── Detect events
   ├── Notify plugins (on_sample)
   └── Take screenshots (if triggered)
   
4. Post-run
   └── Notify plugins (on_post_run)
   
5. Shutdown
   └── Cleanup
```

## 🛠️ Интеграция с SQLAlchemy БД

Dev Probe может работать с DatabaseCore для сохранения результатов:

```python
from ai_evolve.db.database_core import DatabaseCore

db = DatabaseCore()
db.init_db()

# Сохранить результаты теста
with db.session_scope() as session:
    result = TestResult(
        test_name="combat_balance_test",
        status="completed",
        deaths=stats.death_count,
        damage_dealt=stats.total_damage
    )
    session.add(result)
```

## 📈 Метрики для анализа

StatsCollectorPlugin собирает:
- `death_count` - количество смертей
- `spawn_count` - количество спавнов
- `total_damage` - суммарный урон
- `low_hp_events` - события низкого HP
- `session_duration` - длительность сессии

## ⚙️ Конфигурация

```python
config = {
    "duration": 60,              # Длительность теста (сек)
    "sample_interval": 1.0,      # Интервал сэмплинга (сек)
    "low_hp_threshold": 0.2,     # Порог низкого HP (20%)
    "screenshot_dir": "./shots", # Папка для скриншотов
    "enable_anomaly_detection": True,
}

framework = DevProbeFramework(config=config)
```

## 🐛 Отладка

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Включить логирование фреймворка
logger = logging.getLogger("ai_evolve.tools.dev_probe_framework")
logger.setLevel(logging.DEBUG)
```

## 📝 Пример полного теста

```python
from ai_evolve.tools.dev_probe_framework import DevProbeFramework
from ai_evolve.db.database_core import DatabaseCore

def run_combat_test():
    # Инициализация БД
    db = DatabaseCore()
    db.init_db()
    
    # Создание фреймворка
    framework = DevProbeFramework()
    
    # Добавить кастомный плагин для баланса
    class BalanceChecker(DevProbePlugin):
        @property
        def name(self): return "balance_checker"
        
        def on_event(self, event):
            if event.event_type == "damage_dealt":
                damage = event.data.get('damage', 0)
                if damage > 1000:  # Подозрительно высокий урон
                    print(f"WARNING: High damage detected: {damage}")
        
        def get_summary(self):
            return {"high_damage_events": 5}
    
    framework.register_plugin(BalanceChecker())
    
    # Запуск теста
    framework.run(duration=30)
    
    # Анализ результатов
    summary = framework.get_summary()
    print(f"Test completed: {summary}")
    
    # Сохранение в БД
    with db.session_scope() as session:
        # Save results...
        pass

if __name__ == "__main__":
    run_combat_test()
```

## 🎯 Best Practices для агентов

1. **Изоляция тестов**: Создавайте новый Framework для каждого теста
2. **Минимальные плагины**: Регистрируйте только нужные плагины
3. **Сбор метрик**: Используйте `get_summary()` для анализа
4. **Обработка ошибок**: Оборачивайте `run()` в try/except
5. **Очистка ресурсов**: Вызывайте shutdown после теста

## 📚 Связанные модули

- `ai_evolve/core/event_system.py` - Система событий
- `ai_evolve/db/database_core.py` - Ядро БД
- `ai_evolve/core/plugin_manager.py` - Менеджер плагинов
- `tools/dev_probe.py` - Оригинальный dev_probe (для визуальных тестов)
