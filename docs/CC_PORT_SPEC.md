# CC / toughness / stagger / status / combo port spec

Goal: move the unique mechanics of the legacy islands into the canon effect system (`src/effects`, Lua data), so `ai_evolve/`, nested `AI-EVOLVE/`, `game/` and the old combat stacks can be archived by tag `archive/pre-legacy-islands`.
Scope of this doc: analysis only, no code. Evidence = `file:line` read in this pass; anything not read is marked (inferred).

## 1. Canon today (what to map onto)

- 42 op kinds (`src/effects/schema.py:30-81`). Relevant: `mod`, `deal` (+`every` for DoT), `buff`, `apply_effect`, `mark`/`detonate` (`ops.py:502,541`), `purge`, `nullify` (`ops.py:590`), `immune` (`ops.py:486` accepts `status`), `resist`, `move`.
- Statuses are registry rows only: `lua_content/statuses/core_statuses.lua:9-40` (stun, burn 5/s stack, poison 3/s refresh, freeze, silence, blind, root, +3 Naruto/Gojo). Nothing in `src/` loads them (grep `core_statuses` in `src`: no hits), their ops are "planned" per the file's own notes (`:15,20,34`).
- "Broken" already exists as a stat: `effect_rules.lua:32` (`broken` 0/1, set by a `mod` with duration), read by `manager.py:1074` (`theirs("broken") > 0`), applied as x1.15 in `damage.py:175-176`, constant `damage.lua:46`, twin `damage.py:303`. Nothing sets it in live content (grep `lua_content`: only rules/damage lines).
- Dead events: `on_shield_break`, `combat_start/end` (`schema.py:113-117`, APP_SPECIFICS 3.1). Default debuff length `DEFAULT_DEBUFF_SECONDS=5.0` (`manager.py:74`).
- No per-entity toughness/stagger state, no combo table, no CC priority anywhere in `src/effects`.

## 2. Mechanics table

Columns: legacy | numbers | canon? | proposed canon form | test | risk. Risk "neutral" = no same-seed trace change until content uses it.

### 2.1 Damage-over-time and control statuses (`ai_evolve/features/effects/effects_plugin.py:80-150`)

| # | Mechanic | Legacy numbers | Canon? | Proposed | Test | Risk |
|---|---|---|---|---|---|---|
| 1 | bleed | dur 8, tick 5 + 2/stack, max 5 stacks, per-second, no crit (`:81-89`) | no (burn is 5/s flat, `core_statuses.lua:12-15`) | new status row `bleed`: `deal every=1 value={flat=5}` + `mark bleed max_stacks=5`, per-stack via scale `mark_bleed` | spec: 3 applications -> tick = 5+2*3 per second for 8 s | neutral |
| 2 | burn | dur 6, 8 + 3/stack, max 3 (`:90-98`) | partial: `core_statuses.lua:12` flat 5, stacking "stack", no duration | retune row to 6 s / 8 / +3 per stack / cap 3 (owner Q1) | spec: tick sums, expiry at 6 s | neutral |
| 3 | freeze | dur 2, on-apply, no dmg, 1 stack (`:99-105`) | partial: `:18-20` immune physical (wrong: legacy = stun) | `nullify actions` + `mod move_speed set 0`, 2 s; physical-hit shatter via row 12 | spec: no actions for 2 s, expires | neutral |
| 4 | frozen | dur 3, on-apply (`:122-128`) | no (duplicate of freeze in legacy) | drop, keep one `freeze` (Q3) | none | neutral |
| 5 | shock | dur 4, 3 + 1.5/stack, max 4 (`:106-113`) | no | status `shock`, same shape as bleed | spec like #1 | neutral |
| 6 | poison | dur 10, 4 + 1.5/stack, max 6 (`:114-121`) | partial: `:16-17` flat 3, "refresh" | retune to stack rule; 10 s | spec | neutral |
| 7 | stun | dur 1.5, 1 stack (`:129-135`) | partial: `:9-11` `nullify actions`, duration "required" | keep row, add `buff` duration 1.5 in the applying ability | spec: actions nullified 1.5 s | neutral |
| 8 | weaken | dur 5, max 3 stacks, "reduces damage", no number (`:136-142`) | no; `damage_dealt` stat exists (`damage.py`, kernel `mine("damage_"+kind)`) | status `weaken`: `mod damage_<kind> mul` per stack (value not in legacy: Q2) | spec: 2 stacks lower outgoing damage | neutral |
| 9 | vulnerable | dur 4, max 2, "more incoming damage", no number (`:143-149`) | partial: `theirs("damage_taken")` (`manager.py:1079`) | status `vulnerable`: `mod damage_taken add` per stack (Q2) | spec | neutral |
| 10 | stacking rule | re-apply: stacks += n capped, timer reset to base (`:258-265`) | partial: registry `stacking` field only (`core_statuses.lua:4-7`); `mark` has max_stacks | implement `stack` = `mark` + `refresh` via `buff` (no new op) | spec: cap and timer refresh | neutral |
| 11 | resist / immunity | `resistances[type]` chance roll, >=1 immune (`:223-237`) | partial: `immune status` (`ops.py:486`), no chance resist | `immune` for 100%; chance-resist = drop or `mod status_resist_<id>` (Q4) | spec | neutral |

