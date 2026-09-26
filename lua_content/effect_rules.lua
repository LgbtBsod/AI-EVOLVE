-- lua_content/effect_rules.lua
-- Правила статов для Effect Schema: значения юнита по умолчанию и границы
-- итоговых статов. Читает tools/effect_schema/sim.py через tools/lua_bridge.py;
-- без Lua действуют те же значения из sim.py (DEFAULT_RULES).
--
-- Границы применяются к ИТОГОВОМУ стату (база + моды). Бонусы эффектов
-- (mods) не обрезаются: спека предмета проверяет именно их.

return {
  -- база нового юнита (тренировочная комната, кузница предметов)
  defaults = {
    max_hp = 1000, max_mana = 100, max_stamina = 100,
    hp_regen = 0, mana_regen = 0, stamina_regen = 0,
    strength = 0, agility = 0, intelligence = 0, vitality = 0,
    wisdom = 0, charisma = 0, luck = 0, endurance = 0,
    defense = 0, tenacity = 0,
    crit_chance = 0, crit_dmg = 50, aspd = 1.0,
    lifesteal = 0, move_speed = 5, attack_damage = 0,
    spell_power = 0, dodge = 0,     -- dodge в пунктах (%), в игре dodge_chance 0..1
    attack_range = 2,               -- как далеко бьёт удар оружием (лук, копьё - больше)
    vision_range = 20,              -- как далеко сущность замечает других (стелс снижает)
    -- урон: конвейер lua_content/damage.lua + docs/DAMAGE_PIPELINE.md. Броня - это `defense`, крит - crit_chance /
    -- crit_dmg, уклонение - dodge; здесь остальное. Всё 0 = нейтрально (урон как до конвейера).
    accuracy = 0,                   -- атакующий: очки шанса попасть (шанс = 100 + accuracy - evasion, %)
    evasion = 0,                    -- цель: очки шанса промаха по ней
    penetration_pct = 0,            -- атакующий: % брони цели, который удар игнорирует
    penetration_flat = 0,           -- атакующий: очков брони, которые удар игнорирует (после процента)
    resist_pen = 0,                 -- атакующий: пунктов %, снимаемых с каждого положительного resist_<тип>
    block_chance = 0,               -- цель: шанс блока, %
    block_reduction = 0,            -- цель: пунктов % сверх block.reduction из damage.lua, которые режет блок
    damage_taken = 0,               -- цель: % урона сверх обычного (минус - меньше); итоговый модификатор
    cc_duration_mult = 1,           -- цель: x к длительности CC-статусов (statuses.lua); <= 0 - иммунитет к CC. Шанс сопротивления - status_resist_<id> (0..100)
    cc_damage_mult = 1,             -- атакующий: x к урону по цели под CC (умножается на cc_damage_mult строки статуса)
    cc_damage_flat = 0,             -- цель под CC: очков урона, снимаемых до процента: (d - flat) * (1 - reduction/100)
    cc_damage_reduction = 0,        -- цель под CC: % урона, который не проходит
    broken = 0,                     -- цель: 1 = сломана (guard break): весь урон x broken из damage.lua; вешается mod-ом на время
  },

  -- семейства статов по типам урона (типы и их значения по умолчанию - lua_content/damage.lua): rules() добавляет
  -- defaults и bounds для prefix..<тип> (resist_fire, damage_ice ...). default_of - поле типа в damage.lua.
  families = {
    { prefix = "resist_", default_of = "resist", bounds = { min = -100, max = 100 } },  -- цель: % урона типа, который не проходит
    { prefix = "damage_", default_of = "mod",    bounds = { min = -100 } },             -- атакующий: % бонус к урону типа
  },

  -- ресурсы как у Character в игре: текущее значение меняют heal/drain/deal/set,
  -- максимум и реген (в секунду, на тике) - обычные статы
  resources = {
    hp      = { max = "max_hp",      regen = "hp_regen" },
    mana    = { max = "max_mana",    regen = "mana_regen" },
    stamina = { max = "max_stamina", regen = "stamina_regen" },
  },

  -- характеристики -> производные статы (за 1 очко). Герой получает 5 очков за
  -- уровень, обычный враг 10, элита 15, босс +10 к каждой (world.lua -> progression);
  -- предметы и эффекты тоже меняют характеристики («+20% силы»).
  attributes = {
    strength     = { attack_damage = 0.6, max_hp = 1 },
    agility      = { crit_chance = 0.15, aspd = 0.008, dodge = 0.1 },
    intelligence = { spell_power = 0.8, max_mana = 3 },
    vitality     = { max_hp = 6, hp_regen = 0.04 },
    wisdom       = { mana_regen = 0.08, spell_power = 0.2, vision_range = 0.05 },
    endurance    = { max_stamina = 3, stamina_regen = 0.05, defense = 0.3 },
    luck         = { crit_chance = 0.1, dodge = 0.05 },
    charisma     = {},   -- цены у торговцев и отношение NPC (социальная часть)
  },

  -- именованные условия (trigger.when = "low_hp_40"): одно выражение для
  -- Python-симуляции и для Lua (lua_gen кладёт его в реестр PRED предмета)
  predicates = {
    low_hp_40 = "ctx.hp_pct < 40",
  },

  -- min/max итогового стата; нет записи - без ограничений
  bounds = {
    max_hp      = { min = 1 },     -- 0 или меньше ломает hp_pct (деление на ноль)
    max_mana    = { min = 0 },
    max_stamina = { min = 0 },
    crit_chance = { min = 0, max = 100 },
    move_speed  = { min = 0 },
    tenacity    = { min = 0, max = 100 },
    dodge       = { min = 0, max = 75 },
    aspd        = { min = 0.1, max = 4 },  -- больше 4 ударов в секунду не бывает
    attack_range = { min = 0.5, max = 30 },
    vision_range = { min = 0, max = 80 },
    accuracy    = { min = -100, max = 100 },
    evasion     = { min = 0, max = 95 },        -- шанс попасть не падает ниже hit.min из damage.lua
    penetration_pct  = { min = 0, max = 100 },
    penetration_flat = { min = 0 },
    resist_pen  = { min = 0, max = 100 },
    block_chance = { min = 0, max = 75 },
    block_reduction = { min = 0, max = 100 },
    damage_taken = { min = -90 },
    broken      = { min = 0, max = 1 },
  },
}
