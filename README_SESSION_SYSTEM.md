# Система Сессий и Генерации Контента

## Обзор

Система сессий обеспечивает правильную изоляцию данных между игровыми сессиями и корректную генерацию контента (предметов, генов, оружия, врагов, скиллов) для каждой сессии отдельно.

## Проблемы, которые решает система

### ❌ Проблемы старой системы:
- Генерация контента происходила при запуске игры
- При перезапуске игры весь прогресс терялся
- Невозможно было иметь несколько сохранений
- Контент не сохранялся между сессиями

### ✅ Решения новой системы:
- Генерация контента происходит при создании новой игры/уровня
- Каждая сессия имеет уникальный UUID
- Поддержка множественных слотов сохранения
- Полная изоляция данных между сессиями
- Сохранение прогресса и контента в базе данных

## Архитектура системы

### База данных

```
data/game_data.db
├── save_slots              # Слоты сохранения
├── session_data            # Данные сессий
├── session_items           # Предметы сессии
├── session_enemies         # Враги сессии
├── session_weapons         # Оружие сессии
├── session_skills          # Навыки сессии
├── session_genes           # Гены сессии
├── effects                 # Справочник эффектов
├── skill_effects           # Эффекты навыков
├── enemy_types             # Типы врагов
└── weapons                 # Справочник оружия
```

### Ключевые компоненты

#### 1. SessionManager
- Управление игровыми сессиями
- Создание/загрузка/сохранение сессий
- Изоляция данных между сессиями

#### 2. ContentGenerator
- Генерация контента на основе UUID сессии
- Воспроизводимая генерация с помощью seed
- Поддержка предметов, оружия, врагов, навыков, генов

#### 3. База данных сессий
- Хранение данных для каждой сессии отдельно
- Поддержка множественных слотов
- Отслеживание прогресса и состояния

## Использование

### Создание новой игры

```python
from core.session_manager import SessionManager
from core.content_generator import ContentGenerator

# Создаем менеджер сессий
session_manager = SessionManager()

# Находим свободный слот
free_slot = session_manager.get_free_slot()

# Создаем новую сессию
session_data = session_manager.create_new_session(
    slot_id=free_slot,
    save_name="Моя игра",
    world_seed=random.randint(1, 999999)
)

# Генерируем контент для сессии
content_generator = ContentGenerator()
initial_content = content_generator.initialize_session_content(
    session_data.session_uuid, 
    level=1
)

# Добавляем контент в сессию
for content_type, content_list in initial_content.items():
    if content_type != "world_seed":
        for item in content_list:
            session_manager.add_session_content(content_type, item)
```

### Загрузка существующей игры

```python
# Загружаем сессию
session_data = session_manager.load_session(slot_id)

# Получаем контент сессии
items = session_manager.get_session_content("items")
weapons = session_manager.get_session_content("weapons")
enemies = session_manager.get_session_content("enemies")
skills = session_manager.get_session_content("skills")
genes = session_manager.get_session_content("genes")
```

### Сохранение прогресса

```python
# Обновляем данные игрока
session_data.player_data = {
    "name": "Игрок",
    "level": 5,
    "health": 100,
    "mana": 80,
    "position": {"x": 100, "y": 100, "z": 0}
}

# Сохраняем сессию
session_manager.save_session(session_data)
```

## Генерация контента

### Принципы генерации

1. **Воспроизводимость**: Одинаковый UUID сессии + уровень = одинаковый контент
2. **Изоляция**: Каждая сессия имеет свой уникальный контент
3. **Прогрессия**: Контент зависит от уровня игрока
4. **Разнообразие**: Использование seed для создания уникальных комбинаций

### Типы генерируемого контента

#### Предметы (Items)
- Зелья (здоровье, мана, сила)
- Оружие (мечи, топоры, луки, посохи)
- Броня (шлемы, нагрудники, сапоги)
- Кольца и амулеты
- Свитки и зелья

#### Оружие (Weapons)
- Различные типы (меч, топор, лук, посох, кинжал)
- Уровни редкости (common, uncommon, rare, epic, legendary)
- Уникальные эффекты и характеристики
- Требования к использованию

#### Враги (Enemies)
- Различные типы (хищник, жертва, нейтральный, босс)
- Уникальные характеристики и способности
- Поведенческие паттерны
- Сопротивления и слабости

#### Навыки (Skills)
- Боевые навыки
- Магические заклинания
- Поддерживающие способности
- Пассивные умения

#### Гены (Genes)
- Генетические модификации
- Усиление характеристик
- Специальные способности
- Эволюционные пути

