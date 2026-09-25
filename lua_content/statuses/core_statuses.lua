-- lua_content/statuses/core_statuses.lua — базовые статусы реестра reg['statuses']
-- (схема schemas/statuses.lua: required duration/purgeable/stacking). Ядро навешивает
-- их op status/planned-механиками; контент ссылается по id.
local function s(id, duration, purgeable, stacking, ops, note)
  return { id = id, layer = "effect", duration = duration, purgeable = purgeable,
           stacking = stacking, ops = ops, note = note }
end
return {
  s("stun", "required", true, "replace",
    { { kind = "nullify", filter = "actions" } },
    "прерывает действия; breakable_by={damage}"),
  s("burn", "required", true, "stack",
    { { kind = "deal", target = "self", stat = "hp", op = "sub", value = { flat = 5 },
        every = 1, flags = { "no_crit" } } },
    "DoT: deal+every тикает раз в N сек (EFFECT_SCHEMA п.6)"),
  s("poison", "required", true, "refresh",
    { { kind = "deal", target = "self", stat = "hp", op = "sub", value = { flat = 3 }, every = 1 } }),
  s("freeze", "required", true, "replace",
    { { kind = "immune", damage_type = "physical" } },
    "стан + физический урон x shatter_from (planned detonate)"),
  s("silence", "required", true, "replace",
    { { kind = "nullify", filter = "abilities" } }),
  s("blind", "required", true, "refresh",
    { { kind = "mod", target = "self", stat = "vision_range", op = "mul", value = { pct = 0 },
        duration = { flat = 5 } } },
    "через mod vision_range (реализовано сейчас)"),
  s("root", "required", true, "refresh",
    { { kind = "mod", target = "self", stat = "move_speed", op = "set", value = { flat = 0 },
        duration = { flat = 3 } } }),
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
