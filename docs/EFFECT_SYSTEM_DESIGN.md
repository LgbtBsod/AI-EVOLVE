<!-- Source: effect-system design by the DeepSeek agent, pasted by the owner 2026-09-26. TARGET DESIGN: our canon (src/effects, lua_content) must be extended until it can describe 90-95% of character abilities from anime/books/films/novels. Owner decision: bring the system up to this design; see docs/EFFECT_SPEC_GAP.md for the plan. -->

# Финальная спецификация: Effect System

Полный справочник. Всё, что мы наработали — в одном документе.

---

# ЧАСТЬ 1. БАЗОВЫЕ СТРУКТУРЫ

## 1.1. Effect

```lua
Effect = {
  -- ИДЕНТИФИКАЦИЯ
  id:           string,                 -- уникальный, "lost_my_self"
  tags:         [string],               -- ["berserk","passive"]
  layer:        Layer,                  -- см. 2.1
  version:      number,                 -- для миграций

  -- ТРИГГЕР
  trigger:      Trigger,                -- когда эффект активен
  duration:     Value|nil,              -- nil = пока trigger true
  cooldown:     Value|nil,
  cost:         Cost|nil,
  stacks:       StackRule|nil,
  charges:      ChargeRule|nil,

  -- ПРИОРИТЕТ И КОНФЛИКТЫ
  priority:     number,                 -- 0 = default, выше = раньше
  exclusive_group: string|nil,          -- "domain","stance","transformation"
  conflict_with: [string]|nil,          -- явные конфликты

  -- ЛОГИКА
  ops:          [Op],                   -- что делает
  on_enter:     [Op]|nil,               -- при активации
  on_exit:      [Op]|nil,               -- при деактивации

  -- РАСШИРЕНИЯ (опциональные)
  faction:        string|nil,           -- для автономных
  autonomous:     bool|nil,             -- не подчиняется владельцу
  ai_profile:     AIProfile|nil,
  counter_display: CounterDisplay|nil,
  tiered_progression: TieredProgression|nil,
  adaptive_response:  AdaptiveResponse|nil,
  persistent_memory:  PersistentMemory|nil,
}
```

## 1.2. Op

```lua
Op = {
  -- ОСНОВА
  kind:         string,                 -- см. 3.x
  target:       Selector,               -- кого (см. 4.1)
  stat:         string|nil,             -- что (см. 5.1)
  op:           Operator|nil,           -- add/sub/mul/div/set/min/max
  value:        Value|nil,              -- сколько (см. 6.1)
  scale:        Scale|nil,              -- скалирование (см. 6.2)

  -- УСЛОВИЯ
  when:         Condition|nil,
  fail:         [Op]|nil,               -- ветка при провале

  -- МОДИФИКАТОРЫ
  duration:     Value|nil,
  cooldown:     Value|nil,
  extend:       ExtendRule|nil,
  max_stacks:   number|nil,
  permanent:    bool|nil,

  -- ССЫЛКИ
  buff_id:      string|nil,
  effect_id:    string|nil,
  status_id:    string|nil,
  ability_id:   string|nil,
  item_id:      string|nil,
  memory_key:   string|nil,

  -- ФИЛЬТРЫ
  filter:       Filter|nil,
  source_filter: SourceFilter|nil,

  -- ФЛАГИ
  flags:        [string],               -- см. 7.1

  -- РЕКУРСИЯ И ВЛОЖЕННОСТЬ
  ops:          [Op]|nil,               -- для zone, delay, fail
  zone:         ZoneDef|nil,
  summon:       SummonDef|nil,
  tick:         TickDef|nil,

  -- УНИВЕРСАЛЬНЫЕ РАСШИРЕНИЯ
  signature:      Signature|nil,
  faction:        string|nil,
  ai_profile:     AIProfile|nil,
  counter_delta:  CounterDelta|nil,
  tier_advance:   TierAdvance|nil,
  threshold:      Threshold|nil,

  -- LAYER-SPECIFIC
  layer_meta:   table,                  -- специфика слоя
}
```

---

# ЧАСТЬ 2. СЛОИ И KINDS

## 2.1. Слои (Layers)

