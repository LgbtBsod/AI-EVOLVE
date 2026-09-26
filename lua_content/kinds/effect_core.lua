-- lua_content/kinds/effect_core.lua
-- Effect Layer: ВСЕ kinds боевого слоя (ЧАСТЬ 3.1 справочника). Формат записи:
--   { id, layer, handler, fields = {обязательные поля op}, optional = {...}, note }
-- handler — имя в OP_HANDLERS (src/effects/ops.py) или "planned" — обработчика
-- ядра ещё нет (рантайм пишет warning и пропускает op; см. ARCHITECTURE.md).
-- Поля op общие для всех kinds (schema.lua); здесь — какие поля нужны виду.

local function k(id, handler, fields, optional, note)
  return { id = id, layer = "effect", handler = handler, fields = fields,
           optional = optional or {}, note = note }
end

return {
  -- урон / ресурсы -----------------------------------------------------------
  k("deal", "op_damage", { "target", "stat", "op", "value" },
    { "scale", "when", "every", "duration", "flags", "radius", "affects", "center", "arc" },
    "урон по hp через конвейер damage.lua; по mana/stamina — трата ресурса"),
  k("drain", "op_spend", { "target", "stat", "value" }, { "fail", "scale" },
    "списать ресурс; не хватает — ветка fail (Lost My Self: hp->1 + Last Will)"),
  k("heal", "op_heal", { "target", "value" }, { "stat", "op", "scale", "flags" },
    "восстановить ресурс (по умолчанию hp)"),
  k("set", "op_set_resource", { "target", "value" }, { "stat", "op" },
    "жёсткая установка ресурса"),
  k("mod", "op_mod", { "target", "stat", "op", "value" },
    { "scale", "duration", "toward", "when", "flags" },
    "изменить стат; duration -> временный слой external; toward='source' — стелс vision_range"),
  k("consume", "planned", { "resource", "amount" }, {},
    "потратить ресурс способности (cost исполняет менеджер каста)"),
  k("restore", "planned", { "resource", "value" }, {},
    "вернуть ресурс (reverse drain без отката события)"),
  k("kill", "op_kill", { "target" }, { "flags" },
    "убить цель (в игре — истинный урон через _damage)"),
  k("erase", "planned", { "target" }, { "flags" },
    "стереть из существования; irreversible + no_resurrection (см. timeline/event_kinds.lua)"),
  k("mass_resurrect", "planned", { "filter" }, {},
    "массовое воскрешение по фильтру трупов"),

  -- баффы / дебаффы / статусы -------------------------------------------------
  k("buff", "op_buff", { "target", "buff_id", "duration" },
    { "cooldown", "extend", "flags", "ops" },
    "наложить бафф; iframe — неуязвимость; cooldown отсчитывается от выдачи"),
  k("debuff", "op_buff", { "target", "buff_id", "duration" }, { "stacks" },
    "бафф со знаком минус (тот же механизм)"),
  k("status", "planned", { "target", "status_id", "duration" }, { "stacks", "data" },
    "наложить статус из reg['statuses'] (stun, burn, amaterasu...)"),
  k("status_transform", "planned", { "from", "to" }, {},
    "превратить один активный статус в другой"),
  k("status_mod", "planned", { "status_id", "field", "op", "value" }, {},
    "изменить параметры активного статуса"),
  k("remove_effect", "planned", { "effect_id" }, { "filter" }, "снять эффект"),
  k("purge", "planned", { "target" }, { "filter" },
    "снять все баффы (фильтр purgeable из schemas/statuses.lua)"),

  -- марки / детонаторы ---------------------------------------------------------
  k("mark", "planned", { "target", "mark_id", "value" }, { "duration", "stacks" },
    "поставить метку"),
  k("detonate", "planned", { "mark_id" }, { "value", "scale" },
    "детонировать метки (Marksmanship / руны)"),

  -- зоны / ауры ----------------------------------------------------------------
  k("zone", "planned", { "shape", "radius", "ops" }, { "duration", "tick", "affects" },
    "зона с ops внутри (домен, лава, аматэрасу-поле)"),
  k("aura", "planned", { "ops" }, { "radius", "filter" },
    "постоянная аура вокруг носителя"),

  -- существа --------------------------------------------------------------------
  k("summon", "op_summon", { "template" }, { "count", "duration", "stats_override" },
    "призвать (клавы, шары истины, куклы); в комнате — только строка лога"),
  -- контроль цели: одна запись unit.external["control"], возврат по таймеру/смерти контролирующего (src/effects/control.py)
  k("possess", "op_possess", { "target" }, { "duration", "action", "target_ref", "targeting", "requires", "chance", "on_exit", "id" },
    "вселиться: смена фракции + перехват целеуказания, откат по expiry/смерти каста (в игре нет управления чужой сущностью)"),
  k("hypnosis", "op_hypnosis", { "target" }, { "duration", "action", "target_ref", "targeting", "requires", "chance", "on_exit", "id" },
    "гипноз: цель видит иллюзию (perception/target подменены)"),
  k("command", "op_command", { "target" }, { "duration", "action", "target_ref", "targeting", "requires", "chance", "on_exit", "id" },
    "приказ: aggro_mode command:<action>, target_ref"),
  k("dominance", "op_dominance", { "target" }, { "duration", "action", "target_ref", "targeting", "requires", "chance", "on_exit", "id" },
    "доминирование: приказ + смена фракции, обычно с requires"),
  k("temptation", "op_temptation", { "target" }, { "duration", "action", "target_ref", "targeting", "requires", "chance", "on_exit", "id" },
    "соблазн: приказ с условием requires"),
  k("tame", "op_tame", { "target" }, { "duration", "action", "target_ref", "targeting", "requires", "chance", "on_exit", "id" },
    "приручение: постоянная смена фракции, chance% seeded-броском"),
  k("transform", "op_transform", { "id" }, { "duration", "stats", "abilities", "on_enter", "on_exit", "exclusive_group", "conflict_with" },
    "трансформация (Gear, Jubi, Super Saiyan)"),
  k("stance", "op_stance", { "id" }, { "exclusive_group", "conflict_with", "duration", "on_enter", "on_exit" },
    "стойка/режим: swap набора способностей"),

  -- движение / позиция ----------------------------------------------------------
  k("move", "op_move", { "target", "mode", "distance" }, { "toward" },
    "mode: knockback | push | pull | dash | teleport | swap; исполнитель — менеджер (координаты мира)"),
  k("teleport", "alias:move", { "target" }, { "to" }, "alias of move mode=teleport (kind_aliases.lua)"),
  k("swap", "alias:move", { "target" }, {}, "alias of move mode=swap (kind_aliases.lua)"),
  k("timed_power_up", "op_timed_power_up", { "id", "duration" }, { "stats", "on_enter", "on_exit" }, "temporary power-up; on_exit = the drawback at expiry"),

  -- управление / восприятие ------------------------------------------------------
  k("dodge", "planned", { "chance" }, {}, "гарантированное уклонение на окно"),
  k("block", "planned", { "amount" }, {}, "блок (конвейер block_chance/block_reduction)"),
  k("resist", "planned", { "damage_type", "value" }, {}, "временный резист типа"),
  k("immune", "planned", { "damage_type", "value" }, {}, "иммунитет (jubi: all 90%)"),
  k("nullify", "planned", { "filter" }, {}, "отмена сил в области/у цели"),
  k("counter", "planned", { "ops" }, { "when" }, "контратака на событие"),
  k("reflect", "planned", { "pct" }, {}, "отражение урона"),
  k("redirect_harm", "planned", { "to" }, {}, "перенаправление урона на другую сущность"),
  k("untargetable", "planned", { "duration" }, {}, "цель невыбираема селекторами"),
  k("reveal", "planned", { "radius" }, {}, "снять стелс/невидимость в зоне"),
  k("grant_vision", "planned", { "to", "value" }, {}, "дать зрение (mod vision_range союзнику)"),

  -- адаптация / кража / обучение ---------------------------------------------------
  k("adapt", "planned", { "of", "rate" }, {},
    "сопротивление к типу растёт после попаданий (Mahoraga)"),
  k("steal", "planned", { "what", "id" }, {},
    "украсть эффект/способность/стат навсегда"),
  k("absorb", "planned", { "what", "convert" }, {},
    "поглотить (Geto: souls target -> ресурс поглощающего)"),
  k("copy", "planned", { "ability_id" }, { "duration" }, "скопировать способность"),
  k("copy_last_cast", "planned", {}, { "within" }, "скопировать последний каст цели"),
  k("inherit_all", "planned", { "registry" }, {},
    "унаследовать всё из реестра (Yhwach millennium brain)"),
  k("transfer_stat", "planned", { "stat", "pct" }, {}, "перенос стата между сущностями"),
  k("unbounded", "planned", { "stat" }, {}, "снять лимиты стата (bounds off)"),
  k("progressive_state", "planned", { "states", "advance_on" }, {},
    "прогрессия состояний (Gears, Tusk acts)"),

  -- отложенные / условные ------------------------------------------------------------
  k("delay", "planned", { "ops", "after" }, {},
    "отложенное исполнение ops (tick-based поверх Timeline)"),
  k("on_lethal", "planned", { "ops" }, {},
    "сработает при летальном уроне (обобщение Last Will)"),
  k("conditional", "planned", { "when", "ops", "else_ops" }, {},
    "if/else над поддеревом ops"),

  -- гача / случайности -----------------------------------------------------------------
  k("gacha", "planned", { "table", "count" }, {},
    "ролл по reg-таблице; каждый ролл = rng_roll событие Timeline (A.10, replay-детерминизм)"),

  -- спец-эффекты персонажей -------------------------------------------------------------
  k("read", "planned", { "target" }, {}, "прочитать сущность (Rohan) -> data в Timeline"),
  k("write", "planned", { "target", "fact" }, {}, "записать в сущность (Heaven's Gate)"),
  k("rename", "planned", { "target", "new_name", "semantics" }, {},
    "переименовать (Ичибе): смена определения цели"),
  k("wish", "planned", { "goal", "cost" }, {},
    "исполнить желание (дорого; результаты — rules-уровня ops)"),
  k("sever_magic_circuits", "planned", { "target" }, {},
    "разорвать магию: nullify + disable abilities"),
  k("fuel_consume", "planned", { "resource", "per_tick" }, {},
    "сжигать топливо как стоимость состояния (lifespan)"),
  k("steal_stat", "planned", { "stat", "amount" }, {},
    "Hemalurgy: украсть стат навсегда (feruchemia — временно)"),
  k("oath_binding", "planned", { "oath", "penalty", "boon" }, {},
    "клятва: buff пока выполняешь, penalty-ops за нарушение"),
}
