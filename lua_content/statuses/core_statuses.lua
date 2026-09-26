-- lua_content/statuses/core_statuses.lua — базовые статусы реестра reg['statuses']
-- (схема schemas/statuses.lua: required duration/purgeable/stacking). Читает src/effects/statuses.py
-- (EffectManager.apply_status / EffectRuntime.apply_status); контент ссылается по id.
-- Строка = данные: duration (с; число - задаёт длительность операциям без своей), ops (только существующие
-- виды ops.py; target = "enemy" - носитель статуса, источник - тот, кто вешает), stack = { max, add }:
-- повторное наложение stacks += n до max, таймер сбрасывается; add - добавка к value.flat КАЖДОЙ операции
-- на стак (DoT: base + add * stacks). alias = id другой строки. cc_priority (только CC-строки): сильнейший
-- побеждает (STUN 5 > KNOCKDOWN 4 > MICRO_STUN 3 > ROOT 2 > DISORIENTED 1 > SLOW 0; решение владельца Q4: данные).
-- Шанс сопротивления: стат носителя status_resist_<id> (0..100, >=100 - иммунитет), бросок на rng менеджера.
-- cc_damage_mult (бонус атакующего по CC-цели) - только данные, применение в уроне = S2 (нужен хук в damage).
-- Числа - наследие legacy (docs/CC_PORT_SPEC.md 2.1); weaken/vulnerable - решение владельца: -10% / +10% за стак.
local function s(id, duration, purgeable, stacking, ops, note, extra)
  local row = { id = id, layer = "effect", duration = duration, purgeable = purgeable,
                stacking = stacking, ops = ops, note = note }
  for k, v in pairs(extra or {}) do row[k] = v end
  return row
end
local function dot(dur, base)   -- DoT раз в секунду, без крита
  return { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { flat = base },
             every = 1, duration = { flat = dur }, flags = { "no_crit" } } }
end
local TYPES = { "physical", "fire", "ice", "lightning", "poison", "holy", "dark" }
local function per_type(stat_prefix, flat)
  local ops = {}
  for _, ty in ipairs(TYPES) do
    ops[#ops + 1] = { kind = "mod", target = "enemy", stat = stat_prefix .. ty, op = "add", value = { flat = flat } }
  end
  return ops
end
local STOP = { kind = "mod", target = "enemy", stat = "move_speed", op = "set", value = { flat = 0 } }
return {
  s("bleed", 8, true, "stack", dot(8, 5), "legacy: 5 + 2/стак, cap 5",
    { tags = { "dot", "physical" }, damage_type = "physical", stack = { max = 5, add = 2 } }),
  s("burn", 6, true, "stack", dot(6, 8), "legacy: 8 + 3/стак, cap 3",
    { tags = { "dot", "fire" }, damage_type = "fire", stack = { max = 3, add = 3 } }),
  s("poison", 10, true, "stack", dot(10, 4), "legacy: 4 + 1.5/стак, cap 6",
    { tags = { "dot", "poison" }, damage_type = "poison", stack = { max = 6, add = 1.5 } }),
  s("shock", 4, true, "stack", dot(4, 3), "legacy: 3 + 1.5/стак, cap 4",
    { tags = { "dot", "lightning" }, damage_type = "lightning", stack = { max = 4, add = 1.5 } }),
  s("freeze", 2, true, "replace",
    { { kind = "nullify", target = "enemy", filter = "actions" }, STOP },
    "нет действий и движения; shatter от физ. удара - S3", { tags = { "cc", "ice" }, damage_type = "ice", cc = true, cc_priority = 5, cc_damage_mult = 1.0 }),
  s("stun", 1.5, true, "replace",
    { { kind = "nullify", target = "enemy", filter = "actions" } },
    "прерывает действия; breakable_by={damage}", { tags = { "cc" }, cc = true, cc_priority = 5, cc_damage_mult = 1.0 }),
  s("knockdown", 1.0, true, "replace",
    { { kind = "nullify", target = "enemy", filter = "actions" },
      { kind = "move", target = "enemy", mode = "knockback", distance = 1.5 } },
    "stun + отбрасывание", { tags = { "cc" }, cc = true, cc_priority = 4, cc_damage_mult = 1.0 }),
  s("micro_stun", 0.2, true, "replace",
    { { kind = "cancel_technique", target = "enemy" },
      { kind = "nullify", target = "enemy", filter = "abilities" } },
    "прерывает текущий каст", { tags = { "cc" }, cc = true, cc_priority = 3, cc_damage_mult = 1.0 }),
  s("silence", "required", true, "replace",
    { { kind = "nullify", target = "enemy", filter = "abilities", duration = { flat = 3 } } },
    nil, { tags = { "cc" } }),
  s("blind", "required", true, "refresh",
    { { kind = "mod", target = "enemy", stat = "vision_range", op = "mul", value = { pct = 0 },
        duration = { flat = 5 } } },
    "через mod vision_range", { tags = { "cc" }, cc = true, cc_priority = 1, cc_damage_mult = 1.0 }),
  s("disoriented", "required", true, "refresh", {}, "алиас blind", { alias = "blind" }),
  s("root", "required", true, "refresh",
    { { kind = "mod", target = "enemy", stat = "move_speed", op = "set", value = { flat = 0 },
        duration = { flat = 3 } } }, nil,
    { tags = { "cc" }, cc = true, cc_priority = 2, cc_damage_mult = 1.0 }),
  s("slow", 3, true, "refresh",
    { { kind = "mod", target = "enemy", stat = "move_speed", op = "mul", value = { flat = 0.6 } } },
    "скорость x0.6", { tags = { "cc" }, cc = true, cc_priority = 0, cc_damage_mult = 1.0 }),
  s("weaken", 5, true, "stack", per_type("damage_", 0), "решение владельца: -10% исходящего урона за стак, cap 3",
    { tags = { "debuff" }, stack = { max = 3, add = -10 } }),
  s("vulnerable", 4, true, "stack",
    { { kind = "mod", target = "enemy", stat = "damage_taken", op = "add", value = { flat = 0 } } },
    "решение владельца: +10% входящего урона за стак, cap 2", { tags = { "debuff" }, stack = { max = 2, add = 10 } }),
  s("amaterasu", "required", false, "replace",
    { { kind = "zone", shape = "circle", radius = 2, tick = 1,
        ops = { { kind = "deal", target = "enemies", stat = "hp", op = "sub",
                  value = { pct = 4, of = "max_hp" }, flags = { "no_resurrection_guard" } } } } },
    "неpurgeable: горит пока носитель жив (planned zone handler)"),
  s("tsukuyomi", "required", false, "replace",
    { { kind = "hypnosis", when = "true" } },
    "genjutsu-статус: восприятие времени жертвы переписывает State-слой (planned)"),
  s("infinity", "optional", false, "refresh",
    { { kind = "rule_override", rules = { "block_physics" }, scope = "self" } },
    "Gojo: входящий урон делится на бесконечность (planned rules-хэндлер)"),
}
