# Система Искусственного Интеллекта (AI System)

## Обзор

Единая система искусственного интеллекта, объединяющая все AI возможности в одном модуле с поддержкой машинного обучения, памяти поколений и адаптивного поведения.

## Основные возможности

### 🧠 Типы AI
- **Behavior Tree** - Древовидная логика поведения
- **State Machine** - Конечные автоматы состояний
- **Neural Network** - Нейронные сети (PyTorch)
- **Reinforcement Learning** - Обучение с подкреплением
- **Evolutionary** - Эволюционные алгоритмы
- **Hybrid** - Гибридные подходы

### 🎯 Состояния AI
- **IDLE** - Ожидание
- **PATROLLING** - Патрулирование
- **CHASING** - Преследование
- **ATTACKING** - Атака
- **FLEEING** - Бегство
- **SEARCHING** - Поиск
- **RESTING** - Отдых
- **INTERACTING** - Взаимодействие
- **LEARNING** - Обучение
- **ADAPTING** - Адаптация

### 🧬 Система личности
Каждая AI сущность имеет уникальные черты личности:
- **Aggression** - Агрессивность
- **Caution** - Осторожность
- **Curiosity** - Любопытство
- **Intelligence** - Интеллект
- **Discipline** - Дисциплина
- **Persistence** - Настойчивость
- **Patience** - Терпение

### 🧠 Типы памяти
- **Combat** - Боевой опыт
- **Movement** - Движение и навигация
- **Skill Usage** - Использование навыков
- **Item Usage** - Использование предметов
- **Environment** - Окружающая среда
- **Social** - Социальные взаимодействия

## Архитектура

### Основные компоненты

#### AISystem
Главный класс системы, управляющий всеми AI сущностями.

#### AIEntity
Сущность с AI, включающая:
- Нейронную сеть для принятия решений
- Буфер опыта для обучения
- Память поколений
- Черты личности
- Статистику и состояние

#### AIBehavior
Поведение с поддержкой машинного обучения:
- Условия активации
- Действия
- Требования к личности
- Модель ML для выбора действий

#### MemoryEntry
Запись в памяти с:
- Типом памяти
- Контекстом
- Действием
- Результатом
- Ценностью для обучения

#### GenerationMemory
Память поколения для эволюционного обучения.

## Машинное обучение

### Поддерживаемые фреймворки

#### PyTorch (рекомендуется)
- Нейронные сети для принятия решений
- Q-learning для обучения с подкреплением
- Автоматическое дифференцирование
- GPU ускорение

#### Scikit-learn
- Классические ML алгоритмы
- Random Forest для классификации
- Стандартизация данных

### Процесс обучения

1. **Сбор опыта** - Сущности накапливают опыт в буфере
2. **Обучение** - Периодическое обновление моделей
3. **Адаптация** - Изменение черт личности на основе опыта
4. **Эволюция** - Передача знаний между поколениями

## Использование

### Базовая настройка

```python
from src.systems.ai import AISystem, AIType, AIState

# Создание AI системы
ai_system = AISystem()

# Инициализация
ai_system.initialize()

# Регистрация сущности
ai_system.register_entity(
    entity_id="enemy_001",
    ai_type=AIType.HYBRID,
    position=(100, 0, 100)
)
```

### Принятие решений

```python
# Получение решения для сущности
decision = ai_system.make_decision("enemy_001")

if decision:
    print(f"Действие: {decision.action}")
    print(f"Уверенность: {decision.confidence}")
    print(f"Влияние личности: {decision.personality_influence}")
```

### Добавление опыта

```python
# Добавление записи в память
ai_system.add_memory_entry(
    entity_id="enemy_001",
    memory_type=MemoryType.COMBAT,
    context={"enemy_type": "player", "weapon": "sword"},
    action="attack",
    outcome={"damage_dealt": 25, "enemy_health": 75},
    success=True,
    learning_value=0.8
)

# Добавление опыта для обучения
ai_system.add_experience(
    entity_id="enemy_001",
    state=current_state,
    action=action_taken,
    reward=reward_received,
    next_state=next_state,
    done=episode_finished
)
```

