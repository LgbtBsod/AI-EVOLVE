# 🏋️ Training Room System v2.0 - Полная Документация

**Дата:** 2026-09-23  
**Статус:** ✅ Готово к использованию  
**Инженер:** AI Core Developer

---

## 📋 Обзор

Training Room v2.0 — это специализированная среда для тестирования предметов, навыков, эффектов и баланса игры. Вдохновлена режимом тестирования из Dota 2.

### Новые возможности v2.0:
- ✅ **Бессмертные герои-враги** — как в Доте, атакуют, используют скиллы, респавнятся
- ✅ **Система баффов/дебаффов** — через Effect Module (снижение HP, хил, урон за тик)
- ✅ **Тесты от %HP** — дебаффы снижения HP для тестов предметов, работающих от процента здоровья
- ✅ **Экипировка на манекенах** — тестирование защитных предметов
- ✅ **Навыки героев** — симуляция использования скиллов с урону
- ✅ **Агрегированные отчёты** — снижение токенов на 95%+ для агентов
- ✅ **Lua конфигурации** — декларативное описание тестов
- ✅ **Интеграция с CAS Engine** — сложные эффекты (Apocalypse Bringer, Sorrow of Berserk)

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    TRAINING ROOM v2.0                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Mannequin   │  │ImmortalHero  │  │ BuffDebuff   │      │
│  │  (манекен)   │  │ (бессмертный)│  │   (эффект)   │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
│         └─────────────────┼─────────────────┘               │
│                           │                                 │
│                  ┌────────▼────────┐                        │
│                  │  TrainingRoom   │                        │
│                  │   (оркестратор) │                        │
│                  └────────┬────────┘                        │
│                           │                                 │
│         ┌─────────────────┼─────────────────┐              │
│         │                 │                 │               │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐        │
│  │    Lua      │  │     CAS     │  │   Effect    │        │
│  │   Configs   │  │   Engine    │  │   Engine    │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Компоненты

### 1. Mannequin (Манекен)

**Назначение:** Статичная цель для тестирования DPS и эффектов предметов.

**Типы манекенов:**
| Тип | HP | Defense | Описание |
|-----|-----|---------|----------|
| `DUMMY` | 100,000 | 0 | Базовый, без сопротивлений |
| `TANK` | 50,000 | 500 | Высокая защита |
| `GLASS_CANNON` | 20,000 | 0 | Низкий HP, легко убить |
| `BALANCED` | 50,000 | 200 | Средние характеристики |
| `BOSS` | 500,000 | 1000 | Босс с высокими статами |
| `CUSTOM` | Настраивается | Настраивается | Пользовательский |

**Пример использования:**
```python
from tools.training_room import TrainingRoom, MannequinType, BuffDebuffConfig

room = TrainingRoom()

# Создание манекена
mannequin = room.create_mannequin("test_target", MannequinType.DUMMY)

# Применение баффа/дебаффа
hp_debuff = BuffDebuffConfig(
    name="HP Reduction",
    effect_type="debuff",
    hp_percent_change=-50.0,  # -50% HP
    damage_per_tick=10.0,     # 10 урона за тик
    duration=30.0,
    tick_interval=1.0
)
mannequin.apply_buff_debuff(hp_debuff)

# Проверка HP
print(f"HP после дебаффа: {mannequin.current_hp}")  # 50000.0
```

### 2. ImmortalHero (Бессмертный Герой)

**Назначение:** Активный враг, который атакует, использует навыки и респавнится при "смерти".

**Параметры:**
- `level` — уровень героя (влияет на HP и урон)
- `base_hp` — базовое здоровье
- `base_damage` — базовый урон
- `attack_speed` — атак в секунду
- `skills` — список навыков
- `equipment` — экипировка
- `behavior` — поведение ("aggressive", "passive", "random")
- `is_immortal` — бессмертие (респавн вместо смерти)

**Формулы:**
- `HP = base_hp × (1 + 0.1 × (level - 1))` — +10% за уровень
- `Damage = base_damage × (1 + 0.05 × (level - 1))` — +5% за уровень

