-- Fix-hints for `qa.py check`: a failing/warn line gains `| fix: CMD` (tools/qa_report.py apply_fixes).
-- HINT ONLY: nothing here is ever executed. First matching rule wins (order = priority).
-- check   = glob on the check name; pattern = regex on "detail lines + k=v metrics"; fix = ONE command; note = shown by `qa.py check --explain NAME`.
return {
  rules = {
    { check = "*", pattern = "CRLF|include_str", fix = "git add --renormalize .",
      note = "Lua/include_str! parity drift: a CRLF checkout differs from the LF blob; renormalize, then re-run the check." },
    { check = "golden", pattern = "golden recorded on", fix = "python tools/qa.py ci --wait",
      note = "Recorded on another OS: compare in CI. Do NOT re-record here." },
    { check = "golden", pattern = "differs|mismatch|identical=[0-9]+ total=[0-9]+", fix = "python tools/qa.py golden --record",
      note = "Only after an INTENDED behaviour change on the SAME OS as the recording; otherwise it is a regression: fix the code." },
    { check = "quality*", pattern = "improved=[1-9]", fix = "python tools/qa.py quality --update-baseline",
      note = "Locks the improvement in; never raise a number (that needs --force and an owner decision)." },
    { check = "tools", pattern = "undocumented=[1-9]", fix = "use: add a one-line purpose docstring to the file named above, then python tools/qa.py tools --write",
      note = "--write alone does not help: the tool must first say what it is for (docstring / help= / TOOL = {} / qa.lua tools.rows)." },
    { check = "tools", pattern = "(undocumented|drift|stale)=[1-9]", fix = "python tools/qa.py tools --write",
      note = "A tool needs a registry row in lua_content/qa.lua `tools`, then regenerate docs/TOOLS.md." },
    { check = "agent_kit", pattern = "fresh=(no|stale)|stale|drift", fix = "python tools/qa.py route --write-agents",
      note = "Regenerates .claude/agents/*.md from lua_content/agent_kit.lua." },
    { check = "static", pattern = "F821|undefined name", fix = "use: add the import; see file:line",
      note = "The first detail line names file:line of the undefined name; `qa.py static FILE` re-checks." },
    { check = "hygiene", pattern = "tracked=[1-9]|missing_ignore=[1-9]", fix = "git rm -r --cached PATH",
      note = "PATH = the offending path in the detail (venv, __pycache__, saves); add it to .gitignore too." },
    { check = "*", pattern = "ModuleNotFoundError|No module named|missing dep", fix = "python tools/qa.py doctor",
      note = "Prints the missing dependency and how to install it." },
  },
}
