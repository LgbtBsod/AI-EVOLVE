# AI-EVOLVE: app specifics brief

Self-contained brief for an agent that has never seen this repo. Facts carry `path:line`; "(inferred)" marks a claim from grep/arithmetic, not from reading or running the code. Lines drift by a few after edits: re-grep the symbol. Written 2026-09-26 by 4 read-only explorers + 1 writer; all 96 path references were checked mechanically (files exist, line numbers in range), individual claims were not sampled.

## 1. What the app is

- Panda3D action game (Python 3.14). The hero is AI-driven; the player never commands him. Levers: `spawn enemy|trap|chest|boss` (keys 1-4), an emotion (calm/rage/fear/curiosity/greed/resolve) and a directive (north/south/east/west/chest/exit/npc). They only bias the hero's goal scores (`src/gameplay/hero_drive.py:24-31,118-168`; keys and weights in `lua_content/hero_mind.lua`).
- Two UCB1 bandits learn: enemies pick one of 6 tactics per body-shape context (`src/gameplay/tactics.py:25`), the hero picks retreat/press at low HP (`src/gameplay/hero_mind.py:31-147`). Memory persists in `saves/tactics_memory.json` and `saves/hero_mind.json`.
- World: 80 levels = 8 acts x 10 (`lua_content/world.lua`), a boss at each act end, periodic spawns every 3.0 s (1.5 s dev), -5% per level, floor 1.2 s (`src/scenes/main_game_scene.py:41,683-697,973-989`).
- Flow: `main.py:182-205` parses `--dev --full --skip-menu` -> `Game.__init__` (`main.py:66-153`) builds GameCore, DatabaseCore, EventSystem, StateManager, SceneManager and registers 2 plugins -> Panda task `main_game_loop` (`main.py:146,175-179`) calls `game_core.update(dt)`. The menu opens `main_menu`; `game_world` resolves to `GameScene`, a wrapper of `EnhancedGameScene` (`src/scenes/main_game_scene.py`, 1627 lines; `src/scenes/scene_manager.py:280-300,579-581`; `game_scene.py:38`). `--skip-menu` loads `game_world` at once (`main.py:142-143`).
- Split: Python orchestrates. Rust (`rust_core/`, PyO3, optional) holds kernels, each with a Python twin. Lua (`lua_content/`, read via `tools/lua_bridge.py load(path)`, sandbox, JSON string across the boundary) holds all settings and content: items, abilities, bestiary, damage constants, hero mind.
- All combat runs through `src/effects/manager.py` (EffectManager). Half of `src/` is not on the runtime path (section 2).

## 2. Map

| Area | Where | Status |
|---|---|---|
| Boot, loop, plugins | `main.py`, `src/core/game_core.py`, `base_plugin.py`, `architecture.py` (28 importers of BaseComponent) | live |
| Scenes, world, spawns | `src/scenes/*` (`main_game_scene.py`), `src/gameplay/{world,loot,progression,inventory,items}.py` | live |
| Effects/combat engine | `src/effects/{schema,ops,runtime,manager,damage,abilities}.py`; `lua_content/{items,abilities,perks,damage,effect_rules}.lua` | live |
| Damage kernel | `rust_core/src/combat/mod.rs` (448 lines) + twin `src/effects/damage.py` | live; backend on this machine unknown |
| Hero and enemy AI | `src/gameplay/{hero_drive,hero_mind,learning,tactics,enemy_ai}.py`; Rust `TacticsBandit` | live |
| Lua loader | `src/content/lua_bridge.py`, `rust_core/src/lua_content` (mlua), twin lupa | live |
| Item authoring tools | `tools/effect_schema/`, `tools/web_builder/` (`ui_logic.run_training_room`) | live (tools) |
| Pathfinding A*/JPS/flow field | `src/gameplay/pathfinding.py`, Rust `find_path`/`flow_field` | partial: tested, not wired |
| EventSystem, StateManager, RNGManager | `src/core/{event_system,state_manager,rng_manager}.py` | partial (see 3.3) |
| Legacy combat stack | `src/features/{combat_plugin,effects_plugin}.py`, `src/systems/{combat,effects}` | partial: booted by `main.py:120-137`, scene ignores it |
| `src/core/adaptation.py` (Mahoraga) | used by `src/effects/ops.py:25,363,671,692` | live |
| CAS family | `src/core/cas_engine.py`, `python_layer/l9_semantic/cas_*.py`, `src/core/effects/condition_action_system.py` | dead (tests + tools only) |
| Registry/Timeline layer | `src/core/{registry,timeline}.py`, `lua_content/{registry,kinds,timeline}` | dead (tests only) |
| Orphan core modules | `src/core/{async_game_core,combat_advanced,game_master,di_container,entity_manager,combat_mechanics}.py` | dead |
| Dead features/systems | `src/features/*` (except the 2 plugins), `src/systems/{ai,attributes,crafting,dialogue,evolution,items,memory,navigation,audio,particle,testing}`, `src/ai`, `src/ml_agents` | dead (particle_system still used by random calls, see 3.3) |
| Parallel packages | `ai_evolve/` (48 .py), `AI-EVOLVE/`, `game/`, `python_layer/` | dead; `python_layer/l8_probe,l9_semantic` used by tools |
| Rust stubs/unexposed | `SimulationEnv`, `WorldGenerator`, `TickSystem`; `storage/`, `training_room/` | dead |
| Rust tools-only | `RunAnalytics`, `QaKernels`, `ProbeAnalyzer`, `semantic_core` | partial |
| Save/DB | `src/database/db_core.py` (sqlite `saves/game_database.db`), `game_database.py` | DatabaseCore injected, `GameDatabase` dead |