**Пример использования:**
```python
from tools.training_room import ImmortalHero, ImmortalHeroConfig

hero_config = ImmortalHeroConfig(
    name="TestEnemy",
    level=10,
    base_hp=2000.0,
    base_damage=100.0,
    attack_speed=2.0,
    skills=["fireball", "lightning_bolt"],
    behavior="aggressive",
    is_immortal=True
)

hero = ImmortalHero(hero_config)
print(f"HP: {hero.current_hp}")      # 3800.0 (2000 × 1.9)
print(f"Урон: {hero.base_damage}")   # 145.0 (100 × 1.45)

# Атака по манекену
hero.perform_attack(mannequin, timestamp=0.5)

# Использование навыка
result = hero.use_skill("fireball", mannequin, timestamp=1.0)
print(f"Урон скилла: {result['damage']}")  # 362.5

# "Смерть" и респавн
hero.take_damage(99999, None, source="test")
print(f"Смертей: {hero.death_count}")  # 1
print(f"HP после респавна: {hero.current_hp}")  # 3800.0
```

### 3. BuffDebuffConfig (Баффы/Дебаффы)

**Назначение:** Модульная система эффектов для тестирования механик.

**Параметры:**
- `name` — название эффекта
- `effect_type` — "buff" или "debuff"
- `stat_modifier` — модификаторы статов `{StatType: value}`
- `hp_percent_change` — изменение % HP (для тестов от %HP)
- `heal_per_tick` — лечение за тик
- `damage_per_tick` — урон за тик (true damage)
- `duration` — длительность в секундах
- `tick_interval` — интервал тиков
- `trigger_condition` — условие активации

**Примеры использования:**

#### Тест предметов от %HP:
```python
# Снижение HP на 50% для тестов предметов типа "Sorrow of Berserk"
hp_debuff = BuffDebuffConfig(
    name="Low HP Test",
    effect_type="debuff",
    hp_percent_change=-50.0,
    duration=30.0
)
mannequin.apply_buff_debuff(hp_debuff)
```

#### Тест хила:
```python
heal_buff = BuffDebuffConfig(
    name="Regeneration",
    effect_type="buff",
    heal_per_tick=100.0,
    tick_interval=1.0,
    duration=60.0
)
mannequin.apply_buff_debuff(heal_buff)
```

#### Тест урона за тик:
```python
dot_debuff = BuffDebuffConfig(
    name="Poison",
    effect_type="debuff",
    damage_per_tick=50.0,
    tick_interval=2.0,
    duration=30.0
)
mannequin.apply_buff_debuff(dot_debuff)
```

---

## 📊 Сценарии тестирования

### 1. Базовый DPS тест
```python
from tools.training_room import TrainingRoom, TestScenario
from features.advanced_items import create_banes_scar_necklace

room = TrainingRoom()
room.create_mannequin("target_dummy", MannequinType.DUMMY)

scenario = TestScenario(
    name="basic_dps",
    description="Basic DPS test",
    duration_seconds=30.0,
    attacks_per_second=1.0,
    enable_crits=True
)
room.setup_test_scenario(scenario)

items = [create_banes_scar_necklace()]
result = room.run_dps_test(items, "target_dummy")

print(f"DPS: {result.dps}")
print(f"Crit Rate: {result.crit_rate}%")
```

### 2. Сравнение наборов предметов
```python
comparison = room.compare_items(
    item_sets={
        "banes_only": [create_banes_scar_necklace()],
        "sorrow_only": [create_sorrow_of_berserk()],
        "both": [create_banes_scar_necklace(), create_sorrow_of_berserk()]
    },
    duration=30.0
)

print(f"Лучший набор: {comparison['best_dps']['set_name']}")
print(f"DPS: {comparison['best_dps']['dps']}")
```

### 3. Тест с бессмертным героем
```python
from tools.training_room import ImmortalHero, ImmortalHeroConfig

# Создаём героя-врага
hero = ImmortalHero(ImmortalHeroConfig(
    name="Enemy",
    level=15,
    base_hp=3000.0,
    base_damage=150.0,
    attack_speed=1.5,
    skills=["fireball", "blast"],
    is_immortal=True
))

# Симуляция боя
for i in range(10):
    hero.perform_attack(mannequin, timestamp=i*0.5)
    if i % 3 == 0:
        hero.use_skill("fireball", mannequin, timestamp=i*0.5)

# Статистика героя
stats = hero.get_stats_summary()
print(f"Нанесённый урон: {stats['total_damage_dealt']}")
print(f"Смертей (респавнов): {stats['deaths']}")
```