```
"effect"        -- боевые события
"rules"         -- законы мира
"state"         -- память, сны, сохранения
"world"         -- глобальные состояния
"meta"          -- код, файлы, автор
"ontological"   -- уровни бытия
"conceptual"    -- концепции, домены
"social"        -- контракты, репутация
"entity"        -- слоты, чипы, колоды
"temporal"      -- петли, откаты
"narrative"     -- сценарий, автор
```

## 2.2. Все kinds (по слоям)

### EFFECT (боевые события)

**Урон / ресурсы:**
```
deal              -- нанести урон
drain             -- списать ресурс
heal              -- восстановить
set               -- установить значение
mod               -- изменить стат
consume           -- потратить ресурс
restore           -- восстановить ресурс
kill              -- убить
erase             -- стереть из существования
mass_resurrect    -- массовое воскрешение
```

**Баффы / дебаффы / статусы:**
```
buff              -- наложить бафф
debuff            -- наложить дебафф
status            -- наложить статус
status_transform  -- превратить статус
status_mod        -- изменить параметры статуса
remove_effect     -- снять эффект
purge             -- снять баффы
```

**Марки / детонаторы:**
```
mark              -- поставить метку
detonate          -- детонировать метку
```

**Зоны / ауры:**
```
zone              -- создать зону
aura              -- постоянная аура
zone_mod          -- изменить параметры зоны
```

**Существа:**
```
summon            -- призвать
possess           -- вселиться
transform         -- трансформация
stance            -- стойка/режим
core_swap         -- смена формы
```

**Движение / позиция:**
```
teleport          -- телепорт
dash              -- рывок
pull              -- притянуть
push              -- оттолкнуть
swap              -- обмен позициями
```

**Управление / восприятие:**
```
dodge             -- уклонение
block             -- блок
resist            -- сопротивление
immune            -- иммунитет
nullify           -- отмена сил
counter           -- контратака
reflect           -- отражение
redirect_harm     -- перенаправление урона
hypnosis          -- гипноз
untargetable      -- сделать невыбираемым
reveal            -- раскрыть
grant_vision      -- дать зрение
perceive          -- воспринимать
```

**Адаптация / кража / обучение:**
```
adapt             -- адаптация
unadapt           -- сбросить адаптацию
reset_adaptation  -- полный сброс
steal             -- украсть
absorb            -- поглотить
copy              -- скопировать
copy_last_cast    -- скопировать последний каст
inherit_all       -- унаследовать всё
learn             -- выучить
learn_technique   -- выучить технику
use_learned       -- использовать украденное
observe_phenomenon-- наблюдать без урона
register_phenomenon-- записать в память
```

**Управление статами:**
```
transfer_stat     -- перенос статов
unbounded         -- снять лимиты
progressive_state -- прогрессия состояния
tier_advance      -- продвижение по уровням
escalate          -- усиление
deescalate        -- ослабление
counter_delta     -- изменение счётчика
```

**Отложенные / условные:**
```
delay             -- отложенный op
on_lethal         -- при летальном уроне
conditional       -- условный op
```

**Гача / случайности:**
```
gacha             -- ролл
gamble            -- азартная механика
```

**Спец-эффекты:**
```
read              -- прочитать сущность
write             -- записать в сущность
rename            -- переименовать
wish              -- исполнить желание
sever             -- разорвать связь
sever_magic_circuits -- разорвать магию
fuel_consume      -- сжечь топливо
steal_stat        -- украсть стат
oath_binding      -- привязка к клятвам
cancel_technique  -- отменить технику
nullify_technique -- аннулировать технику
absorb_damage     -- поглотить урон
```

**Спец-механики (магичка/другие):**
```
create_weak_point -- слабая точка
precision_strike  -- прицельный удар
soul_transmutation-- изменение души
create_minion     -- создать миньона
self_transfigure  -- изменить себя
remove_restriction-- снять ограничение
awaken            -- пробудить
tame              -- приручить
sympathetic_damage-- урон через связь
body_swap         -- вселение в тело
technique_absorb  -- поглотить технику
fusion_strike     -- слияние ресурсов
copy_technique    -- копировать технику
timed_power_up    -- временное усиление
confiscate        -- изъять
command           -- приказ
telekinetic_weapon-- телекинез оружия
blood_manipulation-- управление кровью
transform_elemental-- элементальная форма
space_manipulation-- управление пространством
polarity_control  -- управление полярностью
```

