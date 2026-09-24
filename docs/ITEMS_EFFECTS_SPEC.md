# 📜 Полная спецификация эффектов и предметов

## 1. Дебаффы (Debuffs)

### `bleed` (Кровотечение)
```lua
{
    name = "Bleed",
    type = "damage_over_time",
    duration = 5.0, -- секунд
    tick_rate = 1.0, -- тик каждую секунду
    damage_type = "physical",
    damage_source = "percent_max_hp", -- % от макс HP
    damage_value = 3.0, -- 3% от макс HP в тик
    stacks = true, -- стакается
    max_stacks = 10,
    stack_duration_refresh = true, -- обновляет длительность при стаке
    visual_effect = "blood_particles",
    description = "Наносит 3% от макс. HP физ. урона каждую секунду. Стакается до 10 раз."
}
```
**Математика:** 
- Урон за тик = `Target.MaxHP * 0.03 * StackCount`
- При 10 стаках: 30% от макс HP в секунду
- Игнорирует броню (true damage по сути)

---

## 2. Sorrow of Berserk - Полный разбор

### Базовые статы предмета:
| Стат | Значение | Тип |
|------|----------|-----|
| Max HP | +2000% | Percent |
| Defense | -80% | Percent (дебафф на себя) |
| Life Steal | +20% | Percent |
| Attack Speed | +50% | Percent |

### Эффекты (CAS Engine V2):

#### 🔴 **Passive Buffs (Low HP)**
```lua
condition = { type = "hp_percent_lt", value = 40 }
effects = [
    { op = "add_percent", stat = "attack_damage", value = 50 },
    { op = "add_percent", stat = "move_speed", value = 30 },
    { op = "add_flat", stat = "tenacity", value = 50 }
]
```
**Что дает:** Когда HP < 40%:
- +50% к урону от атак
- +30% к скорости бега
- +50 Tenacity (сокращение длительности CC)

#### 📈 **Escalation (Scaling)**
```lua
condition = { type = "stat_gte", stat = "current_hp_percent", value = 0 }
-- Срабатывает каждый тик, скалируется от недостающего HP
missing_hp_percent = 100 - current_hp_percent
effects = [
    { op = "add_percent", stat = "attack_damage", value = missing_hp_percent * 0.5 },
    { op = "add_percent", stat = "crit_damage", value = missing_hp_percent * 0.3 }
]
```
**Что дает:** 
- Каждое отсутствующее 1% HP дает +0.5% урона и +0.3% крит. урона
- При 10% HP: +45% урона, +27% крит. урона
- При 1% HP: +49.5% урона, +29.7% крит. урона

#### 🛡️ **Safety Net (Предохранитель)**
```lua
condition = { type = "hp_would_die" } -- триггер при смертельном уроне
effects = [
    { op = "set", stat = "current_hp", value = 1 },
    { op = "add_flat", stat = "iframe_duration", value = 2.0 }
]
cooldown = 180 -- секунд
```
**Что дает:**
- При получении смертельного урона: HP становится 1 вместо смерти
- +2 секунды неуязвимости (iFrames)
- КД: 3 минуты

#### ⚔️ **Kill Refresh (Перезарядка от убийства)**
```lua
condition = { type = "on_kill" }
effects = [
    { op = "reset_cooldowns", all_skills = true },
    { op = "add_flat", stat = "iframe_duration", value = 0.5 },
    { op = "add_percent", stat = "move_speed", value = 100, duration = 3.0 }
]
```
**Что дает при убийстве:**
- Сбрасывает КД всех навыков
- 0.5 сек неуязвимости
- +100% к скорости бега на 3 секунды

---

## 3. Другие предметы в базе

### Bane's Scar Necklace
| Стат | Значение |
|------|----------|
| Attack Damage | +20% |
| Strength | -20 (flat) |
| Attack Speed | +25% |
| Crit Chance | +32.5% |
| HP Regen | +15% |

**Эффекты:**
1. **Blood Cost**: Тратит 1% текущего HP → +1.5% к урону заклинания
2. **Low HP Haste**: При ≤30% HP: +50% AS

### Apocalypse Bringer (Шаблон CAS)
```lua
conditions = [
    { type = "stat_gte", stat = "strength", value = 500 },
    { type = "hp_percent_gt", value = 90 }
]
effects = [
    { op = "multiply", stat = "attack_damage", value = 2.0 },
    { op = "add_flat", stat = "fire_damage", value = 1000 }
]
```
**Что дает:** Если STR ≥ 500 И HP > 90%:
- Умножает урон от атак на 2x
- +1000 flat fire damage к атакам

### Mage Supremacy (Шаблон CAS)
```lua
conditions = [
    { type = "stat_gte", stat = "intelligence", value = 1000 },
    { type = "has_buff", buff = "arcane_charge" }
]
effects = [
    { op = "add_percent", stat = "spell_damage", value = 100 },
    { op = "set", stat = "mana_cost", value = 0 } -- скиллы бесплатны
]
```

