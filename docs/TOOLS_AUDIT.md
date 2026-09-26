# tools/ audit: ranked plan (judge, 2026-09-26)
Scope: tools/ = 79 files, 22.2k LOC, 117 functions CC>=11 (radon), 237 hits of the ratchet's ruff rules (ruff --isolated); 48 of the 237 and 4 of the 117 sit in tools/plugins. Nothing here is applied yet.
ROI = B / cost (S=1, M=3, L=8). B: 1 per 500 dead/duplicate LOC, 1 per 5 s saved per agent session (~45 qa.py calls), 1 per 25 lint/CC hits fixed, 3 per gate or removed security risk.
Rank follows dependencies: T1 is pinned first (owner order; it is the enabler, its stand-alone ROI is shown). "Depends" = must ship first. Measured by the judge: wall times, import costs, ruff/radon counts, full_match, grimp, rayon version.

| rank | id | action | library | ROI | effort | depends |
|---|---|---|---|---|---|---|
| 1 | T1 | Quality ratchet for tools/: second scope + own baseline | ruff, radon, vulture (installed) | 3.0 | M | - | DONE |
| 2 | T2 | Archive dead tools: plugins/, dev_probe_async.py, report JSONs | git tag | 15 | S | T1 |
| 3 | T3 | Archive parallel trees AI-EVOLVE/ (nested) and ai_evolve/ | git tag | 8 | S | T1 |
| 4 | T4 | ruff --fix F401, B905, PERF401 (~50 hits after T2) | ruff | 2.0 | S | T2 |
| 5 | T5 | One glob matcher for check.py / quality_metrics (not guard_hook) | stdlib PurePosixPath.full_match | 2.0 | S | T1 |
| 6 | T6 | Shared helpers: one git wrapper, one jsonl reader/writer | stdlib | 1.5 | S | T1 |
| 7 | T7 | qa startup diet: qa_pool asyncio -> ThreadPoolExecutor, lazy Lua | stdlib | 1.2 | S | T1 |
| 8 | T8 | Slim qa.py: cmd_golden/test/sweep/docs -> qa_plugins | - | 1.0 | M | T1, T6 |
| 9 | T9 | validate_op CC70 -> per-op dispatch table | none (pydantic rejected) | 1.0 | M | T1 |
| 10 | T10 | probe_analysis hypotheses/forecast CC51/49 -> Lua rule table | Lua data | 1.0 | M | T1 |
| 11 | T11 | Manual lint: B023 x10 (closure loop var), BLE001 x34 | ruff | 1.0 | M | T4 |
| 12 | T12 | ci.essentials CC64 -> per-step parser table | - | 0.7 | M | T1 |
| 13 | T13 | rayon in rust_core batch kernels, only after a benchmark gate | rayon 1.12 (MSRV 1.80) | 0.7 | M | T1 |
| 14 | T14 | agent_play: split parse_script CC27 / PlaySession.finish CC28 | - | 0.7 | M | T1 |
| 15 | T15 | dev_probe.py (1481 LOC) split: image analysis / CLI / session | - | 0.5 | L | T4, T14 |
| 16 | T16 | sys.path/ROOT bootstrap in 26 files -> one helper | - | 0.5 | M | T6 |
| 17 | T17 | Split guard_hook (725) and determinism (825) | - | 0.4 | L | T1 |

