-- lua_content/qa.lua
-- tool: settings of the QA layer: checks, scenarios, budgets, thresholds and the tools-registry rows (read through probe_settings.qa_settings)
-- tool.group: content
-- Настройки QA-слоя (tools/qa.py): golden-сценарии, фаззинг действиями игрока,
-- инварианты мира, Monte Carlo, выбор тестов. Python читает через lupa.lua55
-- (tools/probe_settings.py: qa_settings); без lupa - те же значения из Python.

return {
  -- Golden-сценарии: детерминированные прогоны agent_play (fixed-step + seed).
  -- `qa.py golden --record` сохраняет итог и отпечаток траектории в
  -- tests/golden/agent_scenarios.json, `qa.py golden` - сверяет. Любое
  -- расхождение = поведение игры изменилось (намеренно - перезаписать).
  scenarios = {
    { name = "melee_three",   seed = 1, script = "spawn enemy x3; until kills>=3 or dead max 90; expect alive" },
    { name = "trap_and_chest", seed = 2, script = "spawn trap; spawn chest; wait 15; expect alive" },
    { name = "swarm",         seed = 3, script = "spawn enemy x10; wait 45" },
    { name = "idle_explore",  seed = 4, script = "wait 90" },
    -- ci = false: не входит в `qa.py check --ci` (kills>=1 держится без запаса на эталонной Linux-записи)
    { name = "forced_attacks", seed = 5, script = "spawn enemy x2; attack x5; wait 20; expect kills>=1", ci = false },
    -- Damage pipeline (docs/DAMAGE_PIPELINE.md): the golem shard (bestiary `stats`: resist_physical 30, block_chance 25,
    -- penetration_flat 3) - resistance, block and armor penetration show up as resisted / blocks / pierced. 8 of 8 seeds
    -- (21..28) survive with blocks >= 2, so the expects are not a coin flip on another platform.
    { name = "golem_guard", seed = 21, script = "spawn enemy golem_shard x3; until kills>=3 or dead max 60",
      expects = { "alive", "kills>=3", "blocks>=1", "resisted>0", "pierced>0" } },
  },
  -- Поля итогового состояния, которые сравнивает golden (плюс отпечаток траектории)
  golden_fields = { "t", "hp", "max_hp", "lvl", "xp", "kills", "despawns", "enemies",
                    "dealt", "taken", "attacks", "hits", "crits", "alive" },

  -- Фаззинг: случайные последовательности ДЕЙСТВИЙ ИГРОКА + инварианты на каждом кадре.
  -- Найденное нарушение ужимается (delta debugging) до минимального скрипта.
  fuzz = {
    runs = 24,          -- сколько случайных скриптов за запуск
    length = 16,        -- команд в скрипте
    jobs = 4,           -- параллельных процессов игры
    actions = {         -- { команда, вес }
      { "spawn enemy", 4 }, { "spawn enemy x3", 1 }, { "spawn trap", 2 }, { "spawn chest", 2 },
      { "attack", 3 }, { "interact 0.5", 1 }, { "wait 1", 4 }, { "wait 5", 3 }, { "wait 15", 1 },
    },
  },

  -- Инварианты мира, проверяются на каждом кадре (tools/probe_invariants.py).
  invariants = {
    enabled = true,
    hp_epsilon = 0.01,          -- допуск на HP > max_hp
    world_slack = 5.0,          -- насколько юнит может выйти за край карты
    max_enemies_slack = 12,     -- сверх scene.max_enemies (спавн игрока тоже считается)
    dead_enemy_frames = 3,      -- столько кадров мёртвый враг может оставаться в сцене
    max_violations_kept = 20,
  },

  -- Monte Carlo по seed (qa.py sweep): распределения метрик + bootstrap-CI (Rust)
  sweep = { seeds = 16, jobs = 4, bootstrap_resamples = 2000,
            metrics = { "kills", "dealt", "taken", "hp", "lvl", "t" } },

  -- Детерминизм (qa.py determinism): пары одинаковых прогонов сравниваются покадрово
  -- (agent_play --trace-frames). Правила гипотез - ДАННЫЕ: `when` - имя условия из
  -- tools/qa_plugins/determinism.py (PREDICATES), тексты - шаблоны с {полями}.
  determinism = {
    pairs = 6, seed = 5, jobs = 4, timeout = 300,
    variants = { "normal", "aslr-off", "hashseed0" },  -- aslr-off = `setarch <arch> -R` (только Linux)
    float_ulp = 4,          -- поля, отличающиеся не больше чем на столько ULP - "float-level"
    tick_seconds = 1.0,     -- периодические таймеры игры (эффекты, спавн) бьют на целых секундах
    max_fields = 4,         -- сколько расходящихся полей печатать в консоль (остальные - в report.json)
    hypotheses_shown = 5, top_leaks = 5, max_lines = 25,
    -- какие файлы владеют расходящимся полем (поиск float-операций и подсказка "куда смотреть")
    owners = {
      { prefix = "hero.", files = { "src/entities/character.py", "src/gameplay/hero_drive.py" } },
      { prefix = "en[",   files = { "src/entities/enemy.py", "src/gameplay/enemy_ai.py", "src/gameplay/world.py" } },
      { prefix = "t",     files = { "tools/probe_runtime.py", "src/core/game_core.py" } },
    },
    float_sites = [[math\.|numpy|\bnp\.|hypot|atan2|\bsqrt\(|\bsin\(|\bcos\(|\bpow\(|\*\* ?0?\.5]],
    -- порядок находок рекордера утечек: первое совпадение по началу вида, вес больше = выше
    leak_severity = {
      { match = "random.", weight = 90 }, { match = "os.urandom", weight = 90 },
      { match = "uuid.", weight = 80 },   { match = "secrets.", weight = 80 },
      { match = "threading.", weight = 70 }, { match = "datetime.", weight = 60 },
      { match = "date.", weight = 60 },
      { match = "time.perf_counter (real", weight = 40 }, { match = "time.time (real", weight = 40 },
      { match = "time.monotonic (real", weight = 40 },
      { match = "time.", weight = 50 },
    },
    hypotheses = {
      { id = "float_ulp", when = "float_level", severity = "high",
        symptom = "first diff <= {ulp} ULP ({fields}), RNG hashes equal",
        cause = "float non-determinism (libm/FMA/SIMD, numpy) amplified by a threshold",
        look = "math.*/numpy in {sites}; compare cpu flags/libc across classes (report.json env)" },
      { id = "rng_first", when = "rng_first", severity = "high",
        symptom = "RNG hash ({rng_parts}) diverges at f{rng_frame}, state {state_lag}",
        cause = "conditional/extra RNG draw, or an unseeded generator",
        look = "leaks below (random.Random() unseeded); grep 'random|rng' in {owners}" },
      { id = "order", when = "order", severity = "high",
        symptom = "same enemies in a different order",
        cause = "set / dict-of-objects iteration order (hash(obj), id())",
        look = "sets or dicts keyed by objects feeding scene.enemies; sort by a stable key" },
      { id = "only_t", when = "only_t", severity = "high",
        symptom = "only the virtual time t differs",
        cause = "real clock or a timer boundary not covered by the virtual clock",
        look = "time.* leaks below; frame-time source in tools/probe_runtime.py" },
      { id = "tick", when = "tick", severity = "medium",
        symptom = "divergence at a whole-second boundary (t={t})",
        cause = "1 s tick (periodic effects / spawn timers) firing one frame apart",
        look = "periodic effects in src/effects/manager.py; spawn timers in src/gameplay/world.py" },
      { id = "logic", when = "logic_level", severity = "medium",
        symptom = "state differs beyond float noise ({fields}), RNG equal",
        cause = "nondeterministic branch: iteration order, real clock, thread timing or untraced input",
        look = "leaks below; owners {owners}; diff frames f{last_same}..f{frame} with the repro script" },
      { id = "entity_set", when = "entity_set", severity = "medium",
        symptom = "different enemies alive (count differs)",
        cause = "spawn/despawn/kill decided at a different frame (timer, RNG or ordering)",
        look = "spawn timers + KillTracker path in src/gameplay/world.py; 'en.count' in report.json" },
      { id = "length", when = "length", severity = "medium",
        symptom = "identical common prefix but the traces have different lengths ({len_a} vs {len_b})",
        cause = "run ended at a different frame: an untraced metric (kills/dealt) or a condition flipped",
        look = "the script's until/expect conditions; session.json final of both runs" },
      { id = "hashseed_refuted", when = "hashseed_refuted", severity = "info",
        symptom = "PYTHONHASHSEED=0 pairs still diverge ({hashseed_diverged}/{hashseed_pairs})",
        cause = "string-hash randomisation is NOT the cause",
        look = "other variants / float_ulp rule / leaks" },
      { id = "hashseed_implicated", when = "hashseed_implicated", severity = "high",
        symptom = "PYTHONHASHSEED=0 pairs are clean but other variants diverge",
        cause = "str-hash randomisation reaches game logic (set/dict-of-str iteration order)",
        look = "grep 'set(' / '.keys()' loops where the order picks an action; use sorted()" },
      { id = "aslr_implicated", when = "aslr_implicated", severity = "medium",
        symptom = "aslr-off diverges more often ({aslr_diverged}/{aslr_pairs}) than normal ({normal_diverged}/{normal_pairs})",
        cause = "address-dependent behaviour (id()/hash(obj) ordering, native allocator) or a float path",
        look = "sorted(..., key=id), sets of objects; also the float_ulp rule" },
      { id = "multi_class", when = "multi_class", severity = "info",
        symptom = "{runs} runs fall into {classes} recurring trajectory classes",
        cause = "a few stable trajectories, picked by the environment (CPU/libm dispatch, memory layout)",
        look = "which variant/pair lands in which class (report.json fp_a/fp_b); on CI diff the env fingerprints" },
    },
  },

  -- ===== qa.py check: ОДИН формат вывода для всех проверок (tools/qa_report.py) =====
  -- Бюджет вывода и пороги дельт. Дельта метрики против прошлого прогона той же проверки
  -- печатается (`dealt=484.2(-22%)`), только если сдвиг >= delta_pct % И >= delta_abs (по метрике - в `delta`).
  report = {
    max_lines = 30,         -- потолок строк вывода вместе с заголовком; остальное - в файл + `(+N more lines: PATH)`
    detail_lines = 3,       -- строк деталей у упавшей проверки (первая - в её строке)
    line_width = 150,       -- деталь в строке обрезается до стольких символов
    delta_pct = 15, delta_abs = 1,
    delta = { dealt = { pct = 10, abs = 5 }, taken = { pct = 10, abs = 5 }, hp = { pct = 10, abs = 5 }, kills = { pct = 0, abs = 1 },
              -- quality ratchet: any move of a count is news
              ruff = { pct = 0, abs = 1 }, blind_except = { pct = 0, abs = 1 }, cc11 = { pct = 0, abs = 1 }, cc_max = { pct = 0, abs = 1 },
              dup_defs = { pct = 0, abs = 1 }, layers_broken = { pct = 0, abs = 1 }, vulture = { pct = 0, abs = 1 }, improved = { pct = 0, abs = 1 } },
    delta_ignore = { "dur", "wall", "t" },
    history_keep = 400,     -- строк в dev_probe_output/qa/history.jsonl
    cache_hours = 24,       -- кэш результатов старше - не используется
    jobs = 4,               -- параллельных проверок (qa_pool)
    timeout = 600,          -- секунд на проверку, если не задано своё
  },

  -- Каждый элемент `scenarios` (они же golden) и `plays` (только проверки, без golden) - проверка `play:NAME`.
  -- Поля сценария: name, seed, script, [expects = "kills>=1" | {..}], [cost, watches, tags, ci].
  scenario_check = {
    cost = "low", tags = { "play" }, timeout = 120,
    watches = { "src/**/*.py", "lua_content/**/*.lua", "tools/agent_play.py", "tools/probe_*.py", "config.prc", "rust_core/src/**/*.rs" },
    keep = { "hp", "lvl", "kills", "dealt", "taken", "misses", "blocks", "resisted", "pierced", "expects" },   -- метрики строки; остальное RESULT-строки не печатается
    hide_zero = { "errors", "invariants", "expects" },   -- "expects" = "0/0": в сценарии нет expect
  },
  plays = {
    { name = "trap_only", seed = 6, script = "spawn trap; wait 20", expects = "alive" },
  },
  -- Проверка = ДАННЫЕ: python не нужен. cmd - команда (python = текущий интерпретатор); cmd_diff - вместо неё в режиме
  -- `qa.py check` по диффу; parse = result_line | pytest | counts | regex (pattern с именованными группами) | exit;
  -- watches - globs, при правке которых (или их импортёров) проверка выбирается и сбрасывается кэш; cost = low|medium|high;
  -- always - выбирается даже без правок; ci=false - не входит в `check --ci`; solo - гоняется одна (сама параллелит);
  -- soft / soft_if - падение считается warn (известная проблема / регэксп по выводу); warn_over = { метрика = предел };
  -- keep / hide_zero - какие метрики печатать; detail - регэксп строк деталей; requires = "display"; needs = { модули }.
  checks = {
    { name = "combat_smoke", cmd = "python tools/combat_smoke_test.py", parse = "counts", cost = "low", always = true,
      tags = { "combat", "unit" }, what = "combat/effects/leveling formulas (no window)",
      watches = { "src/**/*.py", "lua_content/**/*.lua", "tools/combat_smoke_test.py" } },
    { name = "tests", cmd = "python tools/qa.py test", cmd_diff = "python tools/qa.py test --changed", parse = "pytest",
      cost = "medium", solo = true, ci = false, tags = { "pytest" }, hide_zero = { "skipped", "flaky" },
      what = "pytest in parallel shards (only affected files in diff mode; known failures do not count as NEW)",
      watches = { "src/**/*.py", "tools/**/*.py", "tests/**/*.py", "lua_content/**/*.lua", "tests/*.json", "pytest.ini" } },
    { name = "golden", cmd = "python tools/qa.py golden", parse = "regex", pattern = [[golden: (?P<identical>\d+)/(?P<total>\d+) scenario]],
      detail = "CHANGED|NEW scenario|definition changed|run failed", soft_if = [[golden recorded on [\w.-]+, this is [\w.-]+]],
      cost = "medium", ci = false, tags = { "play", "golden" }, what = "deterministic scenarios vs tests/golden/ (warn, not fail, on another platform than the recording)",
      watches = { "src/**/*.py", "lua_content/**/*.lua", "tools/agent_play.py", "tools/probe_*.py", "tests/golden/**", "rust_core/src/**/*.rs" } },
    { name = "lua", cmd = "python tools/qa.py lua check", parse = "regex", pattern = [[lua: (?P<loaded>\d+)/(?P<files>\d+) files ok]],
      cost = "low", tags = { "lua" }, what = "every lua_content file loads with every backend, same data",
      watches = { "lua_content/**/*.lua", "tools/lua_bridge.py", "rust_core/src/lua_content/**" } },
    { name = "items", cmd = "python tools/qa.py item all", parse = "regex", pattern = [[items: (?P<pass>\d+)/(?P<items>\d+) pass]],
      cost = "low", tags = { "lua", "items" }, what = "every item schema -> Lua -> conditions -> combat (itemcheck)",
      watches = { "lua_content/items/**", "tools/effect_schema/**", "src/**/*.py", "tools/lua_bridge.py" } },
    { name = "pathfinding", cmd = "python -m pytest -q tests/test_pathfinding.py", parse = "pytest", cost = "low",
      hide_zero = { "failed", "skipped", "error" },
      tags = { "pytest", "rust" }, what = "A*/JPS/flow field: Rust kernel vs the Python twin on seeded grids",
      watches = { "src/gameplay/pathfinding.py", "rust_core/src/simulation/pathfinding.rs", "tests/test_pathfinding.py", "tools/probe_kernels.py" } },
    { name = "damage", cmd = "python -m pytest -q tests/test_damage_pipeline.py", parse = "pytest", cost = "low",
      hide_zero = { "failed", "skipped", "error" },
      tags = { "pytest", "rust", "combat" }, what = "damage pipeline: Rust kernel vs the Python twin (bit for bit), stage cases, the neutral guard",
      watches = { "src/effects/damage.py", "src/effects/manager.py", "rust_core/src/combat/**", "lua_content/damage.lua",
                  "lua_content/effect_rules.lua", "tests/test_damage_pipeline.py", "tools/bench_damage.py" } },
    { name = "boot_smoke", cmd = "python tools/boot_smoke_test.py", parse = "result_line", requires = "display", cost = "medium",
      ci = false, tags = { "boot" }, what = "GameCore -> menu -> world -> plugins, offscreen buffer (skip without OpenGL/xvfb)",
      watches = { "src/**/*.py", "main.py", "config.prc", "lua_content/**/*.lua", "tools/boot_smoke_test.py", "tools/probe_runtime.py" } },
    { name = "determinism-quick", cmd = [[python tools/qa.py determinism "wait 5" --pairs 2]], parse = "result_line",
      soft = true, soft_note = "same-seed residual is a known xfail (frame-0 RNG); see docs/LANGUAGE_SPLIT.md",
      keep = { "pairs", "diverged", "classes" }, cost = "medium", ci = false, tags = { "play", "determinism" },
      what = "two same-seed pairs must produce identical trajectories",
      watches = { "src/**/*.py", "tools/probe_runtime.py", "tools/agent_play.py", "tools/qa_plugins/determinism.py", "lua_content/**/*.lua" } },
    { name = "dead-code", cmd = "python tools/qa.py dead", parse = "regex", pattern = [[dead=(?P<dead>\d+) \((?P<loc>\d+) LOC]],
      warn_over = { dead = 100 }, cost = "low", ci = false, tags = { "hygiene" }, what = "modules nobody imports (informational count)",
      watches = { "**/*.py" } },
    { name = "docs-stale", cmd = "python tools/qa.py docs --top 0", parse = "regex",
      pattern = { [[(?P<md>\d+) markdown files]], [[STALE=(?P<stale>\d+)]], [[CHECK=(?P<review>\d+)]] },
      cost = "low", ci = false, tags = { "hygiene" }, what = "markdown files whose references point at missing/dead code (informational count)",
      watches = { "**/*.md", "**/*.py" } },
    -- Repo hygiene (tools/repo_hygiene.py, data = the `hygiene` table below): no tracked virtualenv / build output / saves / big file, and .gitignore keeps
    -- its patterns. Guards against a session that overwrites .gitignore and commits junk. No `watches` = the whole repo: a newly tracked file changes the
    -- cache key, so a stale OK cannot hide it; `always`: it also runs when nothing changed.
    { name = "hygiene", cmd = "python tools/qa.py hygiene --result", parse = "result_line", cost = "low", always = true,
      tags = { "hygiene" }, detail = [[^(?!RESULT |repro:)\S]],
      what = "git ls-files has no .venv*/ target/ *.so *.pyd *.pyc saves/*.db dev_probe_output/ or file > 1 MB; .gitignore covers the required patterns" },
    -- Tools registry (tools/tool_registry.py, data = the `tools` table below): every tool has a purpose, docs/TOOLS.md equals the harvest, no two tools alike,
    -- CLAUDE.md names only real qa.py commands. Same as `hygiene`: no `watches` needed beyond what the harvest reads; `always`: runs even when nothing changed.
    { name = "tools", cmd = "python tools/qa.py tools --result", parse = "result_line", cost = "low", always = true, ci = true,
      tags = { "hygiene", "docs" }, detail = [[^(?!RESULT |repro:)\S]],
      what = "every tool/plugin/check/script has a purpose line, docs/TOOLS.md equals the harvest, no near-duplicate tools, CLAUDE.md commands are real",
      watches = { "tools/**", "CLAUDE.md", "docs/TOOLS.md", "lua_content/**/*.lua", "rust_core/src/**/*.rs" } },
    -- agent-kit: Lua data valid, role files (<= 35 lines, `TURN BUDGET: N` = max_calls, report lines) and generated .claude/agents/*.md consistent; catches a Markdown-only edit that no pytest selects.
    { name = "agent_kit", cmd = "python tools/qa.py route --check --result", parse = "result_line", cost = "low", ci = true,
      tags = { "hygiene", "docs" }, detail = [[^(?!RESULT |repro:)\S]],
      what = "agent-kit data, docs/agent_context role files and generated .claude/agents/*.md agree (models valid, budgets > 0, no drift)",
      watches = { "lua_content/agent_kit.lua", "docs/agent_context/**", ".claude/agents/**", "tools/agent_kit.py", "tools/qa_plugins/route.py", "tools/qa_plugins/prompt.py" } },
    -- Code-quality ratchet: the logic is tools/quality_metrics.py, the data is the `quality` table below. It prints detail lines, `repro:` and one
    -- RESULT line (`qa.py quality --result`); `ci = false`: CI runs it once on Linux (`check --name quality --no-cache`), not on every OS.
    { name = "quality", cmd = "python tools/qa.py quality --result", parse = "result_line", cost = "low", ci = false,
      needs = { "ruff", "radon", "vulture", "importlinter" }, tags = { "hygiene", "quality" }, detail = [[^(?!RESULT |repro:)\S]],
      what = "SOLID/DRY/SRP/SSOT ratchet: ruff + radon CC + vulture + import-linter layers + duplicate definitions vs tests/quality_baseline.json (a NEW violation fails)",
      watches = { "src/**/*.py", "main.py", "pyproject.toml", ".importlinter", "tests/quality_baseline.json", "lua_content/qa.lua",
                  "tools/quality_metrics.py", "tools/qa_plugins/quality.py" } },
  },

  -- ===== code-quality RATCHET (tools/quality_metrics.py) =====
  -- `qa.py check --name quality` | `qa.py quality --worst N | --explain RULE | --update-baseline [--force]`.
  -- SOLID/DRY/SRP/SSOT violations cannot grow: today's ones are the baseline (tests/quality_baseline.json, per metric, per file, per function);
  -- a NEW one fails, an improvement is reported (`improved=N`) and ratcheted down by --update-baseline (it refuses to raise a number without --force).
  -- Tools (nothing re-implemented): ruff (rules below; numeric limits in pyproject.toml), radon (cyclomatic complexity), vulture (dead code),
  -- import-linter (.importlinter: layers; its `ignore_imports` IS the layering baseline), plus a ~20-line ast detector for duplicated definitions.
  quality = {
    baseline = "tests/quality_baseline.json",
    -- Scope: live game modules = qa_graph.liveness == 'game' (reachable from main.py), recomputed every run - no file list to maintain.
    scope = { liveness = "game", exclude = { "setup.py" } },   -- setup.py = Panda3D build script, an entry point but not a game module
    ruff = {
      select = { "C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915", "SIM", "PERF", "RET", "B", "BLE", "E722", "F401", "F841", "ARG002", "PLW", "RUF012" },
      groups = { blind_except = { "BLE001", "E722" } },        -- derived metric = sum of these rules
    },
    cc = { min = 11 },                                         -- radon rank C+: metric cc<min> = functions with CC >= min, cc_max = the worst
    vulture = { min_confidence = 80 },
    -- Duplicated top-level definitions across live modules (DRY/SSOT): class names and UPPER_CONSTANTS defined in >= 2 modules.
    -- allow = names (or "Name@src/x.py") that are duplicated on purpose.
    dup_defs = { const_pattern = [=[^[A-Z][A-Z0-9_]+$]=], allow = {} },
    layers = { config = ".importlinter" },
    budget = { worst = 10, findings = 6, argv_chars = 24000 }, -- default --worst N, detail lines of a failure, max chars of one tool command line (Windows: 32k)
    -- SRP hints for `--worst`: the first row whose `over` is below the function's CC; a module with many complex functions gets `srp_module`.
    cc_hints = {
      { over = 40, hint = "CC>40: split by op kind (one handler per op + a dispatch table)" },
      { over = 25, hint = "CC>25: one helper per branch group; if/elif chains -> table lookup" },
      { over = 15, hint = "CC>15: guard clauses (early return) + extract the loop/branch bodies" },
      { over = 0,  hint = "CC>10: extract the nested branch into a named helper" },
    },
    srp_module = { cc11 = 3, hint = "SRP: {n} functions with CC>10 - split the module by responsibility" },
    -- What each rule means and the usual fix (`qa.py quality --explain RULE`; `hint` = the short form shown by --worst).
    -- Not listed here: `ruff rule CODE` is shown instead.
    rules = {
      BLE001 = { hint = "catch the specific exceptions", what = "`except Exception` (blind except) hides real bugs together with the expected failure.",
                 fix = "catch what can actually happen (OSError, ValueError, KeyError...); a broad catch is only for a plugin/tool boundary: log with logger.exception and add `# noqa: BLE001 - reason`." },
      E722 = { hint = "no bare except", what = "bare `except:` also swallows KeyboardInterrupt and SystemExit.",
               fix = "name the exception; at the very least `except Exception:` with logging." },
      F401 = { hint = "delete unused imports", what = "imported name is never used (dead dependency, slower import, false coupling).",
               fix = "delete the import; for a deliberate re-export list it in __all__; for an optional-dependency probe use importlib.util.find_spec." },
      F841 = { hint = "drop the unused local", what = "local variable is assigned but never read.",
               fix = "delete the assignment (keep the call if it has a side effect) or bind to `_`." },
      ARG002 = { hint = "drop/underscore the unused argument", what = "method argument is never used (a signature that promises more than it does).",
                 fix = "remove the parameter and fix the callers; if an interface/override dictates it, keep it and add `# noqa: ARG002 - interface`." },
      PLR0913 = { hint = "group arguments into a dataclass", what = "function takes more than 5 arguments (one function knows too many details: SRP/ISP).",
                  fix = "bundle the related arguments into a small dataclass/config object, make the rest keyword-only (`*`)." },
      PLR0912 = { hint = "split branches by case", what = "more than 12 branches in one function.",
                  fix = "one function per case + a dispatch dict, or polymorphism when the branches switch on a type." },
      PLR0911 = { hint = "fewer exits: table lookup", what = "more than 6 return statements in one function.",
                  fix = "replace the if-chain by a dict lookup or split the function; keep guard-clause returns, merge the rest." },
      PLR0915 = { hint = "extract the steps", what = "more than 50 statements in one function.",
                  fix = "extract each stage into a helper named for what it does; the original becomes a readable outline." },
      C901 = { hint = "extract branches", what = "McCabe complexity above 10 (too many independent paths to test).",
               fix = "guard clauses, one helper per branch group, table lookup instead of if/elif chains." },
      SIM102 = { hint = "merge nested ifs", what = "`if a:` containing only `if b:` (nested ifs that can be one condition).",
                 fix = "`if a and b:` (one level less; ruff can autofix, run `ruff check --select SIM102 --fix FILE`)." },
      SIM114 = { hint = "merge equal branches", what = "two if-branches have an identical body.", fix = "combine the conditions with `or`." },
      SIM105 = { hint = "contextlib.suppress", what = "`try/except X: pass`.", fix = "`with contextlib.suppress(X):` - says what is ignored and why." },
      PLW0108 = { hint = "pass the callable itself", what = "lambda that only forwards to another callable.", fix = "use the callable directly (`map(str, xs)` not `map(lambda x: str(x), xs)`)." },
      RET505 = { hint = "dedent after return", what = "`else`/`elif` after a branch that already returns.", fix = "drop the `else`, dedent the block (guard-clause style)." },
      RET504 = { hint = "return the expression", what = "value is assigned to a name and returned right away.", fix = "`return expr`." },
      B007 = { hint = "rename unused loop var to _x", what = "loop variable is not used in the loop body.", fix = "rename it `_name`/`_`, or use enumerate/items() correctly." },
      B904 = { hint = "raise ... from err", what = "`raise` inside `except` without `from`: the original cause is lost.", fix = "`raise NewError(...) from err` (or `from None` to hide it on purpose)." },
      B905 = { hint = "zip(..., strict=)", what = "`zip()` without `strict=`: silently truncates on unequal lengths.", fix = "`strict=True` when lengths must match (fails loudly), `strict=False` when truncation is intended." },
      B009 = { hint = "plain attribute access", what = "`getattr(obj, \"name\")` with a constant name.", fix = "`obj.name`." },
      PLW0603 = { hint = "no `global`", what = "`global` statement: hidden shared state (SSOT/testability).", fix = "hold the state in an object/class or pass it in; a module-level cache object beats rebinding a global." },
      PLW2901 = { hint = "new name for the loop value", what = "loop variable is reassigned inside the loop body.", fix = "assign to a new name." },
      RUF012 = { hint = "ClassVar / instance attr", what = "mutable class attribute (list/dict/set) is shared by every instance.", fix = "annotate `ClassVar[...]` if sharing is intended, otherwise create it in __init__." },
      PERF401 = { hint = "list comprehension", what = "list built by `append` in a for loop.", fix = "a list comprehension (or `list.extend(genexpr)`)." },
      PERF403 = { hint = "dict comprehension", what = "dict filled key by key in a for loop.", fix = "a dict comprehension." },
      PERF102 = { hint = "iterate .values()/.keys()", what = "`.items()` where only the key or only the value is used.", fix = "iterate `.keys()`/`.values()` directly." },
      -- metrics that are not a single ruff rule
      blind_except = { hint = "catch the specific exceptions", what = "sum of BLE001 + E722: `except Exception` / bare `except`.", fix = "see --explain BLE001." },
      cc11 = { hint = "extract branches", what = "number of functions with cyclomatic complexity >= 11 (radon rank C or worse): hard to test, usually 2+ responsibilities (SRP).",
               fix = "one helper per branch/op kind, dispatch table instead of if/elif chains, guard clauses. A NEW function with CC >= 11 fails the check; an existing one may not get worse." },
      cc_max = { hint = "split the worst function first", what = "the highest cyclomatic complexity of one function in scope.", fix = "see --worst: the top rows are the ones to split first." },
      dup_defs = { hint = "keep ONE definition, import it", what = "the same top-level class / UPPER_CONSTANT is defined in two live modules (DRY/SSOT): the copies drift apart.",
                   fix = "keep the definition in the lowest module that needs it (usually src/core/constants.py), import it elsewhere; a deliberate duplicate goes to quality.dup_defs.allow." },
      layers_broken = { hint = "invert or move down the import", what = "imports against the layering in .importlinter (a lower layer imports a higher one): the ignore_imports list there IS the baseline.",
                        fix = "move the shared thing down (constant/interface into src.core), invert the dependency (callback/Protocol passed in), or import lazily as the last resort. Never add to ignore_imports." },
      vulture = { hint = "delete the dead code", what = "unused import/variable/argument with >= 80% confidence (vulture).",
                  fix = "delete it; if it is used dynamically (getattr, plugins), reference it once or add a whitelist entry." },
    },
  },

  -- ===== repo hygiene (tools/repo_hygiene.py; `qa.py hygiene`) =====
  -- Every list is in .gitignore syntax (trailing `/` = directories, `*` `?` `[..]` per name, `**` = any depth, `!` re-includes).
  -- `qa.py ckpt` / `qa.py resume` (relay of short agents): journal dev_probe_output/qa/journal.jsonl, snapshots refs/qa/ckpt/N
  ckpt = { keep = 20, history_tail_bytes = 30000, hook_timeout_s = 8 },
  hygiene = {
    max_file_kb = 1024,          -- a tracked file above this fails (assets that must be bigger: list them in `allow`)
    allow = {},
    -- a TRACKED file matching any of these fails: it belongs to the machine, not to the repo
    forbidden = { ".venv*/", "target/", "*.so", "*.pyd", "*.pyc", "saves/*.db", "dev_probe_output/" },
    -- .gitignore must ignore each of these (semantic: `*.py[cod]` covers `*.pyc`); a bot that rewrites it to two lines fails here
    required_ignore = { ".venv-*/", ".venv/", "target/", "dev_probe_output/", "saves/*.db", "__pycache__/", "*.pyc", "*.so", "*.pyd", "build/", "dist/" },
  },

  -- ===== tools registry (tools/tool_registry.py; `qa.py tools --find|--write|--check`) =====
  -- docs/TOOLS.md is GENERATED (`qa.py tools --write`) from what the code says about itself (help=, docstrings, `what`, Rust `///`, `-- tool:` Lua
  -- headers, `TOOL = {}` in a plugin) plus the rows below. A row overrides the harvested fields of the tool with that `id`; `manual = true` adds a
  -- tool nothing can harvest. Row keys: id, purpose, command, when, replaces, output, cost, status, group, wraps, owner.
  -- `check --name tools` FAILS: a tool without a `required` key | docs/TOOLS.md stale | two tools alike (>= dup_threshold, unless wrapper or in dup_allow) |
  -- a `qa.py X` in CLAUDE.md that is not a subcommand | a row whose id matches nothing.
  tools = {
    required = { "purpose" },
    dup_threshold = 0.5,          -- token-set (Jaccard) similarity of name + purpose from which two tools are near-duplicates (today's closest pair: 0.54)
    dup_allow = { "bench_pathfinding~check:pathfinding" },   -- intended look-alikes: "a~b" (ids sorted): the benchmark script and the pytest twin check
    stopwords = { "the", "and", "for", "with", "from", "into", "that", "this", "are", "one", "per", "not", "all", "any", "its", "can", "use", "via",
                  "has", "was", "of", "to", "in", "on", "by", "or", "is", "it", "as", "no", "qa", "py", "python", "tool", "tools", "file", "files" },
    skip_dirs = { "qa_plugins", "qa_checks" },   -- extension points: each file inside is harvested as its own tool
    drift_ignore = {},            -- `qa.py WORD` mentions of CLAUDE.md that are not subcommands on purpose
    cell_width = 110, max_lines = 140, max_detail = 10, max_find = 8,
    groups = {
      { id = "verify",  title = "verify - is the change correct" },
      { id = "read",    title = "read / navigate - instead of reading raw files" },
      { id = "analyse", title = "analyse - runs, balance, performance" },
      { id = "build",   title = "build / release - environment, CI" },
      { id = "content", title = "content - Lua data and items" },
      { id = "kernels", title = "kernels - Rust exports (import rust_core)" },
      { id = "libs",    title = "shared libraries - import them, do not rewrite them" },
    },
    rows = {
      -- qa.py subcommands
      { id = "doctor", purpose = "missing dependencies and the exact command that fixes each", replaces = "trial-and-error pip installs after an ImportError", output = "prose", group = "build", cost = "low" },
      { id = "brief", purpose = "10 lines: environment, changes vs origin/main, known failures, recent runs, what to run next", when = "first command of a session", replaces = "git status + ls + reading old reports", output = "10 lines of prose", group = "read", cost = "low" },
      { id = "affected", command = "python tools/qa.py affected [FILES]", purpose = "which tests and scripts a change touches (import graph)", replaces = "grepping for importers by hand", output = "prose", group = "read", cost = "low" },
      { id = "dead", purpose = "modules nobody imports (dead code) with LOC; --list names them", replaces = "reading modules to see if they are still used", output = "summary line + list", group = "analyse", cost = "low" },
      { id = "ctx", command = "python tools/qa.py ctx FILE", purpose = "outline of a Python file: classes, functions, importers, tests", when = "before opening any big file", replaces = "reading a big file whole", output = "outline (about 40 lines)", group = "read", cost = "low" },
      { id = "docs", purpose = "which .md files are stale (they name code that is missing or dead)", when = "before trusting an old report", replaces = "opening old .md reports", output = "counts + top stale files", group = "read", cost = "low" },
      { id = "test", command = "python tools/qa.py test [--changed]", purpose = "pytest in parallel shards; prints only NEW failures (--changed = tests your diff affects)", replaces = "raw pytest and its full output", output = "counts + new failures", group = "verify", cost = "medium" },
      { id = "golden", purpose = "deterministic agent_play scenarios vs tests/golden (--record after an intended change)", when = "did gameplay behaviour change", replaces = "comparing gameplay runs by eye", output = "one line per scenario", group = "verify", cost = "medium" },
      { id = "sweep", command = "python tools/qa.py sweep \"SCRIPT\"", purpose = "one agent_play script over many seeds: metric distributions + bootstrap CI (Rust)", when = "did my balance fix help", replaces = "eyeballing a few seeds", output = "table per metric", group = "analyse", cost = "high" },
      { id = "fuzz", purpose = "random player actions + world invariants every frame; a failure is shrunk to a minimal repro script", replaces = "manual exploratory play", output = "minimal repro line", group = "verify", cost = "high" },
      { id = "perf", command = "python tools/qa.py perf \"SCRIPT\"", purpose = "hot functions of a game run (cProfile, fast mode)", replaces = "ad-hoc cProfile runs", output = "top-N table", group = "analyse", cost = "medium" },
      { id = "check", command = "python tools/qa.py check [--all|--fast|--name a,b]", when = "the one command to verify a change", replaces = "running pytest/ruff/smoke scripts one by one", output = "qa_report lines, worst first, <= 30", group = "verify", cost = "medium" },
      { id = "ci", command = "python tools/qa.py ci [--wait]", purpose = "GitHub Actions run via gh: verdict + only the essentials of the failed step", when = "why did CI fail", replaces = "gh run view --log", output = "verdict + failing step", group = "build", cost = "low" },
      { id = "changed", command = "python tools/qa.py changed [REV]", purpose = "semantic diff: +added -removed ~changed symbols per file, churn, RISK flags, checks to run", replaces = "git diff", output = "<= 30 lines", group = "read", cost = "low" },
      { id = "determinism", command = "python tools/qa.py determinism \"SCRIPT\" --pairs 6", purpose = "why two same-seed runs differ: paired traced runs, first divergent frame, hypotheses", replaces = "bisecting a desync by hand", output = "verdict + first divergent frame", group = "analyse", cost = "high" },
      { id = "gauntlet", command = "python tools/qa.py gauntlet [--campaign --lives 5]", replaces = "playing bosses by hand", output = "one line per boss", group = "analyse", cost = "high" },
      { id = "hygiene", replaces = "eyeballing git ls-files and .gitignore", output = "qa_report line", group = "verify", cost = "low" },
      { id = "item", command = "python tools/qa.py item check|digest|diff|all", purpose = "Effect Schema items: itemcheck, one line per effect (digest), diff vs a git ref", replaces = "reading generated item Lua", output = "one line per effect", group = "content", cost = "low" },
      { id = "lua", command = "python tools/qa.py lua check|show FILE|bench", purpose = "Lua content: every file loads with every backend (check), a file's data as compact JSON (show), load time (bench)", when = "any question about lua_content", replaces = "reading Lua files", output = "summary or JSON", group = "content", cost = "low" },
      { id = "quality", command = "python tools/qa.py quality [--worst N|--explain RULE]", replaces = "running ruff, radon, vulture, import-linter separately", output = "qa_report line + worst-N table", group = "verify", cost = "low" },
      { id = "guard", command = "python tools/qa.py guard [--stats|--explain|--simulate FILE.json|--compile|--install|--uninstall]", purpose = "read guard (Claude Code hooks): outline instead of a big unranged Read, one-line stub for an unchanged re-read, digest command for raw logs, batch nudge",
        when = "an agent burns context on big or repeated reads; --stats shows the blocks and the tokens kept out of the context", replaces = "hoping agents read with offset/limit and batch their calls", output = "qa_report line (+ per-rule lines for --stats)", group = "read", cost = "low" },
      { id = "ckpt", command = "python tools/qa.py ckpt \"done\" --next \"next action\" [--files a,b] [--agent NAME] [--auto]", purpose = "checkpoint of unfinished work: one journal line + a safety snapshot (refs/qa/ckpt/N, working tree untouched), the last 20 kept",
        when = "about every 10 tool calls and at the call cap of an agent (relay), before a risky step", replaces = "a hand-written handoff brief", output = "one line: ckpt #N saved", group = "build", cost = "low" },
      { id = "resume", command = "python tools/qa.py resume [--brief|--check|--diff N|--restore N [--apply]]", purpose = "where the last session stopped (<= 6 lines, silent when clean): dirty, orphan modules, broken files, last ckpt, SAFE/RISKY/BROKEN",
        when = "start of a session or of a relay agent (continue: $(qa.py resume --brief)), after a limit crash", replaces = "re-exploring the repo to find out what was half done", output = "<= 6 lines", group = "build", cost = "low" },
      { id = "prompt", command = "python tools/qa.py prompt ROLE --task \"...\" [--files a,b] [--done \"...\"] [--pack] | --workflow ROLE", purpose = "a SHORT agent prompt (<= 400 tokens): the shared context is a repo file (docs/agent_context/), the prompt only points at it and states TASK / SCOPE / DONE WHEN",
        when = "before every Agent call or Workflow script (agent, prompt, subagent, context)", replaces = "hand-typing a 1.5-6k-char agent prompt or an inlined CONTEXT block of a Workflow script", output = "the prompt on stdout, one size line on stderr", group = "build", cost = "low" },
      { id = "route", command = "python tools/qa.py route [STAGE|--list|--check|--write-agents]", purpose = "model / effort / tool-call budget per stage of a Workflow or Agent call (cheap for tests and logs, strong for design and review); generates .claude/agents/*.md",
        when = "choosing the model tier of an agent or a Workflow stage", replaces = "guessing the model and effort of each stage", output = "qa_report line + table", group = "build", cost = "low" },
      -- checks (`check:NAME`; purpose = the `what` of the check)
      { id = "check:agent_kit", replaces = "noticing by hand that a role file, a budget or .claude/agents/*.md drifted from agent_kit.lua" },
      { id = "check:boot_smoke", replaces = "launching the game to see whether it starts" },
      { id = "check:combat_smoke", replaces = "hand-testing combat formulas" },
      { id = "check:damage", replaces = "hand-checking damage numbers" },
      { id = "check:dead-code", replaces = "grepping for unused modules" },
      { id = "check:determinism-quick", replaces = "diffing two same-seed runs by eye" },
      { id = "check:docs-stale", replaces = "opening old .md reports to see if they still hold" },
      { id = "check:golden", replaces = "re-running scenarios and comparing by eye" },
      { id = "check:hygiene", replaces = "eyeballing git ls-files and .gitignore" },
      { id = "check:items", replaces = "loading items in the game to see if they work" },
      { id = "check:lua", replaces = "loading each Lua file by hand" },
      { id = "check:pathfinding", replaces = "comparing the Rust and Python pathfinders by hand" },
      { id = "check:play:*", replaces = "playing the game to test behaviour" },
      { id = "check:quality", replaces = "running ruff, radon, vulture, import-linter separately" },
      { id = "check:tests", replaces = "raw pytest and its full output" },
      { id = "check:tools", replaces = "grepping tools/ before writing a new tool; a hand-kept tool table in CLAUDE.md" },
      -- tools/*.py scripts
      { id = "agent_play", command = "python tools/agent_play.py \"SCRIPT\" [--seed N]", purpose = "play like the player (spawn / attack / interact levers, the hero AI decides) without a window; --serve for turn by turn",
        when = "any gameplay question", replaces = "launching the game window", output = "RESULT line + observations", group = "verify", cost = "low" },
      { id = "bench_damage", replaces = "timing the damage pipeline ad hoc", output = "hits per second per backend", group = "analyse", cost = "medium" },
      { id = "bench_pathfinding", purpose = "A*/JPS/flow-field benchmark: rust_core vs the Python twin", replaces = "timing pathfinding ad hoc", output = "time per backend", group = "analyse", cost = "medium" },
      { id = "boot_smoke_test", replaces = "starting the game by hand", output = "RESULT line", group = "verify", cost = "medium" },
      { id = "boss_gauntlet", purpose = "boss test bench: the real hero against world bosses without a window (engine of qa.py gauntlet)", replaces = "playing bosses by hand", output = "one line per boss", group = "analyse", cost = "high", wraps = "python tools/qa.py gauntlet" },
      { id = "cas_training_demo", purpose = "demo run of the CAS engine 2.0 (conditional effect system)", replaces = "-", output = "prose", group = "analyse", status = "demo" },
      { id = "combat_smoke_test", purpose = "windowless smoke test of combat, effects, leveling and AI targeting (no Panda3D)", replaces = "hand-testing combat formulas", output = "passed/failed counts", group = "verify", cost = "low" },
      { id = "dev_probe", purpose = "long headless run with anomaly hunt: samples, combat stats, contact sheet, findings in probe_db", when = "unattended run or anything visual", replaces = "reading raw state.jsonl and screenshots", output = "RESULT line + summary.md", group = "analyse", cost = "high" },
      { id = "dev_probe_async", purpose = "async multi-threaded probe framework that runs the tools/plugins/*.py analyzers", replaces = "-", output = "prose", group = "analyse" },
      { id = "guard_hook", command = "python tools/guard_hook.py  (hook JSON on stdin; installed by qa.py guard --install)", purpose = "hook entry point of the read guard: stdlib only, decides in a few ms, fails open (exit 2 + stderr = deny with the answer, JSON additionalContext = nudge)",
        replaces = "-", output = "exit code + stderr / hook JSON", group = "read", cost = "low", wraps = "python tools/qa.py guard" },
      { id = "dev_probe_diff", purpose = "delta-only comparison of two dev_probe runs (--frames adds a visual diff)", replaces = "diffing two summary.json by eye", output = "changed metrics only", group = "analyse", cost = "low" },
      { id = "probe_db", command = "python tools/probe_db.py stats|why|predict|compare|trend|sql", purpose = "SQLite analytics over every recorded probe run: stats, why, predict, compare, trend, free SQL", when = "numbers across runs, did my fix help", replaces = "reading state.jsonl / game.log", output = "short tables", group = "analyse", cost = "low" },
      { id = "repo_hygiene", purpose = "logic of the hygiene check: what git must never track (virtualenv, build output, saves, big files) and the .gitignore that keeps it out", replaces = "-", output = "RESULT line", group = "verify", cost = "low", wraps = "python tools/qa.py hygiene" },
      { id = "trace_compare", purpose = "did a refactor change behaviour: per-frame trace hashes of every play scenario, before vs after", replaces = "eyeballing runs after a refactor", output = "first divergent frame per scenario", group = "verify", cost = "medium" },
      { id = "training_room", purpose = "training room with mannequins to try equipment and effects (v2.0)", replaces = "-", output = "prose", group = "analyse" },
      { id = "training_room_demo", purpose = "demo run of the training room: equipment on mannequins", replaces = "-", output = "prose", group = "analyse", status = "demo" },
      -- libraries of tools/ (import them: do not write a second pool / report format / graph)
      { id = "agent_kit", purpose = "roles, short prompts, stage routing and generated .claude/agents/*.md for sub-agents and Workflow stages (logic of qa.py prompt / route; data in lua_content/agent_kit.lua)", replaces = "re-typed CONTEXT blocks in agent prompts and Workflow scripts", output = "prompt text / problem list", group = "libs" },
      { id = "file_toc", purpose = "table of contents helper (stdlib only): Python via ast with line ranges, other languages via the regexes of guards.lua; behind qa.py ctx and the read guard", replaces = "reading a big file to see what is in it", output = "list of `Lnn name` lines", group = "libs" },
      { id = "lua_bridge", purpose = "alias of src/content/lua_bridge.py: load(path) runs a Lua file in the sandbox and returns its data (rust_core.LuaContent, lupa fallback)", replaces = "reading Lua files or embedding a Lua runtime", output = "dict from one JSON string", group = "libs" },
      { id = "probe_analysis", purpose = "run analysis shared by dev_probe, agent_play and probe_db: hypotheses and one summary; the loops live in probe_kernels", replaces = "reading raw samples", output = "summary text", group = "libs" },
      { id = "probe_invariants", purpose = "world invariants checked on every frame of agent_play (HP over max, NaN, unit outside the map)", replaces = "noticing broken state by eye", output = "violation list", group = "libs" },
      { id = "probe_kernels", purpose = "number-crunching of run analysis: rust_core.RunAnalytics with an equivalent Python fallback", replaces = "Python loops over samples", output = "numbers", group = "libs" },
      { id = "probe_runtime", purpose = "shared runtime of dev_probe and agent_play: quiet engine, render modes, virtual clock, scene reads", replaces = "booting Panda3D by hand", output = "-", group = "libs" },
      { id = "probe_settings", purpose = "loads lua_content/dev_tools.lua and qa.lua as settings (qa_settings(), Python defaults as fallback)", replaces = "hard-coded thresholds in Python", output = "dict", group = "libs" },
      { id = "qa_graph", purpose = "static import graph: what is live or dead, which tests a change touches (behind affected, dead, ctx, check)", replaces = "grepping for importers", output = "graph object", group = "libs" },
      { id = "qa_pool", purpose = "async subprocess pool: many game runs or tests in parallel with timeouts", replaces = "hand-written subprocess loops", output = "results per job", group = "libs" },
      { id = "qa_pytest_plugin", purpose = "pytest plugin (-p qa_pytest_plugin): every test outcome as one JSONL row for qa.py test", replaces = "parsing pytest console output", output = "JSONL", group = "libs" },
      { id = "qa_report", purpose = "THE output format of every check: Result, format_line, worst-first budgeted report, history, deltas", replaces = "ad-hoc print formats", output = "one line per check", group = "libs" },
      { id = "quality_metrics", purpose = "the code-quality ratchet behind qa.py quality: ruff, radon CC, vulture, import-linter, duplicate definitions vs a baseline", replaces = "running the linters separately", output = "Result", group = "libs" },
      { id = "tool_registry", purpose = "harvest, render and gap detection of the tools registry (logic of qa.py tools)", replaces = "a hand-written tool table", output = "Result / markdown", group = "libs" },
      -- subdirectories of tools/
      { id = "effect_schema", command = "python -m tools.effect_schema.itemcheck lua_content/items/x.lua", purpose = "Effect Schema v1 (Effect -> Ops[]): model, Lua generator and parser, validator, catalog, itemcheck", when = "build or verify an item", replaces = "hand-writing item Lua", output = "one line per finding", group = "content", cost = "low" },
      { id = "web_builder", command = "python tools/web_builder/app.py --web", purpose = "Flet UI that builds items visually (Effect -> Ops[]); headless.py drives it without a window", replaces = "hand-writing item Lua", output = "UI / Lua file", group = "content" },
      { id = "plugins", purpose = "analyzer plugins of dev_probe_async: balance, AI behaviour, CAS inspector, hot reload, stress test, profilers", replaces = "-", output = "prose", group = "analyse" },
      -- Rust exports (rust_core; purpose = the first sentence of the Rust `///` docs)
      { id = "rust:EventCorrelator", replaces = "-", cost = "low" },
      { id = "rust:FlowField", replaces = "-", cost = "low" },
      { id = "rust:LogCompressor", replaces = "-", cost = "low" },
      { id = "rust:LuaContent", replaces = "lupa (the Python Lua backend)", cost = "low" },
      { id = "rust:ProbeAnalyzer", replaces = "-", cost = "low" },
      { id = "rust:QaKernels", replaces = "Python graph walks and bootstrap loops", cost = "low" },
      { id = "rust:RunAnalytics", replaces = "Python loops of probe_kernels", cost = "low" },
      { id = "rust:SimulationEnv", replaces = "-", cost = "low", status = "stub" },
      { id = "rust:StateDiffCalculator", replaces = "-", cost = "low" },
      { id = "rust:TacticsBandit", replaces = "the Python bandit of enemy_ai", cost = "low" },
      { id = "rust:WorldGenerator", replaces = "-", cost = "low" },
      { id = "rust:find_path", replaces = "the Python pathfinder (twin)", cost = "low" },
      { id = "rust:flow_field", replaces = "the Python flow field (twin)", cost = "low" },
      { id = "rust:resolve_hit", replaces = "the Python damage pipeline (twin)", cost = "low" },
      { id = "rust:resolve_hits", replaces = "a Python loop of damage.resolve", cost = "low" },
      -- Lua files that declare `-- tool:`
      { id = "lua:agent_kit.lua", replaces = "roles, call budgets, model choices and report contract typed into every agent prompt", cost = "low" },
      { id = "lua:guards.lua", replaces = "hard-coded thresholds, path patterns and messages in the hook", cost = "low" },
      { id = "lua:qa.lua", replaces = "hard-coded QA thresholds and check lists in Python", cost = "low" },
    },
  },

  -- Выбор тестов по графу импортов (qa.py affected / test --changed)
  tests = {
    always = { "tools/combat_smoke_test.py" },   -- дешёвые проверки, гоняются всегда
    base_ref = "origin/main",                    -- с чем сравнивать для "изменённых файлов"
    known_failures = "tests/qa_known_failures.json",
  },
}
