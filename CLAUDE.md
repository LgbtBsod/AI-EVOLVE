# AI-EVOLVE — notes for coding agents

Panda3D game. Python orchestrates; heavy number crunching lives in `rust_core/` (PyO3,
optional at runtime — every tool has a Python fallback); settings/content in `lua_content/`
(Lua 5.5). Read any Lua file with `tools/lua_bridge.py` (`load(path)`): the file is executed in a
sandbox (`rust_core.LuaContent` / mlua, fallback lupa) and the data crosses as one JSON string.

## Environment

- Python **3.14** (PEP 695 syntax in `src/`; 3.11 cannot even import `main`).
  `uv python install 3.14 && uv venv -p 3.14 .venv && uv pip install -r requirements-dev.txt`
- Optional: `uv pip install -r tools/requirements-dev.txt` (Pillow/OpenCV image extras),
  `uv pip install ./rust_core` (Rust kernels, needs cargo; ~13x faster analysis).

## Start here

`python tools/qa.py brief` (10 lines: env, what your diff affects, recent runs) and
`python tools/qa.py doctor` (missing deps + exact fix command). Before reading a big file:
`python tools/qa.py ctx path/to/file.py` (outline, importers, covering tests). `qa.py dead` lists
modules nobody imports (~18k LOC) and `qa.py docs` marks stale .md reports — don't read those.

## Verify changes cheaply — pick the first tool that answers the question

| Question | Command | Cost |
|---|---|---|
| Combat/effects/leveling formulas | `python tools/combat_smoke_test.py` | 0.3 s, no window |
| Does the game boot (menu→world→plugins) | `xvfb-run -a python tools/boot_smoke_test.py` | 5 s, needs OpenGL |
| **Gameplay behaviour** (play like the player) | `python tools/agent_play.py "spawn enemy x3; until kills>=3 or dead max 90; expect alive"` | <1 s for minutes of game time, no GPU |
| Long unattended run + anomaly hunt | `python tools/dev_probe.py --render none --fast --seed 1 --duration 120 --action-at 1:1` | <1 s |
| Anything visual (rendering, labels, HUD) | `xvfb-run -a python tools/dev_probe.py --headless --fast --seed 1 --screenshot-interval 10` then Read `contact_sheet.jpg` only | a few s |
| Numbers across runs / "did my fix help" | `python tools/probe_db.py stats` · `why` · `predict` · `compare RUN_A` · `trend kills` | ms |
| Which tests to run for my diff | `python tools/qa.py test --changed` (parallel shards; prints only NEW failures, auto-detects flaky ones) | ~1-4 s |
| Did gameplay behaviour change at all | `python tools/qa.py golden` (deterministic scenarios vs `tests/golden/`) | ~2 s |
| Hunt bugs automatically | `python tools/qa.py fuzz` (random player actions + per-frame invariants → minimal repro script) | ~10 s |
| Balance / "how often does X happen" | `python tools/qa.py sweep "SCRIPT" --seeds 16` (distribution + bootstrap CI) | ~3 s |
| Visual regression between two probe runs | `python tools/dev_probe_diff.py --before A --after B --frames` (image only for changed frames) | s |
| Why did the hero AI do that | `agent_play "...; story"` (compressed ai_state transitions) | <1 s |
| Performance hot spots | `python tools/qa.py perf "spawn enemy x10; wait 60"` | 2 s |
| Does an item work (schema → Lua → combat) | `python -m tools.effect_schema.itemcheck lua_content/items/X.lua` (`--forge N` stress item, `--hostile` Python/Lua parity hunt) | <1 s per 300 effects |

Rules of thumb:
- Read only the `RESULT` line + printed hypotheses first; open `summary.md` / `session.json`
  only if they point at something. Never read `state.jsonl`/`game.log` raw — ask `probe_db.py`
  (`sql "SELECT ..."` for anything custom).