### Управление поколениями

```python
# Начало нового поколения
ai_system.start_new_generation()

# Сохранение моделей и памяти
ai_system.save_models("models/ai_models")

# Загрузка моделей
ai_system.load_models("models/ai_models")
```

## Настройки

### AISettings

```python
settings = AISettings(
    update_interval=0.1,           # Интервал обновления (сек)
    max_entities=1000,             # Максимум сущностей
    enable_learning=True,          # Включить обучение
    enable_neural_networks=True,   # Включить нейронные сети
    learning_rate=0.001,           # Скорость обучения
    exploration_rate=0.1,          # Скорость исследования
    experience_buffer_size=10000,  # Размер буфера опыта
    batch_size=32,                 # Размер батча для обучения
    personality_adaptation_rate=0.01  # Скорость адаптации личности
)
```

## Производительность

### Оптимизации

- **Многопоточность** - Обновление сущностей в отдельных потоках
- **Кэширование** - Кэш для часто используемых данных
- **Lazy Loading** - Загрузка моделей по требованию
- **Batch Processing** - Пакетная обработка опыта

### Мониторинг

```python
# Получение статистики
stats = ai_system.get_statistics()

print(f"Активных сущностей: {stats['active_entities']}")
print(f"Принято решений: {stats['decisions_made']}")
print(f"Событий обучения: {stats['learning_events']}")
print(f"Обновлений моделей: {stats['model_updates']}")
print(f"Записей памяти: {stats['memory_entries']}")
print(f"Поколений: {stats['generations']}")
```

## Расширение

### Добавление новых поведений

```python
# Создание нового поведения
new_behavior = AIBehavior(
    behavior_id="stealth",
    name="Скрытность",
    description="Скрытное перемещение и атаки",
    conditions={"visibility": "low", "has_target": True},
    actions=["sneak", "backstab", "hide"],
    priority=7,
    learning_enabled=True,
    personality_requirements={"caution": 0.6, "intelligence": 0.7}
)

# Добавление в систему
ai_system.behaviors["stealth"] = new_behavior
```

### Кастомные модели ML

```python
# Создание кастомной нейронной сети
class CustomAINetwork(nn.Module):
    def __init__(self):
        super().__init__()
        # Ваша архитектура
        
    def forward(self, x):
        # Ваша логика
        pass

# Использование в сущности
entity.neural_network = CustomAINetwork()
```

## Требования

### Обязательные
- Python 3.8+
- NumPy

### Рекомендуемые
- PyTorch 1.9+ (для нейронных сетей)
- Scikit-learn 1.0+ (для классических ML)
- Pandas (для анализа данных)

### Установка

```bash
# Базовые зависимости
pip install numpy

# Для полной функциональности
pip install -r requirements_ml.txt

# Или по отдельности
pip install torch torchvision
pip install scikit-learn
pip install pandas matplotlib
```

## Примеры использования

### Простой AI агент

```python
# Создание простого патрульного агента
patrol_agent = ai_system.register_entity(
    entity_id="guard_001",
    ai_type=AIType.STATE_MACHINE,
    position=(0, 0, 0)
)

# Агент автоматически начнет патрулирование
# и будет адаптироваться к окружающей среде
```

### Обучающийся боец

```python
# Создание боевого агента с обучением
fighter = ai_system.register_entity(
    entity_id="fighter_001",
    ai_type=AIType.REINFORCEMENT_LEARNING,
    position=(50, 0, 50)
)

# Агент будет учиться на своих боях
# и развивать тактику
```

### Эволюционный исследователь

```python
# Создание исследовательского агента
explorer = ai_system.register_entity(
    entity_id="explorer_001",
    ai_type=AIType.EVOLUTIONARY,
    position=(100, 0, 100)
)

# Агент будет исследовать мир
# и передавать знания следующим поколениям
```

## Заключение

Система AI предоставляет мощный и гибкий инструмент для создания интеллектуальных сущностей в игре. Объединение различных подходов к AI в одном модуле позволяет легко комбинировать и настраивать поведение, а поддержка машинного обучения обеспечивает адаптивность и реалистичность.
