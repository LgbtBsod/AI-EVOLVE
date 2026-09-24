# AI-EVOLVE — notes for coding agents

Panda3D game. Python orchestrates; heavy number crunching lives in `rust_core/` (PyO3,
optional at runtime — every tool has a Python fallback); settings/content in `lua_content/`
(Lua 5.5 via `lupa.lua55`).

## Environment

- Python **3.14** (PEP 695 syntax in `src/`; 3.11 cannot even import `main`).
  `uv python install 3.14 && uv venv -p 3.14 .venv && uv pip install -r requirements-dev.txt`
- Optional: `uv pip install -r tools/requirements-dev.txt` (Pillow/OpenCV image extras),
  `uv pip install ./rust_core` (Rust kernels, needs cargo; ~13x faster analysis).

## Verify changes cheaply — pick the first tool that answers the question

| Question | Command | Cost |
|---|---|---|
| Combat/effects/leveling formulas | `python tools/combat_smoke_test.py` | 0.3 s, no window |
| Does the game boot (menu→world→plugins) | `xvfb-run -a python tools/boot_smoke_test.py` | 5 s, needs OpenGL |
| **Gameplay behaviour** (play like the player) | `python tools/agent_play.py "spawn enemy x3; until kills>=3 or dead max 90; expect alive"` | <1 s for minutes of game time, no GPU |
| Long unattended run + anomaly hunt | `python tools/dev_probe.py --render none --fast --seed 1 --duration 120 --action-at 1:1` | <1 s |
| Anything visual (rendering, labels, HUD) | `xvfb-run -a python tools/dev_probe.py --headless --fast --seed 1 --screenshot-interval 10` then Read `contact_sheet.jpg` only | a few s |
| Numbers across runs / "did my fix help" | `python tools/probe_db.py stats` · `why` · `predict` · `compare RUN_A` · `trend kills` | ms |

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
- Default dev map: enemies spawn ~160u from the hero and rarely reach him — a run without
  `spawn enemy` usually has no combat at all (hypothesis `NO_COMBAT`).

## Where things live

- `tools/probe_runtime.py` — boot (render window/offscreen/none), virtual fixed-step clock,
  data-model ADAPTER (`get_scene/get_entities`), `KillTracker`, combat recorder.
- `tools/probe_analysis.py` — rule-based hypotheses (symptom → cause → file) and forecasts.
- `tools/probe_kernels.py` — Rust/Python kernels; data crosses as columnar buffers
  (`array('d')`, `HeroTable` struct-of-arrays → one `scan_hero` FFI call).
- `rust_core/src/analytics/` — those kernels in Rust; `rust_core/src/probe/` — frame analysis.
- `lua_content/dev_tools.lua` — thresholds, agent limits, DB path; `lua_content/probe_config.lua` — frame analysis.
- Outputs go to `dev_probe_output/` (git-ignored), DB at `dev_probe_output/probe.sqlite`
  (override with env `AI_EVOLVE_PROBE_DB`).

## Tests

`python -m pytest -q tests/test_agent_tools.py` (3 s) covers the agent tools incl. determinism on the
real game; `cd rust_core && cargo test` + `pytest rust_core/tests/test_ffi.py` for Rust.
