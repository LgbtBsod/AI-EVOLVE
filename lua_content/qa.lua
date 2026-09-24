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

  -- Выбор тестов по графу импортов (qa.py affected / test --changed)
  tests = {
    always = { "tools/combat_smoke_test.py" },   -- дешёвые проверки, гоняются всегда
    base_ref = "origin/main",                    -- с чем сравнивать для "изменённых файлов"
    known_failures = "tests/qa_known_failures.json",
  },
}
