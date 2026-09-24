-- lua_content/damage.lua
-- Damage pipeline data: damage types and the tunable constants of ONE hit resolution
-- (docs/DAMAGE_PIPELINE.md). The formulas live in the Rust kernel rust_core/src/combat/
-- and its Python twin src/effects/damage.py; this file only says WHICH numbers they use.
-- Stats (resist_<type>, accuracy, evasion, penetration_*, block_*, ...) are registered in
-- lua_content/effect_rules.lua (bounds!), not here.
--
-- Every value below is neutral: with no resist / penetration / block / accuracy content
-- a hit is exactly `max(1, damage * crit - defense)` as before the pipeline existed.

return {
  -- Damage types. `id` is what an ability/effect tag names ("fire" in tags = fire damage;
  -- no type tag = default_type). For every type the stat registry (effect_rules.lua ->
  -- families) gets resist_<id> (target: % of that damage ignored) and damage_<id> (attacker:
  -- % bonus to that damage). `resist` / `mod` here are the DEFAULTS of those two stats
  -- (a baseline every unit starts with; 0 = nothing).
  default_type = "physical",
  types = {
    { id = "physical",  resist = 0, mod = 0 },
    { id = "fire",      resist = 0, mod = 0 },
    { id = "ice",       resist = 0, mod = 0 },
    { id = "lightning", resist = 0, mod = 0 },
    { id = "poison",    resist = 0, mod = 0 },
    { id = "holy",      resist = 0, mod = 0 },
    { id = "dark",      resist = 0, mod = 0 },
  },

  constants = {
    -- accuracy vs evasion: chance to hit = clamp(base + accuracy - evasion, min, max) percent.
    -- 100 means "cannot miss" (no accuracy roll is drawn).
    hit = { base = 100, min = 5, max = 100 },

    -- armor curve. "subtractive": damage - armor (never below min_damage), today's rule.
    -- "percent": damage * k / (k + armor).
    armor = { curve = "subtractive", k = 100 },

    -- resistance per damage type, percent. The effective value (after resist penetration)
    -- is clamped to [min, max]; a raw resist >= immune_at is immunity: damage 0, no min damage.
    resist = { min = -100, max = 90, immune_at = 100 },

    -- block: when the block roll succeeds the damage is cut by `reduction` percent
    -- (+ the target's block_reduction stat), 0..100.
    block = { reduction = 50 },

    -- multiplier of a target with the "broken" buff flag (final modifier, with damage_taken)
    broken = 1.15,

    -- floor of a hit that got through (true damage and immunity are not floored)
    min_damage = 1.0,

    -- +-spread of every avoidable hit: damage * (1 + variance * (2 * roll - 1)). 0 = off,
    -- and then no variance roll is drawn.
    variance = 0.0,

    -- critical multiplier of a unit that has none (the entity field critical_damage is falsy)
    crit = { default_mult = 1.5 },
  },
}
