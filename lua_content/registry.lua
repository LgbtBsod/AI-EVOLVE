-- lua_content/registry.lua
-- REGISTRY SYSTEM — расширяемость без правки ядра (ЧАСТЬ 0.4 / B справочника).
-- Чистые данные: ни одной функции (lib/export.lua их отбрасывает). Ядро
-- (src/core/registry.py::default_registries + RegistrySet) резолвит записи по
-- именам; контент и моды добавляют ЗАПИСИ, не поля Op (правило №5).
--
-- Каждая запись: { id, layer?, handler?, tags?, source? }.
--   handler — имя обработчика в OP_HANDLERS (src/effects/ops.py) или "planned"
--   (handler ядра ещё не написан: рантайм пишет warning и пропускает op).
-- Реализация kind'ов детально — в kinds/*.lua, этот файл — корневые словари.

return {
  version = 1,

  -- Namespace'ы реестра (B.3). exists_in: где живёт Python-сторона.
  namespaces = {
    stats        = { exists_in = "effect_rules.lua defaults/bounds, reg['stats']" },
    resources    = { exists_in = "effect_rules.lua resources, reg['resources']" },
    statuses     = { exists_in = "reg['statuses']; дефиниции — effects/*.lua" },
    effects      = { exists_in = "reg['effects']; дефиниции — abilities.lua, items/, effects/" },
    abilities    = { exists_in = "reg['abilities']; дефиниции — abilities.lua, bosses.lua" },
    items        = { exists_in = "reg['items']; дефиниции — items/, bricks/items.lua" },
    conditions   = { exists_in = "reg['conditions']; именованные pred — effect_rules.lua predicates" },
    selectors    = { exists_in = "reg['selectors']; см. selectors ниже" },
    scales       = { exists_in = "reg['scales']; см. scales ниже" },
    damage_types = { exists_in = "reg['damage_types'] + damage.lua types" },
    flags        = { exists_in = "reg['flags']; см. flags ниже" },
    layers       = { exists_in = "reg['layers']; см. layers ниже" },
    kinds        = { exists_in = "kinds/*.lua; сводный список — kinds/all.lua loader" },
    triggers     = { exists_in = "triggers ниже; рантайм — src/effects/manager.py" },
    ops          = { exists_in = "MOD_MATH add|sub|mul|div|set|min|max (src/effects/ops.py)" },
    value_sources= { exists_in = "value_sources ниже; compute_amount (src/effects/ops.py)" },
    tags         = { exists_in = "семантические теги контента (berserk, dojutsu, cursed...)" },
    factions     = { exists_in = "world.lua / менеджер фракций" },
    regions      = { exists_in = "world.lua regions" },
  },

  -- Слои (ЧАСТЬ 1). priority — порядок исполнения рантаймов (низкий раньше);
  -- runtime — какой интерпретатор исполняет ops слоя.
  layers = {
    { id = "effect",      priority = 10, runtime = "src/effects/manager.py + ops.py" },
    { id = "entity",      priority = 15, runtime = "src/entities (слоты, структура)" },
    { id = "social",      priority = 20, runtime = "planned: src/systems/social" },
    { id = "state",       priority = 30, runtime = "src/core/timeline.py (snapshot/rewind)" },
    { id = "world",       priority = 40, runtime = "planned: world state machine" },
    { id = "rules",       priority = 50, runtime = "planned: интерпретируется ДО effect" },
    { id = "temporal",    priority = 60, runtime = "src/core/timeline.py (rewind/fork/simulate)" },
    { id = "ontological", priority = 70, runtime = "planned: над rules" },
    { id = "meta",        priority = 80, runtime = "ОТДЕЛЬНЫЙ интерфейс к платформе, не игровой" },
    { id = "narrative",   priority = 90, runtime = "вне игры (автор, сценарий)" },
  },

  -- Типы урона: id задаётся ТЕГОМ способности (abilities.lua header), числа
  -- конвейера — damage.lua. resistible=false: резисты не работают (true/existential).
  damage_types = {
    { id = "physical",  resistible = true },
    { id = "fire",      resistible = true },
    { id = "ice",       resistible = true },
    { id = "lightning", resistible = true },
    { id = "poison",    resistible = true },
    { id = "holy",      resistible = true },
    { id = "dark",      resistible = true },
    { id = "cursed_energy", resistible = true, tags = { "jjk" } },
    { id = "genjutsu",  resistible = false, tags = { "naruto" }, note = "по чабре/восприятию, не по броне" },
    { id = "true",      resistible = false, flags = { "true_damage" } },
    { id = "existential", resistible = false, tags = { "erase" }, note = "стирание из существования" },
  },

  -- Флаги ops/событий (core flag system).
  flags = {
    { id = "true_damage",      desc = "игнорирует броню/резисты" },
    { id = "no_crit",          desc = "удар не критует" },
    { id = "silent",           desc = "без телеграфа/звука" },
    { id = "iframe",           desc = "неуязвимость на время баффа" },
    { id = "bypass_infinity",  desc = "игнорирует Gojo Infinity" },
    { id = "undodgeable",      desc = "не уклоняется" },
    { id = "no_heal",          desc = "цель не лечится" },
    { id = "no_resurrection",  desc = "после erase не воскрешается (Balefire)" },
    { id = "preserves_memory", desc = "помнит при rewind (Time Leap / Contessa)" },
  },

  -- Триггеры (Trigger.kind + event-имена; src/effects/manager.py).
  triggers = {
    { id = "passive",   spec = "{ kind='passive' }" },
    { id = "condition", spec = "{ kind='condition', when=pred }" },
    { id = "event",     spec = "{ kind='event', event=..., filter=pred, owner_has=effect_id }" },
    { id = "applied",   spec = "{ kind='applied' } — запускается op apply_effect" },
    { id = "tick",      spec = "{ kind='tick', every=N } (planned fully)" },
    { id = "threshold", spec = "эффект-поле threshold + trigger.cross (EFFECT_SCHEMA п.14)" },
    -- события ядра (пишутся и в Timeline, timeline/event_kinds.lua):
    { id = "attack" }, { id = "attack_hit" }, { id = "on_cast" }, { id = "kill" },
    { id = "on_death" }, { id = "hp_cross" },
  },

  -- Селекторы целей (поле target/area op'а).
  selectors = {
    { id = "self",  spec = "target='self'" },
    { id = "enemy", spec = "target='enemy' — одна цель" },
    { id = "ally" }, { id = "allies" }, { id = "source" },
    { id = "area",  spec = "target='area' + radius(число|стат) + center + arc + affects" },
    { id = "line",  spec = "planned: cone/line" },
    { id = "cone",  spec = "через area+arc (mvp)" },
    { id = "lowest_hp", spec = "planned: sort-filter селектор" },
  },

  -- Источники для value.pct.of и scale.of (value_sources).
  value_sources = {
    "max_hp", "max_mana", "max_stamina", "attack_damage", "spell_power",
    "strength", "agility", "intelligence", "vitality", "wisdom", "endurance",
    "luck", "defense", "crit_chance", "crit_dmg", "aspd", "lifesteal",
    "move_speed", "attack_range", "vision_range", "hp_missing_below_40",
    "ctx.hp_pct", "ctx.stacks", "ctx.power",
    -- + семейство hp_missing_below_<N> (N = порог в %, напр. _35): определяется в src/effects/ops.py derived_ctx, здесь перечислен только _40
  },

  -- Именованные скейлы (Scale.mode).
  scales = {
    { id = "linear", spec = "base + floor(ctx[of]/every) * value * factor" },
    { id = "exp",    spec = "planned: base * factor^floor(ctx[of]/every)" },
    { id = "cap",    spec = "любой + cap/floor границы" },
  },

  -- Порядок загрузки namespace'ов (B.6): зависимые — после зависимостей.
  load_order = {
    { "stats", "resources", "damage_types", "flags", "tags", "ops", "kinds",
      "triggers", "value_sources", "selectors", "conditions", "scales" },
    { "layers", "regions", "factions", "statuses" },
    { "effects", "abilities" },
    { "items" },
    { "contracts", "oaths", "narratives" },  -- planned
  },

  -- Валидация записей — схемами из schemas/* (B.5). freeze перед матчем:
  -- RegistrySet.freeze_all(); модам после freeze — отказ (FrozenRegistryError).
  validate_with = { stats = "schemas/stats.lua", resources = "schemas/resources.lua",
                    statuses = "schemas/statuses.lua", effects = "schemas/effects.lua" },
}
