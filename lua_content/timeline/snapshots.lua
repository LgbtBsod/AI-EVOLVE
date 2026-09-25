-- lua_content/timeline/snapshots.lua — КОНФИГ снапшотов/компакции/RNG
-- (A.6, A.9, A.10; исполнение — src/core/timeline.py capture_snapshot/compaction).
return {
  snapshots = {
    every_ticks = 300,                    -- базовый снимок (~5 c при 60 тик/с)
    before = { "boss_fight", "ultimate", "scene_enter", "save_game" },  -- критические точки
    differential = true,                  -- между базовыми — delta изменённых полей
    include = { "entities.stats", "entities.resources", "entities.statuses",
                "entities.effects", "entities.marks", "world.rules", "world.regions",
                "world.time", "rng.state" },
    registries_version = true,            -- версии реестров в снимке (B.7 миграция сейва)
    exclude = { "event_log", "undo_functions", "caches" },  -- восстанавливаются/пересчитываются
  },
  compaction = {                          -- A.9: лог растёт бесконечно
    rolling_window_ticks = 18000,         -- полный лог ~5 минут
    keep_snapshots_at = "every_base",     -- старше окна — только снапшоты
    aggregate = { ["hp_regen_tick"] = "per_second" },  -- микро-события агрегатом
  },
  rng = {                                 -- A.10: детерминизм replay/simulate
    record_rolls = true,                  -- каждый roll = событие rng_roll
    event_fields = { "seed_before", "seed_after", "value", "purpose" },
    gacha_uses_timeline = true,           -- op gacha роллит через журнал
  },
}
