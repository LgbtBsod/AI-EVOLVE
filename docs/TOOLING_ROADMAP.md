# Tooling roadmap: fewer tokens, less time per verified change (2026-09-26)

Scoring: benefit = kTok saved per trigger x frequency weight (every-turn 10, every-task 5, weekly 1, rare 0.2); ROI = benefit / cost (S=1, M=3, L=8).
Evidence base: transcript analysis of 2026-09-21..26 (Read 57% of tool tokens, 18 unbounded Reads >2.5k tok = 120k, `dev_probe.py` 64.6k tok over 6+ reads, 18 identical re-reads,
Bash 35% mostly mid-size outputs, subagent logs 2.4x main, ~1.9M tok lost once to a limit kill). Verified by the judge on 2026-09-26: no `.claude/settings.json` (zero hooks),
no `docs/TOOLS.md`, no `.pre-commit-config.yaml`; ruff runs only as the ratchet and `qa.lua:237` `select` omits F821/F811/E9; `qa.py ctx rust_core/src/lib.rs` answers
"not a project .py file"; `history.jsonl` has 100 rows; hypothesis/orjson/tree-sitter are not in any requirements file; twin-parity tests exist (`test_damage_pipeline.py`, `test_pathfinding.py`).
Library facts not re-checked online (PyPI pages did not load) are marked "verify".

## Ranked table (all output goes through `tools/qa_report.py`; thresholds and rules live in `lua_content/*.lua`)

