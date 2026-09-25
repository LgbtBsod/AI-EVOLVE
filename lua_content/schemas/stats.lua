-- lua_content/schemas/stats.lua — схема записей namespace stats (B.5).
-- Данные фактических статов — effect_rules.lua (defaults/bounds/families/attributes).
return {
  namespace = "stats",
  required  = { "scope", "type" },
  fields = {
    scope    = "'self' | 'target' | 'world' — где живёт",
    type     = "'number' | 'bool' | 'string'",
    min      = "nil | число (границы режут ИТОГОВЫЙ стат, не бонус — EFFECT_SCHEMA п.11)",
    max      = "nil | число",
    default  = "значение нового юнита",
    visible  = "bool — показывать в UI/HUD",
    computed = "bool | nil — производный (hp_missing_below_40)",
    tags     = "{string} (derived, berserk...)",
  },
}
