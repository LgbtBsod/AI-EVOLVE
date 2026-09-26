-- tool: settings of the tool-call guards of Claude Code hooks (tools/guard_hook.py, `qa.py guard`): thresholds, path patterns and message templates.
-- Compiled by `qa.py guard --compile` (the hook recompiles it itself when this file changed) to dev_probe_output/qa/guards.json: the hook never boots Lua.
-- Disable: env AI_EVOLVE_GUARD=off (one shell) | mode = "off" below (everyone) | `qa.py guard --uninstall` (removes the hook entries from .claude/settings.json).
-- Patterns: `glob` = .gitignore-like on the lower-cased forward-slash path (`**` any depth, `*` inside a name); regexes are Python `re`.
return {
  -- soft: a denied call passes when the SAME call is repeated within `window_s` (a guard can never dead-lock a session);
  -- log: decide and log, never block (dry run); off: allow everything.
  mode = "soft",
  window_s = 600,
  chars_per_token = 3.5,                   -- token estimate for the saved-context statistics
  state = { path = "guard_state.json", ttl_s = 21600, max_entries = 1500 },   -- files live in dev_probe_output/qa/ (or $AI_EVOLVE_GUARD_OUT)
  log = { path = "guards.jsonl", max_kb = 512 },

  -- READ GUARD: an unranged Read of a big file is answered with its outline instead of its text.
  read = {
    min_lines = 250,                       -- more lines than this (and no limit) -> deny with the outline
    min_bytes = 30000,                     -- or more bytes than this (long lines)
    ranged_max_lines = 600,                -- a Read with a limit up to this passes as "ranged"; a bigger limit counts as unranged
    default_lines = 2000,                  -- what a Read without limit returns at most (the Read tool's own cap)
    max_scan_bytes = 8000000,              -- a bigger file is judged by its size alone (never read whole by the guard)
    outline_lines = 40,                    -- the whole deny message, outline included
    sym_file = "tools/qa_plugins/sym.py",  -- when this file exists the retry hint also names `qa.py sym FILE:func`
    allow = { "**/.claude/**", "**/memory/**", "**/memory.md", "**/claude.md", "**/skill.md", "**/agents.md" },   -- always pass
    binary_ext = { "png", "jpg", "jpeg", "gif", "webp", "bmp", "ico", "pdf", "ipynb", "svg", "mp3", "wav", "ogg", "mp4", "zip", "gz", "whl", "so", "pyd", "dll", "exe",
                   "bam", "egg", "sqlite", "db", "ttf", "otf", "woff", "woff2" },
  },

  -- REPEAT-READ STUB: a second Read of an UNCHANGED file (content hash) in the same context returns a one-line stub.
  repeat_read = { enabled = true, min_chars = 2500, max_ranges = 8 },   -- smaller reads are cheaper than the stub's extra turn

  -- RAW-LOG GUARD: raw dumps are answered with the command that digests them plus a small head/tail sample.
  raw = {
    max_bytes = 6000, ranged_max_lines = 200, head = 6, tail = 8, line_cap = 200,   -- sample = head + tail lines (<= 15 with the `...` row)
    skip = { "**/*.md", "**/repro.sh", "**/*.txt" },        -- summaries meant to be read
    rules = {                                               -- first match wins
      { glob = "**/state.jsonl",             digest = "python tools/probe_db.py stats | why RUN | compare RUN | sql \"SELECT ...\"" },
      { glob = "**/game.log",                digest = "python tools/probe_db.py why RUN  (or the RESULT line of the run)" },
      { glob = "**/ci_*.log",                digest = "python tools/qa.py ci [--sha S | --run ID]  (verdict + the failing step only)" },
      { glob = "**/dev_probe_output/qa/*.jsonl", digest = "python tools/qa.py guard --stats | qa.py check (history is summarised there)" },
      { glob = "**/dev_probe_output/**",     digest = "the RESULT line of the run, `python tools/probe_db.py stats`, summary.md; never the raw dump" },
      { glob = "**/*.jsonl",                 digest = "the tool that owns this file, or Read with offset/limit near the part you need" },
      { glob = "**/tasks/*.output",          digest = "Read with offset/limit near the END of the file (the result is at the bottom)" },
      { glob = "**/*.output",                digest = "Read with offset/limit near the END of the file (the result is at the bottom)" },
    },
    bash_cat = [[^\s*(?:cat|type|more|less)\s+(?:--\s+)?(?P<path>"[^"]+"|'[^']+'|[^\s|;&<>]+)\s*$]],   -- `cat FILE` counts as an unranged Read
  },

  -- BASH GUARD: known-bad command forms are denied once with the replacement command (soft: the identical repeat passes; `# allow:ID` in the command passes at once).
  -- Each rule: id, pattern (Python `re`, searched in the whole command text), say = the fix (replaces = the tool-registry `replaces` column in lua_content/qa.lua).
  bash = {
    enabled = true,
    rules = {
      { id = "python3", pattern = [[(?:^|[\s;&|(])python3(?:\.\d+)?(?=\s|$)]],
        say = "`python3` is the Windows Store stub and hangs: use `.venv/Scripts/python.exe` (or `python` from the activated venv)." },
      { id = "gh_log", pattern = [[\bgh\s+run\s+(?:view\b[^\n]*--log|download\b)]],
        say = "raw CI logs cost 10k+ tokens: use `python tools/qa.py ci [--wait] [--sha S | --run ID]` (verdict + the failing step only; cleaned log in dev_probe_output/qa/ci_<run>.log)." },
      { id = "sleep", pattern = [[\bsleep\s+(?:3[1-9]|[4-9]\d|\d{3,})(?![\d.])|\b(?:until|while)\b[^\n]*\bsleep\b]],
        say = "no sleep/poll loops: use `run_in_background` (you are re-invoked on exit), the Monitor tool with an until-loop, or `python tools/qa.py ci --wait`." },
      { id = "raw_cat", pattern = [[^\s*(?:(?:head|tail|less|more|type)\b|cat\s+(?:-\S+\s+|[^\s|;&<>]+\s+[^\s|;&<>]))[^|;&\n]*(?:\.jsonl\b|game\.log\b|dev_probe_output/)]],
        say = "raw dumps: `python tools/probe_db.py stats|why RUN|sql \"SELECT ...\"` for runs, `python tools/qa.py tokens` / `qa.py guard --stats` for transcripts and guard logs." },
      { id = "heredoc", pattern = [[<<-?[ \t]*[A-Za-z_]\w*[^\n]*\n[\s\S]*(?:`|\$\()]],
        say = "an unquoted heredoc delimiter executes backticks and $( ) in the body: quote it, `<<'EOF'`." },
      { id = "winpath", pattern = [[\bpython[\w.-]*\s+(?:\S+\s+)*?[A-Za-z]:\\\S]],
        say = "a bare backslash Windows path as a python argument loses its backslashes in bash: use forward slashes (`C:/x/y.py`) or a path relative to the repo root." },
    },
  },

  -- POST-EDIT LINT (PostToolUse Edit|Write|NotebookEdit): a syntax error / undefined name in the edited .py file comes back as additionalContext (never blocks).
  post_edit = { enabled = true, exts = { "py" }, select = "F821,F811,E9", timeout_s = 5, max_lines = 6 },

  -- BATCH NUDGE (additionalContext, never a deny): two single read-only calls in a row -> "put independent read-only calls into ONE message".
  batch = {
    enabled = true, prior_turns = 2, cooldown_s = 90, lookback_bytes = 262144,
    readonly_tools = { "Read", "Grep", "Glob" },
    readonly_bash = [[^\s*(?:\S*python\S*\s+)?(?:\./)?tools/qa\.py\s+(?:ctx|sym|brief|changed|tools|docs|dead|affected|lua\s+show|item\s+digest|guard\s+--(?:stats|explain))\b[^;&<>]*$|^\s*(?:ls|cat|head|tail|wc|grep|rg|find|git\s+(?:status|diff|log|show|branch)|pwd)\b[^;&<>]*$]],
  },

  -- OUTLINE of a denied file: Python via ast (tools/file_toc.py), other languages via these regexes (group 1 = the name shown).
  outline = {
    head_lines = 12,                       -- files without a known outline: the first N lines
    by_ext = {
      lua = { [[^\s{0,2}(?:local\s+)?function\s+([\w.:]+)]], [[^\s{0,2}([A-Za-z_]\w*)\s*=\s*\{\s*(?:--.*)?$]], [[^-- (?:tool|=====)\s*(.*)$]] },
      rs  = { [[^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?((?:fn|struct|enum|trait|impl|mod|const|static)\s+\w+)]] },
      md  = { [[^(#{1,3}\s+.+)$]] },
      toml = { [=[^(\[[^\]]+\])]=] },
      yml = { [[^([\w.-]+):\s*$]] }, yaml = { [[^([\w.-]+):\s*$]] },
      js  = { [[^\s*(?:export\s+)?(?:async\s+)?(?:function|class|const)\s+(\w+)]] },
    },
  },

  messages = {
    read_big = "GUARD read denied: {rel} = {lines} lines, {kb} KB (~{tok}k tokens). Outline instead (Lnn = line numbers for offset/limit):\n{outline}\n"
            .. "Retry: Read with offset/limit around the symbol you need{sym}; `python tools/qa.py ctx {rel}` adds importers and tests; "
            .. "or repeat the same Read once within {window} min to force the full read.",
    read_repeat = "GUARD read unchanged: {rel} has not changed since your read {age} ago (~{tok}k tokens): use what you already have, read only "
               .. "the part you need with offset/limit, or repeat this exact Read once to force it.",
    read_raw = "GUARD read denied: {rel} is a raw dump ({kb} KB, ~{tok}k tokens). Digest it with: {digest}\nsample (head/tail):\n{sample}\n"
            .. "Retry with offset/limit for a specific part, or repeat the same call once within {window} min to force it.",
    batch = "GUARD batch: your last {n} tool calls were single read-only calls. Put ALL independent read-only calls "
         .. "(Read/Grep/Glob/qa.py ctx/sym) into ONE message; one turn re-reads the whole context, so N calls in one message cost one turn.",
    bash = "GUARD bash denied ({id}): {say}\nRepeat the identical command once within {window} min to force it, or append `# allow:{id}`.",
    post_edit = "GUARD lint: {n} problem(s) in the file you just edited (fix them in this turn):\n{lines}",
  },
}
