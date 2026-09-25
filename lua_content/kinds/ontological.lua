-- lua_content/kinds/ontological.lua — Ontological/Conceptual Layer (ЧАСТЬ 3.6).
-- Выше Rules: меняет сам КЛАСС сущностей (change_tier переписывает entity.tier).
local function k(id, fields, note)
  return { id = id, layer = "ontological", handler = "planned", fields = fields, note = note }
end
return {
  k("embody_concept", { "concept" }, "воплощение концепции (Endless: Dream = сны)"),
  k("domain_control", { "domain", "absolute" }, "власть над доменом бытия (Люцифер над адом)"),
  k("change_tier", { "tier" }, "смена уровня бытия (Ascension: mortal -> higher)"),
  k("concept_erase", { "concept" }, "стереть понятие (Death of the Endless: умерщвление сна)"),
  k("concept_deny", { "concept" }, "отрицание понятия (Accelerator: 'магии не существует')"),
  k("concept_rewrite", { "old", "new" }, "перезапись концепции (rename на уровне мира)"),
  k("create_ex_nihilo", { "what" }, "создание из ничего (Почита: контракт-желание)"),
  k("soul_merge", { "souls" }, "слияние душ (Гето: curse inventory)"),
  k("narrative_control", { "scope" }, "управление нарративом (Физерин: скрипт поверх скрипта)"),
}