**Faction / AI:**
```
set_faction       -- установить фракцию
set_aggro         -- установить режим агрессии
set_targeting     -- правила выбора цели
retarget          -- сменить цель
clear_aggro       -- сбросить агро
```

**Визуал / счётчики:**
```
rotate_wheel      -- оборот колеса
display_wheel     -- показать счётчик
halt_wheel        -- остановить счётчик
play_anim         -- проиграть анимацию
play_sound        -- проиграть звук
```

**Правила:**
```
rule              -- добавить правило
rule_override     -- переопределить правило
```

### RULES (законы мира)

```
rule_override          -- переопределить правило
rule_entity            -- правило как объект
reality_marble         -- свой мир в области
reality_by_theme       -- реальность под жанр
causality_control      -- управление причинностью
reverse_causality      -- обратная причинность
global_time_scale      -- глобальная скорость времени
block_physics          -- блокировать физику
```

### STATE (память, сны, сохранения)

```
snapshot               -- снимок
restore_state          -- восстановить состояние
load_state             -- загрузить сейв
state_rewind           -- откат состояния
time_loop              -- временная петля
enter_dream            -- войти в сон
hack_consciousness     -- взлом сознания
memory_block           -- блок памяти
nonlinear_time_perception -- нелинейное восприятие
```

### WORLD (глобальные состояния)

```
apply_status_to_world  -- статус на мир
thresholds             -- пороги состояния мира
world_reset            -- сброс мира
universe_reset         -- сброс вселенной
global_event           -- глобальное событие
```

### META (код, файлы, автор)

```
file_access            -- доступ к файлам
file_delete            -- удаление файлов
save_corruption        -- порча сейва
game_transform         -- смена жанра
close_game             -- закрыть игру
author_contact         -- контакт с автором
see_panels             -- видеть панели
panel_jump             -- прыжок между панелями
off_panel_win          -- победа вне кадра
rule_authority         -- власть над правилами
narrative_agent        -- активный рассказчик
goal_seek              -- поиск цели (Contessa)
precognition           -- предвидение
advisor                -- советник
```

### ONTOLOGICAL / CONCEPTUAL

```
embody_concept         -- воплощение концепции
domain_control         -- власть над доменом
change_tier            -- смена уровня бытия
concept_erase          -- стирание понятия
concept_deny           -- отрицание понятия
concept_rewrite        -- перезапись концепции
create_ex_nihilo       -- создание из ничего
soul_merge             -- слияние душ
narrative_control      -- управление нарративом
```

### SOCIAL

```
contract               -- контракт
contract_manipulation  -- манипуляция контрактами
temptation             -- соблазнение
dominance              -- доминирование
narrative_warfare      -- нарративная война
reputation             -- репутация
diplomacy              -- дипломатия
```

### ENTITY

```
slot_system            -- система слотов
reagent_slot           -- слоты реагентов
identity_source        -- идентичность из данных
```

### TEMPORAL

```
pan_temporal_control   -- контроль через все времена
time_as_space          -- время как пространство
time_erase             -- стирание времени
time_direction         -- направление времени
retroactive_erase      -- ретроактивное стирание
```

### NARRATIVE

```
narrator               -- активный рассказчик
narrative_hook         -- точка сюжета
fourth_wall            -- 4-я стена
```

## 2.3. Все операторы (Operator)

```
"add"    -- +
"sub"    -- -
"mul"    -- *
"div"    -- /
"set"    -- =
"min"    -- минимум
"max"    -- максимум
```

---

# ЧАСТЬ 3. СЕЛЕКТОРЫ, СТАТЫ, ЗНАЧЕНИЯ

## 3.1. Селекторы (target)

**Простые:**
```
"self"
"enemy"
"ally"
"attacker"
"killer"
"caster"
"summoner"
"source"
"owner"
```

