-- lua_content/schema.lua — СПРАВОЧНИК ПОЛЕЙ Effect/Op/Value/Scale/Trigger/Condition
-- (ЧАСТЬ 2 справочника; человекочитаемый twin docs/EFFECT_SCHEMA.md). Чистые данные:
-- валидатор tools/effect_schema/validate.py сверяет контент по этому словарю.
-- Правило №4: единая форма Op для всех kinds; правило №5: персонаж добавляет kind,
-- а НЕ поле здесь. Новые поля Op = изменение ядра = согласовано с docs/EFFECT_SCHEMA.md.
return {
  version = 1,

  -- Уровень 1: Effect ---------------------------------------------------------
  effect = {
    id       = "string, уникальный (reg['effects'])",
    tags     = "{string} (berserk, passive, domain...)",
    layer    = "registry.lua layers; по умолчанию 'effect'",
    trigger  = "Trigger — когда эффект включён",
    duration = "nil | Value (nil = пока trigger истинен)",
    cooldown = "nil | Value (событийный эффект не чаще раза в N сек)",
    stacks   = "nil | StackRule",
    exclusive_group = "nil | string (пересекающиеся эффекты вытесняют друг друга)",
    priority = "nil | number (порядок применения внутри слоя)",
    amplify  = "nil | { when, every, of, factor } — все mod-бонусы x factor^floor(ctx[of]/every)",
    threshold= "nil | зона hp_cross (п.14 EFFECT_SCHEMA)",
    ops      = "{Op}",
    on_enter = "nil | {Op} (при активации)",
    on_exit  = "nil | {Op} (с снятии)",
  },

  -- Уровень 2: Op — ОДИН объект на все kinds ----------------------------------
  op = {
    kind     = "см. kinds/*.lua (deal|mod|buff|status|retroactive_erase|...)",
    target   = "registry.lua selectors: self|enemy|ally|source|allies|area",
    stat     = "имя стата из reg['stats'] или ресурс (hp|mana|stamina) | nil",
    op       = "add|sub|mul|div|set|min|max (MOD_MATH src/effects/ops.py)",
    value    = "Value",
    scale    = "Scale",
    when     = "pred (строка ctx-выражения или имя из effect_rules.lua predicates)",
    fail     = "{Op} — ветка при невыполнимости (drain без ресурса)",
    flags    = "{string} из registry.lua flags",
    duration = "Value | nil (временный слой external)",
    cooldown = "Value | nil",
    extend   = "{ on='kill', flat=5 } — продление баффа по событию",
    buff_id  = "для buff/debuff/apply_effect",
    status_id= "для status (reg['statuses'])",
    ability_id = "для copy/steal (reg['abilities'])",
    filter   = "pred над множеством целей",
    radius   = "число | имя стата ('attack_range') — для area",
    center   = "'self'|'target' — для area",
    arc      = "градусы конуса (mvp area+arc)",
    affects  = "all|others|enemies|allies (френдли фаер)",
    toward   = "'source' — только mod vision_range (стелс)",
    every    = "число|Value — DoT/HoT интервал (вместе с duration)",
    mode     = "для move: knockback|pull|dash",
    distance = "для move",
    template = "для summon (reg['summon_templates'])",
    count    = "Value — для summon/gacha",
    ops      = "{Op} — рекурсия (zone/delay/conditional/on_enter)",
    layer_meta = "table — специфика слоя (rules={physics}, goal_seek={max_steps})",
  },

  -- Уровень 3: Value ------------------------------------------------------------
  value = {
    flat  = "{ flat = N }",
    pct   = "{ pct = N, of = source? } — без of: процент от того же стата; аддитивные статы (crit_chance) пишут flat!",
    ref   = "{ ref = 'ctx.strength' } | { ref=..., mul=N, add=N }",
    expr  = "{ expr = '...' } — для редактора",
    random= "{ random = { min, max } } — ролл пишется rng_roll событием Timeline",
    clamp = "{ clamp = { min, max }, ref = '...' }",
    table = "{ table = 'registry.name' } — таблица из реестра",
  },

  -- Уровень 4: Scale --------------------------------------------------------------
  scale = { every="шаг", of="стат-источник", value="Value шага", factor="множитель (amplify/exp)",
            cap="потолок", floor="пол", mode="linear|exp (registry.lua scales)" },

  -- Уровень 5: Trigger --------------------------------------------------------------
  trigger = {
    passive   = "{ kind='passive' }",
    condition = "{ kind='condition', when=pred }",
    event     = "{ kind='event', event=..., filter=pred, owner_has=effect_id }",
    applied   = "{ kind='applied' } — запускается op apply_effect",
    tick      = "{ kind='tick', every=N }",
    timeline  = "{ kind='timeline', at_tick=N } — сработает на тике журнала",
    all       = "{ kind='all', of={Trigger} }", any = "...", not_ = "{ kind='not', of=Trigger }",
    meta      = "{ kind='meta', condition=... } — условие вне игры (Meta-слой)",
  },

  -- Условия (pred): Python/Lua-подмножество ctx-выражений (EFFECT_SCHEMA раздел
  -- «Условия»), либо имя из effect_rules.lua predicates, либо {kind='registry', name=...}.
  condition = {
    hp_below = "{ kind='hp_below', pct=40 }",
    stat_cmp = "{ kind='stat_cmp', stat, op, value }",
    has_status = "{ kind='has_status', id }", has_buff = "{ kind='has_buff', id }",
    has_flag = "{ kind='has_flag', flag }",
    last_skill = "{ kind='last_skill', id, within }",
    attacker_has_flag = "{ kind='attacker_has_flag', flag }",
    distance = "{ kind='distance', op, value }", team_size = "{ kind='team_size', op, value }",
    hp_missing_below = "{ kind='hp_missing_below', pct }",
    time_since = "{ kind='time_since', event, op, value }",
    all = "{ kind='all'|'any'|'not', of={Condition} }",
    registry = "{ kind='registry', name, args }",
    expr = "{ kind='expr', code } — для редактора",
  },
}