### 2.2 Combo reactions (`effects_plugin.py:153-162`, trigger `:239-254`, event `:335-347`)

Rule: applying B while A is active (A != B) consumes A and fires `(name, damage)`; reaction damage is only carried in the event, legacy never applies it (no `deal` in `_trigger_combo`).

| # | Reaction | Trigger pair | Damage | Canon? | Proposed | Test |
|---|---|---|---|---|---|---|
| 12 | melt | freeze+burn | 50 | no | Lua effect `trigger.kind="applied"` on burn, `owner_has` freeze -> `purge` freeze + `deal true_damage 50` | spec: freeze then burn = 50 true dmg, freeze removed |
| 13 | superconduct | freeze+shock | 80 | no | same shape, 80 | spec |
| 14 | explosion | burn+poison | 60 | no | same, `area` radius (legacy has none: Q5) | spec |
| 15 | hemorrhage | bleed+bleed | 30 | no; but legacy skips same type (`:244`) so it never fires | drop, or `detonate mark bleed` at max stacks (`ops.py:541`) | spec if kept |
| 16 | overload | shock+shock | 20 | no; same dead-code case | drop / `detonate` | spec if kept |

Risk for 12-16: neutral until content applies two statuses; reaction uses existing `apply_effect`/`purge`/`deal`. No new op.

### 2.3 Toughness and stagger (three legacy shapes)

