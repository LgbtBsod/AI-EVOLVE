# 🎨 CAS Web Item Builder

Визуальный конструктор предметов с CAS эффектами на базе Flet.

## 🚀 Запуск

```bash
python tools/web_builder/app.py
```

Приложение откроется в браузере по адресу `http://localhost:8550`

## 📋 Возможности

### 1. **Шаблоны предметов**
- Sorrow of Berserk
- Bane's Scar Necklace  
- Apocalypse Bringer
- Пустой предмет (создание с нуля)

### 2. **Редактирование базовых статов**
- Max HP (%)
- Defense (%)
- Life Steal (%)
- Attack Speed (%)
- Attack Damage (%)
- Crit Chance (%)
- Strength (flat)
- Intelligence (flat)

### 3. **CAS Эффекты**
Добавляйте эффекты с условиями:

**Типы условий:**
- `hp_percent_lt/gt/lte/gte` - HP меньше/больше %
- `stat_gte/lte/eq` - Стат >=/<=/== значения
- `has_buff/debuff` - Наличие баффа/дебаффа
- `equipped_item` - Надетый предмет
- `on_kill` - При убийстве
- `on_spell_cast` - При касте скилла
- `hp_would_die` - При смертельном уроне
- `and/or` - Комбинированные условия

**Операции над статами:**
- `add_flat` - Добавить плоское значение (+100 AD)
- `add_percent` - Добавить процент (+50% AD)
- `multiply` - Умножить (x2 урон)
- `set` - Установить значение (HP = 1)
- `reset_cooldowns` - Сбросить КД

### 4. **Экспорт**
- 💾 **Lua** - сохранение в `lua_content/items/custom/`
- 📋 **JSON** - экспорт для агентов/тестов
- 🧪 **Тестирование** - валидация через CAS Engine

## 📁 Структура проекта

```
tools/web_builder/
├── app.py                 # Основное приложение Flet
├── exports/              # JSON экспорты
└── README.md            # Эта документация

lua_content/items/custom/ # Lua файлы предметов
```

## 🎯 Пример использования

1. Выберите шаблон "Sorrow of Berserk"
2. Отрегулируйте базовые статы
3. Добавьте CAS эффект:
   - Условие: `hp_percent_lt` = 40
   - Действие: `add_percent` → `attack_damage` = 50
4. Нажмите "💾 Сохранить в Lua"
5. Файл сохранится в `lua_content/items/custom/sorrow_of_berserk.lua`

## 🔗 Интеграция

### С CAS Engine
```python
from python_layer.l9_semantic.cas_engine_v2 import CASSolver

solver = CASSolver()
item_data = {...}  # Из JSON экспорта
result = solver.validate(item_data)
```

### С Training Room
```python
from features.training_room import TrainingRoom, Mannequin

room = TrainingRoom()
room.load_item_from_lua("lua_content/items/custom/my_item.lua")
room.test_dps(mannequin_type="Tank")
```

### С Dev Probe
Автоматическое тестирование предметов при изменениях:
```bash
dev_probe --test-items --auto-balance
```

## 🎨 UI Компоненты

- **Левая панель**: Настройки предмета, базовые статы, кнопки экспорта
- **Центральная панель**: Редактор CAS эффектов
- **Правая панель**: Предпросмотр и лог операций

## 📝 Генерируемый Lua код

```lua
-- Sorrow of Berserk
-- Легендарный амулет берсерка. Сила растёт с потерей HP.
-- Сгенерировано в CAS Item Builder: 2026-09-23 14:30:00

return {
    name = "Sorrow of Berserk",
    description = "Легендарный амулет берсерка. Сила растёт с потерей HP.",
    
    base_stats = {
        max_hp_percent = 2000,
        defense_percent = -80,
        life_steal_percent = 20,
        attack_speed_percent = 50,
    },
    
    cas_effects = {
        {
            name = "Passive Buffs (Low HP)",
            condition = { type = "hp_percent_lt", value = 40 },
            effects = {
                { op = "add_percent", stat = "attack_damage", value = 50 },
                { op = "add_percent", stat = "move_speed", value = 30 },
            }
        },
        -- Другие эффекты...
    },
}
```

## 🛠️ Расширение

Для добавления новых шаблонов отредактируйте `load_templates()` в `app.py`:

```python
def load_templates(self):
    return {
        "My Custom Item": {
            "description": "...",
            "base_stats": {...},
            "effects": [...]
        }
    }
```

## ⚠️ Требования

- Python 3.8+
- Flet (`pip install flet`)
- CAS Engine (уже в проекте)

## 📊 Статус

✅ Работает базовый функционал
✅ Шаблоны загружаются
✅ Экспорт в Lua/JSON
⏳ Полная валидация через CAS Engine (в разработке)
⏳ Интеграция с Training Room (в разработке)
