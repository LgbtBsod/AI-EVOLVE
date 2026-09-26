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

    -- slice G1b (src/effects/social.py, tests/test_effect_social_spec.py): reputation / diplomacy / contract / pools. family = "social".
    { id = "hold_zero_speech", corpus = 108, family = "social", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 20, needs_target = true,
      ops = { { kind = "reputation", target = "enemy", faction = "citizens", delta = 60,
                on_tier = { revered = { { kind = "set_faction", target = "enemy", faction = "hero" } } } } } },

    { id = "hold_paragon_persuasion", corpus = 145, family = "social", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 20, needs_target = true,
      ops = { { kind = "reputation", target = "enemy", delta = 30,
                on_tier = { friendly = { { kind = "diplomacy", target = "enemy", relation = "ceasefire", duration = { flat = 20 } } } } } } },

    { id = "hold_pewter_burn", corpus = 110, family = "social", tags = { "spell" }, trigger = "cast", cooldown = 30,
      ops = { { kind = "fuel_consume", target = "self", pool = "pewter", rate = 10, duration = { flat = 8 },
                ["then"] = { { kind = "mod", target = "self", stat = "attack_damage", op = "add", value = { flat = 10 }, duration = { flat = 8 } } } } } },

    { id = "hold_bardic_inspiration", corpus = 127, family = "social", tags = { "spell" }, trigger = "cast", cooldown = 10,
      ops = { { kind = "pool", target = "self", pool = "inspiration", action = "grant", amount = 2 } } },

    { id = "hold_waterfowl_dance", corpus = 140, family = "social", tags = { "attack" }, trigger = "cast", range = 30, cooldown = 15, needs_target = true,
      ops = { { kind = "pool", target = "self", pool = "lifesteal_hits", action = "grant", amount = 4 },
              { kind = "pool", target = "enemy", pool = "lifesteal_hits", action = "use", count = 4,
                ["then"] = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { flat = 4 } },
                             { kind = "heal", target = "self", stat = "hp", value = { flat = 2 } } } } } },

    { id = "hold_smite", corpus = 142, family = "social", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 6, needs_target = true,
      ops = { { kind = "fuel_consume", target = "enemy", pool = "warp", amount = 15,
                ["then"] = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { flat = 30 } } } } } },

    { id = "hold_broker_ceasefire", corpus = 154, family = "social", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 30, needs_target = true,
      ops = { { kind = "diplomacy", target = "enemy", relation = "ceasefire", duration = { flat = 30 } } } },

    { id = "hold_loan_interest", corpus = 155, family = "social", tags = { "spell" }, trigger = "cast", range = 30, cooldown = 30, needs_target = true,
      ops = { { kind = "contract", target = "enemy", id = "loan", principal = 100, duration = { flat = 20 }, interest = { rate = 0.1, every = 5 },
                b_ops = { { kind = "heal", target = "enemy", stat = "mana", value = { flat = 100 } } },
                breach = { penalty_ops = { { kind = "mod", target = "enemy", stat = "defense", op = "add", value = { flat = -5 }, duration = { flat = 10 } } } } } } },
  },
}
