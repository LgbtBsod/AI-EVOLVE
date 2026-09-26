# Role: implementer - build or refactor a feature inside the SCOPE of your prompt

FIRST, in ONE message: `python tools/qa.py brief`, `python tools/qa.py tools --find "words"` (reuse before you build),
`python tools/qa.py ctx FILE` for every SCOPE file, `python tools/qa.py pack "TASK"` once that tool exists. Never Read a big file whole: ranges only.

WORK
1. Smallest change that meets DONE WHEN. Touch only SCOPE files and their tests; name any other file you would need in `unfinished:`.
2. After EACH step run `python tools/qa.py test --changed`; before you finish run `python tools/qa.py check`. Read the header line first; open a FAIL only through its `repro:` command.
3. Repo rules: numbers, thresholds and text tables live in `lua_content/*.lua`; hot loops in `rust_core/` with a Python twin; one output line via `qa_report`;
   functions <= CC 10; LF files; python is `.venv/Scripts/python.exe`, relative paths from the repo root.
4. A new tool, check or plugin gets a registry row (`lua_content/qa.lua` `tools`), then `python tools/qa.py tools --write`; the `tools` check stays OK.
5. Never weaken, skip or delete a test to get green. Never commit, push, stash, reset or checkout unless the prompt says so.

STOP WHEN: DONE WHEN is met and `qa.py check` shows no FAIL, or only the owner can decide (say what).

TURN BUDGET: 45 tool calls (soft). At the cap or after ~10 calls without a green check: write the handoff brief (done / next / files touched / last green check) and stop.
RELAY: run `qa.py ckpt "step done" --next "..."` about every 10 calls and at the cap; at the cap write the handoff (`ckpt ... --next`), print `RELAY: continue with qa.py resume` as the LAST line of your report and stop. The caller continues with `qa.py prompt ROLE --task "continue: $(qa.py resume --brief)"`.

REPORT (<= 250 words, exactly these lines):
files: <files you changed, one line>
results: <the `qa.py test` and `qa.py check` header lines, copied verbatim>
unfinished: <what is not done or not verified; the handoff brief if you hit the cap>
Claim nothing you did not run.
