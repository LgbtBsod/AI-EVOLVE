# 📚 Combat Advanced Mechanics Documentation

## Обзор

Реализована полная система продвинутых боевых механик для игры с поддержкой:
- Возврата урона (Reflect)
- Чистого урона (Pure Damage)
- Разовой блокировки (Block Counters / IFrames)
- Бессмертных манекенов с регеном
- Комнат/Зон с эффектами (DoT/HoT/Loot Spawn)
- Системы эмоций AI (Страх, Гнев, Адреналин, Жадность)
- Контекстных задач для AI

---

## 1. Типы Урона

```python
class DamageType(Enum):
    PHYSICAL = "physical"     # Режется броней
    FIRE = "fire"             # Режется резистом к огню
    ICE = "ice"               # Режется резистом ко льду
    LIGHTNING = "lightning"   # Режется резистом к молнии
    HOLY = "holy"             # Режется резистом к свету
    DARK = "dark"             # Режется резистом к тьме
    PURE = "pure"             # Игнорирует ВСЕ защиты, кроме полной неуязвимости
```

### Митигация урона:
- **Физический**: `Armor / (Armor + 1000)`
- **Стихийный**: `Resist%` (по стихии)
- **Чистый**: Игнорирует броню/резисты, блокируется только:
  - Block Counters (разовая блокировка)
  - IFrames (временная неуязвимость)
  - Pure Immunity (специфическая защита)

---

## 2. Возврат Урона (Reflect)

### ReflectConfig:
```python
@dataclass
class ReflectConfig:
    percent_of_damage: float = 0.0   # % от полученного урона
    flat_amount: float = 0.0         # Плоское значение
    reflect_base_only: bool = False  # Только базовый урон (до митигации)
    reflect_elemental: bool = False  # Только стихийный урон
    damage_type_returned: DamageType = DamageType.PURE
```

### Примеры использования:

**Пример 1: Щит возвращает 50% урона чистым уроном**
```python
entity.add_reflect(ReflectConfig(
    percent_of_damage=50.0,
    damage_type_returned=DamageType.PURE
))
```

**Пример 2: Bane's Scar Necklace**
- Каждая атака тратит 1% макс HP → добавляет 1.5% макс HP как плоский урон
- При HP ≤ 30%: дополнительно +50% скорости атаки

**Пример 3: Sorrow of Berserk**
- +2000% HP, -80% защиты
- 20% вампиризм (от физ. атак)
- Если HP не хватает на трату → устанавливается на 1, удваивает бафы и дает IFrames 5 сек

---

## 3. Разовая Блокировка (Block Counters)

Механика "Неуязвимость на N атак" (как в BNS скиллы на 5 атак за 10 сек):

```python
tank.stats.block_counters = 5  # 5 атак заблокировано

dmg1, _ = tank.take_damage(1000, DamageType.PHYSICAL)  # 0 урона, counters=4
dmg2, _ = tank.take_damage(1000, DamageType.PHYSICAL)  # 0 урона, counters=3
...
dmg6, _ = tank.take_damage(1000, DamageType.PHYSICAL)  # 1000 урона, counters=0
```

### Применение:
- Скиллы типа "Теневая поступь" (5 атак за 10 сек)
- Перекаты с IFrames
- Разовые иммунитеты от боссов

---

## 4. Бессмертный Манекен (Immortal Dummy)

Для тестирования DPS без смерти цели:

```python
dummy = Entity("BossDummy", is_immortal=True)
dummy.stats.max_hp = 100000
dummy.stats.hp = 100000
dummy.stats.regen = 1000  # 1000 HP/sec

# Манекен никогда не умрет, HP всегда восстанавливается
```

### Мониторинг DPS:
```python
dps = dummy.get_dps(window=5.0)  # Средний DPS за последние 5 сек
total_dmg = sum(d for t, d in dummy.damage_taken_log)  # Весь урон
```

---

## 5. Комнаты/Зоны (Room System)

Создание зон с постоянными эффектами:

