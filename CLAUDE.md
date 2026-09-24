# AI-EVOLVE — notes for coding agents

Panda3D game. Python orchestrates; heavy number crunching lives in `rust_core/` (PyO3, optional at runtime —
every tool has a Python fallback); settings/content in `lua_content/` (Lua 5.5). Read any Lua file with
`tools/lua_bridge.py` (`load(path)`): executed in a sandbox (`rust_core.LuaContent` / mlua, fallback lupa), data crosses as one JSON string.

## Environment

- Python **3.14** (PEP 695 syntax in `src/`): `uv python install 3.14 && uv venv -p 3.14 .venv && uv pip install -r requirements-dev.txt`
- Optional: `uv pip install -r tools/requirements-dev.txt` (image extras), `uv pip install ./rust_core` (Rust kernels, needs cargo).
- Start: `python tools/qa.py brief` (10 lines) · `qa.py doctor` (missing deps + fix) · `qa.py ctx FILE` (outline, importers, tests — instead of reading
  a big file) · `qa.py dead` / `qa.py docs` (unimported modules / stale .md: don't read those).

## Verify changes: ONE command first

`python tools/qa.py check` runs the checks your diff affects (vs origin/main + working tree; `--all` `--fast` `--name a,b` `--tag play`
`--explain NAME` `--ci` `--json` `--no-cache`). One format for every check, worst first, hard cap 30 lines (overflow goes to a file):

    QA verdict=FAIL checks=3 ok=1 fail=1 warn=0 cached=1 dur=6s head=1d147e1 dirty=3 selected=3/16 by=diff
    FAIL   play:swarm hp=0.0/154.0 kills=6(-40%) dealt=484.2(-22%) dur=2.0s | FAIL expect alive at t=40 | repro: python tools/agent_play.py ...
    cached tests      passed=831 new=0 known=1 dur=0.0s age=4m

A line is `STATUS NAME metrics dur [| first detail | repro: ONE command]`. `ok` · `FAIL` (code is wrong) · `warn` (known/soft/over a limit) ·
`ERROR` (the check itself broke) · `skip` (missing dep/display) · `cached` (same inputs, not re-run). `(-22%)` = moved against the previous run of that
check, printed only above the thresholds in `lua_content/qa.lua`. Exit 0 ok/warn, 1 fail, 2 tool error. History: `dev_probe_output/qa/history.jsonl`.

- `python tools/qa.py changed [REV]` — semantic diff (<= 30 lines: +added -removed ~changed symbols per file, churn per area, RISK flags,
  which checks to run). Read it instead of `git diff`.
- `python tools/qa.py ci [--wait] [--sha S | --run ID]` — GitHub Actions via `gh`: verdict + only the failing step's essentials (FAILED tests,
  assertion + 3 diff lines, last traceback frame, cargo errors, our RESULT lines); cleaned full log in `dev_probe_output/qa/ci_<run>.log`. Never `gh run view --log`.

Drill down only when a line fails — first tool that answers the question:

| Question | Command (cost) |
|---|---|
| Combat/effects/leveling formulas | `python tools/combat_smoke_test.py` (0.3 s) |
| Does the game boot | `xvfb-run -a python tools/boot_smoke_test.py` (5 s, OpenGL) |
| **Gameplay behaviour** (play like the player) | `python tools/agent_play.py "spawn enemy x3; until kills>=3 or dead max 90; expect alive"` (<1 s, no GPU) |
| Long unattended run + anomaly hunt | `python tools/dev_probe.py --render none --fast --seed 1 --duration 120 --action-at 1:1` |
| Anything visual | `xvfb-run -a python tools/dev_probe.py --headless --fast --seed 1 --screenshot-interval 10`, Read `contact_sheet.jpg` only |
| Numbers across runs / "did my fix help" | `python tools/probe_db.py stats` · `why` · `predict` · `compare RUN_A` · `trend kills` · `sql "SELECT ..."` |
| All tests / tests for my diff / did behaviour change | `qa.py test` (~4 s) · `qa.py test --changed` (new failures only, flaky auto-detected) · `qa.py golden` (`--record` after an intended change) |
| Why do same-seed runs differ | `qa.py determinism "SCRIPT" --pairs 6` (first divergent frame, hypotheses; `--diff A B`; rules in `qa.lua`) |
| Bugs / balance / speed | `qa.py fuzz` (minimal repro) · `qa.py sweep "SCRIPT" --seeds 16` (bootstrap CI) · `qa.py perf "SCRIPT"` |
| Why did the hero AI do that / bosses | `agent_play "...; story"` · `qa.py gauntlet [--campaign --lives 5 --trace]` |
| Visual regression between runs | `python tools/dev_probe_diff.py --before A --after B --frames` |
| Pathfinding (A*/JPS/flow field) | `python tools/bench_pathfinding.py` · `pytest tests/test_pathfinding.py` (`AI_EVOLVE_PATHFINDING=python` = twin) |
| Damage (types, resist, armor + pen, block, accuracy) | `docs/DAMAGE_PIPELINE.md` (stage table) · `pytest tests/test_damage_pipeline.py` · `python tools/bench_damage.py` (`AI_EVOLVE_DAMAGE=python` = twin; numbers in `lua_content/damage.lua`) |
| Code quality: SOLID/DRY/SRP/SSOT | `qa.py quality --worst 10` (top offenders + SRP hint) · `--explain BLE001` (what/fix) · `--update-baseline` (1 s; part of `qa.py check`) |
| Lua / items without reading Lua | `qa.py lua show FILE --keys\|--key a.b` · `qa.py item diff FILE\|digest FILE\|all` · `python -m tools.effect_schema.itemcheck FILE` |
| Build an item like a designer | `tools/web_builder/headless.py` (`UI().pick("Шаблон из каталога", "venom_bite")…click("Проверить предмет (itemcheck)")`) |

