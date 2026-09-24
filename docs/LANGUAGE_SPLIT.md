# Language split: who does what

Rule (developer, 2026-09-24): Python keeps only what nothing else can do, or does better. Everything
that is number crunching, a hot loop or analytics goes to **Rust** (`rust_core`, PyO3, every kernel has a
pure-Python twin so tools work without a toolchain). Everything that is content, rules, thresholds or
scenarios is **Lua data** (`lua_content/*.lua`, read through `src/content/lua_bridge.py`).

## Python stays (no better option)

- The Panda3D scene graph: nodes, models, camera, HUD/menu widgets, input, the frame loop.
- Orchestration and glue: `GameCore`, plugins, `SceneManager`, `StateManager`, SQLAlchemy `DatabaseCore`.
- The QA harness (`tools/`): subprocess pools, pytest, CLI front doors. Its number crunching is Rust.
- Anything that must touch live Python objects every frame (entities, nodes): Python calls a Rust kernel
  with column buffers in ONE FFI call instead of crossing the boundary per object.

## Already moved

| What | Where |
|---|---|
| Enemy/hero tactic learning (UCB1 bandit) | `rust_core.TacticsBandit` (twin `PyBandit`, `src/gameplay/tactics.py`) |
| Run analytics, bootstrap statistics, graph walks for QA | `rust_core.RunAnalytics`, `QaKernels` |
| Lua execution (sandbox, data as one JSON string) | `rust_core.LuaContent` (mlua, Lua 5.5), fallback lupa |
| World, bosses, perks, loot, bestiary, hero mind, dev/QA settings, item definitions | `lua_content/*.lua` |

## Next, ordered by measured cost (`python tools/qa.py perf "spawn enemy x10; wait 60"`, 61 s of game time)

| # | Hot spot (profile) | Share | Move to |
|---|---|---|---|
| 1 | `src/effects/runtime.py:_eff` (439k calls), `manager.py: pull / push_stats / base_game` (27k each, per entity per frame) | ~40% of scene update | Rust `EffectKernel`: layered-mod stat resolution for all entities in one call, plus a dirty flag so unchanged entities are skipped (algorithmic fix first) |
| 2 | `manager.py: can_see / vision_toward` (73k calls) | ~8% | Rust batch visibility (positions, vision range, stealth as arrays) |
| 3 | Grid pathfinding (nothing does it yet) | new | Rust: A*/JPS + Dijkstra flow field (`src/gameplay/pathfinding.py` twin) |
| 4 | `manager.py: is_alive / position / state` (0.5M calls) | ~6% | fewer crossings: the columns of #1/#2 replace them |
| 5 | Damage pipeline (resist, armor penetration, block, accuracy) | not wired | Rust formula kernel, tunables in Lua (`lua_content/formulas/`) |
| 6 | Crowd control + toughness/stagger | not wired | port the tested logic (`src/systems/combat/components/toughness_component.py`, `src/features/cc_system.py`) as effects; numbers in Lua |

## How to work on it

1. Measure: `qa.py perf "<script>"` before and after; keep the top-15 table in the commit message.
2. Behaviour must not move: `qa.py test` and `qa.py determinism` (same seed, identical frames) and, after an
   INTENDED change, `qa.py golden` then `--record`.
3. Twin first: the Python twin defines the semantics; the Rust kernel must match it in a parity test on seeded
   random inputs. No toolchain -> the twin runs and the game still works.
4. Data goes to Lua when a designer would tweak it; formulas stay code, their constants go to Lua.
