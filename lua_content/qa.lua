-- lua_content/qa.lua
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
    { name = "forced_attacks", seed = 5, script = "spawn enemy x2; attack x5; wait 20; expect kills>=1" },
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

  -- Выбор тестов по графу импортов (qa.py affected / test --changed)
  tests = {
    always = { "tools/combat_smoke_test.py" },   -- дешёвые проверки, гоняются всегда
    base_ref = "origin/main",                    -- с чем сравнивать для "изменённых файлов"
    known_failures = "tests/qa_known_failures.json",
  },
}