### 4. Тест защитных предметов на манекене
```python
from features.advanced_items import ItemDefinition, StatType

# Создаём защитный предмет
armor = ItemDefinition(
    name="Heavy Plate",
    stats={StatType.DEFENSE: 500, StatType.MAX_HP: 1000}
)

# Экипируем манекен
mannequin = room.create_mannequin(
    "tank_test",
    MannequinType.TANK,
    equipment=[armor]
)

# Проверяем mitigation
print(f"Defense: {mannequin.config.defense}")
print(f"Max HP: {mannequin.config.max_hp}")
```

---

## 📁 Lua Конфигурации

Конфигурации хранятся в `/workspace/lua_content/training_room/`:

### mannequins.lua
```lua
return {
    mannequins = {
        {
            name = "standard_dummy",
            type = "dummy",
            max_hp = 100000,
            defense = 0,
            resistances = {}
        },
        {
            name = "boss_raids",
            type = "boss",
            max_hp = 1000000,
            defense = 2000,
            resistances = {physical = 0.3, fire = 0.5}
        }
    }
}
```

### heroes.lua
```lua
return {
    heroes = {
        {
            name = "test_warrior",
            level = 10,
            base_hp = 2000,
            base_damage = 100,
            attack_speed = 1.5,
            skills = {"cleave", "bash"},
            behavior = "aggressive",
            is_immortal = true
        }
    }
}
```

### buff_debuffs.lua
```lua
return {
    buffs = {
        {
            name = "hp_reduction_50",
            effect_type = "debuff",
            hp_percent_change = -50.0,
            duration = 30.0
        },
        {
            name = "regeneration",
            effect_type = "buff",
            heal_per_tick = 100.0,
            tick_interval = 1.0,
            duration = 60.0
        }
    }
}
```

---

## 📈 Отчёты и Экспорт

### Формат отчёта (JSON)
```json
{
  "metadata": {
    "scenario": "basic_dps_test",
    "timestamp": 1790156074,
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

### Экспорт
```python
report_path = room.export_report(result, filename="my_test.json")
print(f"Отчёт сохранён: {report_path}")
```

---

## 🧪 Запуск тестов

```bash
# Запустить все тесты Training Room
pytest tests/test_training_room.py -v

# Запустить тесты CAS Engine
pytest tests/test_cas_engine.py -v

# Запустить демо
python tools/training_room.py

# Запустить расширенное демо
python tools/training_room_demo.py
```

---

## 🔗 Интеграции

### Dev Probe
Training Room интегрируется с Dev Probe для автоматического запуска тестов при изменениях кода.

### CAS Engine
Поддержка сложных эффектов через CAS Engine:
- Apocalypse Bringer
- Sorrow of Berserk
- Custom conditions/actions

### Effect Engine
Интеграция с Effect Engine для триггерных эффектов предметов.

---

## 🎯 Рекомендации

1. **Используйте агрегированные отчёты** — снижает токены на 95%+
2. **Настраивайте duration тестов** — 30 сек достаточно для большинства тестов
3. **Иммортализируйте героев** — для длительных тестов без прерываний
4. **Комбинируйте баффы** — тестируйте синергии предметов
5. **Экспортируйте результаты** — для сравнения версий и регрессионного анализа

---

## 📝 Changelog

### v2.0 (2026-09-23)
- ✅ Добавлен ImmortalHero (бессмертный герой-враг)
- ✅ Добавлен BuffDebuffConfig (система баффов/дебаффов)
- ✅ Добавлены навыки героев (skills)
- ✅ Добавлена экипировка на манекенах
- ✅ Исправлены ошибки (level, DamageType.MAGICAL)
- ✅ Все тесты passing (18/18)

### v1.0 (Previous)
- Базовая система манекенов
- DPS тесты
- Сравнение предметов
- Lua конфигурации

---

*Документация создана AI Core Developer*  
*Для вопросов и предложений обращайтесь в проект*