## 3. Areas

### 3.1 Effects (`src/effects`, `lua_content` items/abilities/perks/damage, `rust_core/src/combat`, `tools/effect_schema`)

How it works:
- An Effect is Lua data `{id, trigger{kind = passive|condition|event|applied}, ops[]}` (`src/effects/schema.py:111,113`). Perks use the same schema.
- passive/condition effects live in a per-entity `EffectRuntime`: layered mods -> `Unit._eff` -> pushed into the entity's own fields (`manager.py:271` pull, `:305` push_stats, `:330` refresh, `STAT_MAP :55`). Event effects fire from `EffectManager.emit` (`:678`).
- One op interpreter, `ops.apply_op` (`ops.py:919`) over `OP_HANDLERS` (`:895`, 42 kinds = `schema.OP_KINDS :30`), against the `OpHost` protocol (`ops.py:256`), implemented twice: `EffectManager` (game) and `EffectRuntime` (sim, forge, training room).
- Every HP loss goes through `EffectManager._damage` (`manager.py:1081`) -> `damage.roll_hit` (`:1090`) -> pure kernel (16 params, 5 rolls, 11 outputs). Rust and the Python twin share the ABI; Python draws the dice.
- Wiring: `main_game_scene.py:114-117` builds `EffectManager(world=self, abilities=load_abilities())`, sets `game.effect_manager`; `effects.update(dt)` once per frame (`:789`). Enemies use the same pipeline and perks.
- Items are verified as executable specs on the isolated `EffectRuntime`, not on the manager (`tests/test_lost_my_self_spec.py`).

