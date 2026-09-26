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
   Symbols/chains: `qa.py sym FILE:NAME [--callers]` (one function, numbered) and `qa.py q "grep:PAT@glob+ctx" "sym:F:N" "read:F:A-B"` (a grep -> outline -> range chain in ONE call).
9. **Relay:** long agents cost more per turn, so work in short relays: `qa.py ckpt "done" --next "..."` about every 10 calls; at your call cap write the handoff the same way, end with the LAST line `RELAY: continue with qa.py resume` and stop. Start of a continuation: `qa.py resume` (silent when nothing is unfinished).
10. **Yardstick:** `qa.py tokens [--agents]` shows your turns, calls/turn and batchable read-only runs from the transcript; the goal is more calls per turn, no unbounded or repeated reads.
12. **Guard hints are fixes:** a `GUARD bash denied` / `GUARD lint` message names the replacement command or the `file:line` to fix; follow it instead of repeating the call (`qa.py static FILE` re-checks).
11. **Pack first:** `python tools/qa.py pack "TASK" [--files a,b]` = ranked files with line ranges, importers/tests, existing tools, verify command and a do-not-read list in ~1.5k tokens: read it instead of exploring.
13. **Workflows:** `qa.py wf new NAME` before writing one; always `agentType` on `agent()` (67k vs 12k cold start per agent); explorers write their own file section, the script assembles (`qa.py wf assemble`); `qa.py wf estimate` before running.