---

## 4. Система условий (CAS V2)

### Типы условий:
| Тип | Описание | Пример |
|-----|----------|--------|
| `stat_gte` | Стат ≥ значения | `strength >= 500` |
| `stat_lte` | Стат ≤ значения | `defense <= 100` |
| `stat_eq` | Стат == значения | `level == 18` |
| `hp_percent_lt` | HP% < значения | `hp < 40%` |
| `hp_percent_gt` | HP% > значения | `hp > 90%` |
| `has_buff` | Есть бафф | `has_buff("arcane_charge")` |
| `has_debuff` | Есть дебафф | `has_debuff("bleed")` |
| `equipped_item` | Надет предмет | `equipped_item("Sorrow of Berserk")` |

### Операции над статами:
| Операция | Формула | Пример |
|----------|---------|--------|
| `add_flat` | `new = base + value` | `+100 AD` |
| `add_percent` | `new = base * (1 + value/100)` | `+50% AD` |
| `multiply` | `new = base * value` | `x2 урон` |
| `set` | `new = value` | `HP = 1` |

---

## 5. Пример расчёта урона с Sorrow of Berserk

**Сценарий:** Герой с 10% HP, надет Sorrow of Berserk

**Базовые статы героя:**
- Base AD: 100
- Base HP: 1000
- Base Crit Dmg: 150%

**После применения предмета:**

1. **Базовые модификаторы:**
   - HP: `1000 * (1 + 2000%) = 21,000 HP`
   - Defense: `Base * (1 - 80%) = 20% от базы`
   - AS: `Base * (1 + 50%) = 1.5x`
   - Vamp: `+20%`

2. **Passive Buffs (HP < 40%):** ✅ Активно (10% < 40%)
   - AD: `100 * (1 + 50%) = 150`
   - Move Speed: `+30%`
   - Tenacity: `+50`

3. **Escalation (Missing HP = 90%):**
   - AD Bonus: `90 * 0.5 = 45%`
   - Crit Dmg Bonus: `90 * 0.3 = 27%`
   - Итоговый AD: `150 * (1 + 45%) = 217.5`
   - Итоговый Crit Dmg: `150% + 27% = 177%`

**Финальные статы при 10% HP:**
- HP: 21,000 (текущее: 2,100)
- AD: 217.5 (+117.5% от базы)
- Crit Dmg: 177%
- Defense: 20% от базы (очень мало!)
- AS: 1.5x
- Vamp: 20%

**Урон автоатаки с критом:**
```
Damage = AD * CritMultiplier * (1 + Vamp)
       = 217.5 * 1.77 * 1.2
       = 461 урона + 92 хила
```

---

## 6. Интеграция с боевой системой

### Поддерживаемые типы урона:
- `physical` - уменьшается броней
- `fire/ice/lightning/holy/dark` - уменьшаются резистами
- `pure` - игнорирует всё (true damage)

### Механики защиты:
- `armor` - снижает физ. урон
- `resist` - снижает маг. урон
- `block_counter` - шанс блока/контратаки
- `iframes` - полная неуязвимость
- `pure_immunity` - иммунитет к pure урону

### Reflect (Отражение урона):
```lua
reflect = {
    percent = 30, -- 30% отражается
    flat = 50, -- +50 flat урона
    base_only = true, -- только от базового урона
    elemental = "fire" -- тип отражённого урона
}
```

### AI Emotions (влияют на поведение):
| Эмоция | Триггер | Эффект |
|--------|---------|--------|
| `fear` | HP < 20% | Попытка отступления |
| `anger` | Получил крит | +20% урона, -10% защиты |
| `adrenaline` | Kill streak | +15% AS, +10% MS |
| `greed` | Видит лут | Игнорирует врагов, идёт к луту |

---

## 7. Контекстные задачи (Contextual Tasks)

AI может получать задачи в зависимости от ситуации:

```lua
tasks = {
    attack = { priority = 10, target = "nearest_enemy" },
    flee = { priority = 100, condition = "hp_percent < 15" },
    pickup = { priority = 5, item_type = "gold" },
    move = { priority = 1, position = {x=100, y=200} },
    use_skill = { priority = 8, skill = "heal", condition = "hp_percent < 30" },
    wait = { priority = 0, duration = 2.0 },
    buy = { priority = 3, shop_id = 1, item = "potion" }
}
```

Приоритеты: 100 = немедленно, 0 = фон

---

## 8. Rooms (Зоны с эффектами)

```lua
rooms = {
    dot_zone = {
        effect = "damage_over_time",
        damage = 50, -- per second
        damage_type = "fire"
    },
    hot_zone = {
        effect = "heal_over_time",
        heal = 100, -- per second
    },
    buff_zone = {
        effect = "add_percent",
        stat = "attack_damage",
        value = 50
    },
    loot_spawn = {
        effect = "spawn_loot",
        loot_table = "legendary_items",
        chance = 0.1
    }
}
```

---

Эта документация используется веб-билдером для создания предметов!
