-- lua_content/schemas/effects.lua — namespace effects: валидация Effect-дефиниций.
-- Жёсткую проверку делает tools/effect_schema/validate.py (этот файл — декларация правил).
return {
  namespace = "effects",
  required  = { "id", "trigger", "ops" },
  optional  = { "tags", "layer", "duration", "cooldown", "stacks", "exclusive_group",
                "priority", "amplify", "threshold", "on_enter", "on_exit" },
  rules = {
    "layer обязан быть в registry.lua layers",
    "каждый op.kind обязан быть в kinds/*.lua (unknown handler -> warning, op пропускается)",
    "все функции запрещены (lib/export.lua их теряет): условия — pred-строки или имена predicates",
    "when обязан быть булевым выражением (валидатор проверяет сравнение/and/or)",
    "apply_effect/owner_has ведут на эффекты этого же предмета, циклов apply_effect нет (п.13)",
    "ссылки на статы — только reg['stats']; деление на литерал 0 — ошибка (п.17)",
  },
}