**Одиночные:**
```
"nearest_enemy"
"farthest_enemy"
"random_enemy"
"lowest_hp_ally"
"highest_hp_ally"
"highest_threat"
"lowest_hp"
"highest_hp"
```

**Геометрия:**
```lua
{ line = N, width = W, filter = "enemy" }
{ cone = degrees, range = N, filter = "enemy" }
{ circle = radius, filter = "enemy" }
{ all_in_radius = N, filter = "enemy" }
{ all_in_radius = N, filter = "any" }
{ self_radius = N, affects = "enemies" }
```

**Цепочки:**
```lua
{ chain = N, jump = M, filter = "enemy" }
```

**По тегам / эффектам:**
```lua
{ tagged = "cursed_spirit" }
{ by_effect = "mark.cleave" }
{ by_status = "burn" }
{ with_buff = "last_will" }
{ of_faction = "feral" }
```

**Комбинированные:**
```lua
{ nearest = true, in_radius = 20, filter = "enemy" }
{ random = N, of = "enemies_in_radius", radius = 15 }
```

## 3.2. Статы (stat) — реестр

**Базовые:**
```
hp, max_hp, hp_regen
mana, max_mana, mana_regen, mana_control, mana_cost_multiplier
stamina, max_stamina, stamina_regen
strength, agility, intelligence
armor, magic_resist
attack, magic_power
crit_chance, crit_dmg
aspd, move_speed, cast_speed
attack_count
sanity, max_sanity
existence
```

**Производные:**
```
hp_pct, hp_missing, hp_missing_below_N
toughness
reaction_time
vision_range, vision_arc
detection_range
threat_level
```

**Signature (для конкретных персонажей):**
```
mahoraga.wheel
mahoraga.wheel_max
mahoraga.known_phenomena
mahoraga.adaptation_progress
mahoraga.adaptation_power
mahoraga.learned_techniques
mahoraga.current_target
mahoraga.aggro_mode
mahoraga.escalation_level
mahoraga.true_form
mahoraga.faction
mahoraga.phenomenon_memory

mark.cleave
mark.dismantle
mark.kagutsuchi
mark.amenotejikara
mark.wood
mark.limbo
mark.spear
```

## 3.3. Value

```lua
{ flat = N }                          -- просто число
{ pct = N }                           -- процент
{ pct = N, of = "max_hp" }            -- процент от чего-то
{ ref = "self.rage" }                 -- ссылка
{ ref = "self.rage", mul = 2, add = 10 }
{ expr = "max(10, current_hp * 0.3)" } -- для редактора
{ random = { min = 10, max = 20 } }
{ clamp = { min = 0, max = 999 }, ref = "self.rage" }
{ table = "registry.name" }
```

**Источники `of`:**
```
max_hp, current_hp, missing_hp
max_mana, current_mana
strength, agility, intelligence
armor, magic_resist
target.max_hp, target.current_hp, target.hp_missing
target.toughness
self.stacks
self.wheel
ctx.<any_field>
```

## 3.4. Scale

```lua
Scale = {
  every:   number,                    -- каждые N единиц
  of:      string,                    -- от чего считать
  value:   Value,                     -- что добавить за шаг
  factor:  number|nil,                -- множитель (default 1)
  cap:     number|nil,                -- максимум шагов
  floor:   number|nil,                -- минимум шагов
  mode:    "linear"|"exponential"|"threshold"|"step",
}
```

## 3.5. Trigger

```lua
{ kind = "passive" }
{ kind = "condition", when = Condition }
{ kind = "event", event = EventName, filter = Filter|nil }
{ kind = "tick", every = Value }
{ kind = "all", of = [Trigger] }
{ kind = "any", of = [Trigger] }
{ kind = "not", of = Trigger }
{ kind = "timeline", at_tick = N }
{ kind = "meta", condition = MetaCondition }
```

