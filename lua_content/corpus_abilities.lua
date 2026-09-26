-- lua_content/corpus_abilities.lua
-- Executable specs of the corpus abilities (tests/fixtures/ability_corpus.json) that the FORM and MOVEMENT families unblocked.
-- NOT wired into live gameplay: no enemy/hero uses these rows; tests/test_effect_forms_movement_spec.py runs each on EffectManager.
-- corpus = id in the corpus; trigger = "cast" (the caster uses it); numbers are small and plausible, not balanced.
-- Slice F2 rows carry family = "control" (hypnosis / command / possess / dominance / tame / temptation: src/effects/control.py, docs/EFFECT_SCHEMA.md "Control").
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

    -- ---- slice F2: CONTROL family (family = "control") ----
    { id = "corpus_tsukuyomi", corpus = 11, family = "control", tags = { "spell" }, trigger = "cast", range = 15, cooldown = 30, needs_target = true,
      ops = { { kind = "hypnosis", target = "enemy", id = "tsukuyomi", duration = { flat = 6 }, target_ref = "caster", perception = "dream" } } },
    { id = "corpus_infinite_tsukuyomi", corpus = 13, family = "control", tags = { "spell" }, trigger = "cast", range = 15, cooldown = 90, needs_target = true,
      ops = { { kind = "hypnosis", target = "enemy", id = "infinite_tsukuyomi", duration = { flat = 12 }, perception = "dream" } } },
    { id = "corpus_kyoka_suigetsu", corpus = 15, family = "control", tags = { "spell" }, trigger = "cast", range = 15, cooldown = 20, needs_target = true,
      ops = { { kind = "hypnosis", target = "enemy", id = "kyoka_suigetsu", duration = { flat = 8 }, perception = "false" } } },
    { id = "corpus_parasite_strings", corpus = 20, family = "control", tags = { "spell" }, trigger = "cast", range = 20, cooldown = 15, needs_target = true,
      ops = { { kind = "possess", target = "enemy", id = "parasite", duration = { flat = 10 },
                requires = { stat = "max_hp", cmp = "lt", vs = "source" },
                on_exit = { { kind = "deal", target = "self", stat = "hp", op = "sub", value = { flat = 5 } } } } } },
    { id = "corpus_one_ring", corpus = 49, family = "control", tags = { "spell" }, trigger = "cast", range = 20, cooldown = 60, needs_target = true,
      ops = { { kind = "dominance", target = "enemy", id = "one_ring", duration = { flat = 20 }, requires = { stat = "max_hp", cmp = "lt", vs = "source" } } } },
    { id = "corpus_the_voice", corpus = 51, family = "control", tags = { "spell" }, trigger = "cast", range = 10, cooldown = 12, needs_target = true,
      ops = { { kind = "command", target = "enemy", id = "voice", duration = { flat = 4 }, action = "stand_still" } } },
    { id = "corpus_axii", corpus = 58, family = "control", tags = { "spell" }, trigger = "cast", range = 8, cooldown = 10, needs_target = true,
      ops = { { kind = "command", target = "enemy", id = "axii", duration = { flat = 8 }, action = "ally" },
              { kind = "set_faction", target = "enemy", faction = "hero" } } },
    { id = "corpus_bloodbending", corpus = 60, family = "control", tags = { "spell" }, trigger = "cast", range = 12, cooldown = 25, needs_target = true,
      ops = { { kind = "possess", target = "enemy", id = "bloodbend", duration = { flat = 5 }, action = "puppet" } } },
    { id = "corpus_tame_beast", family = "control", tags = { "spell" }, trigger = "cast", range = 8, needs_target = true,   -- permanent, seeded roll
      ops = { { kind = "tame", target = "enemy", chance = 50 } } },
    { id = "corpus_temptation", family = "control", tags = { "spell" }, trigger = "cast", range = 8, needs_target = true,
      ops = { { kind = "temptation", target = "enemy", duration = { flat = 6 }, action = "follow", requires = { stat = "max_hp", cmp = "lt", vs = 1000 } } } },

    -- ---- slice F3: PERCEPTION family (family = "perception"; src/effects/perception.py, docs/EFFECT_SCHEMA.md "Perception") ----
    { id = "corpus_spider_sense", corpus = 39, family = "perception", tags = { "spell" }, trigger = "cast", cooldown = 30,
      ops = { { kind = "precognition", target = "self", id = "spider_sense", duration = { flat = 20 }, cooldown = { flat = 4 } },
              { kind = "reveal", target = "area", radius = 10, center = "self", affects = "enemies", duration = { flat = 20 } } } },
    { id = "corpus_prescience", corpus = 50, family = "perception", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 30, needs_target = true,
      ops = { { kind = "perceive", target = "enemy", duration = { flat = 15 }, what = { "hp", "statuses", "intent" } },
              { kind = "precognition", target = "self", id = "prescience", duration = { flat = 15 }, cooldown = { flat = 5 }, negate = false } } },
    { id = "corpus_shinigami_eyes", corpus = 55, family = "perception", tags = { "spell" }, trigger = "cast", range = 40, cooldown = 10, needs_target = true,
      ops = { { kind = "perceive", target = "enemy", duration = { flat = 30 } },
              { kind = "reveal", target = "enemy", duration = { flat = 30 }, to = "caster" } } },
    { id = "corpus_sharingan_watch", family = "perception", tags = { "spell" }, trigger = "cast", range = 25, needs_target = true,   -- perceive part of #10 (copy_technique is not unblocked)
      ops = { { kind = "perceive", target = "enemy", duration = { flat = 10 }, what = { "stats", "intent" }, stat_names = { "attack", "defense" } } } },
    { id = "corpus_gae_bolg_foresight", family = "perception", tags = { "spell" }, trigger = "cast", cooldown = 20,   -- precognition part of #34 only (reverse_causality stays a model-breaker)
      ops = { { kind = "precognition", target = "self", id = "gae_bolg", duration = { flat = 10 }, cooldown = { flat = 10 }, chance = 60 } } },
    { id = "corpus_far_sight", family = "perception", tags = { "spell" }, trigger = "cast",   -- grant_vision = mod vision_range
      ops = { { kind = "grant_vision", target = "self", value = { flat = 15 }, duration = { flat = 10 } } } },
    { id = "corpus_evade", family = "perception", tags = { "spell" }, trigger = "cast",       -- dodge = precognition without a warning
      ops = { { kind = "dodge", target = "self", duration = { flat = 10 }, cooldown = { flat = 3 } } } },
  },
}