Specifics:
- `cast()` emits `attack` (tag attack) and `cast` (tag spell) BEFORE the ops run; `attack_hit` fires after landing (`manager.py:624-649`). An on-`attack` `kill` op executes the target first.
- `emit`: prolongs buffs by `extend.on`, checks `trigger.cross`, `owner_has`, `filter`, cooldown. Cooldown is written before the ops run (`:707`), so a no-op effect still burns it. Depth cap `MAX_EVENT_DEPTH=6` drops deeper events silently (`:75,681`). Only the owner's events fire.
- Events really emitted: tick (max 1/s), hp_cross, attack, cast, dodge, attack_hit, crit, take_damage, kill, die, use (`manager.py:495-498,530,639,643,660,1095,1113-1127`).
- Two hosts diverge on purpose, 8 items (`docs/EFFECT_SCHEMA.md:187-203`): deal-hp path, default duration 10 s (room) vs `DEFAULT_DEBUFF_SECONDS=5` (`manager.py:74`), `extend`, `mod` contribution order. A green spec does not prove in-game numbers there.
- Effects mutate live entity fields; the game base is `field - applied`. Code that assigns a field absolutely gets skewed by last frame's delta. `crit_chance`/`dodge` are percentage points in schema (x100), 0..1 in fields and kernel (`manager.py:55-72,264-320`).
- Stat cache (dirty flags, `manager.py:157-397`, `tests/test_stat_cache.py`) is bypassed for any entity with a passive/condition effect or event-mod (`:340`): a hero wearing Sorrow of Berserk recomputes every frame. Caching helps monsters. Nested mutation inside `Tracked` dicts is untracked (inferred).
- `_damage` order: dice drawn, THEN iframe check, then HP cap, lifesteal (attack-tagged hits only), events. An invulnerable target still consumes rolls (matters for seed traces) and emits neither take_damage nor kill. DoTs have `tags=()`: no lifesteal, no attack_hit.
- Kernel params are positional and must match `manager._hit_params` (`:1069`) and Rust (`rust_core/src/combat/mod.rs:14-30`). A neutral hit = 3 kernel calls (`damage.py:282-289`). The manager calls only `roll_hit`; batch `resolve_hits` needs pre-drawn rolls (used by bench/tests only, inferred).
- `lua_content/damage.lua:17-57`: armor curve subtractive, resist clamp [-100, 90], immune at raw >= 100 (95 is not immune), block 50%, broken x1.15, `min_damage` 1.0 applied twice (`damage.py:156-178`) so DoTs are effectively immune to resist/block, variance 0, default crit 1.5 (falsy `critical_damage` becomes 1.5, `manager.py:1073`), 7 damage types. Flags true_damage/unavoidable/periodic -> CERTAIN (no accuracy/dodge/block rolls); type rides as `type:<kind>` (`damage.py:376-400`).
- `ally`/`allies` targets resolve to the caster only; `area` includes the caster, iterates registration order (= dice order) (`manager.py:734-772`), although companions register in faction `hero` (`main_game_scene.py:471`).
- `apply_op` ignores an unknown `kind` (`ops.py:928-930`). Buff-backed kinds (`schema.py:91`) are recognised by buff-id prefixes (`untargetable:`, `block:`, `nullified`), a string protocol shared by `ops.py:552` and `manager.py:777`.
- Predicates: whitelisted AST mini-language, no eval, Lua-like arithmetic (x/0 -> inf, `%` = luai_nummod), float-only ctx, unknown ctx field raises; `hp_missing_below_<N>` via `ops.derived_ctx` (`ops.py:105`; `runtime.py:97-260`). `rules()` on any Lua error returns plain defaults BEFORE damage-type families are added (`runtime.py:76-88`).
- Designer traps (found by running specs; `docs/EFFECT_SCHEMA.md:74-130`): `pct` without `of` = % of the same stat; an event `mod` REPLACES its previous contribution; bounds clip the final stat; heal never revives; buff `cooldown` counts from grant.
- Spec workflow: change the spec, then the catalog template, then regenerate Lua with `ui_logic.to_lua`; `test_lua_item_matches_catalog` fails otherwise. Items: `catalog()` globs `lua_content/items/*.lua` only (`src/gameplay/items.py:113-128`), about 34 (regex count, inferred); `lua_content/bricks/items.lua` is not loaded.

Live vs dead: manager/ops/runtime/damage/perks/items live. `combat_start`, `combat_end`, `on_shield_break` are listed in `schema.py:113-117` and emitted nowhere in `src/` (grep) - dead events. Rust op interpreter or stat cache: does not exist (`docs/EFFECT_SCHEMA.md:167` is a plan). Mahoraga/audit ops (30 kinds): handlers wired, live-content use unverified.

### 3.2 CAS

"CAS" is a label on unrelated modules, not one engine, and none is imported by `src/` gameplay. Live effects are `src/effects` (3.1). The premise "manager.py and test_system.py use CAS" is false: `manager.py` has no CAS reference and `src/systems/testing/test_system.py` never touches CAS.
- Members: `src/core/cas_engine.py` (CASManager + DamageCalculator; importers `tools/training_room.py:45`, tests), `python_layer/l9_semantic/cas_engine_v2.py` (CASSolver, 354 lines; `tools/cas_training_demo.py:11`, `tests/test_cas_engine_v2.py`), `cas_effect_system.py` (event bus; tests only), `src/core/effects/condition_action_system.py` (own `EffectManager`; only `tests/test_condition_action_system.py`), `rust_core/src/training_room/mod.rs` (274 lines; re-exported in Rust at `lib.rs:39`, absent from `ffi/mod.rs:20-36`), and the header string "CAS Item Builder" in generated Lua (`tools/effect_schema/lua_gen.py:273`, live generator, unrelated).