## Specs (top 12: what / files / acceptance / risk)
**T1 what:** `quality` (lua_content/qa.lua:245) has one scope, `liveness="game"` (:248), one baseline. Add a `tools` scope (qa_graph liveness `tool`, 97 modules) with `tests/quality_baseline_tools.json`; same ruff select and CC>=11; import-linter stays src-only.
**T1 files/accept:** qa.lua, tools/quality_metrics.py (scope() at :66), tools/qa_plugins/quality.py, watches += `tools/**/*.py`. Accept: `--update-baseline` records 237 ruff / 117 CC; a dummy CC>10 function makes `qa.py check --name quality` FAIL with file+function, removing it gives ok; game-scope output unchanged.
**T1 risk:** low. The check gets slower (ruff+radon over 79 files, unmeasured): keep it cached by `watches`. Never `--force` a baseline up.
**T2 what:** tag `archive/tools-plugins-2026-09`, then `git rm -r tools/plugins tools/dev_probe_async.py tools/memory_reports tools/performance_reports tests/test_ai_systems.py`; drop qa.lua rows :418 (dev_probe_async) and :445 (plugins); `qa.py tools --write`.
**T2 files/accept:** evidence in "Delete/archive list". Accept: `qa.py check --name tools,hygiene,quality,tests` ok; quality prints `improved=` (about 48 ruff + 4 CC) then `--update-baseline`; `qa.py dead` loses ~5k LOC.
**T2 risk:** low. Stale docs (DEV_PROBE_*.md, TRAINING_ROOM_COMPLETE.md) show up in `qa.py docs`: archive them in the same commit.
**T3 what:** tag, then `git rm -r AI-EVOLVE ai_evolve` (24 + 116 tracked files): two extra probe frameworks, contradicting the one-project direction in memory.
**T3 files/accept:** `qa.py dead` lists AI-EVOLVE/tools/dev_probe/{plugins 2129, core 638, data_layer 527 LOC}, ai_evolve/plugins 540; `ai_evolve` in src/tools/tests/main.py = 0 hits. Accept: `git grep -n ai_evolve` clean outside them (pyproject, CI, docs), `pytest --collect-only -q` no errors, `qa.py check --all` same verdict.
**T3 risk:** medium: the owner may want ideas from them (tag keeps them). Separate commit, independent revert.
**T4 what:** `ruff check tools --select F401,B905,PERF401 --fix --unsafe-fixes` after T2 (B905 adds `strict=`, PERF401 rewrites loops: read the diff).
**T4 files/accept:** whatever ruff reports (34 + 18 + 17 before T2). Accept: `qa.py check` + `qa.py test --changed` green, quality `improved=N` then `--update-baseline`.
**T4 risk:** low; F401 in re-exports and side-effect imports (`# noqa: E402` at dev_probe.py:112): run tests before committing.
**T5 what:** tools/qa_plugins/check.py:99-114 (`_glob_re`/`gmatch`) and the fnmatch calls (check.py:142, quality_metrics.py:71) -> `PurePosixPath(p).full_match(glob)`. repo_hygiene `_segments` (gitignore semantics) stays.
**T5 files/accept:** measured on 3.14.5: `src/**/*.py` matches `src/a/b.py` and `src/b.py`; fnmatch `*` crosses `/` and has no `**`, so semantics differ per tool. Accept: parity test of every `watches` glob in qa.lua over `git ls-files`, old vs new = 0 unexplained diffs.
**T5 risk:** guard_hook.py:263 is EXCLUDED: pathlib import costs 30 ms here on a 120 ms hook that runs on every tool call, and the hook imports no pathlib today (importtime: 0 hits).
**T6 what:** one git wrapper (4 copies: qa.py:69, qa_plugins/ci.py:299, qa_plugins/ckpt.py:33, repo_hygiene.py:108) -> tools/gitx.py; jsonl read/append (probe_db.py:130, ckpt/resume, qa_report history) -> tools/jsonl_io.py (flat-dir modules; orjson rejected).
**T6 files/accept:** `qa.py changed` shows about -80 LOC; `qa.py check --name tests,tools,quality`; `qa.py ckpt` and `qa.py resume` smoke.
**T6 risk:** low; signatures differ (root arg, env, timeout): keep the old names as re-exports for one step. guard_hook keeps its own subprocess use (stdlib-only hot path).
**T7 what:** qa_pool.py:17 imports asyncio (83 ms cumulative) -> `ThreadPoolExecutor` + `subprocess.run`; import probe_settings/lua_bridge (52 ms) lazily so brief/ctx/dead skip Lua.
**T7 evidence/accept:** warm `qa.py brief` 660 ms, `dead` 487, `affected` 462 vs 90 ms bare interpreter; cold import asyncio 145 ms vs threads+subprocess 79 ms. Accept: median of 5 `qa.py brief` runs at least 100 ms lower; a hung job still gets killed at its timeout.
**T7 risk:** low-medium: on Windows `subprocess.run(timeout=)` kills only the child, not its tree (use taskkill /T). ~65-150 ms x 45 calls = 3-7 s per session (INFERENCE on the call count).
**T8 what:** qa.py:397 cmd_golden CC43, :286 cmd_test CC42, :474 cmd_sweep CC29, :212 cmd_docs CC25 -> qa_plugins/{golden,test,sweep,docs}.py (auto-discovered); qa.py 698 -> ~150 LOC, the dispatcher imports only the plugin it runs.
**T8 files/accept:** `qa.py golden` shows no diff, `qa.py test --changed`, `qa.py sweep "..." --seeds 4`, `qa.py docs` output equal before/after; quality shows 4 fewer CC>=25 functions.
**T8 risk:** low. `_rerun_for_flakes` (qa.py:328) moves as is; pytest-rerunfailures rejected. Startup gain from lazy plugin import is unmeasured.
**T9 what:** effect_schema/validate.py:87 validate_op CC70, :28 validate_effect CC34, :178 _references CC21 -> one small validator per op kind + dict dispatch (drive it from the existing ops table if it covers the kinds: INFERENCE from tests/test_ops_table.py).
**T9 files/accept:** `python -m tools.effect_schema.itemcheck` over lua_content/items/ prints identical lines; `qa.py check --name items,tests`; every new function CC<=10.
**T9 risk:** medium: message texts are golden. pydantic/jsonschema rejected (semantic checks, import cost).
**T10 what:** probe_analysis.py:149 hypotheses CC51, :302 forecast CC49, :71 combat_stats CC35 are if/elif rule chains -> a `rules` table in lua_content/probe_config.lua (thresholds already live there) + a 30-line interpreter; the maths stays in probe_kernels (Rust RunAnalytics + twin).
**T10 files/accept:** `probe_db.py why` / `predict` on 3 recorded runs byte-identical; `qa.py golden`; `qa.py check --name tests`.
**T10 risk:** medium; Lua load is ~50 ms: load lazily and cache the JSON by mtime.
**T11 what:** fix B023 x10 (closure captures the loop variable: a real bug class) and BLE001 x34 (named exceptions, or `# noqa: BLE001` with a reason at true fail-open boundaries such as guard_hook).
**T11 files/accept:** `qa.py quality --worst 10` (tools scope) lists them. Accept: `improved=44`, tests green, then `--update-baseline`.
**T11 risk:** low; the fail-open behaviour of guard_hook is intended, annotate it instead of changing it.
**T12 what:** qa_plugins/ci.py:105 essentials CC64 and :311 resolve_run CC21 -> one parser per failing-step kind (pytest / cargo / ruff / generic) in a dict; regexes into a `ci` table in qa.lua.
**T12 files/accept:** `qa.py ci` output on 3 stored logs (dev_probe_output/qa/ci_*.log, saved before the change) identical; each function CC<=10.
**T12 risk:** medium: only testable on stored logs; copy 3 as fixtures into tests/.

