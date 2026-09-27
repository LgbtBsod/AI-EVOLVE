-- lua_content/toughness.lua
-- S4 (docs/CC_PORT_SPEC.md 2.3 rows 17/19/21/22/25): the ONE toughness/break bar (owner decision 3
-- merged rows 4/18/20/24/26 into this single bar; do not resurrect them).
--
-- `enabled` is the kill switch: while false, op `toughness_damage`, the automatic per-landed-hit hook in
-- `EffectManager._damage` and the break/CC-block rule in `EffectManager.apply_status` (src/effects/manager.py)
-- are all a no-op -- traces are byte-for-byte the same as before this slice. Live as of this slice: every
-- landed hit (excluding true_damage/unavoidable/periodic DoT ticks) subtracts from the target's toughness
-- bar automatically -- flip back to false instantly if a determinism/play run looks wrong.
return {
  enabled = true,

  -- base toughness by class (data field per bestiary/boss row; a row without one gets a class default
  -- through `toughness_class(entity)`, src/effects/toughness.py). Legacy numbers, constants.py:409-415.
  base_by_class = {
    player = 100,
    npc    = 50,
    enemy  = 800,
    boss   = 2000,
    elite  = 1500,
  },

  -- element (attacker damage type, lua_content/damage.lua ids) vs toughness: multiplier applied to the
  -- `value` of `toughness_damage` before it subtracts. Every canon type starts neutral (1.0); an unknown
  -- type (not in this table) is also 1.0 -- tune per design later, this slice only wires the mechanism.
  type_factor = {
    physical  = 1.0,
    fire      = 1.0,
    ice       = 1.0,
    lightning = 1.0,
    poison    = 1.0,
    holy      = 1.0,
    dark      = 1.0,
  },

  -- break: duration (s) of the `broken` status (mod broken=1 -> damage.lua constants.broken x1.15,
  -- effect_rules.lua:36/94 already apply it; nullify actions; purges every active CC). Game-clock
  -- recovery only (EffectManager.now in `update`), never a thread (owner decision 4).
  break_duration = 5.0,

  -- toughness_max growth per break: +5% of the entity's max_hp, capped at +20% total (cumulative across
  -- repeated breaks); full refill to the (possibly grown) max when the break ends.
  break_growth_pct = 5.0,
  break_growth_cap_pct = 20.0,
}
