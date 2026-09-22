# AI-EVOLVE Architecture Documentation

## Новая модульная архитектура

### Обзор
Проект был рефакторен в модульную архитектуру на основе плагинов с четким разделением ответственности.

### Компоненты ядра (Core)

#### 1. EventSystem (`core/event_system.py`)
- **Назначение**: Централизованная система событий для слабой связанности компонентов
- **Возможности**:
  - Singleton паттерн
  - Подписка/отписка от событий
  - Emit событий с данными
  - Основан на библиотеке blinker

#### 2. DatabaseCore (`db/database_core.py`)
- **Назначение**: Управление всеми операциями БД через SQLAlchemy
- **Возможности**:
  - Singleton паттерн
  - Контекстный менеджер сессий
  - Автоматический rollback при ошибках
  - Bulk insert операции
  - Поддержка SQLite/PostgreSQL

#### 3. PluginBase (`core/plugin_base.py`)
- **Назначение**: Базовый класс для всех игровых плагинов
- **Жизненный цикл**:
  - `on_init()` - инициализация
  - `on_update(delta_time)` - обновление каждый кадр
  - `on_shutdown()` - завершение работы

#### 4. PluginManager (`core/plugin_manager.py`)
- **Назначение**: Управление жизненным циклом плагинов
- **Возможности**:
  - Регистрация плагинов
  - Инициализация в порядке регистрации
  - Завершение в обратном порядке
  - Обновление всех плагинов

#### 5. GameCore (`core/game_core.py`)
- **Назначение**: Главная точка входа приложения
- **Ответственность**:
  - Инициализация систем
  - Регистрация плагинов
  - Игровой цикл

### Плагины (Features)

#### CombatPlugin (`features/combat/`)
- Расчет урона
- Критические удары (TODO)
- Блок и уклонение (TODO)
- События: `attack_requested`, `damage_dealt`

#### ToughnessPlugin (`features/toughness/`)
- Снижение урона от брони
- Формула diminishing returns
- События: `damage_dealt` → `damage_finalized`

#### SceneManagerPlugin (`features/scenes/`)
- Управление сценами
- Плавные переходы
- События: `change_scene`

### Поток данных (Data Flow)

```
[Input] → event_system.emit("attack_requested") 
       → CombatPlugin.handle_attack()
       → event_system.emit("damage_dealt")
       → ToughnessPlugin.apply_toughness_reduction()
       → event_system.emit("damage_finalized")
       → [Apply damage to target]
```

### Тестирование

#### Unit Tests (`tests/unit/`)
- TestEventSystem: события, подписчики
- TestDatabaseCore: CRUD операции, транзакции
- TestPluginManager: жизненный цикл плагинов

#### Integration Tests (`tests/integration/`)
- Взаимодействие плагинов
- Combat + Toughness интеграция
- Scene transitions
- DB integration

### Запуск тестов
```bash
cd /workspace
PYTHONPATH=/workspace:$PYTHONPATH python -m pytest ai_evolve/tests/ -v
```

### Запуск игры
```bash
PYTHONPATH=/workspace:$PYTHONPATH python ai_evolve/core/game_core.py
```

### Расширение функциональности

Для добавления новой фичи:
1. Создать класс плагина наследуясь от `GamePlugin`
2. Реализовать `on_init`, `on_update`, `on_shutdown`
3. Зарегистрировать в `GameCore._register_plugins()`
4. Добавить unit/integration тесты

### Преимущества архитектуры

✅ **Слабая связанность** - компоненты общаются через события  
✅ **Модульность** - плагины независимы и заменяемы  
✅ **Тестируемость** - каждый компонент тестируется изолированно  
✅ **Расширяемость** - новые фичи как плагины  
✅ **Чистый код** - разделение ответственности  
✅ **Централизованное управление БД** - все операции через DatabaseCore  

### Следующие шаги

- [ ] Миграция старого кода Character/Enemy на плагины
- [ ] Вынос балансных параметров в конфиги
- [ ] Добавление type hints
- [ ] Интеграция с основным main.py
- [ ] CI/CD pipeline