## Order of work (each step: one commit, verified by `qa.py check`, then `qa.py test --changed`)
1. T1 ratchet FIRST: clean tree = ok, dummy violation = FAIL, commit the tools baseline. Every later step must lower or hold it; a step that raises a number is reverted (never `--force`).
2. T2 archive (tag first) -> quality prints `improved=`, run `--update-baseline`. Then T3 as its own commit (owner may veto it).
3. T4 ruff autofix, T5 globs, T6 helpers, T7 startup: independent small commits, in this order.
4. T8 slim qa.py, then T9, T10, T12 by CC descending, T11 lint review; each checked by identical before/after output on saved inputs (`qa.py golden`, itemcheck, stored ci logs).
5. T13 only after the benchmark gate below; T14, T15, T16, T17 last (god-module splits need T1 + T6; keep re-export shims for one step; verify with `qa.py golden` and `tools/trace_compare.py`).
6. Whenever a tool is added or removed: `qa.py tools --write` (check:tools fails on drift) and `qa.py docs` for stale .md.

## Delete/archive list (importer evidence)
- tools/plugins/ (14 files, 4437 LOC): only importer is tests/test_ai_systems.py:18 (ai_behavior_analyzer); the other grep hits are ai_evolve/core/hot_reload (its own relative import) and 4 report JSONs. Risks: agent_command_plugin.py:506 `exec(code, {'__builtins__': {}}, ...)`, network_remote_plugin.py:17,210 HTTP server.
- tools/dev_probe_async.py (566 LOC): no importer (grep over *.py); only lua_content/qa.lua:418 and docs name it. It does NOT load tools/plugins (no importlib/import_module/`tools.plugins` in it), so its registry purpose text is stale.
- tools/memory_reports/, tools/performance_reports/ (4 tracked JSONs with `/workspace/...` paths), tests/test_ai_systems.py, qa.lua rows :418 and :445, regenerate docs/TOOLS.md.
- AI-EVOLVE/ (24 tracked files) and ai_evolve/ (116): `qa.py dead` lists dev_probe/plugins 2129, core 638, data_layer 527, ai_evolve/plugins 540 LOC; `ai_evolve` is imported by nothing in src, tools, tests, main.py.
- KEEP (audit said archive): tools/training_room.py, imported by tests/test_training_room.py:16 and run in CI (.github/workflows/ci.yml:42 lists test_training_room_effectschema). The two demo scripts are `status = demo` in qa.lua: confirm with `qa.py dead --list` first (unverified).
- Out of tools/ scope: dead game code src/core/contracts (1114 LOC) and src/systems/ai (1111 LOC) from `qa.py dead`.

