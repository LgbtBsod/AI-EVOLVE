# Slice contract (implementer agents working on an effect-system slice)

Read this instead of re-deriving it. The task prompt only gives the DELTA (what to unblock); everything below is standing.

## Reading budget
- First command: `python tools/qa.py pack "<task words>" --files <a,b>` and read only the ranges it lists. Never read a file over 300 lines whole (`qa.py ctx FILE`, `qa.py sym FILE:NAME`, `qa.py q "grep:PAT@glob" "sym:F:N" "read:F:A-B"` = N queries in one call).
- Independent reads go into ONE message. Do not re-read a file you already read.

## Where a new effect kind touches the repo (checklist, in this order)
1. `src/effects/<family>.py` (new module for the family): the handler; register it in `OP_HANDLERS` (`src/effects/ops.py`); hooks on EffectManager (`manager.py`); `EffectRuntime` (`runtime.py`) only RECORDS the op (training room), document that divergence.
2. Schema: `src/effects/schema.py` and `lua_content/kinds/effect_core.lua` (kind rows); `tools/effect_schema/validate.py` (checker) and `tools/effect_schema/forge.py` (a `prim.<family>` row: the forge tests demand one).
3. Spec names that only differ from canon: `lua_content/kind_aliases.lua` (`exact=true` only when behaviour is identical); `canonical_kind` in ops.py resolves them.
4. Content = executable specs: real Lua rows in `lua_content/corpus_abilities.lua` (main corpus) or `lua_content/corpus_holdout_abilities.lua` (holdout), each with `corpus = <id>` and a `family` marker; `tests/test_effect_<family>_spec.py` proves each on EffectManager (two same-seed runs identical); earlier corpus tests filter by family (`tests/test_effect_forms_movement_spec.py`): keep their filters working.
5. Golden for the validator: `VALIDATE_OP_RECORD=1 python -m pytest tests/test_validate_op_parity.py` re-records `tests/fixtures/validate_op_golden.json`: ONLY for added rows, zero-error cases, report any changed old row.
6. Yardstick: `python tools/qa.py coverage [--corpus holdout]`; `+feature` names are recognised in `tools/qa_plugins/coverage.py`; raise `coverage.floor` / `coverage.holdout_floor` in `lua_content/qa.lua` (ratchet: never lower, never game it: a model-breaker keeps its `lacks`).
7. Docs: a short subsection in `docs/EFFECT_SCHEMA.md`, the status line in `docs/EFFECT_GAP.md` (and `docs/EFFECT_HOLDOUT.md` for holdout work).

## Hard rules
- Traces must stay identical: BEFORE your first edit `python tools/trace_compare.py --record <scratch dir>` (use `.venv/Scripts/python.exe`), after your LAST source edit compare ALL scenarios and count `same` vs total (never `tail`).
- No live wiring unless the task says so. Never re-record `qa.py golden` (recorded on Linux). Never `git stash`, no `git worktree`, no commit/push (the parent ships with `qa.py ship`). You are a sonnet agent: spawn nothing.
- Quality ratchet: new functions under CC 11; `qa.py quality --update-baseline` only to LOWER numbers and only after the final refactor.
- Small verified steps: `qa.py test --changed` after each. `qa.py ckpt "done" --next "..."` about every 10 calls; reserve the last 10-12 calls for the finish steps (golden rows, docs, floors, quality, trace_compare, `qa.py check --all --no-cache`); at the cap stop with `RELAY: continue with qa.py resume`.

## Report (<= 200 words)
Exactly the lines `files:`, `results:`, `unfinished:`. `results:` = `qa.py` header lines copied verbatim + the coverage lines + the trace_compare verdict as `n same / n scenarios`. Claim nothing you did not run; name every deviation (outside-scope edit, changed old golden row, weakened assertion) explicitly.
