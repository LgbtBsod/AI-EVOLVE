# Agent preamble - the token rules every agent prompt starts from

Every turn re-reads the whole context, so only two things are cheap: fewer turns and smaller results. `python tools/qa.py prompt ROLE --task "..."` points every agent at this file plus `docs/agent_context/<role>.md` (turn budget, stop rules, report contract; data in `lua_content/agent_kit.lua`).

1. **Batch.** Put ALL independent read-only calls (Read / Grep / Glob / `qa.py ctx` / `qa.py tools --find`) into ONE message. Only a dependent chain
   (grep -> ctx -> read a range) may take a second turn. The read guard nudges you when two single read-only calls follow each other.
2. **Never read a big file whole.** `python tools/qa.py ctx FILE` (outline, importers, tests), then Read with offset/limit around the symbol. An unranged Read
   over 250 lines is answered with the outline; repeat the same call once to force it. An unchanged re-read gets a one-line stub: use what you have.
3. **Never read raw dumps** (`state.jsonl`, `game.log`, `ci_*.log`, `dev_probe_output/**`): `python tools/probe_db.py stats|why`, `python tools/qa.py ci`, the RESULT line.
4. **Look before you build:** `python tools/qa.py tools --find "words"` before any new tool, script, check or plugin (`docs/TOOLS.md` lists all).
5. **Verify with ONE command:** `python tools/qa.py check`, then `qa.py test --changed`. Read the verdict line first; drill down only into a FAIL (its `repro:` line).
6. **Small verified steps:** one change, run the check, next change. Do not re-read a file you just edited (a failed Edit says so). `qa.py changed` instead of `git diff`.
7. **Environment:** project python is `.venv/Scripts/python.exe` (never `python3`: the Store stub hangs), relative paths from the repo root, LF files, no windowed game.
8. **Report:** the contract of your role file (<= 250 words; lines `files:` / `results:` / `unfinished:`); only what you ran; name what is uncertain. At the turn budget: hand off and stop. Off switch of the guard: `AI_EVOLVE_GUARD=off`.