## Rust / Lua / parallel plan
- Yes, Rust threads are real (no GIL): `rayon` `par_iter` inside a `#[pyfunction]`, wrapped in `py.detach(|| ...)` (PyO3 0.29 name of allow_threads). Already there: `py.detach` at rust_core/src/ffi/mod.rs:384-428 (linear_fit, sparkline, nearest_distances, pinned_interval, stuck_interval). Missing: rayon in rust_core/Cargo.toml (0 hits). crates.io: rayon 1.12.0, MSRV 1.80.
- Where it does not pay: `qa.py check` is already process-parallel (qa_pool, one subprocess per check = every core, no GIL). Wall time is start-up (0.4-0.6 s per qa call), pytest 14 s on 12 shards and boot 6 s; kernels take milliseconds.
- Gate (T13): run `tools/bench_damage.py`, `tools/bench_pathfinding.py`, `qa.py sweep "..." --seeds 16`, `qa.py perf`; go only if a kernel is >10% of a check's wall or a call carries >=10^4 items.
- Candidates, in order: (1) QaKernels bootstrap CI (sweep is a high-cost check): parallel over resamples with per-resample seed f(seed, i), so the result is independent of thread count; the numbers change, so kernel + Python twin + golden move together. (2) resolve_hits batch damage: `par_chunks` over rows, ordered collect. (3) nearest_distances (:405) and find_path batches. Expected 3-8x on those kernels, 1-2 s check-wide (INFERENCE, not benchmarked).
- Constraints: Python twins stay bit-identical (check:damage, check:pathfinding compare them), ordered reduction, `RAYON_NUM_THREADS` pinned in CI; local cargo may be missing (memory note 2026-09-24): use `qa.py doctor`, else `qa.py ci`.
- Lua: rule tables of T10/T12 and thresholds go to lua_content (pattern already used by probe_settings/qa.lua), loaded lazily. Not Rust: import graph (mtime cache exists, qa_graph.py:32,138; warm `dead` = 487 ms) and ast.parse (C code holding the GIL: processes, not threads).

## Rejected (reason, evidence)
- "One boot path" merge of dev_probe/agent_play/training_room: probe_runtime is already the shared runtime (docs/TOOLS.md:112); training_room is a tested mannequin sim.
- lark/pyparsing (agent_play DSL), typer/click (23-30 argparse CLIs): CC comes from command dispatch, not grammar; adds imports.
- rich/tabulate for probe_db.py:189 (10 LOC): rich 15.0 is installed, but an import of tens of ms per call buys nothing.
- grimp for qa_graph: installed (3.17, Rust core) but `grimp.build_graph('qa_report','qa_graph')` raises NotATopLevelModule on the flat scripts dir (measured); qa_graph already uses Rust QaKernels.
- diskcache/joblib/tenacity/pydantic-settings/blake3/orjson: the cache key (import closure + env) is the value; no measured hashing or JSON cost.
- pytest-rerunfailures/xdist/testmon: qa.py has weighted shards (qa.py:275) and import-graph `--changed`; a rerun lib changes the qa_pytest_plugin JSONL rows. Revisit xdist only if pytest wall exceeds 30 s.
- Free-threaded 3.14t: wheel status unverified, single-thread slowdown 10-20% is INFERENCE; rayon is the safer route.
- Persistent qa worker / check reordering: no fork on Windows, global state threatens determinism, gain <= 4-6 s of an uncached 25-30 s run (INFERENCE). Revisit with a per-check timeline.
- Rust hash/graph pool (graph has an mtime cache), shared AST cache (5 parses/run unmeasured), sqlite result cache (race not evidenced: check.py:228 atomic write is unverified, S fix), porting probe_analysis stats to Rust (RunAnalytics already exists, unmeasured).
- guard_hook glob swap: +30 ms pathlib import on a 120 ms hook that fires on every tool call (measured).
