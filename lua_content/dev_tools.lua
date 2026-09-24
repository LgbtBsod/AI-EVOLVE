-- lua_content/dev_tools.lua
-- Настройки агентских dev-инструментов: tools/agent_play.py, tools/dev_probe.py,
-- tools/probe_db.py (анализ - tools/probe_analysis.py).
-- Python читает этот файл через lupa.lua55 (tools/probe_runtime.py:
-- load_tool_settings). Без lupa действуют те же значения по умолчанию из
-- Python - поэтому здесь можно менять, но не удалять ключи.

return {
  runtime = {
    fps = 30,               -- фиксированный шаг fast-режима (кадров игрового времени в секунду)
    render = "none",        -- agent_play по умолчанию: none | offscreen | window
    sample_interval = 1.0,  -- как часто писать state.jsonl (секунды игрового времени)
  },

  -- Пороги правил-гипотез (probe_analysis.hypotheses)
  analysis = {
    low_hp_fraction = 0.2,     -- "низкий HP" - доля от max_health
    pinned_seconds = 5.0,      -- столько секунд под порогом без смерти = HP_PINNED
    stuck_seconds = 8.0,       -- окно для HERO_STUCK
    stuck_distance = 0.5,      -- ...если за окно сместился меньше чем на столько
    close_range = 5.0,         -- враг ближе - "контакт был" (NO_COMBAT vs CLOSE_BUT_NO_ATTACKS)
    zero_damage_ratio = 0.2,   -- доля попаданий с уроном 0 для ZERO_DAMAGE_HITS
    crit_min_hits = 40,        -- CRIT_NEVER_FIRES проверяется только от стольких попаданий
    crit_min_chance = 0.05,
    pressure_per_min = 4.0,    -- рост числа врагов (в минуту) для ENEMY_PRESSURE
    forecast_window_min = 5.0, -- окно линейной экстраполяции HP (секунды)
    forecast_window_max = 15.0,
    forecast_recent_s = 3.0,   -- окно темпа урона для ETA смерти (бэктест: ошибка ~8% против ~34% у тренда HP)
    hypotheses_shown = 5,      -- сколько гипотез печатать (остальные - в JSON)
  },

  -- Интерфейс управления для агента: ТОЛЬКО то, что может живой игрок
  -- (main.py: _bind_input). Команда DSL -> клавиша игры.
  agent = {
    player_keys = {
      enemy = "1",       -- spawn enemy
      trap = "2",        -- spawn trap
      chest = "3",       -- spawn chest
      attack = "space",  -- атаковать ближайшего врага
      interact = "e",    -- взаимодействие (удержание)
    },
    max_wait_per_command = 600,  -- потолок "wait"/"until" на одну команду (сек игрового времени)
    max_repeat = 10,             -- потолок "spawn enemy x N"
    observe_nearest = 3,         -- сколько ближайших врагов показывать в observe
  },

  db = {
    path = "dev_probe_output/probe.sqlite",  -- относительно корня репозитория
    keep_runs = 200,                         -- старые прогоны вычищаются при ingest
  },
}
