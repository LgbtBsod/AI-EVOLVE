-- lua_content/corpus_holdout_abilities.lua
-- Executable specs of the BLIND holdout corpus (tests/fixtures/ability_corpus_holdout.json, ids 101-160) that slice G1a unblocked.
-- NOT wired into live gameplay; tests/test_effect_exchange_spec.py runs each row on EffectManager. family = "exchange" (src/effects/exchange.py).
-- Recipes, caps and tier tracks are DATA in effect_rules.lua `exchange`; a row only names them.
return {
  abilities = {
    { id = "hold_equal_exchange", corpus = 101, family = "exchange", tags = { "spell" }, trigger = "cast", cooldown = 5,
      ops = { { kind = "create_ex_nihilo", target = "self", recipe = "equal_exchange" } } },

    { id = "hold_balefire", corpus = 114, family = "exchange", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 30, needs_target = true,
      ops = { { kind = "time_erase", target = "enemy", window = 6 } } },

    { id = "hold_healing_weave", corpus = 116, family = "exchange", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 8, needs_target = true,
      ops = { { kind = "heal", target = "enemy", stat = "hp", value = { flat = 10 } },
              { kind = "status_mod", target = "enemy", status = "burn", duration_mult = 0.5, potency_mult = 0.5 } } },

    { id = "hold_priori_incantatem", corpus = 119, family = "exchange", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 10, needs_target = true,
      ops = { { kind = "read", target = "enemy" }, { kind = "copy_last_cast", target = "enemy" } } },

    { id = "hold_dream_extraction", corpus = 132, family = "exchange", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 10, needs_target = true,
      ops = { { kind = "read", target = "enemy", fields = { "name", "abilities" } } } },

    { id = "hold_dream_fold", corpus = 134, family = "exchange", tags = { "spell" }, trigger = "cast", cooldown = 5,
      ops = { { kind = "create_ex_nihilo", target = "self", recipe = "dream_fold" } } },

    { id = "hold_resurrect", corpus = 135, family = "exchange", tags = { "spell" }, trigger = "cast", cooldown = 60,
      ops = { { kind = "mass_resurrect", target = "self", radius = 10, pct = 40 } } },

    { id = "hold_age_of_stars", corpus = 141, family = "exchange", tags = { "spell" }, trigger = "cast", cooldown = 20,
      ops = { { kind = "change_tier", target = "self", track = "stars", steps = 1 } } },

    { id = "hold_doom", corpus = 143, family = "exchange", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 10, needs_target = true,
      ops = { { kind = "debuff", target = "enemy", stat = "defense", value = { flat = 6 }, duration = { flat = 10 } } } },

    { id = "hold_avatar_state", corpus = 146, family = "exchange", tags = { "spell" }, trigger = "cast", cooldown = 60,
      ops = { { kind = "unbounded", target = "self", stat = "attack_damage", mult = 9, duration = { flat = 20 } } } },

    { id = "hold_forge_weapon", corpus = 150, family = "exchange", tags = { "spell" }, trigger = "cast", cooldown = 5,
      ops = { { kind = "create_ex_nihilo", target = "self", recipe = "forge_weapon" } } },

    { id = "hold_skill_hunter", corpus = 159, family = "exchange", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 10, needs_target = true,
      ops = { { kind = "steal", target = "enemy", technique = "wand_strike", fidelity = 0.8 } } },

    { id = "hold_garden_of_avalon", corpus = 160, family = "exchange", tags = { "spell" }, trigger = "cast", cooldown = 60,
      ops = { { kind = "mass_resurrect", target = "self", radius = 30, pct = 100 } } },
  },
}