**Все events:**
```
on_attack_start      on_attack_hit       on_attack
on_kill              on_death            on_resurrect
on_crit              on_dodge            on_block
on_damage_taken      on_damage_dealt     on_heal_received
on_buff_gained       on_buff_lost        on_status_applied
on_cast              on_combo_end        on_tick
on_enter_combat      on_leave_combat     on_zone_enter
on_consume_item      on_touch            on_emotion
on_observe           on_wheel_max        on_hp_below
on_hp_above          on_stat_change      on_progress_threshold
on_set_goal          on_lethal           on_sleep
on_unconscious       on_awakening        on_ascension
on_set_goal          on_inside_domain    on_outside_domain
```

## 3.6. Condition

**Базовые:**
```lua
{ kind = "hp_below", pct = 40 }
{ kind = "hp_above", pct = 60 }
{ kind = "hp_missing_below", pct = 50 }
{ kind = "stat_cmp", stat = "rage", op = ">=", value = 100 }
{ kind = "has_status", id = "stun" }
{ kind = "has_buff", id = "last_will" }
{ kind = "has_effect", id = "berserk" }
{ kind = "has_flag", flag = "true_damage" }
{ kind = "last_skill", id = "blue", within = 3 }
{ kind = "attacker_has_flag", flag = "bypass_infinity" }
{ kind = "target_has_tag", tag = "cursed_spirit" }
{ kind = "has_weapon", id = "inverted_spear" }
{ kind = "has_mana", target = "enemy" }
{ kind = "distance", op = "<", value = 3 }
{ kind = "team_size", op = "==", value = 1 }
{ kind = "time_since", event = "on_cast", op = ">", value = 5 }
{ kind = "incoming_attack" }
{ kind = "dodged_last" }
{ kind = "attack_has_flag", flag = "magic" }
{ kind = "self_aware" }
{ kind = "automatic" }
{ kind = "high_emotion" }
{ kind = "both_have_domain_active" }
```

**Логические:**
```lua
{ kind = "all", of = [Condition] }
{ kind = "any", of = [Condition] }
{ kind = "not", of = Condition }
```

**Расширяемые:**
```lua
{ kind = "registry", name = "my_condition", args = {...} }
{ kind = "expr", code = "ctx.hp_pct < 40" }
{ kind = "reagent_combo", matches = ["quas","quas","wex"] }
```

## 3.7. Filter

```lua
Filter = {
  tag:      string|[string]|nil,      -- "enemy","cursed_spirit"
  faction:  string|nil,
  status:   string|[string]|nil,
  effect:   string|nil,
  stat_cmp: StatCmp|nil,              -- { stat, op, value }
  custom:   Condition|nil,
  exclude:  Filter|nil,
}
```

---

# ЧАСТЬ 4. УНИВЕРСАЛЬНЫЕ РАСШИРЕНИЯ

## 4.1. Signature

```lua
Signature = {
  keys:         [string],             -- ["damage_type","technique_id"]
  combine:      "all"|"any"|"distinct",
  granularity:  "exact"|"type"|"family",
  id_formula:   string,               -- "damage_type..':'..technique_id"
}
```

## 4.2. AIProfile

```lua
AIProfile = {
  target_select:    "nearest"|"farthest"|"lowest_hp"|"highest_hp"
                  | "highest_threat"|"random"|"custom",
  filter:           Filter,
  switch_on:        "timer"|"death"|"threat_change"|"event",
  switch_interval:  Value|nil,
  priority_list:    [Selector]|nil,
  follow_owner:     bool|nil,
}
```

## 4.3. CounterDelta

```lua
CounterDelta = {
  stat:   string,                     -- какой счётчик
  op:     "add"|"sub"|"set",
  value:  Value,
}
```

## 4.4. TierAdvance

```lua
TierAdvance = {
  track:        string,
  delta:        number,
  max:          number|nil,
  on_threshold: [Op]|nil,
}
```

## 4.5. Threshold

```lua
Threshold = {
  hits:          number|nil,
  damage_total:  number|nil,
  time_window:   Value|nil,
  wheel_min:     number|nil,
  custom:        Condition|nil,
}
```

## 4.6. SourceFilter

```lua
SourceFilter = {
  include:           Filter|nil,
  exclude:           Filter|nil,
  exclude_self:      bool|nil,
  exclude_owner:     bool|nil,
  exclude_allies:    bool|nil,
  require_seen:      bool|nil,        -- для Yhwach
  require_inferior:  bool|nil,        -- для Makima
  require_tag:       [string]|nil,
  require_flag:      [string]|nil,
}
```