| # | Mechanic | Legacy numbers | Canon? | Proposed | Test | Risk |
|---|---|---|---|---|---|---|
| 17 | Toughness bar (poise) | max 100; recover 10/s after 3 s no-hit; break 5 s; damage per hit subtracts (`src/systems/combat/components/toughness_component.py:27-34,207-208,341-346`) | no | NEW entity state `toughness/toughness_max` in `EffectManager` + op `toughness_damage {value, type}` (semantics: subtract x elemental factor, clamp 0, at 0 fire event `break`) | spec on `EffectRuntime`: N hits -> break at hit k | changes traces only if content calls it |
| 18 | Weakened band | state WEAKENED below 25% max; takes +12.5% (half of broken bonus) (`:211-213,152-153`) | no | drop or `condition` effect `toughness_pct<25` -> `mod damage_taken` | spec | neutral |
| 19 | Broken state | +25% dmg taken, 5 s, hard stun; max grows +5% maxHP per break, cap 20% maxHP; full refill on exit (`:33-35,148-156,277-298,300-326`) | partial: `broken` stat x1.15 (`damage.lua:46`, `effect_rules.lua:32`) | on break emit `mod broken=1 duration 5` (rule exists) + `nullify actions`; port break-growth as `set toughness_max` in break handler | spec: break -> x1.15 for 5 s -> refill; growth capped | uses existing stat |
| 20 | Recovering state | +5% dmg taken, 3 s delay, recovery x2 (`:154-155`; `constants.py:418-431`) | no | drop (Q3) | none | neutral |
| 21 | Element vs toughness type | matrix fire/ice/lightning/wind/quantum/imaginary/physical/universal; physical vs elements 0.5/0.3 (`src/core/constants.py:41-51,450-461`, applied `:230-246`) | no; canon has 7 damage types (`damage.lua`) | `lua_content/toughness.lua` matrix keyed by canon damage types | spec: matrix lookup, unknown -> 1.0 | neutral |
| 22 | Base toughness by class | player 100, npc 50, enemy 800, boss 2000, elite 1500 (`constants.py:409-415`); component default 100 | no; bosses in `bosses.lua` have no toughness | add `toughness` field per bestiary/boss row (data) | play scenario: boss break | neutral until read |
| 23 | Break damage / stun tables (constants) | multipliers weakened 1.5, broken 2.0, recovering 1.2; stun 0/1/3/0.5 s (`constants.py:433-447`) | contradicts #19 (1.25) and `damage.lua:46` (1.15) | pick ONE (Q1); default keep canon 1.15 | none | neutral |
| 24 | StaggerBar | max 500, regen 10/s, resist mult, break length = 0.5 + max/50*0.1 s (500 -> 1.5 s) x break_resist (`src/features/cc_system.py:50-81,96-98,201-202`) | no | second bar = same op as #17 (`stagger` = toughness with regen+time formula). Keep only one of #17/#24 (Q3) | spec: 500 -> 1.5 s | neutral |
| 25 | Break priority | in BROKEN new CC is ignored, existing CC list cleared, no CC ticking (`cc_system.py:131-137,184-185,193-198`) | no | rule in status `apply`: skip if target has `broken>0`; on break `purge debuff` | spec | neutral |
| 26 | Combat-mechanics stagger | max 1000 (5000 boss), same 0.5+max/50*0.1 break time (`src/core/combat_mechanics.py:66,134,227`); break recovery via `threading` sleep (`:238-246`) | duplicate of #24 | drop (thread timer is nondeterministic) | none | neutral |

### 2.4 CC types and CC stats (`src/features/cc_system.py`)

