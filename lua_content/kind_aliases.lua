-- lua_content/kind_aliases.lua
-- spec kind names (docs/EFFECT_SYSTEM_DESIGN.md) -> canon op kinds of OP_HANDLERS; read by canonical_kind() and `qa.py coverage`
-- exact = true : pure rename (optionally `params` = fields the alias implies), the canon handler does the same thing (content may use either name; traces are identical).
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
    -- movement family: the alias row carries the implied `params` (canonicalize_op fills them; the op's own fields win)
    dash     = { canon = "move", exact = true, params = { mode = "dash" },     note = "move mode=dash: self toward the target, stops 1.5 short" },
    teleport = { canon = "move", exact = true, params = { mode = "teleport" }, note = "move mode=teleport: to=[x,y] or behind the target" },
    pull     = { canon = "move", exact = true, params = { mode = "pull" },     note = "move mode=pull: target toward the source" },
    push     = { canon = "move", exact = true, params = { mode = "push" },     note = "move mode=push: target away from the source" },
    swap     = { canon = "move", exact = true, params = { mode = "swap" },     note = "move mode=swap: exchange positions with the other party" },
    -- control family (src/effects/control.py)
    blood_manipulation = { canon = "possess",   exact = true, params = { action = "puppet" }, note = "possess action=puppet: the caster drives the target's body (faction + targeting override)" },
    enter_dream        = { canon = "hypnosis",  exact = true, params = { perception = "dream" }, note = "hypnosis perception=dream: the target lives in the caster's illusion" },
    debuff   = { canon = "buff", exact = false, note = "buff carries mods via a buff record; semantics differ" },
    erase    = { canon = "kill", exact = false, note = "kill is weaker: no removal from the world / memory" },
    copy_technique = { canon = "learn", exact = false, note = "learn needs observed_technique from perception" },
  },
}