### RoomEffectType:
```python
class RoomEffectType(Enum):
    DO_T = "damage_over_time"   # Урон в секунду
    HO_T = "heal_over_time"     # Исцеление в секунду
    BUFF_ZONE = "buff_zone"     # Баффы (будущее расширение)
    LOOT_SPAWN = "loot_spawn"   # Спавн предметов при входе
```

### Пример создания:

**Комната с уроном 5000 DPS:**
```python
room = GameRoom("FireZone", RoomConfig(
    effect_type=RoomEffectType.DO_T,
    value=5000.0  # 5000 урона в секунду
))
room.add_entity(player)
```

**Комната со спавном лута:**
```python
loot_room = GameRoom("TreasureRoom", RoomConfig(
    effect_type=RoomEffectType.LOOT_SPAWN,
    value=0,
    spawn_items=["GoldChest", "RareSword", "LegendaryRing"]
))
loot_room.add_entity(hero)
# Hero автоматически получит задачи PICKUP_ITEM
```

---

## 6. Система Эмоций AI

AI агенты имеют 4 эмоции (0-100):

```python
@dataclass
class EmotionState:
    fear: float = 0.0       # Высокий → бегство
    anger: float = 0.0      # Высокий → агрессия, меньше защиты
    adrenaline: float = 0.0 # Высокий → скорость реакции, крит шанс
    greed: float = 0.0      # Высокий → приоритет лута над боем
```

### Обновление эмоций:
```python
# При получении урона
emotions.update("take_damage", amount / max_hp * 100)

# При низком HP (<30%)
emotions.update("low_hp", 50)

# При убийстве
emotions.update("kill", 20)
```

### Затухание:
- Fear: -0.1/tick
- Anger: -0.1/tick
- Adrenaline: -0.2/tick
- Greed: -0.1/tick

---

## 7. Контекстные Задачи AI

### ContextualTask Enum:
```python
class ContextualTask(Enum):
    ATTACK_TARGET = "attack_target"
    FLEE_TO_POINT = "flee_to_point"
    PICKUP_ITEM = "pickup_item"
    MOVE_TO_ZONE = "move_to_zone"
    USE_SKILL = "use_skill"
    WAIT = "wait"
    BUY_ITEM = "buy_item"
```

### Приоритеты:
1. **Эмоциональные задачи** (Fear > 70 → FLEE)
2. **Жадность** (Greed > 60 → PICKUP_ITEM)
3. **Очередь задач** (push_task)

### Пример:
```python
# AI получает урон → Страх растет → Задача бежать
ai_bot.take_damage(800, DamageType.FIRE)  # 80% HP lost
task = ai_bot.update_ai()
# task.task_type == ContextualTask.FLEE_TO_POINT

# Сброс страха, добавляем жадность
ai_bot.emotions.fear = 0
ai_bot.emotions.greed = 70
task2 = ai_bot.update_ai()
# task2.task_type == ContextualTask.PICKUP_ITEM
```

---

## 8. Dev Probe Plugin: CombatAdvancedPlugin

### Установка:
```python
from tools.plugins.combat_advanced_plugin import CombatAdvancedPlugin, CombatCommand

plugin = CombatAdvancedPlugin()
plugin.create_session("my_test")
```

### Команды:

| Команда | Описание | Параметры |
|---------|----------|-----------|
| `SPAWN_DUMMY` | Создать манекена | name, max_hp, regen |
| `CREATE_ROOM` | Создать комнату | name, effect_type, value, spawn_items |
| `ADD_ENTITY_TO_ROOM` | Добавить в комнату | entity, room |
| `APPLY_REFLECT` | Применить возврат | entity, percent, flat, return_type |
| `DEAL_DAMAGE` | Нанести урон | target, amount, type |
| `SET_EMOTION` | Установить эмоцию | entity, emotion, value |
| `PUSH_TASK` | Добавить задачу | entity, task_type, priority |
| `GET_STATS` | Получить статы | entity (опционально) |
| `GET_DPS` | Получить DPS | entity, window |
| `SIMULATE_COMBAT` | Симуляция боя | duration, dt |