Specifics:
- `cas_engine.py`: AND-only conditions; `Condition.target` never read; only `modify_stat` applied (`:29-43,85-123`). Its ThreadPool is unused overhead; scaling uses a mock 1000.0 (`:69-73,156-219`). Import runs `logging.basicConfig(INFO)` (`:14`), which probably defeats `tools/training_room.py` log level (inferred).
- `tools/training_room.py:246` uses `DamageType.TRUE` (absent: AttributeError for any damage_per_tick > 0, untested); `:456-458` build unused CAS objects. The live training room is `tools/effect_schema/ui_logic.py:203` via `tools/web_builder/app.py:510`.
- CAS v2: `HP_DEFICIT_PERCENT` and `MANA_PERCENT` raise TypeError on evaluate (`cas_engine_v2.py:18-70`); a `set` modifier is silently ignored by `resolve_stat` (`:72-103,185-209`); `ComplexEffect` uses `time.time()` (`:121-166`, breaks the virtual clock) and reports hp_set without applying it. A missing stat reads as 0 there but raises in the live runtime.
- It is a buggier subset of the schema (mod ops with when/scale/amplify, MOD_MATH, buff flags iframe, extend on kill). Only `has_buff/has_debuff/has_item` predicates have no schema equivalent found; whether `manager.py:723 _ctx` exposes them is unverified.
- Sorrow of Berserk exists in 6 copies (live Lua `lua_content/items/sorrow_of_berserk.lua`, `src/features/advanced_items.py:378`, cas_engine_v2, cas_effect_system.py:406, condition_action_system.py:249, `tools/cas_training_demo.py:38`); only the Lua one has a spec. Numbers differ: v2 `2**int(missing/10)` = 512 at 1% HP vs Lua amplify capped at 16 (inferred arithmetic).
- Name collisions: `EffectManager` at `src/effects/manager.py:414` (live), `condition_action_system.py:324`, `cas_effect_system.py:325`; `DamageType` in 4 `src/core` files. Tests import `core.*` via `sys.path`, live code `src.core.*`: one file may load under two names (inferred).
- Stale docs claiming "single source of truth", NEQ, Rust acceleration: `CAS_ENGINE_V2_README.md`, `CAS_ENGINE_SESSION_REPORT.md`, `CAS_ENGINE_SUMMARY.md:218`, `PROJECT_STATUS_FINAL.md:54`, `docs/WEB_BUILDER_SESSION_REPORT.md:280`.
- `python_layer/` is excluded from the tools quality scope (`lua_content/qa.lua:261`); `cas_training_demo` is `status='demo'` (`qa.lua:479`).

Live vs dead: everything above is dead for gameplay; `cas_engine` is a partial tool dependency (54 CAS/training-room tests pass in 0.18 s, per the audit run).

### 3.3 Core (`src/core`, `main.py`)

How it works:
- `main.py:100-146`: services are wired by hand; plugins `effects` then `combat` (combat depends on effects, `:120-134`); order = `game_core.plugin_order` (`game_core.py:47,322`). `game_core.update` updates plugins then SceneManager (`game_core.py:185-206`).
- The scene owns the world; `Game._find_entity_by_id` is a linear scan (`main.py:163-173`); `game.effect_manager` is set at `main_game_scene.py:117`, cleared at `:1337`. Probes reach the world via `scene_manager.get_active_scene_data().instance.world` (`tools/probe_runtime.py:507-522`).
- `src/core` has no Rust or Lua dependency and reads no `AI_EVOLVE_*` env (`src/core/__init__.py:11-25` re-exports rng only). Rust/Lua hang off `src/effects`, `src/gameplay`, tools.