## Структура базы данных

### Таблица save_slots
```sql
CREATE TABLE save_slots (
    slot_id INTEGER PRIMARY KEY,
    session_uuid TEXT UNIQUE NOT NULL,
    save_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_played TEXT NOT NULL,
    player_level INTEGER DEFAULT 1,
    world_seed INTEGER DEFAULT 0,
    play_time REAL DEFAULT 0.0,
    is_active INTEGER DEFAULT 1
)
```

### Таблица session_data
```sql
CREATE TABLE session_data (
    session_uuid TEXT PRIMARY KEY,
    slot_id INTEGER NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_saved TEXT NOT NULL,
    player_data TEXT,
    world_data TEXT,
    inventory_data TEXT,
    progress_data TEXT,
    generation_seed INTEGER DEFAULT 0,
    current_level INTEGER DEFAULT 1,
    FOREIGN KEY(slot_id) REFERENCES save_slots(slot_id)
)
```

### Таблица session_items
```sql
CREATE TABLE session_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid TEXT NOT NULL,
    item_id TEXT NOT NULL,
    name TEXT NOT NULL,
    item_type TEXT NOT NULL,
    rarity TEXT NOT NULL,
    effects TEXT,
    value INTEGER DEFAULT 0,
    weight REAL DEFAULT 0.0,
    icon TEXT DEFAULT '',
    is_obtained INTEGER DEFAULT 0,
    obtained_at TEXT,
    FOREIGN KEY(session_uuid) REFERENCES session_data(session_uuid)
)
```

## Тестирование

### Запуск тестов

```bash
# Создание базы данных
python create_db.py

# Заполнение начальными данными
python populate_db.py

# Тестирование системы сессий
python test_session_system.py
```

### Тесты включают:

1. **Создание сессий** - проверка создания множественных сессий
2. **Генерация контента** - проверка генерации для каждой сессии
3. **Сохранение/загрузка** - проверка персистентности данных
4. **Множественные сессии** - проверка изоляции данных
5. **Статистика** - проверка подсчета контента

## Интеграция с игрой

### В GameInterface

```python
def _start_new_game(self):
    """Начало новой игры"""
    # Создаем новую сессию
    free_slot = self.session_manager.get_free_slot()
    session_data = self.session_manager.create_new_session(
        slot_id=free_slot,
        save_name=f"Save {free_slot}",
        world_seed=random.randint(1, 999999)
    )
    
    # Генерируем контент
    initial_content = self.content_generator.initialize_session_content(
        session_data.session_uuid, 
        level=1
    )
    
    # Добавляем в сессию
    for content_type, content_list in initial_content.items():
        if content_type != "world_seed":
            for item in content_list:
                self.session_manager.add_session_content(content_type, item)
```

### В игровом цикле

```python
def save_game_state(self):
    """Сохранение состояния игры"""
    if self.session_manager.active_session:
        # Обновляем данные игрока
        self.session_manager.active_session.player_data = {
            "name": self.player.name,
            "level": self.player.level,
            "health": self.player.health,
            "mana": self.player.mana,
            "position": {
                "x": self.player.position.x,
                "y": self.player.position.y,
                "z": self.player.position.z
            }
        }
        
        # Сохраняем сессию
        self.session_manager.save_session()
```

## Преимущества новой системы

### 🎯 Изоляция данных
- Каждая сессия полностью независима
- Нет конфликтов между сохранениями
- Безопасное удаление сессий

### 🔄 Персистентность
- Прогресс сохраняется между запусками
- Контент не теряется при перезапуске
- Автоматическое резервное копирование

### 🎲 Воспроизводимая генерация
- Одинаковый контент для одинаковых сессий
- Возможность воспроизведения багов
- Детерминированная генерация

### 📊 Отслеживание прогресса
- Статистика по каждой сессии
- Отслеживание полученных предметов
- История игровых событий

### 🔧 Масштабируемость
- Поддержка множественных слотов
- Легкое добавление новых типов контента
- Гибкая система расширений

## Заключение

Новая система сессий решает все проблемы старой системы и обеспечивает:

- ✅ Правильную генерацию контента при создании новой игры
- ✅ Сохранение прогресса между сессиями
- ✅ Поддержку множественных слотов сохранения
- ✅ Полную изоляцию данных между сессиями
- ✅ Воспроизводимую генерацию контента
- ✅ Масштабируемую архитектуру

Система готова к использованию и может быть легко расширена для новых типов контента и функций.
