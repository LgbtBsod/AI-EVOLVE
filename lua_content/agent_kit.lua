-- tool: agent-kit data of `qa.py prompt` / `qa.py route`: roles (context file, model, effort, turn budget, tools), stage routes for Agent and Workflow calls, prompt templates, report contract
-- DATA ONLY. Logic: tools/agent_kit.py; commands: tools/qa_plugins/prompt.py, route.py. `python tools/qa.py route --check` validates this file (roles have files, valid model
-- names, budgets > 0, templates fit, .claude/agents/*.md fresh); `python tools/qa.py route --write-agents` regenerates .claude/agents/*.md (a new agents directory needs a harness restart).
-- Template placeholders are <name>: preamble role role_file max_calls hard_turns handoff report lines max_words model effort tools task scope done (agent_kit.PLACEHOLDERS).
-- Model names are mapped to concrete model IDs by the harness, not by this repo. Lists are never empty here (an empty Lua table crosses as {}).
return {
  context_dir = "docs/agent_context",                -- <role>.md of every role lives here (max_role_lines, `TURN BUDGET: N` = max_calls, the report lines: checked by `route --check`)
  preamble = "docs/agent_context/preamble.md",       -- the token rules every role starts from
  agents_dir = ".claude/agents",
  chars_per_token = 4,                               -- token estimate = chars / 4 (the roadmap's measurements use the same rule)
  max_prompt_tokens = 400,                           -- `qa.py prompt` REFUSES a larger prompt (the appended pack is not counted: it is a tool answer, not typing)
  min_task_tokens = 200,                             -- the empty template must leave at least this much room for TASK / SCOPE / DONE WHEN
  max_role_lines = 35,                               -- a role file is read on every spawn
  hard_turns_factor = 1.2,                           -- frontmatter maxTurns = max_calls * factor: a backstop above the soft budget (turns <= calls; the agent needs room to write its handoff)
  models = { "sonnet", "opus", "haiku", "fable" },   -- valid `model` names of the Agent / Workflow options and of `model:` in .claude/agents/*.md
  efforts = { "low", "medium", "high", "xhigh", "max" },
  planned = {},                              -- `qa.py X` named in the docs before X exists (roadmap steps 4 and 5); `route --check` warns when one exists and should be dropped here

  -- `qa.py wf estimate` / `qa.py tokens --workflow`: MEASURED cost of Workflow agents. Source: run wf_970d0c97-06a (5 default agents: 73 turns, billed 787649, cw 637648, out 149855; first_ctx 67.1k x4, write 106.9k)
  -- and wf_9b684e34-b18 (typed explorer: first_ctx 11679). billed = in + cache_write + out; per turn the context grows by `growth_per_turn` (cache write) and the agent writes `out_per_turn`.
  workflow_cost = {
    source_run = "wf_970d0c97-06a", typed_source_run = "wf_9b684e34-b18",
    cold_default = 67000, cold_typed = 12000,       -- first context of an agent without / with agentType
    avg_turns = 17,                                 -- turns of a map agent of that run (14-18)
    growth_per_turn = 3600, out_per_turn = 2050,    -- (637648 - 375k cold) / 73 turns ; 149855 / 73 turns
    default_fanout = 3,                             -- agent() inside .map(...) of an array whose size is not literal
    untyped_first_ctx = 40000,
  },

  -- `qa.py wf new NAME --kind K`: lean skeletons (placeholders <name> <kind>); every agent() carries agentType, explorers write their own file section, the script only assembles.
  wf = {
    header = "Read docs/agent_context/preamble.md first, in ONE message (your role file is in your agent definition). Budget 14 tool calls; every ~10 run `qa.py ckpt \"done\" --next \"...\"`; at the cap end with `RELAY: continue with qa.py resume`.",
    kinds = { "audit", "map-write", "review" },
    agent_type = { audit = "explorer", ["map-write"] = "implementer", review = "reviewer" },  -- map-write agents WRITE their section: explorer has no Write tool
    skeleton = {
      "// workflow <name> (<kind>): lean by design - `qa.py wf new`; estimate: `qa.py wf estimate <this file>`; every agent() has agentType (untyped = 67k cold start vs 12k)",
      "const HEADER = '<header>'",
      "const AREAS = [",
      "  { key: 'a', prompt: 'AREA = ... (say what to read and what to write)' },",
      "  { key: 'b', prompt: 'AREA = ...' },",
      "]",
      "const DONE = { type: 'object', properties: { file: { type: 'string' }, lines: { type: 'number' } }, required: ['file', 'lines'] }",
      "log('estimate: qa.py wf estimate <this file> (fan-out x turns x 12k typed cold start)')",
      "phase('Work')",
      "const done = (await parallel(AREAS.map(a => () =>",
      "  agent(HEADER + ' ' + a.prompt + ' WRITE your section to docs/_wf/<name>/' + a.key + '.md (do not return its text); return only {file, lines}.',",
      "    { label: a.key, phase: 'Work', schema: DONE, agentType: '<agent_type>' })",
      "))).filter(Boolean)",
      "// no verifier agent: the parent assembles and validates with a script step",
      "return { sections: done, next: 'python tools/qa.py wf assemble docs/_wf/<name> --out docs/<NAME>.md' }",
    },
  },

  handoff = "every ~10 calls and at the cap run `qa.py ckpt \"done\" --next \"...\"`; at the cap print `RELAY: continue with qa.py resume` as the LAST line and stop.",   -- relay protocol (roadmap step 4)
  report = {
    max_words = 250,
    lines = { "files:", "results:", "unfinished:" },  -- fixed lines of every report; a role may put one more line in front (`report_extra`)
    text = "<= <max_words> words, exactly the lines <lines>; `results:` are qa.py header lines copied verbatim; claim nothing you did not run.",
  },
  scope_default = { write = "only what the task needs (name every file you touched in `files:`)", readonly = "read-only: edit nothing" },

  -- `qa.py prompt ROLE --task ...` prints these lines (one per line) with the placeholders filled: the whole prompt is about 150 tokens plus your task text.
  prompt = {
    "Read <preamble> and <role_file> first, in ONE message.",
    "TASK: <task>",
    "SCOPE (files you may touch): <scope>",
    "DONE WHEN: <done>",
    "BUDGET: <max_calls> tool calls; <handoff>",
    "REPORT: <report>",
  },
  pack_heading = "CONTEXT PACK (qa.py pack; use it instead of searching):",

  -- `qa.py prompt --workflow ROLE`: what a Workflow script embeds INSTEAD of an inlined CONTEXT block (the model/effort are the role's; per stage see `qa.py route --list`).
  workflow = {
    [[// agent-kit (`python tools/qa.py prompt --workflow <role>`): shared context lives in the repo, not in this script; stage routing: `python tools/qa.py route --list`]],
    [[const CTX = 'Read <preamble> and <role_file> first, in ONE message. Budget <max_calls> tool calls; <handoff> Report <report>']],
    [[// per stage: agent(`${CTX}\nTASK: ...\nSCOPE: ...\nDONE WHEN: ...`, { model: '<model>', effort: '<effort>' })   // after a harness restart also: agentType: '<role>']],
  },

  -- .claude/agents/<role>.md = frontmatter (name, description, tools, model, effort, maxTurns) + this body.
  agent_body = {
    "Generated by `python tools/qa.py route --write-agents` from lua_content/agent_kit.lua: do not edit (`qa.py route --check` finds drift).",
    "Read <preamble> and <role_file> first, in ONE message, then do the task in the prompt.",
    "Budget: <max_calls> tool calls (soft); <handoff> Report <report>",
  },

  -- ROLES. `writes = false` roles never edit repo files. `done` = the default DONE WHEN. `report_extra` = one more fixed report line, put first.
  roles = {
    { name = "implementer", model = "sonnet", effort = "medium", max_calls = 45, writes = true,
      tools = "Read, Grep, Glob, Edit, Write, Bash",
      description = "Build or refactor one feature inside a given file scope; verifies with qa.py test --changed and qa.py check.",
      done = "the change works and `qa.py test --changed` and `qa.py check` show no FAIL" },
    { name = "verifier", model = "haiku", effort = "low", max_calls = 15, writes = false,
      tools = "Read, Grep, Glob, Bash",
      description = "Runs the named qa.py checks and reports only the verdict lines. Read-only.",
      done = "every requested check has a verdict line" },
    { name = "explorer", model = "sonnet", effort = "low", max_calls = 25, writes = false,
      tools = "Read, Grep, Glob, Bash",
      description = "Read-only research; answers with file:line evidence, marks FACT vs INFERENCE.",
      done = "the question is answered with file:line evidence, or its gaps are listed",
      report_extra = "answer:" },
    { name = "rust-kernel", model = "sonnet", effort = "medium", max_calls = 45, writes = true,
      tools = "Read, Grep, Glob, Edit, Write, Bash, PowerShell",
      description = "Rust kernel in rust_core plus its Python twin and a parity fuzz test; builds from PowerShell with maturin.",
      done = "twin and Rust agree on the parity test, `cargo test` and `qa.py check` show no FAIL" },
    { name = "lua-content", model = "sonnet", effort = "medium", max_calls = 35, writes = true,
      tools = "Read, Grep, Glob, Edit, Write, Bash",
      description = "Lua data, items and rules under lua_content; verifies with qa.py lua check, itemcheck and the item specs.",
      done = "`qa.py lua check` loads every file, the item spec passes and `qa.py check` shows no FAIL" },
    { name = "stabilizer", model = "sonnet", effort = "medium", max_calls = 45, writes = true,
      tools = "Read, Grep, Glob, Edit, Write, Bash",
      description = "Fixes a red main by root cause; never weakens a test or grows a baseline.",
      done = "`qa.py check --all --no-cache` verdict is OK (known warns allowed)" },
    { name = "reviewer", model = "opus", effort = "high", max_calls = 25, writes = false,
      tools = "Read, Grep, Glob, Bash",
      description = "Adversarial review of a diff: tries to break it, reports defects with file:line and a repro. Read-only.",
      done = "every changed file was attacked at least once and the verdict is stated",
      report_extra = "verdict:" },
  },

  -- STAGE ROUTES for Workflow / Agent calls (`qa.py route STAGE`, `--list`). Cheap first, strongest last. `escalate` = the model to retry with when this one FAILS
  -- (one tier up, never up front). `role` = which role file supplies the context. Effort names are the Workflow `effort` option's.
  routes = {
    { stage = "run-tests",       role = "verifier",    model = "haiku",  effort = "low",    max_calls = 15, escalate = "sonnet",
      why = "running one command and copying its verdict line needs no reasoning" },
    { stage = "summarise-log",   role = "verifier",    model = "haiku",  effort = "low",    max_calls = 10, escalate = "sonnet",
      why = "qa.py ci / probe_db already digest the log; the agent only relays the essentials" },
    { stage = "mechanical-edit", role = "implementer", model = "sonnet", effort = "low",    max_calls = 30, escalate = "opus",
      why = "a rename or a rewrite by rule: exact edits matter more than depth (a wrong edit costs a retry turn)" },
    { stage = "grep-research",   role = "explorer",    model = "sonnet", effort = "low",    max_calls = 25, escalate = "opus",
      why = "search plus file:line evidence; low effort is enough when the tools do the ranking" },
    { stage = "implement",       role = "implementer", model = "sonnet", effort = "medium", max_calls = 45, escalate = "opus",
      why = "a well-scoped feature with checks that catch mistakes; the strongest model is not needed to type it" },
    { stage = "refactor",        role = "implementer", model = "sonnet", effort = "medium", max_calls = 45, escalate = "opus",
      why = "behaviour must not change and qa.py golden / test --changed prove it" },
    { stage = "rust-kernel",     role = "rust-kernel", model = "sonnet", effort = "medium", max_calls = 45, escalate = "opus",
      why = "twin plus parity fuzz pin the semantics, so the model only has to satisfy them" },
    { stage = "lua-content",     role = "lua-content", model = "sonnet", effort = "medium", max_calls = 35, escalate = "opus",
      why = "data edits checked by qa.py lua check and the item specs" },
    { stage = "fix-red-main",    role = "stabilizer",  model = "sonnet", effort = "medium", max_calls = 45, escalate = "opus",
      why = "root-causing a failure is bounded by its repro line; escalate when two causes were wrong" },
    { stage = "design",          role = "explorer",    model = "opus",   effort = "high",   max_calls = 25,
      why = "a wrong design costs every later step: the one place the strongest model pays back" },
    { stage = "judge",           role = "reviewer",    model = "opus",   effort = "high",   max_calls = 15,
      why = "choosing between candidate results needs judgement, and a weak judge poisons the choice" },
    { stage = "adversarial-review", role = "reviewer", model = "opus",   effort = "high",   max_calls = 25,
      why = "finding what the author missed is the hardest reasoning task in the loop" },
  },
}