## 4.7. CounterDisplay

```lua
CounterDisplay = {
  stat:      string,
  style:     "wheel"|"bar"|"number"|"dots"|"aura",
  segments:  number|nil,
  colors:    [string]|nil,
  animation: string|nil,
  position:  "above_head"|"hud"|"aura",
}
```

## 4.8. TieredProgression

```lua
TieredProgression = {
  track:     string,
  max:       number,
  per_tier:  { [stat] → Value },
  thresholds: [
    { at: number, ops: [Op] }
  ],
}
```

## 4.9. AdaptiveResponse

```lua
AdaptiveResponse = {
  trigger:       string,              -- "on_damage_taken"|"on_observe"
  signature:     Signature,
  threshold:     Threshold,
  response:      [Op],
  permanent:     bool,
  cooldown:      Value|nil,
  source_filter: SourceFilter,
  memory_key:    string,
}
```

## 4.10. PersistentMemory

```lua
PersistentMemory = {
  keys:           [string],
  persist:        "combat"|"death"|"save"|"forever",
  max_entries:    number|nil,
  decay:          Value|nil,
  serialization:  "full"|"hash"|"index",
  priority:       [string],
}
```

---

# ЧАСТЬ 5. ЗОНЫ И SUMMON

## 5.1. ZoneDef

```lua
ZoneDef = {
  target:           Selector,
  radius:           number,
  affects:          "enemies"|"allies"|"all"|Filter,
  barrier:          "open"|"closed"|"none",
  guaranteed_hit:   bool|nil,
  linked:           bool|nil,         -- для порталов
  duration:         Value,
  tick:             TickDef|nil,
  on_enter:         [Op]|nil,
  on_exit:          [Op]|nil,
  ops:              [Op]|nil,         -- что делает зона
}
```

## 5.2. SummonDef

```lua
SummonDef = {
  template:         string|{ from: string, pick: string },
  count:            Value,
  controller:       "self"|"owner"|"enemy"|"neutral",
  inherit:          { [stat] → Value },
  duration:         Value|nil,
  flags:            [string],
  on_owner_attack:  [Op]|nil,
  on_death:         [Op]|nil,
  on_expire:        [Op]|nil,
  rarity_roll:      RarityRoll|nil,
  pity:             Pity|nil,
}
```

## 5.3. TickDef

```lua
TickDef = {
  every:  Value,
  ops:    [Op],
  when:   Condition|nil,
}
```

---

# ЧАСТЬ 6. ФЛАГИ (реестр)

```
-- Урон
true_damage, physical, magic, soul_damage, mental
irreparable              -- неизлечимый
ignores_immunity         -- игнорирует иммун
ignores_armor
ignores_physical_defense
ignores_regeneration
is_not_mana              -- не мана (для иммунов)
imaginary_mass           -- мнимая масса
erase_matter             -- стирание материи
concept_pierce           -- пробивает концепции
world_cut                -- режет мир
dimensional_transcendence-- вне измерений
```

```
-- Попадание
guaranteed_hit, unavoidable, pierce
no_dodge, no_block, no_counter, no_resurrect
no_crit, can_crit
cannot_kill              -- оставляет 1 HP
```

```
-- Защита
bypass_infinity
bypass_mana_defense
domain_immunity
untargetable
invisible_to_magic
phase
```

```
-- Спец
soul_weapon
adaptive
lethal_intent
knockback
anti_magic
anti_domain
silent
```

---

# ЧАСТЬ 7. РЕЕСТРЫ

## 7.1. Namespaces

```
stats, resources, damage_types, flags
statuses, effects, abilities, items
targets, conditions, scales, selectors
layers, kinds, triggers, ops, value_sources
tags, factions, regions
narratives, contracts, oaths
recipes, achievements
meta_ops, rules, ontologies
phenomena, signatures
aggro_modes, targeting_modes
wheel_segments, adaptation_types
```

## 7.2. API

