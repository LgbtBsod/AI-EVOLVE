-- lua_content/kinds/social.lua — Social Layer (ЧАСТЬ 3.7). Вне боя; события contract/*
-- пишутся в Timeline (by_entity их читает), репутация — регистр связей мира.
local function k(id, fields, note)
  return { id = id, layer = "social", handler = "planned", fields = fields, note = note }
end
return {
  k("contract", { "parties", "terms", "penalty" }, "контракт (Макима: условия исполняются миром)"),
  k("contract_manipulation", { "find", "patch" }, "манипуляция контрактами (Константин: мелкий шрифт)"),
  k("temptation", { "target", "offer", "escalation" }, "соблазнение (Кольцо: растущая цена отказа)"),
  k("dominance", { "target", "level" }, "доминирование воли (Макима Control)"),
  k("narrative_warfare", { "story", "reach" }, "нарративная война (Transmetropolitan: статья меняет город)"),
  k("reputation", { "faction", "delta" }, "репутация у фракции"),
  k("diplomacy", { "with", "stance" }, "дипломатия: relations[faction] += delta"),
}