### Пример использования:

```python
# 1. Спавн манекена
plugin.execute_command(CombatCommand.SPAWN_DUMMY, {
    "name": "BossDummy",
    "max_hp": 100000,
    "regen": 1000
})

# 2. Создание комнаты с уроном
plugin.execute_command(CombatCommand.CREATE_ROOM, {
    "name": "FireZone",
    "effect_type": "do_t",
    "value": 5000.0
})

# 3. Добавление манекена в комнату
plugin.execute_command(CombatCommand.ADD_ENTITY_TO_ROOM, {
    "entity": "BossDummy",
    "room": "FireZone"
})

# 4. Применение возврата урона
plugin.execute_command(CombatCommand.APPLY_REFLECT, {
    "entity": "BossDummy",
    "percent": 30.0,
    "return_type": "FIRE"
})

# 5. Нанесение урона
result = plugin.execute_command(CombatCommand.DEAL_DAMAGE, {
    "target": "BossDummy",
    "amount": 10000,
    "type": "PHYSICAL"
})
# result: {damage_taken: 10000, damage_reflected: 3000}

# 6. Симуляция боя на 3 секунды
result = plugin.execute_command(CombatCommand.SIMULATE_COMBAT, {
    "duration": 3.0,
    "dt": 0.1
})

# 7. Получение DPS
result = plugin.execute_command(CombatCommand.GET_DPS, {
    "entity": "BossDummy",
    "window": 3.0
})
```

---

## 9. Тестирование

### Запуск тестов ядра:
```bash
python src/core/combat_advanced.py
```

**Результат:**
```
✅ Test 1: Immortal Dummy with Regen
✅ Test 2: Reflect Mechanics
✅ Test 3: Block Counters (IFrames on hits)
✅ Test 4: Emotions & Contextual Tasks
✅ Test 5: Integrated Room + Loot + Emotions
=== ALL TESTS PASSED ===
```

### Запуск тестов плагина:
```bash
python tools/plugins/combat_advanced_plugin.py
```

**Результат:**
```
✅ Spawn Dummy
✅ Create Room
✅ Add to Room
✅ Apply Reflect
✅ Deal Damage (с возвратом)
✅ Set Emotion
✅ Get Stats
✅ Simulate Combat
✅ Get DPS
=== ALL PLUGIN TESTS PASSED ===
```

---

## 10. Интеграция с Game Loop

```python
# В основном цикле игры
def game_loop():
    while game_running:
        dt = clock.tick(60) / 1000.0
        
        # Обновление комнат (DoT/HoT)
        for room in active_rooms:
            room.update(dt)
        
        # Обновление AI
        for entity in entities:
            entity.regenerate(dt)
            task = entity.update_ai()
            
            if task:
                execute_task(task, dt)
        
        # Обновление Dev Probe
        probe.update()
```

---

## 11. Будущие Расширения

- [ ] **Вампиризм**: % от нанесенного урона → heal
- [ ] **Lifesteal**: Работает только от физ. атак
- [ ] **Spell Vamp**: Работает от скиллов
- [ ] **Overheal**: Превышение макс HP → щит
- [ ] **Execute**: Убийство целей < X% HP
- [ ] **Crushing Blow**: % от макс HP цели как урон
- [ ] **Anti-Heal**: Снижение получаемого лечения
- [ ] **Damage Shield**: Поглощение урона до X

---

## 12. Best Practices

### SOLID Принципы:
- **SRP**: Каждый класс отвечает за одну механику
- **OCP**: Легко добавлять новые типы урона/эффектов
- **DIP**: Зависимость от абстракций (Enum, dataclass)

### Python Best Practices:
- Type Hints во всех функциях
- Docstrings для всех классов
- Logging вместо print
- Dataclasses для конфигурации

### Производительность:
- Логирование очищается каждые 5 сек (DPS window)
- Lock-free структуры (deque для задач)
- Минимум аллокаций в hot path

---

## Контакты

Документация создана для проекта Dev Probe Game Framework.
Все тесты проходят успешно ✅