**Quality ratchet** (`qa.py check --name quality`; ruff + radon + vulture + import-linter `.importlinter` + an ast duplicate-definition detector on the live game modules; rules, scope, thresholds, hints = `quality` in `lua_content/qa.lua`):
today's violations are the baseline (`tests/quality_baseline.json`: per metric, file, function with CC>=11); a NEW one fails, an improvement prints `improved=N` (warn) and
`qa.py quality --update-baseline` locks it in (refuses to raise a number without `--force`). Fix a new violation (`--explain RULE`); never grow the baseline or `ignore_imports`.

## How to add a check (no wiring: all three are picked up by `qa.py check`)

1. **pytest file** `tests/test_x.py` — automatic: the `tests` check runs every file and, in diff mode, the ones your change affects.
2. **One Lua table** in `lua_content/qa.lua` (`parse` = `result_line` | `pytest` | `counts` | `regex` | `exit`; more keys in that file's header):

       plays = { { name = "boss_dies", seed = 7, script = "spawn boss; wait 60", expects = "kills>=1" } },   -- gameplay test -> check play:boss_dies
       checks = { { name = "lua_fast", cmd = "python tools/qa.py lua check", parse = "regex", cost = "low",
                    pattern = [[lua: (?P<loaded>\d+)/(?P<files>\d+)]], watches = { "lua_content/**/*.lua" }, what = "every Lua file loads" } },

3. **Python** `tools/qa_checks/mine.py` for custom logic (auto-discovered):

       from qa_report import check, Result
       @check("mine", cost="low", watches=["src/x/**"], tags=["combat"])
       def mine(ctx):
           out = ctx.run("python tools/x.py")                 # via the parallel pool
           return ctx.result(out, parse="counts")             # or Result("fail", {"n": 3}, ["why"], repro="cmd")

`watches` = globs that select the check and invalidate its cached result. Try it: `qa.py check --explain mine`, `qa.py check --name mine --no-cache`.

## Rules of thumb

- Read only the `RESULT`/verdict line first; open `summary.md` / `session.json` only if pointed there. Never read `state.jsonl`/`game.log` raw — use `probe_db.py`.
- `--fast` + a seed (agent_play defaults to seed 1) = byte-for-byte reproducible; every failing run prints `repro:` (also `repro.sh` in the run dir).
- The player's levers in agent_play: `spawn enemy|trap|chest|boss` (`spawn enemy golem_shard x3` = a bestiary kind) (keys 1-4), `attack`, `interact`, `emotion calm|rage|fear|curiosity|greed|resolve`,
  `direct north|south|east|west|chest|exit|npc|none`. They shift the hero's interest (`src/gameplay/hero_drive.py`), never command him; `observe` shows
  `mood/directive/goal/stance`. Keys: `lua_content/dev_tools.lua` → `agent.player_keys`, `lua_content/hero_mind.lua`. Templates: `--list-scenarios`, `--scenario swarm`.
  Turn-based: `agent_play.py --serve --port 8765` in the background, `curl -s localhost:8765/do -d 'wait 5; observe'`, `curl -s -X POST localhost:8765/quit`.
- Tests that wait on game timers: `pytestmark = pytest.mark.virtual_time` (tests/conftest.py), never real `time.sleep`. Known failures: `tests/qa_known_failures.json`.
- Items: mechanics are executable specs (`tests/test_lost_my_self_spec.py`, run on the catalog AND `lua_content/items/`); change the spec, then the item, regenerate Lua with
  `tools/effect_schema` (`ui_logic.to_lua`). Semantics that are easy to get wrong: `docs/EFFECT_SCHEMA.md`. Look with `effect_schema.digest.digest(item)` / `diff(a, b)`.
- Periodic spawns appear 30-50u from the hero (outside his 30u vision); `spawn enemy` guarantees a fight. Enemies see the hero via `EffectManager.can_see`, fight with a learned
  tactic (`src/gameplay/enemy_ai.py`, Rust bandit in `tactics.py`; tools use `AI_EVOLVE_TACTICS_MEMORY=off`). The hero learns "retreat" vs "press" (`hero_mind.py`, `AI_EVOLVE_HERO_MIND=off`).

## Where things live

- `tools/qa.py` + `qa_plugins/*.py` (auto-discovered commands: `check`, `ci`, `changed`, `item`, `lua`, `determinism`, ...; a new command needs no edit of qa.py), `qa_report.py`
  (the one output format), `qa_graph.py` (import graph), `qa_pool.py` (parallel subprocesses), `probe_runtime.py` (boot, virtual clock), `probe_analysis.py`, `probe_kernels.py`.
- `lua_content/qa.lua` — checks, scenarios, budgets, delta thresholds; `dev_tools.lua` — thresholds/limits/DB path; `probe_config.lua`. `rust_core/src/{analytics,probe,lua_content}/` — the Rust kernels.
- Outputs go to `dev_probe_output/` (git-ignored; DB `probe.sqlite`, override `AI_EVOLVE_PROBE_DB`). Rust: `cd rust_core && cargo test` + `pytest rust_core/tests/test_ffi.py`.
