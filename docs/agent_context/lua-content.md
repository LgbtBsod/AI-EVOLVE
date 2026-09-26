# Role: lua-content - Lua data, items and rules under lua_content/

FIRST, in ONE message: `python tools/qa.py lua show FILE --keys` (structure, never the raw file), `python tools/qa.py item digest FILE` for an item,
`python tools/qa.py tools --find "words"`, `docs/EFFECT_SCHEMA.md` when you touch effects, `python tools/qa.py pack "TASK"`.

WORK
1. Data only: a file `return`s ONE table. Numbers, thresholds and text tables that Python reads live here, not in Python. Runtime is Lua 5.5 in a sandbox
   (`rust_core.LuaContent`, fallback lupa); the result crosses as one JSON string, so an empty `{}` is ambiguous (list or dict): avoid it where the type matters.
2. Prefer the Lua 5.1 / LuaJIT-compatible subset in data (no `//`, bit operators, `goto`, integer-subtype tricks); use 5.5-only syntax only where needed and say so.
3. Items: change the executable spec first (`tests/test_lost_my_self_spec.py` runs on the catalog AND `lua_content/items/`), then the item; regenerate Lua with
   `tools/effect_schema` (`ui_logic.to_lua`); never hand-edit generated item Lua. Semantics that are easy to get wrong: `docs/EFFECT_SCHEMA.md`.
4. A file that is a tool or a settings source gets a `-- tool: purpose` header line (registry), then `python tools/qa.py tools --write`.
5. Verify: `python tools/qa.py lua check` (every file loads), `python -m tools.effect_schema.itemcheck FILE`, `python tools/qa.py item diff FILE`,
   then `python tools/qa.py test --changed` and `python tools/qa.py check`.

STOP WHEN: `qa.py lua check` loads every file, the item spec passes, `qa.py check` shows no FAIL.

TURN BUDGET: 35 tool calls (soft). At the cap or after ~10 calls without a green check: write the handoff brief (files done / next / last green check) and stop.
RELAY: run `qa.py ckpt "step done" --next "..."` about every 10 calls and at the cap; at the cap write the handoff (`ckpt ... --next`), print `RELAY: continue with qa.py resume` as the LAST line of your report and stop. The caller continues with `qa.py prompt ROLE --task "continue: $(qa.py resume --brief)"`.

REPORT (<= 250 words, exactly these lines):
files: <Lua files you changed, one line>
results: <`qa.py lua check`, itemcheck, `qa.py test` and `qa.py check` lines, verbatim>
unfinished: <what is not done or not verified; the handoff brief if you hit the cap>
Claim nothing you did not run.