| # | id | title | ROI | effort | depends on | libraries | Rust / Lua part | automation |
|---|----|-------|-----|--------|------------|-----------|-----------------|------------|
| 1 | guard-read | Read guard: ctx outline instead of big file, repeat-read stub, raw-log digest | 50 | S | hook-runner (same step) | none | Lua: thresholds, allow-globs | PreToolUse Read hook |
| 2 | static-gate | `static` check: ruff F821/F811/E9/F63/F7 + py_compile + actionlint + luajit -bl; edit lint | 30 | S | - (hook part: hook-runner) | ruff (have), actionlint-py (verify), lupa | Lua: check declaration | `qa.py check`, PostToolUse Edit/Write |
| 3 | tools-registry | generated `docs/TOOLS.md` + duplicate/drift detector (`qa.py tools`) | 20 | M | - (mandated first) | difflib (rapidfuzz optional) | Lua: metadata schema, sim threshold | `qa.py check` watches tools/**, CLAUDE.md |
| 4 | guard-bash | deny known-bad Bash forms with a one-line redirect | 20 | S | guard-read, registry | bashlex (optional) | Lua: deny table = registry "replaces" column | PreToolUse Bash hook |
| 5 | pack | `qa.py pack TASK`: 1.5k-tok context pack + "use tool instead" map | 17 | M | registry, sym-multi | rank-bm25 (optional) | Rust: existing graph kernel; Lua: budgets, answer map | called by agent-kit preamble |
| 6 | resume | `qa.py resume`: tree state after a kill (SAFE/RISKY/BROKEN) | 15 | S | - | none (git subprocess) | Lua: limits | SessionStart + Stop/SubagentStop hooks |
| 7 | agent-kit | prompt templates + model/effort routing table | 13 | M | registry | none | Lua: templates, routes, call budgets | `.claude/agents/*.md` generated |
| 8 | tokens | `qa.py tokens`: transcript waste ledger, trend in probe_db | 8 | M | guard log (optional) | orjson (verify) | Rust scan only if >2 s; Lua: patterns | SessionEnd hook, `brief` line |
| 9 | sym-multi | `ctx` for Rust/Lua + `qa.py sym FILE:func` | 5 | M | - | tree-sitter-language-pack (verify Py3.14 wheel) | Lua: none | guard outline uses it |
| 10 | fix-hints | `| fix: CMD` on failing check lines (never auto-run) | 5 | S | registry | ruff --fix | Lua: `fixes` table | `qa.py check` |
| 11 | rewrite | `qa.py rewrite`: dry-run-first structural codemods | 5 | M | registry | ast-grep-cli, libcst (verify) | Lua: named codemods | on demand |
| 12 | trend | median-of-20 duration/flip warning | 2 | S | - | none | Lua: thresholds | warn line in `check` |
| 13 | health | weekly pip-audit warn + typos on docs | 1 | S | - | pip-audit, typos | Lua: allowlist | nightly CI |
| 14 | kernel-spike | Python-subset to Rust/Lua converter (spike only) | 1 | L | twin-fuzz | hypothesis, lupa | generated Rust / LuaJIT | CI regen + fuzz |

## Specs for the top 12

**1 guard-read** `python tools/qa.py guard read` (hook, JSON on stdin). Evidence: 120k tok of unbounded Reads, 18 identical re-reads.
- Prints: deny (exit 2, stderr, <=6 lines) `GUARD read denied 46k chars | outline: <top 20 ctx lines> | retry with offset/limit (2nd identical call passes)`; repeat `GUARD unchanged since turn N`; raw logs (`state.jsonl`, `game.log`, Temp `*.output`) get head 20 / tail 40 / RESULT-line digest.
- Files: `tools/qa_plugins/guard.py` (stdlib only, import-light), `lua_content/guards.lua` (compiled by `qa.py check` to `dev_probe_output/qa/guards.json` so the hook never boots Lua), `.claude/settings.json`, `tests/test_guard.py`, log `dev_probe_output/qa/guards.jsonl`.
- Accept: 900-line file without limit -> exit 2 + outline; with limit -> exit 0; second identical call passes; hook p95 < 150 ms on Windows; `AI_EVOLVE_GUARD=off` disables.
- Risks: blocks a legitimate full read (retry-once rule); "already read" is false after /compact (expire entries on PreCompact); hook must call `.venv/Scripts/python.exe` (bare `python3` is the hanging Store stub).

**2 static-gate** `python tools/qa.py check --name static` (also in `--fast`). Evidence: the lost `import re` incident; ratchet select has no F821/F811/E9; workflows and Lua are unlinted.
- Prints: `ok static ruff=0 py_compile=0 actionlint=0 lua=0 files=7 dur=0.4s` or `FAIL static F821 undefined name 're' tools/x.py:12 | repro: ruff check --select F821 tools/x.py`.
- Files: entry in `lua_content/qa.lua` (`checks`, cost=low, watches src/**, tools/**, .github/**, lua_content/**), `tools/qa_checks/static.py` (changed files only), PostToolUse branch in `guard.py` (silent when clean).
- Accept: temp file using `re` without import -> FAIL with file:line; clean tree -> ok in < 1 s; missing actionlint/luajit -> `skip` plus a `doctor` hint.
- Risks: binaries not installable on Windows (skip, never fail); noise (keep to F821,F811,E9,F63,F7,F82).

**3 tools-registry** `python tools/qa.py tools [--write|--check]`. Evidence: owner rule; 9 plugins + ~20 scripts documented by a hand-written CLAUDE.md table and the `qa.py` epilog (drift); no registry exists.
- Prints: `QA verdict=WARN tools=41 undocumented=3 dup-suspects=1 drift=2` then <=10 lines `WARN dup ctx~sym sim=0.71 | fix: extend ctx instead`.
- Files: `docs/TOOLS.md` (generated: name, command, answers, replaces raw action, output line, owner file), `tools/qa_plugins/tools.py`, `lua_content/qa.lua` `tools` (required keys, threshold, manual rows for standalone scripts), `tests/test_tools_registry.py`; `--write` also refreshes a marked block in CLAUDE.md.
- Accept: plugin without docstring -> FAIL; new plugin 0.7-similar to an existing one -> dup line; CLAUDE.md command that is not a real subcommand -> drift line.
- Risks: boilerplate (auto-derive from docstrings and `register(sub)` help, FAIL only on missing purpose); similarity false positives (warn only).

**4 guard-bash** `python tools/qa.py guard bash`. Evidence: 21 commands with sleep, 2 Store-stub hangs, hand-read raw CI logs, backtick heredoc executed text; only 15 outputs >2k tok, so deny bad forms rather than truncate.
- Prints: one line per rule, e.g. `GUARD bash denied: python3 -> .venv/Scripts/python.exe`, `gh run view --log -> qa.py ci`, `sleep loop -> run_in_background/Monitor`, `cat *.jsonl|game.log -> probe_db.py`, `unquoted C:\ path -> quote it`.
- Files: `lua_content/guards.lua` `bash` rules (`pattern, say, allow`), branch in `guard.py`, table-driven `tests/test_guard.py`.
- Accept: 12 sample commands (denied vs allowed); `# allow:python3` passes; every deny is logged.
- Risks: false denies (allow token + env off); regex misses (bashlex later); over-1.5k-tok output hint is warn-only.

**5 pack** `python tools/qa.py pack "TASK" [--files a,b] [--budget 1500]`. Evidence: subagent logs 2.4x main; each spawn explores from scratch.
- Prints: `PACK files=5 tokens=1.2k`, top-5 files with only relevant symbol line ranges, importers/tests, failing checks, `verify: CMD`, `use tool instead: qa.py determinism ...` (Lua answer map: ci, flaky, dead, slow), `do NOT read: stale docs, dead modules`.
- Files: `tools/qa_plugins/pack.py` (reuses ctx, affected, changed, dead, docs), `qa.lua` `pack`, tests.
- Accept: "port toughness to damage pipeline" ranks `src/effects/damage.py` and its test in the top 3 within 1.5k tok; "why did CI fail" -> `qa.py ci`.
- Risks: wrong ranking hides the real file (always print the `ctx FILE` fallback, log hit rate); needs sym-multi for slices.

**6 resume** `python tools/qa.py resume` (`--hook` silent when clean). Evidence: kills by session/weekly limit, tree state unknown, red merges by parallel sessions.
- Prints <=6 lines: `RESUME verdict=RISKY head=540153e dirty=5 behind=2 last=FAIL play:swarm age=3h`, `orphan: src/x.py (untracked, 0 importers)`, `broken: F821 tools/y.py:14`, `next: CMD`.
- Files: `tools/qa_plugins/resume.py`, Stop/SubagentStop hook writing `dev_probe_output/qa/resume.json`, SessionStart hook, `brief` line, tests. Phase 2: `refs/qa/ckpt/N` checkpoints (cap 20).
- Accept: temp repo with an orphan file and a syntax error -> BROKEN naming both; clean repo -> no output in `--hook`.
- Risks: stale json after a hard kill (print age); never restore over dirty work.

**7 agent-kit** `python tools/qa.py prompt ROLE --task T --files F` and `qa.py route "TASK"`. Evidence: 1.5-2k tok prompts retyped; repeated Windows gotchas.
- Prints: rendered prompt <=400 tok (venv path, own tools first, one-format rule, call budget, "return only the QA line", pack) / `ROUTE stage=run_check model=small effort=low turns=10 tool_can_answer=qa.py check`.
- Files: `lua_content/agent_kit.lua` (preamble, roles, routes, budgets), generated `.claude/agents/*.md`, `tools/qa_plugins/prompt.py`.
- Accept: every command named in a template parses via `qa.py --help`; route table covers every stage of the workflow script.
- Risks: template drift (generated + checked); misroute (escalate one tier on FAIL); model names are mapped by the harness, not the repo.

**8 tokens** `python tools/qa.py tokens [--session latest] [--subagents] [--top 8]`. Evidence: waste was found once by a bespoke scan; without a ledger steps 1-7 cannot be proven.
- Prints: `QA verdict=WARN waste=210k of 680k tok~ (chars/4)` then one line per pattern (unbounded reads, repeats, big Bash, sleep polls, retries, subagent share, top files) each with its replacement command; a row goes to SQLite (`probe_db trend`).
- Files: `tools/qa_plugins/tokens.py`, `qa.lua` `tokens`, synthetic-JSONL test; Rust kernel only if the scan exceeds 2 s.
- Accept: synthetic transcript with 2 identical Reads + one 60k-char Read -> 2 flagged lines; real 15 MB session < 3 s.
- Risks: undocumented transcript schema (tolerant parser, counts labelled approximate); local only.

**9 sym-multi** `python tools/qa.py ctx FILE.rs|FILE.lua`, `qa.py sym FILE:func`. Evidence (verified): ctx rejects non-.py; ctx already gives line numbers, so sym adds only a callers/callees footer.
- Prints: same outline format (`L40 pub fn ...`, `#[pyfunction]` -> Python twin, Lua top-level keys/functions); sym = numbered slice <=60 lines + `callers(static)`.
- Files: `tools/qa_plugins/ctx_lang.py`, ctx dispatch, tests. Accept: outline of `rust_core/src/lib.rs` lists pyfunctions with twin paths.
- Risks: Lua data files have few functions (reuse `lua show --keys`); grammar wheel on Py3.14 (verify; regex fallback).

**10 fix-hints** no new command; failing lines gain `| fix: CMD`. Evidence: CRLF/`include_str!` parity, golden re-record, baseline update were diagnosed by hand; quality hints exist (`qa.lua:279`).
- Prints: `FAIL lua_parity crlf drift | fix: git add --renormalize . | repro: ...`. Files: `lua_content/fixes.lua`, `Result.fix` in `qa_report.py`, tests.
- Accept: seeded CRLF file -> fix shown, nothing executed. Risks: masking bugs (hint only; golden/baseline fixes need explicit flags).

**11 rewrite** `python tools/qa.py rewrite PATTERN REPL --lang py [--apply]`. Evidence: 81 blind excepts + 4 duplicate classes = many identical edits.
- Prints: `REWRITE matches=40 files=12 (dry-run)` + 10-line diff summary; `--apply` then runs `check` on touched files. Files: `qa_plugins/rewrite.py`, `qa.lua` `codemods`.
- Accept: blind-except pattern count equals the baseline; `--apply` refused on a dirty tree. Risks: mass edits (dry-run default); do it only when a burn-down is scheduled.

**12 trend** `qa.py trend` + a `warn trend tests dur=+34% vs median(20)` line inside `check`. Evidence: 100 unused history rows; a same-seed flake cost hours.
- Files: `check.py` hook, `qa.lua` thresholds. Accept: synthetic history flags one slow check and one flipping check. Risks: CI timing noise (median + 3-run confirm). `check` already prints `(-22%)` vs the previous run; this adds only median-of-20 and flips.

## Implementation order (REVISED 2026-09-26: sub-agent cost first - agents cost 2.4x the main session)

Every step: one output line via `qa_report`, thresholds in Lua, a pytest file, an auto-generated registry row, no growth of CLAUDE.md beyond one pointer line.

**A. Agent-cost levers (do these first, in this order)**
1. **tools-registry** - DONE (docs/TOOLS.md, `qa.py tools --find`).
2. **guard-read + hook-runner + batch-nudge** - DONE (`qa.py guard`, `tools/guard_hook.py`, `lua_content/guards.lua`, `docs/agent_context/preamble.md`; hooks installed in soft mode in `.claude/settings.json`). OPEN: the hooks docs say PreToolUse fires for SUBAGENT tool calls (payload carries `agent_id`; the guard keys its state by it) - confirm in a live session: `qa.py guard --stats` must show rows with `sub=1` in `dev_probe_output/qa/guards.jsonl`, else the same rules must live in the agent preamble.
3. **agent-kit**: `docs/agent_context/*.md` (preamble + role files) referenced by short prompts, `qa.py prompt ROLE`, `qa.py route` (model/effort/turn budget per stage: cheap model + low effort for running tests, summarising logs, mechanical edits; strong model only for design), the `batch-rule` text, and the standard report contract (<= 250 words, fixed lines).
4. **agent-relay**: cap an agent at ~40-50 tool calls and hand off through the checkpoint journal to a FRESH agent (per-turn cost grows with context length, so N turns cost about N^2; two agents of N/2 turns cost about half). Needs `resume` + `checkpoint` (`qa.py ckpt "step done" --next "..."` writes the journal + a git stash-create ref); the agent prompt tells it to checkpoint every ~10 calls and to stop at the cap with the handoff brief.
5. **resume** (+ SessionStart/Stop hooks, journal): SAFE/RISKY/BROKEN, orphan modules, next command; makes relays and limit crashes cheap.
6. **q** (batched read-only queries in ONE call) and **sym-multi** (`qa.py sym FILE:func`, ctx for Rust/Lua): agents read less and use fewer turns (59% of agent turns are in read-only runs).
7. **pack** (`qa.py pack TASK`: ~1.5k-token context pack + do-not-read list) - the payload of every agent prompt.
8. **tokens** with per-AGENT rows (turns, tool calls, calls/turn, peak context, biggest reads; trend) - the yardstick for 2-7; run it before and after each step.
9. **static-gate** (F821/F811/E9 + py_compile + actionlint + luajit -bl) and **guard-bash** (python3 stub, `gh run view --log`, sleep loops, backtick heredocs, backslash paths): fewer agent errors and retries.
10. **fix-hints** (`| fix: CMD` on failing check lines), **edit / new / note** (writing tools), **trend**.

**B. On demand only:** rewrite (ast-grep/libcst), health, kernel-spike.

## Rejected / duplicates

- 8 read-guard variants from 4 lenses (read-guard, repeat-read-cache, big-read-outline, scratch-dump-cap, readguard, read-guard-hook, hook-pretool-guard, bash-output-budget): merged into 1 and 4.
- preflight (scope/budget verdict): budget is not machine-readable; the "one workflow at a time" memory rule exists; the USE_TOOL part lives in pack.
- agentcache: no measured repeat-audit rate; `check` already caches by content hash; revisit after `tokens`.
- hotspot-risk (pydriller): `qa.py changed` prints RISK flags; 51 commits are too few; the origin-drift signal moved into resume.
- context-slim nag hook: the harness compacts; nag fatigue; the number comes from `tokens`.
- qa-where: duplicates the built-in Grep, `ctx` and `lua show --keys`; no measured search-driven waste.
- qa-impact (L): `affected` covers files; dynamic dispatch yields false negatives; cost 8 for unproven gain.
- pre-commit + typos: duplicates `qa.py check`/`hygiene` and ci.yml; bots bypass `--no-verify`. Owner action instead: make the `qa.py check --ci` job a required status on main.
- qa-fix-signatures auto-apply engine: masks bugs; only fix-hints kept. tooling-accel (Rust hash/graph): no profile shows a >1 s hotspot (run `qa.py perf` first). SessionStart quick-start injection: subagents already load CLAUDE.md. detect-secrets/pip-licenses: no incident evidence.

## Python->Lua/Rust converter: verdict and spike plan

Verdict: NO-GO for a general converter; a timeboxed spike on a scalar-numeric subset is allowed only after the parity fuzz, and not before the playable loop is solid (anti-spiral rule).
- py2many has no Lua target (README checked 2026-09-26: Rust, C++, Go, Zig, Julia, Nim, Dart; Rust most mature, subset undocumented); mypyc/Nuitka/Cython emit CPython extensions, not Rust or Lua.
- `src/effects/ops.py` (930 lines, 119 defs, imports `re`, dataclasses) is a handler registry, not numeric code; only `damage.py` (409 lines) is a plausible subset. The three existing twins already have parity tests; the real incident class was drift (stale rust_core wheel), which a fuzz harness fixes without a generator.
- LuaJIT is the Lua 5.1 dialect while `lua_content` runs on Lua 5.5 (mlua): a generated kernel needs its own 5.1 emitter (no `//`, no integer subtype, no bit operators) and must not mix with content files. The `_eff` hotspot (439k calls) in `docs/LANGUAGE_SPLIT.md` is a hand-written Rust `EffectKernel` job, not a converter job.
- Spike (2 days, owner approval): step 0 hypothesis differential fuzz Python vs Rust vs Lua twins (useful alone). Step 1 `# @kernel` ast linter (float/int/bool, list[float], scalar dataclass, if/for/while, `math.*`; no classes, closures, exceptions, str) over `damage.py`. Step 2 emit Rust (PyO3 fn) and Lua 5.1, fuzz 1e5 cases within 1 ulp via lupa/LuaJIT.
- Go only if: >=90% of `damage.py` functions lint in-subset, 0 divergences at 1e6 cases, generated Rust within 1.3x of hand-written (`bench_damage.py`), generated Lua >=3x faster than the Python twin. Otherwise stop and keep hand-written twins plus the fuzz.

## Addendum 2026-09-26: writing tools (owner request; evidence measured on the session transcript)

What the agent WRITES costs as much as what it reads: 225k tokens of tool-call input vs 295k of results. Split: `Edit` 58k tok (192 calls; **32% of it is `old_string`** - text re-typed only to locate the spot; `dev_probe.py` alone was edited 90 times), `Workflow` scripts 42k (18.7k per call: the shared context is inlined every time), `Write` 32k, agent prompts 15k, Python-heredoc file/memory edits 14k.

| id | idea | expected saving | effort | depends on |
|---|---|---|---|---|
| `edit` | `qa.py edit FILE (--symbol NAME \| --range A:B \| --after-symbol NAME \| --append) < new_text`, plus `--batch FILE` (several anchored edits, applied bottom-up). Locates by symbol/range (ast for .py; tree-sitter later for .rs/.lua), never by re-typed old text; validates after writing (py_compile + ruff F821/E9, `luajit -bl` for Lua) and prints ONE line `edit ok file.py 120-135 -> 118 lines, static ok`. Refuses if the file changed since `sym`/`ctx` printed the range (hash guard). | ~19k tok/session from `old_string` alone; fewer failed Edits (exact-match misses) | M | tools-registry, static-gate |
| `new` | `qa.py new check\|plugin\|test\|scenario\|kernel NAME` scaffolds a file from templates that already follow the conventions (uniform output, registry row, test skeleton, Lua declaration). | boilerplate of every new tool/test (~1-2k tok each) + guaranteed documentation | S | tools-registry |
| `note` | `qa.py note memory\|journal SECTION "text"` appends/replaces a section in the memory files / checkpoint journal without a Python heredoc. | ~14k tok/session | S | - |
| `agent-kit` (raised) | Shared agent/workflow context lives in repo files (`docs/agent_context/*.md`, rendered by `qa.py prompt ROLE`); a Workflow script and every agent prompt only says "read docs/agent_context/X.md first". | up to ~57k tok/session (Workflow scripts + agent prompts = 25% of everything written) | M | tools-registry |

Order: `note` and `new` right after `guard-read` (both S); `edit` after `static-gate` (it reuses it); `agent-kit` moves in front of `pack`. Agents use the same CLI; every one is a row in docs/TOOLS.md.

### Addendum 2 (2026-09-26): batching beats cheaper greps - agents pay per TURN, not per search

Measured on the transcripts (grouped by assistant message id): main session 790 turns, 1.13 calls/turn, only 10% multi-call turns; 226 turns (28%) sit in runs of consecutive read-only turns that could have been one. Agents: 37 turns per agent, 1.27 calls/turn, 18% multi-call; up to 805 of 1356 turns (59%) sit in read-only runs (upper bound: later reads may depend on earlier results; assume about half). Every turn re-reads the whole context, so cutting turns is the biggest lever for the agents, which cost 2.4x the main session.

| id | idea | saving | effort |
|---|---|---|---|
| `batch-rule` | Free, do first: agent preamble + CLAUDE.md say "put ALL independent read-only calls (Read/Grep/Glob/qa.py ctx/sym) into ONE message"; the guard hook nudges when two read-only single-call turns follow each other. | up to ~15-30% of agent turns | S |
| `q` | `qa.py q "grep:PAT@glob" "sym:file.py:func" "ctx:file" "read:file:120-160" "find:GLOB" "changed" ...` runs N read-only queries in parallel in ONE call and prints one grouped, capped output (grep -> outlines of the matching files in the same call). Replaces dependent chains (grep -> ctx -> read range) that today cost 3 turns. Built on rg + the ctx/sym outlines; thresholds in lua_content/guards.lua. | the dependent chains the batch-rule cannot cover; ~10-20% of agent turns | M |

Order: `batch-rule` inside step 2 (guard-read) and agent-kit; `q` right after `sym-multi` (it needs `sym`). Re-run the turn statistics after each step (`qa.py tokens` will report calls/turn and read-only run length as first-class metrics).
