-- lua_content/corpus_abilities.lua
-- Executable specs of the corpus abilities (tests/fixtures/ability_corpus.json) that the FORM and MOVEMENT families unblocked.
-- NOT wired into live gameplay: no enemy/hero uses these rows; tests/test_effect_forms_movement_spec.py runs each on EffectManager.
-- corpus = id in the corpus; trigger = "cast" (the caster uses it); numbers are small and plausible, not balanced.
-- Kinds: dash / teleport / pull / push / swap = `move` with an implied mode (kind_aliases.lua); stance / transform / timed_power_up
-- = forms (docs/EFFECT_SCHEMA.md "Forms"); consume = drain; status = apply_effect.
local function hit(v) return { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { flat = v } } end

return {
  abilities = {
    { id = "corpus_rasengan", corpus = 8, tags = { "spell" }, trigger = "cast", range = 12, cooldown = 4, needs_target = true,
      ops = { { kind = "dash", target = "self", distance = 6 }, hit(25) } },

    { id = "corpus_kurama_mode", corpus = 9, tags = { "spell", "form" }, trigger = "cast", cooldown = 60,
      ops = {
        { kind = "transform", target = "self", id = "kurama", duration = { flat = 30 },
          stats = { { kind = "mod", target = "self", stat = "defense", op = "add", value = { flat = 10 } },
                    { kind = "mod", target = "self", stat = "move_speed", op = "mul", value = { flat = 1.3 } } },
          abilities = { add = { "kurama_bomb" }, remove = { "weapon_attack" } } },
        { kind = "timed_power_up", target = "self", id = "kurama_chakra", duration = { flat = 30 },
          on_exit = { { kind = "drain", target = "self", stat = "hp", op = "sub", value = { flat = 5 } } } },
      } },

    { id = "corpus_gear5", corpus = 17, tags = { "spell", "form" }, trigger = "cast", cooldown = 90,
      ops = {
        { kind = "stance", target = "self", id = "gear_fifth", exclusive_group = "gear", duration = { flat = 20 },
          conflict_with = { "gear_second" },
          on_enter = { { kind = "heal", target = "self", stat = "hp", value = { flat = 10 } } } },
        { kind = "transform", target = "self", id = "sun_god", duration = { flat = 20 },
          stats = { { kind = "mod", target = "self", stat = "defense", op = "mul", value = { flat = 1.5 } } } },
        { kind = "timed_power_up", target = "self", id = "gear5_rush", duration = { flat = 20 },
          on_exit = { { kind = "drain", target = "self", stat = "stamina", op = "sub", value = { flat = 30 } } } },
      } },

    { id = "corpus_gear_second", tags = { "spell", "form" }, trigger = "cast", cooldown = 10,   -- the rival of gear5 (conflict_with)
      ops = { { kind = "stance", target = "self", id = "gear_second", exclusive_group = "gear2", duration = { flat = 10 },
                conflict_with = { "gear_fifth" } } } },

    { id = "corpus_bungee_gum", corpus = 23, tags = { "spell" }, trigger = "cast", range = 15, cooldown = 6, needs_target = true,
      ops = { { kind = "pull", target = "enemy", distance = 5 },
              { kind = "mark", target = "enemy", mark_id = "gum", value = { flat = 1 }, duration = { flat = 8 } },
              { kind = "status", target = "enemy", buff_id = "corpus_sticky" } } },
    { id = "corpus_sticky", tags = { "debuff" }, ops = { { kind = "deal", target = "self", stat = "stamina", op = "sub", value = { flat = 5 } } } },

    { id = "corpus_guanyin_zero", corpus = 24, tags = { "spell" }, trigger = "cast", range = 10, cooldown = 8, needs_target = true,
      ops = { { kind = "dash", target = "self", distance = 8 }, hit(40),
              { kind = "summon", target = "self", summon = "guanyin_echo", count = 1 } } },

    { id = "corpus_instant_transmission", corpus = 27, tags = { "spell" }, trigger = "cast", range = 30, cooldown = 10, needs_target = true,
      ops = { { kind = "mark", target = "enemy", mark_id = "shunshin", value = { flat = 1 }, duration = { flat = 10 } },
              { kind = "teleport", target = "self" } } },
    { id = "corpus_blink_to", tags = { "spell" }, trigger = "cast",                            -- teleport to a fixed point
      ops = { { kind = "teleport", target = "self", to = { 20, 5 } } } },
    { id = "corpus_shambles", tags = { "spell" }, trigger = "cast", range = 20, needs_target = true,   -- swap with the target
      ops = { { kind = "swap", target = "self" } } },
    { id = "corpus_gust", tags = { "spell" }, trigger = "cast", range = 20, needs_target = true,       -- push the target away
      ops = { { kind = "push", target = "enemy", distance = 4 } } },

    { id = "corpus_super_saiyan", corpus = 28, tags = { "spell", "form" }, trigger = "cast", cooldown = 45,
      ops = { { kind = "transform", target = "self", id = "super_saiyan", duration = { flat = 40 },
                stats = { { kind = "mod", target = "self", stat = "defense", op = "mul", value = { flat = 1.5 } },
                          { kind = "mod", target = "self", stat = "move_speed", op = "add", value = { flat = 2 } } } } } },

    { id = "corpus_repulsor", corpus = 36, tags = { "spell" }, trigger = "cast", range = 14, cooldown = 3, needs_target = true,
      ops = { { kind = "consume", target = "self", stat = "mana", value = { flat = 20 } }, hit(18),
              { kind = "dash", target = "self", distance = 3 } } },
  },
}