- `--fast` + a seed (agent_play defaults to seed 1) = byte-for-byte reproducible run. Every
  failing run prints a `repro:` command; each run dir also has `repro.sh`.
- The player's controls are the only levers agent_play exposes: `spawn enemy|trap|chest` (keys
  1/2/3), `attack` (space), `interact` (e). Key map: `lua_content/dev_tools.lua` → `agent.player_keys`.
- Turn-based interactive play: run `python tools/agent_play.py --serve --port 8765` in the
  background, then `curl -s localhost:8765/do -d 'wait 5; observe'`, `curl -s -X POST localhost:8765/quit`.
- Named scenario templates: `agent_play.py --list-scenarios`, `--scenario swarm` (lua_content/qa.lua).
- Tests that wait on game timers: mark them `pytestmark = pytest.mark.virtual_time` (tests/conftest.py)
  instead of real `time.sleep` — the toughness suite went from 68 s to 0.1 s.
- Known pre-existing failures live in `tests/qa_known_failures.json`; `qa.py test` reports them as known.
- Item mechanics: the designer's words are encoded as executable specs (e.g. `tests/test_lost_my_self_spec.py`,
  run against the catalog AND the Lua item in `lua_content/items/`). Change the spec first, then the item;
  regenerate the Lua with `tools/effect_schema` (`ui_logic.to_lua`).
- Effect semantics that are easy to get wrong (resources hp/mana/stamina, `mod` goes to the op's target,
  stat bounds in `lua_content/effect_rules.lua`, float-only conditions) are listed in `docs/EFFECT_SCHEMA.md`.
- Looking at an item: `effect_schema.digest.digest(item)` (one line per effect) and `diff(a, b)` (changed
  effects only) instead of reading the Lua. Conditions in Lua are `pred("ctx.hp_pct < 40", function…)`:
  tools get the source string, the engine calls the function.
- After an intended gameplay change: `qa.py golden` shows what moved, then `qa.py golden --record`.
- Default dev map: enemies spawn ~160u from the hero and rarely reach him — a run without
  `spawn enemy` usually has no combat at all (hypothesis `NO_COMBAT`).

## Where things live

- `tools/probe_runtime.py` — boot (render window/offscreen/none), virtual fixed-step clock,
  data-model ADAPTER (`get_scene/get_entities`), `KillTracker`, combat recorder.
- `tools/probe_analysis.py` — rule-based hypotheses (symptom → cause → file) and forecasts.
- `tools/probe_kernels.py` — Rust/Python kernels; data crosses as columnar buffers
  (`array('d')`, `HeroTable` struct-of-arrays → one `scan_hero` FFI call).
- `rust_core/src/analytics/` — those kernels in Rust; `rust_core/src/probe/` — frame analysis.
- `tools/lua_bridge.py` — the only Lua loader (`load`, `eval_preds`, `bench`, JSON cache);
  `rust_core/src/lua_content/` — its Rust backend; `export.lua` there is shared by both backends.
- `lua_content/dev_tools.lua` — thresholds, agent limits, DB path; `lua_content/qa.lua` — scenarios, fuzz
  weights, invariants, sweep; `lua_content/probe_config.lua` — frame analysis.
- `tools/qa.py` + `qa_graph.py` (import graph), `qa_pool.py` (asyncio subprocess pool),
  `probe_invariants.py`; Rust `QaKernels` (graph reachability, bootstrap stats, trajectory hashes).
- Outputs go to `dev_probe_output/` (git-ignored), DB at `dev_probe_output/probe.sqlite`
  (override with env `AI_EVOLVE_PROBE_DB`).

## Tests

`python tools/qa.py test` runs everything in ~4 s. `tests/test_agent_tools.py` + `tests/test_qa_tools.py`
cover the tooling incl. determinism on the real game; `cd rust_core && cargo test` +
`pytest rust_core/tests/test_ffi.py` for Rust.
