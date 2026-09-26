-- Правила гипотез и прогноза (tools/probe_analysis.py -> tools/probe_rules.py).
-- Данные, не код: порядок строк = порядок проверки (потом стабильная сортировка по severity).
--
-- Строка правила:
--   id, severity ("high"|"medium"|"low"|"info" или "@факт" - severity вычисляет Python),
--   when  : условие (см. ниже), say: шаблон str.format над фактами ({min_near:.0f}, {cfg[low_hp_fraction]:.0%}),
--   evidence: список { ключ, факт [, "r1"] } ("r1" = round(v, 1)),
--   look  : список шаблонов или "@факт" (список из Python), next: подсказка (опционально).
-- Условие: лист { m = факт | {числитель, знаменатель}, op = eq|ne|gt|ge|lt|le|truthy|falsy|isnone|notnone,
--   v = число | "$порог" | "@факт" } или { all = { ... } } / { any = { ... } }.
--   Сравнение с None = ложь; деление на 0 = None.
-- Факты, требующие арифметики (fn в probe_analysis._facts_*): err_*, died_*, stuck_*, growth/kill_rate, blank_sev.
local function c(m, op, v) return { m = m, op = op, v = v } end

return {
  hypotheses = {
    { id = "ERRORS", severity = "high", when = c("errors_n", "truthy"),
      say = "{errors_n} ERROR log line(s) during the run",
      evidence = { { "first", "err_first" }, { "where", "err_where" } }, look = "@err_look",
      next = "fix the first error; later ones are often its consequences" },

    { id = "NO_ENEMIES", severity = "high",
      when = { all = { c("attacks", "eq", 0), c("duration", "ge", 5), c("min_near", "isnone") } },
      say = "no living enemies existed during the whole run",
      evidence = { { "samples", "n_samples" } },
      look = { "src/scenes/main_game_scene.py:_spawn_enemies/_spawn_initial_enemies" } },

    { id = "NO_COMBAT", severity = "medium",
      when = { all = { c("attacks", "eq", 0), c("duration", "ge", 5), c("min_near", "gt", "$close_range") } },
      say = "no combat at all: nearest enemy never came closer than {min_near:.0f}u",
      evidence = { { "min_distance", "min_near", "r1" }, { "duration", "duration", "r1" } },
      look = { "src/scenes/main_game_scene.py:_spawn_enemies (spawns at map edges)",
               "src/entities/enemy.py:update_ai (detection_range)" },
      next = "spawn an enemy next to the hero: agent_play 'spawn enemy' or dev_probe --action-at 1:1" },

    { id = "CLOSE_BUT_NO_ATTACKS", severity = "high",
      when = { all = { c("attacks", "eq", 0), c("duration", "ge", 5), c("min_near", "le", "$close_range") } },
      say = "enemy was {min_near:.1f}u from the hero yet nobody attacked",
      evidence = { { "min_distance", "min_near", "r1" } },
      look = { "src/entities/character.py:update_ai", "src/entities/enemy.py:update_ai/attack",
               "src/features/combat_plugin.py (combat_system wiring)" } },

    { id = "HERO_NEVER_ATTACKS", severity = "high",
      when = { all = { c("enemy_attacks", "truthy"), c("player_attacks", "falsy") } },
      say = "hero was attacked {enemy_attacks}x but never attacked back",
      evidence = { { "taken", "taken" } },
      look = { "src/entities/character.py:update_ai (fighting state)", "src/entities/character.py:attack" } },

    { id = "ENEMIES_PASSIVE", severity = "medium",
      when = { all = { c("player_attacks", "truthy"), c("enemy_attacks", "falsy"), c("min_near", "lt", 2) } },
      say = "hero attacked {player_attacks}x, enemies never attacked back despite contact",
      evidence = { { "min_distance", "min_near", "r1" } },
      look = { "src/entities/enemy.py:update_ai/attack" } },

    { id = "ZERO_DAMAGE_HITS", severity = "medium",
      when = { all = { c("hits", "ge", 5), { m = { "zero_damage_hits", "hits" }, op = "gt", v = "$zero_damage_ratio" } } },
      say = "{zero_damage_hits}/{hits} landed hits dealt 0 damage",
      evidence = { { "zero", "zero_damage_hits" }, { "hits", "hits" } },
      look = { "src/systems/combat/combat_system.py:execute_attack (defense/floor)" } },

    { id = "CRIT_NEVER_FIRES", severity = "medium",
      when = { all = { c("crit_chance", "truthy"), c("crit_chance", "ge", "$crit_min_chance"),
                       c("player_hits", "ge", "$crit_min_hits"), c("player_crits", "eq", 0) } },
      say = "0 crits in {player_hits} hero hits with crit_chance={crit_chance:.0%}",
      evidence = { { "expected", "crit_expected", "r1" } },
      look = { "src/systems/combat/combat_system.py:execute_attack (critical roll)", "src/core/rng_manager.py" } },

    { id = "HP_INVALID", severity = "high", when = c("invalid_count", "truthy"),
      say = "invalid hero HP/position in {invalid_count} sample(s)",
      evidence = { { "first_t", "invalid_t" }, { "hp", "invalid_hp" }, { "max_hp", "invalid_mhp" } },
      look = { "src/entities/character.py (health setter / level-up max_health)" } },

    { id = "HP_PINNED", severity = "high", when = c("pinned", "truthy"),
      say = "hero stayed under {cfg[low_hp_fraction]:.0%} HP for {pinned_secs:.0f}s without dying",
      evidence = { { "from_t", "pinned_t0" }, { "hp", "pinned_hp", "r1" } },
      look = { "src/scenes/main_game_scene.py:update (health_regen)", "src/entities/character.py:is_alive/take_damage" },
      next = "possible death latch / regen fighting damage" },

    { id = "HERO_DIED", severity = "@died_sev", when = c("death_t", "notnone"),
      say = "hero died at t={death_t:.1f}s{died_note}",
      evidence = { { "killed_by_last5s", "died_killers" }, { "dmg_last5s", "died_dmg" } },
      look = { "src/entities/enemy.py (damage by type)", "src/entities/enemy.py:apply_level_bonus" } },

    { id = "HERO_STUCK", severity = "medium", when = c("stuck", "truthy"),
      say = "hero didn't move for {stuck_secs:.0f}s and wasn't fighting",
      evidence = { { "from_t", "stuck_t0" }, { "ai", "stuck_ai" }, { "pos", "stuck_pos" } }, look = "@stuck_look" },

    { id = "ENEMY_PRESSURE", severity = "low",
      when = { all = { c("growth", "ge", "$pressure_per_min"), c("kill_rate", "lt", "@growth") } },
      say = "enemy count grows +{growth:.1f}/min, kills only {kill_rate:.1f}/min",
      evidence = { { "start", "count_start" }, { "end", "count_end" } },
      look = { "src/scenes/main_game_scene.py (enemy_spawn_interval/max_enemies)" } },

    { id = "RENDER_BLANK", severity = "@blank_sev", when = c("blank_frames", "truthy"),
      say = "{blank_frames} blank/solid-color screenshot(s) while game state looked alive",
      evidence = { { "blank", "blank_frames" }, { "screenshots", "screenshots" } },
      look = { "panda3d.log", "src/scenes/main_game_scene.py:_setup_camera" } },
  },

  -- forecast()["outlook"]: первое сработавшее правило (факты = ключи прогноза)
  outlook = {
    { when = c("death_eta_s", "notnone"), say = "hero projected to die in ~{death_eta_s:.0f}s ({eta_basis})" },
    { when = c("hp_slope_per_s", "notnone"), say = "hero HP stable or recovering at the current pressure" },
  },
}
