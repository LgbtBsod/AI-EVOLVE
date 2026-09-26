# Holdout corpus: how well the effect system generalises

`tests/fixtures/ability_corpus_holdout.json` (ids 101-160): 60 abilities tagged BLIND, from the design spec's kind catalog only, before
any implementation file was read. `hand_canon` is null (no author bias). 13 are non-combat (crafting, trading, banking, healing,
terrain, scouting, diplomacy, persuasion, dream/info). Run: `qa.py coverage --corpus holdout --list`; check `coverage_holdout`
(warn under `coverage.holdout_target` = 80, FAIL under the ratchet `coverage.holdout_floor`).

## Measured (same resolver as the main corpus)

| corpus | canon only | with aliases + `+feature` | spec has no `lacks` |
|---|---|---|---|
| main (hand-tagged) | 35.0% | 96.7% | 80.0% |
| holdout (blind) | 5.0% (3/60) | **15.0% (9/60)** | 25.0% (15/60) |

All spec kinds of 15/60 (25%) exist as canon ops when `lacks` is ignored; `lacks` (things the spec cannot say) blocks the rest. So the
96.7% was optimistic: on unseen abilities the honest number is about 15%, gap ~80 points.

## Top blocking kinds (frequency, abilities)

1. create_ex_nihilo 3: Equivalent exchange, Dream architecture fold, Forge a weapon
2. reputation 3: Zero's speech, Paragon persuasion, Bulk trading contract
3. mass_resurrect 2: Resurrect, Garden of Avalon
4. diplomacy 2: Paragon persuasion, Broker a ceasefire
5. contract 2: Bulk trading contract, Loan with interest
6. fuel_consume 1: Pewter burn
7. time_erase 1: Balefire
8. status_mod 1: Healing weave
9. copy_last_cast 1: Priori Incantatem
10. see_panels 1: Code sight
11. read 1: Dream extraction
12. change_tier 1: Age of Stars
13. debuff 1: Doom
14. unbounded 1: Avatar State
15. learn_technique / steal 1 each: Skill Hunter book

Beyond these ~17 kinds the tail is 40+ distinct `+lacks` (each 1 ability): the model has no field for them.

## Model-breakers (the spec itself cannot say them)

- Economy: Bulk trading (price discovery, stock exchange), Loan (compound interest, debt tracking): no market/inventory/price layer.
- Crafting and terrain: recipe quality, walkable terrain creation, persistent map knowledge: no world-edit or knowledge store.
- Resource-burn systems: Allomancy metal reserves, Pewter crash debt, Warp perils: `fuel_consume` exists but no reserve/debt model.
- Gating: full-moon only, near-death trigger, eye-contact, ancestry, terrain-gated heal: no generic precondition on an op.
- Area and reaction: sphere target (Fireball), interrupt a cast (Counterspell), extraplanar return (Banishment).
- Player-facing/meta: co-op summon sign, persistent minion roster (Shadow Extraction), emotion control.

## Recommended slice order

1. Trivial wins: op aliases/handlers for kinds the spec already names (create_ex_nihilo, reputation, diplomacy, contract, mass_resurrect,
   fuel_consume, status_mod, debuff, unbounded, steal/learn_technique, copy_last_cast, read, see_panels, change_tier, time_erase).
2. Generic `requires`/gate condition on any op (fixes ~8 `+lacks`: moon, near-death, terrain, eye contact, ancestry).
3. Target shapes: sphere/cone area and reaction/interrupt timing (Fireball, Counterspell).
4. Resource pools with reserve/debt (Allomancy, warp perils, granted dice, lifesteal counters).
5. Economy family: market, inventory, loan/interest, crafting recipes with quality.
6. World/knowledge store: terrain edits, persistent maps, roster of extracted minions.
Re-measure after each slice; raise `coverage.holdout_floor` (never lower). Never tag new holdout rows after reading the implementation.

**G1a (2026-09-27)**: 11 spec kinds implemented as bounded opt-in handlers (`src/effects/exchange.py`, data in `effect_rules.lua` `exchange`, rows `lua_content/corpus_holdout_abilities.lua`, proof `tests/test_effect_exchange_spec.py`): holdout 15.0% -> 23.3% (14/60), main 96.7% -> 98.3%. Unblocked outright: #134 Dream fold, #143 Doom, #160 Garden of Avalon; #101 (`+exchange.equal_mass`, recipe cost) and #119 (`+read.wand_history`) get their features. The rest of the 13 rows still carry a `lacks` (e.g. #114 retroactive window by power, #116 cost to resistance, #135 delayed single target, #146 near-death trigger, #159 ordered conditions). Left: `see_panels` (meta). Floor `coverage.holdout_floor` = 23.
