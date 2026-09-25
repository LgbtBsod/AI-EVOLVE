-- lua_content/kinds/all.lua — сводная карта kind'ов для редактора/валидации loader'а.
-- Ядро склеивает kinds/*.lua в reg['kinds'] (RegistrySet.create_domain("kinds"));
-- дубли kind id — DuplicateEntryError (duplicate_policy="error").
return {
  sources = { effect_core = "effect", rules = "rules", state = "state", world = "world",
              temporal = "temporal", meta = "meta", ontological = "ontological",
              social = "social", entity = "entity" },
  -- kinds, уже реализованные ядром (OP_HANDLERS, src/effects/ops.py):
  implemented = { "deal", "drain", "heal", "set", "mod", "buff", "extend", "remove_buff",
                  "apply_effect", "kill", "summon", "move" },
  -- остальное handler="planned"/"platform": рантайм пишет warning и пропускает op.
}