```lua
Registry.register(namespace, id, def, options)
Registry.get(namespace, id) → Entry
Registry.has(namespace, id) → bool
Registry.all(namespace, filter) → [Entry]
Registry.find_by_tag(namespace, tag) → [Entry]
Registry.update(namespace, id, patch)
Registry.deprecate(namespace, id, replaced_by)
Registry.declare_namespace(name, deps)
Registry.freeze() / unfreeze()
Registry.on_change(namespace, callback)
Registry.export(namespace) → table
```

---

# ЧАСТЬ 8. RUNTIME-МОДУЛИ

| Модуль | Назначение |
|---|---|
| **EffectManager** | Управление эффектами |
| **OpExecutor** | Исполнение ops |
| **ConditionEvaluator** | Проверка условий |
| **SelectorResolver** | Выбор целей |
| **ValueEvaluator** | Вычисление значений |
| **ScaleEvaluator** | Скалирование |
| **ModifierStack** | Стек модификаторов |
| **DamagePipeline** | Урон, криты, резисты |
| **EventBus** | Шина событий |
| **Timeline** | Лог событий, откаты |
| **SnapshotManager** | Снимки состояния |
| **ZoneManager** | Зоны и ауры |
| **SummonManager** | Призывы |
| **FactionManager** | Фракции и отношения |
| **AggroManager** | Агро и targeting |
| **AdaptationManager** | Адаптации |
| **PhenomenonRegistry** | Подписи феноменов |
| **SignatureHasher** | Генерация подписей |
| **EscalationManager** | Прогрессия уровней |
| **WheelRenderer** | Визуал счётчиков |
| **LearnedTechniqueManager** | Украденные техники |
| **MemoryManager** | Память |
| **TrueFormManager** | Истинные формы |

---

# ЧАСТЬ 9. ПРИМЕР ПОЛНОГО ЭФФЕКТА

```lua
Registry.register("effects","sukuna_cleave",{
  id = "sukuna_cleave",
  tags = { "slash","signature","offensive" },
  layer = "effect",
  version = 1,

  trigger = { kind="event", event="on_attack" },

  cost = { resource="mana", value={ flat=15 } },

  priority = 10,
  exclusive_group = nil,

  ops = {
    -- основной урон
    { kind="deal",
      target="enemy",
      stat="hp",
      op="sub",
      value = { pct=30, of="target.max_hp" },
      scale = {
        every = 10,
        of = "target.hp_missing_below_50",
        value = { pct=5, of="target.max_hp" }
      },
      flags = { "adaptive","pierce" },
      when = { kind="hp_above", target="enemy", pct=0 }
    },

    -- метка
    { kind="mark",
      target="enemy",
      stat="mark.cleave",
      value = { flat=1 },
      duration = { flat=6 }
    },

    -- ветка при провале (враг неуязвим)
    fail = {
      { kind="apply_status",
        target="self",
        status_id="cleave_miss",
        duration={ flat=1 } }
    }
  },

  on_enter = {
    { kind="play_anim", target="self", anim="cleave_slash" }
  },

  on_exit = nil,

  -- расширения (не используются здесь, но доступны)
  faction = nil,
  autonomous = nil,
  ai_profile = nil,
  counter_display = nil,
  tiered_progression = nil,
  adaptive_response = nil,
  persistent_memory = nil,
})
```

---

# ЧАСТЬ 10. ПРИНЦИПЫ (не нарушать)

1. **Один Effect = триггер + ops.** Всё остальное — опционально.
2. **Один Op — одна форма.** Различается только `kind`.
3. **Персонаж добавляет kind и реестры.** Не поля Op.
4. **Поле Op добавляется только если:** общий паттерн + 3+ прецедента + сериализуемо + не выражается комбинацией.
5. **Всё регистрируется.** Никаких хардкодных статов/статусов.
6. **Всё сериализуемо.** Функции — только через `expr` или именованные предикаты.
7. **Timeline — фундамент.** Без него половина kinds не работает.
8. **Слои не смешиваются.** Effect ≠ Rules ≠ State ≠ Meta.
9. **Числовые ID на hot path.** Строки — только при загрузке.
10. **Расширяется enum'ами, не структурой.**

-