Specifics:
- `Game.__init__` does `os.chdir(APP_ROOT)` and creates `saves/` (`main.py:25-29,72-73`); every relative path depends on it.
- `plugin_auto_discovery` is a config flag with no implementation (`game_core.py:52`). `src/plugins/*` (analytics, probe, token, test accelerator) are never registered; only tests build them.
- Plugin exceptions are swallowed twice and logged every frame; a plugin is never disabled (`base_plugin.py:185-200`, `game_core.py:200-206`). A green run does not mean plugins work.
- `EventSystem` signals live in a module-global blinker Namespace: instances share handlers (`event_system.py:27,240,300-304`). A handler exception aborts the rest, `emit` returns False (`:228-238`); `priority` is unused; ids are ms-resolution and collide (`:175`). Gameplay barely uses it; combat events go through `EffectManager.register_event_handler` (`manager.py:442`). Features call the nonexistent `EventSystem.instance.trigger_event` (`features/terraforming.py:92`, `neuro_resonance.py:159`, `dynamic_weather.py:96`).
- `src/features/__init__.py:6-31` eagerly imports 6 dead feature modules, so a break there breaks boot.
- `StateManager` is a write-mostly blackboard with a daemon cleanup thread, persisting to `saves/states` (`state_manager.py:114-136,600-608`); no literal reader in `src`. May leak between "reproducible" runs (unverified).
- RNG: `RNGManager` default singleton is deterministic seed 42 (`rng_manager.py:148,158`), never reseeded by `main.py`. 26 `src` files still import global `random` (particle_system 25 calls, main_game_scene 17, dialogue_system 11, ai_system 10).
- Registry/Timeline are not wired: `registry.py` (12 string-keyed domains) and `timeline.py` (418 lines) are imported only by `tests/core/`; no code loads `registry.lua`. They already drift from Lua (layer priorities social/entity swapped; damage_types lists differ; `registry.py:189-208`). No numeric ids exist; ids are strings, only Timeline event ids are ints. `lua_content/ARCHITECTURE.md` describes the bridge as if it existed.
- Damage is computed in 8+ places (`cas_engine`, `combat_mechanics.py:321`, `features/combat_plugin.py:105`, `systems/combat/unified_combat_system.py:153,358`, `utils/helpers.py`, contracts, effects) and 4 DamageType taxonomies; the live one is `manager._damage`. Which path the hero's real fight takes beyond that was not traced.
- `src/core` is a grab bag: `adaptation.py`, `renderer.py`, `stats_loader.py`, `validation.py`, `constants.py` are domain code. `game_core.py` upward refs are TYPE_CHECKING only; `entity_manager.py:14-16` has an upward import (dead).

Live vs dead: live = game_core, architecture, base_plugin, adaptation (via ops), constants/interfaces/cache/circuit_breaker/stats_loader/validation/config_manager/renderer. Partial = event_system, state_manager, rng_manager. Dead = registry, timeline, di_container, entity_manager, async_game_core (594 lines), combat_advanced (460), game_master (133), combat_mechanics.

### 3.4 Other (AI, Rust, Lua, legacy)

How it works:
- Hero goal score = `goal_weight * option.base * emotion_weight + directive_bonus` (+0.15 stickiness); goals fight 1.4, loot 0.8, exit 0.7, hint 0.5, explore 0.25 (`hero_drive.py:24-31,118-168`). HeroMind opens an episode at hp <= `retreat_hp` (default 0.30), bandit (c=0.5, decay=0.98) picks retreat/press; press lowers `heal_at` (`hero_mind.py:31-147`).
- Enemies: 6 arms x 8 contexts, reward `dealt/(dealt+taken+1)` +0.5 if the hero died; bandit c=0.6, decay=0.97; untried arms first (`tactics.py:24-67`, `learning.py:37-69`). `EnemyBrain` sees via `EffectManager.can_see` (stealth works), 3 melee + 2 ranged attack slots, bosses skip the queue, movement is straight-line `move_towards` (`enemy_ai.py:33-70,114-175`).
- Rust exposed to Python (`rust_core/src/ffi/mod.rs:20-36`): used by the game = `TacticsBandit`, `resolve_hit(s)`, `LuaContent`; tools only = `RunAnalytics`, `QaKernels`, `ProbeAnalyzer`, semantic_core classes; also `find_path`, `flow_field`, stubs (below).

