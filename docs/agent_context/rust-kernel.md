# Role: rust-kernel - a hot loop in rust_core/ with a Python twin and a parity fuzz test

FIRST, in ONE message: `python tools/qa.py tools --find "words"`, `python tools/qa.py ctx FILE` (the Python twin), `docs/LANGUAGE_SPLIT.md` (twin first),
the closest parity test as the model (`tests/test_damage_pipeline.py`, `tests/test_pathfinding.py`), `python tools/qa.py pack "TASK"` once that tool exists.

WORK
1. Twin first: the Python twin defines the semantics and is the fallback without rust_core. Change the twin and its test before the Rust.
2. Rust in `rust_core/src/`: `#[pyclass]` / `#[pyfunction]` with a `///` first-sentence doc (the tools registry harvests it; add a `rust:NAME` row in `lua_content/qa.lua`).
3. Parity test: seeded random inputs plus edge cases (empty, zero, max, NaN/inf); Rust == twin bit for bit; the forced-twin switch (`AI_EVOLVE_DAMAGE=python`,
   `AI_EVOLVE_PATHFINDING=python`) must still pass with rust_core missing. A bench in `tools/` only when speed is the point.
4. Build from PowerShell, never Git Bash (Git's link.exe shadows MSVC). In EACH PowerShell call: refresh PATH from the registry, set `CARGO_TARGET_DIR` to
   `$env:LOCALAPPDATA/ai-evolve-cargo-target` and `PYO3_PYTHON` to the repo's `.venv/Scripts/python.exe`, then `cd rust_core; ../.venv/Scripts/python.exe -m maturin develop --release`.
   Do not pipe build output through `tail` (masks the exit code). Rebuild before every parity run: a stale extension passes for old code.
5. Verify: `cd rust_core; cargo test`, `pytest rust_core/tests/test_ffi.py`, the parity test, `python tools/qa.py test --changed`, `python tools/qa.py check`.

STOP WHEN: parity green both ways (Rust and forced twin), cargo test green, `qa.py check` no FAIL; or the toolchain is missing (report it, do not fake the result).

TURN BUDGET: 45 tool calls (soft). At the cap or after ~10 calls without a green check: write the handoff brief (twin state / Rust state / next command) and stop.
<!-- HOOK relay (roadmap step 4): replace the handoff brief by `qa.py ckpt "step done" --next "..."` -->

REPORT (<= 250 words, exactly these lines):
files: <files you changed, one line>
results: <`cargo test`, parity, `qa.py test` and `qa.py check` result lines, verbatim>
unfinished: <what is not built, not verified, or twin-only; the handoff brief if you hit the cap>
Claim nothing you did not run.
