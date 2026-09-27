-- lua_content/statuses/combos.lua — combo reactions (docs/CC_PORT_SPEC.md 2.2, rows 12-16).
-- Read by src/effects/statuses.py (load_combos / find_pair_reaction / find_same_reaction), fired from
-- EffectManager.apply_status (S3: _combo_react) when a status is applied. Existing ops only (deal/purge/
-- detonate), no new op kind.
--   a, b, purge, damage[, radius]  — pair reaction: fires when `a` is applied while `b` is active on the
--     target (or vice versa); always purges the `purge` id and deals `damage` true damage to the target.
--     `radius` (explosion only, legacy had none: owner Q5) turns the hit into an "enemies" area burst.
--   same, damage                  — same-type reaction (owner decision Q5: KEEP; not blocked by the legacy
--     A!=B rule): fires when `same` stacks to its own cap (core_statuses.lua `stack.max`); detonates the
--     stacks (ops.py op_detonate) for a flat `damage` regardless of the stack count.
return {
  { id = "melt", a = "freeze", b = "burn", purge = "freeze", damage = 50 },
  { id = "superconduct", a = "freeze", b = "shock", purge = "freeze", damage = 80 },
  { id = "explosion", a = "burn", b = "poison", purge = "poison", damage = 60, radius = 4 },
  { id = "hemorrhage", same = "bleed", damage = 30 },
  { id = "overload", same = "shock", damage = 20 },
}