Specifics:
- Bandit memory `load_state` checks array LENGTH only; names are never compared (`learning.py:78-81,102-108,135-141`). Adding an arm silently wipes learning; reordering equal-length arms silently corrupts it. `HeroMind.baseline` is not saved (`hero_mind.py:58,156`), so `empowered()` is False after restart. Rage's press_bias overrides a retreat pick via a hash, not RNG (`:105-111`). `interest()` clears an expired directive as a side effect (`hero_drive.py:127`); `config()` merges Lua shallowly, so an `emotions` table without `calm` would KeyError (`:45-46`).
- Pathfinding: A*, JPS, flow field, Rust + twin (`src/gameplay/pathfinding.py`, 403 lines, `AI_EVOLVE_PATHFINDING=python`). Importers are only `tools/bench_pathfinding.py` and `tests/test_pathfinding.py` (grep); the scene and `enemy_ai.py` do not use it.
- Rust stubs: `PySimulationEnv.step/step_batch` return empty tuples, `WorldGenerator.generate` returns an empty 32x32 world, `TickSystem.tick` only adds time (`ffi/mod.rs:53-82`, `generator/mod.rs:22-36`, `simulation/tick.rs:26-31`). `python_layer/l4_gym/env_wrapper.py` builds on the stub. `Cargo.toml` overstates the crate.
- Lua files: abilities (weapon hit, skills as Effect->Ops), bestiary, bosses, damage, hero_mind, loot, perks, world, effect_rules, registry/kinds/schemas (data only), statuses/core_statuses (41 lines), rules/combinations (ITEM validation, e.g. fire+ice on a weapon; not elemental reactions), items/*, tool-only qa.lua, dev_tools.lua, agent_kit.lua, guards.lua. `lib/export.lua` strips functions; copies are embedded in Rust (`include_str`) and mirrored at `src/content/lua_bridge.py:37`.
- Status combos (melt, superconduct, explosion, hemorrhage, overload) and bleed/burn/freeze/shock/poison numbers exist only in `ai_evolve/features/effects/effects_plugin.py:80-162`. CC/stagger/toughness lives in 5 places outside the live path (`src/features/cc_system.py`, `src/core/combat_mechanics.py`, `systems/combat/components/toughness_component.py`, `ai_evolve/features/toughness`, `game/core/toughness.py`). Port these before archiving.
- Double combat stack: `main.py:120-137` boots `CombatPlugin`/`EffectsPlugin`; only `tools/boot_smoke_test.py:48-50` and `combat_smoke_test.py:196,352` use `game.combat_system`. `src/entities/character.py:30-31` imports `systems.combat`, which pulls `refactored_combat_system` (`systems/combat/__init__.py:8-13`).
- `pytest.ini:2` has `testpaths=tests`, so `ai_evolve/tests` do not run. `test_system.py:744,803,840` imports nonexistent `skills`/`rendering` packages. Only persisted learning is the two bandit JSONs; hero progression has no save (inferred from grep).

Live vs dead: see section 2. `ai_evolve/`, `AI-EVOLVE/`, `game/` are imported only by themselves and by `tests/test_effects_toughness_*.py` (`game.core.*`). Root `*_COMPLETE.md` / `*_REPORT.md` are stale history (not verified line by line).

## 4. Cross-cutting

- Determinism: `EffectManager` owns its clock (`self.now += dt`, no wall time). Hit dice come from the GLOBAL `random` because the scene passes no rng (`manager.py:419`, `main_game_scene.py:116`); enemy AI (`enemy_ai.py:80`), scene, particles share that stream, so any change in draw count shifts later hits. The kernel draws only the rolls a stage needs to keep old traces. `tools/probe_runtime.py` seeds `random.seed` and `RNGManager` (`:199-202`), installs `VirtualTime` over `time`/`perf_counter` and Panda `MNonRealTime` (`:79-139,472-500`); `from time import x` in game code bypasses the shim. `--fast` + seed = byte-for-byte runs.
- Env toggles/twins: `AI_EVOLVE_DAMAGE=python`, `AI_EVOLVE_DAMAGE_LUA=path`, `AI_EVOLVE_PATHFINDING=python`, `AI_EVOLVE_TACTICS_MEMORY` / `AI_EVOLVE_HERO_MIND` (path or `off`), bandit `backend="python"`. Tools `setdefault` both memories to `off` (`probe_runtime.py:490-491`), so tool runs differ from a real launch. Twins: bandit (`learning.py:22-25`), damage (`damage.py:33-37`, 41 parity tests in `tests/test_damage_pipeline.py`), pathfinding, Lua (mlua <-> lupa, `lua_bridge.py:43`), probe kernels (`tools/probe_kernels.py:25-32`). `damage.config()` and `rules()` are `lru_cache(1)`: clear them when swapping Lua (clearing `rules()` invalidates all StatCaches).
- Content as data: numbers belong in `lua_content/*.lua`; Python `DEFAULT_DATA` must equal the Lua (test-enforced for damage, `damage.py:295-367`). Op-kind SSOT is `schema.OP_KINDS` (`tests/test_ops_table.py` checks key equality with `OP_HANDLERS`). Item Lua is generated (`ui_logic.to_lua`), never hand-edited. Predicates must stay float-only with Python/mlua/lupa parity.
- Run: `python main.py [--dev] [--skip-menu]` (`--dev` small map, `--full` for the frozen build). Tests: `pytest -q tests`. Gameplay: `python tools/agent_play.py "spawn enemy x3; until kills>=3 or dead max 90; expect alive"`. Also `python tools/qa.py check`, `qa.py brief`. Env: `uv venv -p 3.14 .venv`, Rust optional (`uv pip install ./rust_core`, needs cargo; memory says cargo was absent on this machine, so the Python twins likely run).

## 5. Known problems (ranked)

1. Silent content failures: unknown op kind is a no-op (`ops.py:928`); 3 events never emitted (`schema.py:113-117`); `ally`/`allies` = caster (`manager.py:734-742`); `schema.FLAGS` (`:145`) lacks `unavoidable`/`periodic` used by `damage.CERTAIN_FLAGS` (validator effect inferred).
2. Two combat stacks plus five dead families (CAS x6 copies, `ai_evolve/`, `AI-EVOLVE/`, `game/`, `python_layer/`) with colliding class names (`EffectManager`, `DamageType`, `BreakState`); agents grep into dead code.
3. Determinism coupling: shared global `random` for dice, AI, particles; production `RNGManager` seeded 42.
4. Bandit memory is length-checked only; baseline not persisted.
5. `EffectRuntime` vs `EffectManager` divergences: specs do not prove in-game numbers.
6. Unwired Registry/Timeline already drift from Lua; docs describe a bridge that does not exist.
7. EventSystem defects (shared namespace, abort on error, id collisions, dead `.instance` API).
8. Damage code in 8+ places, 4 DamageType taxonomies, 5 CC/toughness copies.
9. Hero with passive effects defeats the stat cache.
10. Lifecycle: plugin errors logged forever, StateManager persists into `saves/states`, eager dead-feature imports.
11. Layer breaks: domain modules in `src/core`; dual import roots `core.*` / `src.core.*`; `entity_manager.py:14-16` upward edge.
12. Latent crashes: `tools/training_room.py:246`, `cas_engine_v2.py:18-70`, `terraforming.py:92`.
13. Rust stubs and overclaiming docs (`Cargo.toml`, `docs/EFFECT_SCHEMA.md:164` says ~20 primitives, code has 34; CAS docs).
14. Pathfinding built but unused; enemies walk straight lines.

## 6. Candidate next steps (ranked by value/cost)

| # | Idea | Why | Size | Where |
|---|---|---|---|---|
| 1 | DONE 2026-09-26: Make silent failures loud: log/raise on unknown op kind, emit or delete the 3 events, align FLAGS with CERTAIN_FLAGS, fix "~20" doc | Designer content silently does nothing | S | `ops.py:928`, `schema.py:113-117,145`, `docs/EFFECT_SCHEMA.md:164` |
| 2 | Real `ally`/`allies` targeting (same faction, alive, radius) + tests | Schema promises it; companions exist | S | `manager.py:734-742`, `main_game_scene.py:471` |
| 3 | Inject `random.Random(seed)` into EffectManager, re-record goldens; later named RNG streams (particles/ai/loot), lint global `random` in gameplay | Unrelated draws shift every hit | S then M | `main_game_scene.py:116`, `manager.py:419`, `rng_manager.py:144-149`, `particle_system.py` |
| 4 | DONE 2026-09-26: Harden BanditMemory: version + compare arm/context names, persist `baseline` | Adding a tactic wipes learning | S | `learning.py:78-141`, `hero_mind.py:58,156` |
| 5 | Archive-by-tag then delete dead families: CAS, orphan core modules, `ai_evolve/`, `AI-EVOLVE/`, `game/`; port unique scenarios (Apocalypse Bringer, Mage Supremacy) to Lua specs first; add import-linter ban | Matches consolidation direction; removes name collisions | M | see section 2; `.importlinter`, `qa.lua:479` |
| 6 | DONE 2026-09-26: Fix EventSystem: per-instance Namespace, isolate handler errors, counter ids, drop `.instance` calls | Latent bugs once the bus is used | S | `event_system.py:27,175,228-240` |
| 7 | Plugin/state lifecycle: disable plugin after N errors, surface `errors_count`, temp StateManager path in probes, lazy `src/features/__init__` | Probes report healthy runs that are not | S | `game_core.py:200-206`, `base_plugin.py:185-200`, `state_manager.py:114-136` |
| 8 | DONE 2026-09-26: Benchmark single-hit Rust vs twin (up to 3 FFI calls per hit); fuse or switch default | Rust may be slower per hit | S | `tools/bench_damage.py`, `damage.py:251-289` |
| 9 | Registry/Timeline: Lua-vs-Python diff test (cheap) or attach Timeline to `register_event_handler`, else archive | Dead code with drifting tables | S / M | `registry.py:185-208`, `timeline.py:384-414`, `registry.lua` |
| 10 | Run executable specs on EffectManager too; remove host divergences one by one | Spec green != in-game green | M | `test_lost_my_self_spec.py:23-25`, `EFFECT_SCHEMA.md:187-203` |
| 11 | Decide `has_buff/has_debuff/has_item` predicates via `ops.derived_ctx` | Only CAS capability without a schema twin | M | `manager.py:723`, `ops.py:105` |
| 12 | Shrink `src/core` to the kernel; move adaptation/renderer/stats_loader out; contract "core imports nothing above" | Layer ratchet | M | `src/core/*.py`, `.importlinter` |
| 13 | Retire the double combat stack (route via plugins or delete; migrate smoke tools) | Two architectures, one used | M | `main.py:120-137`, `tools/*smoke_test.py` |
| 14 | Second hero bandit (engage/avoid or loot/fight), lessons in HUD | Hero learns 1 decision, enemies 6 | M | `hero_mind.py:150-154`, `hero_drive.py:154-168` |
| 15 | Rust stubs: implement or delete (`SimulationEnv`, `WorldGenerator`, storage, training_room); add hero progression save | Constant data, no progress save | M | `ffi/mod.rs:53-82`, `db_core.py:35` |
| 16 | Wire pathfinding: shared flow field in `enemy_ai` | Kernel exists, tests exist | L | `enemy_ai.py:156,175`, `pathfinding.py:377` |
| 17 | Port statuses/combos and toughness/stagger to Lua + ops with specs | Blocks archiving `ai_evolve/` | L | `effects_plugin.py:80-162`, `cc_system.py:50`, `core_statuses.lua` |
| 18 | Collapse damage to `manager._damage` + `damage.lua`; delete duplicates | 8+ implementations | L | section 3.3 list |
| 19 | Stat cache for passive effects, or Rust port of `refresh_passives`/ops (twin + parity test) | Heroes recompute every frame | L | `manager.py:330-348`, `runtime.py:607-665`, `ops.py` |
| 20 | Typed player-lever event stream (record first) for replay and "why did the hero do that" | Influence is not observable data | L | `hero_drive.py`, `lua_content/timeline/event_kinds.lua` |

## 7. Questions to ask an agent

1. In the dev venv, what do `damage.BACKEND` and `damage.available_backends()` return, and does `tools/bench_damage.py` show Rust faster than the twin for single `roll_hit` calls?
2. Which of the 30 non-core op kinds (14 audit + 16 Mahoraga) do `lua_content/{bosses,abilities}.lua` and `statuses/core_statuses.lua` use in the live game, and which only the training room?
3. Does `EffectManager._ctx` (`manager.py:723`) expose buff/debuff presence or equipped items to predicates?
4. What does `op_add_periodic` (`manager.py:817`) store as `p['source']`, and who gets kill credit when that source was unregistered (`:511`)?
5. Does schema validation / itemcheck reject the flags `unavoidable` and `periodic`?
6. Do any dynamic imports reach `src/systems/effects/effect_system.py` or `cc_system.StatusEffectManager`, and is `CombatPlugin.calculate_damage` (`features/combat_plugin.py:105`) reachable from the hero's fight?
7. Which lifecycle events trigger `tactics.save()`/`mind.save()` (`main_game_scene.py:1231,1333-1335,1554-1558`), and is learning lost on a crash?
8. Which tests and tools break if `python_layer/` and `ai_evolve/` are archived, and which Sorrow of Berserk numbers are canonical (Lua amplify cap 16 vs CAS `2**int(missing/10)`)?