| # | Mechanic | Legacy numbers | Canon? | Proposed | Test |
|---|---|---|---|---|---|
| 27 | CC types + priority | STUN 5 > KNOCKDOWN 4 > MICRO_STUN 3 > ROOT 2 > DISORIENTED 1 > SLOW 0; strongest wins (`:20-27,225-236`) | partial: stun/root/silence/blind rows (`core_statuses.lua`); no knockdown/slow/disoriented | rows `slow` (`mod move_speed mul`), `knockdown` (= stun + `move`), `disoriented` = `blind` alias; priority = derived, not stored (Q4) | spec per row |
| 28 | Micro-stun | 0.2 s, interrupts the current cast (`:25,101,156-165`; flag never cleared `:206-208`) | partial: `cancel_technique` (`schema.py:51`) | `cancel_technique` + `nullify abilities 0.2 s` | spec: cast interrupted |
| 29 | CC duration resist | duration x `cc_duration_resist`, <=0 = immune (`:93,129,140`) | no | stat `cc_duration_mult` in `effect_rules.lua` applied where `buff` computes `until` (`manager.py:851`) | spec |
| 30 | Damage while CC'd | flat then percent reduction (`(d-flat)*(1-pct)`), broken x1.15 (`:244-266`) | broken yes (#19); reduction no | `condition` effect `has_cc` -> `mod damage_taken` | spec |
| 31 | cc_damage_mult (attacker bonus vs CC'd) | field only, never applied (`:87,250-251`) | no | drop or `condition` on target status (Q4) | none |
| 32 | Combat-mechanics CC stack | stack counting, `cc_damage_reduction_percent` (`combat_mechanics.py:88-91,171-172,183-208`) | duplicate | drop | none |

### 2.5 Other unique features found

| # | Feature | Legacy | Canon? | Proposal |
|---|---|---|---|---|
| 33 | Loot rarity table (mimic 10% legendary, 30% epic, 30% rare, 30% common) | `ai_evolve/plugins/loot_plugin.py:384-394`; prefixes/suffixes `:282-302` | `lua_content/loot.lua` exists (not compared, inferred partial) | diff numbers against `loot.lua` in slice 4, port only the mimic row |
| 34 | Nested `AI-EVOLVE/` dev_probe toughness/combos plugins | observers of toughness/combo events (`AI-EVOLVE/tools/dev_probe/plugins/toughness_plugin.py`, `advanced_mechanics_plugin.py`: `ComboEvent :12`) | observer only, no mechanics | archive, drop |

## 3. Slices (order by value/risk)

1. **S1 (S): statuses as data. DONE 2026-09-26** (`lua_content/statuses/core_statuses.lua`, `src/effects/statuses.py`, `EffectManager.apply_status` / `EffectRuntime.apply_status`, `tests/test_statuses_spec.py`). Deviations: stack numbers via `stack = {max, add}` (add to `value.flat` of every op, no `mark` op needed); `frozen` dropped, `disoriented` = alias of `blind`; `cc_priority` is DATA per CC row (decision Q4); `chance_resist` = carrier stat `status_resist_<id>` (>=100 immune, else one rng draw only when > 0: traces unchanged); `cc_damage_mult` is a data field only (application = S2, damage hook); micro_stun row added (`cancel_technique` + `nullify abilities`, 0.2 s); no boss-immunity (spec rows do not require it); a status applied by two sources on one target keeps separate mod layers (key includes the source); EffectRuntime does not expire timed mods on the dummy (host divergence, APP_SPECIFICS row 5), so mod expiry is specified on the manager only. Original plan: Rows 1-9, 27 in `core_statuses.lua` with real durations/ticks, plus a loader that reads them (currently unread). Test: `tests/test_statuses_spec.py` on `EffectRuntime`. Risk: neutral (rows unused by live content).
2. **S2 (M): stacking + resist. DONE 2026-09-26** (`tests/test_cc_stacking_spec.py`). Deviations: stack cap/refresh and chance-resist were already in S1; new: `cc_duration_mult` (stat, default 1.0, ADDED to by innate/mods, <= 0 = immune, only rows with `cc = true`, applied in `statuses.plan/materialize` = where apply_status builds `until`, not in the generic `buff` op), `row_duration` (blind/root carry the duration on the op), `EffectManager.active_cc(target)` + ctx keys `has_cc` / `cc_is_<id>` (target-side, manager only), damage while CC'd = Python `damage.cc_adjust` AFTER the Rust kernel (`(d - cc_damage_flat) * (1 - cc_damage_reduction/100) * row.cc_damage_mult * attacker cc_damage_mult`, no Rust change, no twin needed), defaults 0/0/1.0 = identical numbers; EffectRuntime (training room) gets duration mult/immunity only. Original: Rows 10, 11, 29 (`cc_duration_mult` stat). Test: stack cap/refresh spec. Risk: touches `buff` duration path (`manager.py:851`), run `qa.py golden`.
3. **S3 (M): combo reactions as Lua triggers.** Rows 12-16 with existing ops only. Test: 5 specs (one per reaction) + `agent_play` scenario "freeze then burn". Risk: neutral until content applies pairs; verify depth cap (`MAX_EVENT_DEPTH=6`, `manager.py:75`).
4. **S4 (L): toughness/break.** Rows 17-26, 28, 30: new state on entity, op `toughness_damage`, matrix in `lua_content/toughness.lua`, break -> `broken` mod (reuses `damage.py:175`), revive dead event `on_shield_break`. Test: executable spec + play "spawn boss; hit until break; expect broken dmg x1.15". Risk: HIGH for traces if wired into `_damage` (dice order, `manager.py:1081-1090`); wire behind a Lua flag default off, `qa.py determinism`.
5. **S5 (S): loot + cleanup.** Row 33 diff; drop 4, 15/16 (if unwanted), 20, 26, 31, 32, 34.

## 4. Archive checklist (importers found by grep of `src tests tools main.py ai_evolve/tests`)

Tag first: `git tag archive/pre-legacy-islands` (then `git rm -r`).

- `ai_evolve/` is imported by its own `ai_evolve/tests/**` only (files: unit/test_core_components, tools/test_dev_probe_framework, plugins/test_loot_plugin, test_entity_components, integration/test_plugin_integration, test_game_session, features/test_toughness_plugin, test_inventory_plugin, test_effects_plugin). Not collected (`pytest.ini:2` testpaths=tests). Safe once S1-S4 specs exist.
- Root `tests/` importing legacy (must be rewritten to the new specs or deleted): `test_effects_toughness_comprehensive.py:16,23` (`game.core.*`), `test_effects_toughness_full.py:18` and `test_toughness_effects.py:16` (`src.systems.combat.components.toughness_component`), `test_cc_break_system.py:4` (`src.features.cc_system`), `test_combat_mechanics.py:11` (`src.core.combat_mechanics`), `test_qa_tools.py:190,200` (toughness_component), `test_comprehensive.py:24-27`, `test_plugins_integration.py:12` (`src.systems.combat`).
- `src/`: `entities/character.py:30-31`, `entities/enemy.py:27`, `features/combat_plugin.py:13`, `systems/combat/{__init__,unified_combat_system,refactored_combat_system}.py`, `systems/testing/test_system.py:765-921`. `tools/combat_smoke_test.py:37` (+`:196,352`) and `tools/boot_smoke_test.py:48-50` use `CombatSystem`: rewire to `EffectManager` before removing `src/systems/combat` (item 18 of APP_SPECIFICS).
- `cas_engine`: `tests/test_cas_engine.py:11`, `tools/training_room.py:45` import `core.cas_engine` (no CC/stagger hits, `grep` count 0): out of scope here.
- `main.py:120-137` boots `CombatPlugin`/`EffectsPlugin` (APP_SPECIFICS 3.4): remove after `combat_smoke_test` rewires.
- Nested `AI-EVOLVE/` and `game/`: only self-imports (APP_SPECIFICS 3.4); nothing to rewire, `game/core/{toughness,effects}` need the same specs as `test_effects_toughness_*`.
- Also update: `docs/APP_SPECIFICS.md` rows 17/18, `tests/qa_known_failures.json`, `lua_content/qa.lua` tools rows for deleted tools; run `qa.py dead`, `qa.py hygiene`, `qa.py check --all`.

## 5. Owner decisions

1. DECIDED 2026-09-26: keep legacy numbers (bleed 5+2/stack, burn 8+3 ...). Break multiplier: one value, canon x1.15 stays (row 23).
2. DECIDED 2026-09-26: weaken -10% damage dealt per stack (cap 3), vulnerable +10% damage taken per stack (cap 2).
3. DECIDED 2026-09-26: ONE bar (toughness 100, 5 s break); frozen/recovering/weakened states dropped (rows 4, 18, 20, 24, 26 = merged into the one bar).
4. DECIDED 2026-09-26: KEEP the "dead" features: chance-resist, cc_damage_mult, the CC priority list, break recovery (deterministic: a game-clock timer, never a thread).
5. DECIDED 2026-09-26: KEEP combo reactions: real true damage 50/80/60, `area` for explosion, hemorrhage/overload kept and made reachable (the legacy same-type skip must NOT block them).

Consequences for the slices: S3 - hemorrhage/overload fire on same-type stacking (e.g. at cap via `detonate`), not blocked by an "A != B" rule; S4 - a single toughness bar, break recovery on the game clock (`EffectManager.now`); S2 - `cc_damage_mult` needs a hook in the damage path (attacker bonus vs a CC'd target) and `cc_duration_mult`.
