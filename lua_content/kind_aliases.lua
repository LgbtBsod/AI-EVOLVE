-- lua_content/kind_aliases.lua
-- spec kind names (docs/EFFECT_SYSTEM_DESIGN.md) -> canon op kinds of OP_HANDLERS; read by canonical_kind() and `qa.py coverage`
-- exact = true : pure rename, the canon handler does the same thing (content may use either name; traces are identical).
-- exact = false: a variant the canon kind cannot say by name alone (needs an extra field or is weaker); listed for `qa.py coverage`, NOT resolved, NOT counted.
return {
  aliases = {
    status          = { canon = "apply_effect",         exact = true,  note = "op_apply_effect: run the effect with id buff_id" },
    consume         = { canon = "drain",                exact = true,  note = "op_drain: pay a resource, fail branch on shortage" },
    restore         = { canon = "heal",                 exact = true,  note = "op_heal: add to a resource" },
    remove_effect   = { canon = "remove_buff",          exact = true,  note = "op_remove_buff: drop the buff by buff_id" },
    oath_binding    = { canon = "binding_vow",          exact = true,  note = "op_binding_vow: cost + gain ops" },
    use_learned     = { canon = "use_learned_technique", exact = true, note = "op_use_learned_technique" },
    create_minion   = { canon = "summon",               exact = true,  note = "op_summon: summon + count" },
    nullify_technique = { canon = "nullify",            exact = true,  note = "op_nullify: what=abilities" },
    dash     = { canon = "move", exact = false, note = "move mode=charge: the alias cannot inject the mode" },
    teleport = { canon = "move", exact = false, note = "move mode=blink" },
    pull     = { canon = "move", exact = false, note = "move mode=pull" },
    push     = { canon = "move", exact = false, note = "move mode=knockback" },
    swap     = { canon = "move", exact = false, note = "no swap mode in MOVE_MODES" },
    debuff   = { canon = "buff", exact = false, note = "buff carries mods via a buff record; semantics differ" },
    erase    = { canon = "kill", exact = false, note = "kill is weaker: no removal from the world / memory" },
    copy_technique = { canon = "learn", exact = false, note = "learn needs observed_technique from perception" },
  },
}
