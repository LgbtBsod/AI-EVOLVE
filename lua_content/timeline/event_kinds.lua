-- lua_content/timeline/event_kinds.lua — КОНФИГ журнала (логика в src/core/timeline.py).
-- A.8: кто что пишет в Timeline; reversible-политика (A.4): irreversible событие
-- блокирует rewind за себя. commit kind'ов слоёв = строки ниже; интеграция с живым
-- EventSystem — attach_event_system(es, kinds) (префикс "es." задаёт ядро).
return {
  -- слой -> { пишет (commit kinds), читает (query) }
  by_layer = {
    effect   = { writes = { "damage", "heal", "cast", "mod_add", "buff_apply", "kill", "summon" },
                 reads  = { "attack_hit", "kill" } },   -- counter/on_kill триггеры
    rules    = { writes = { "rule_add", "rule_remove" }, reads = {} },
    state    = { writes = { "snapshot", "restore" },     reads = { "*" } },
    world    = { writes = { "world_event", "threshold_cross" }, reads = { "between", "by_kind" } },
    meta     = { writes = { "file_op", "save_op" },      reads = {} },
    temporal = { writes = { "rewind", "branch", "time_scale" }, reads = { "*" } },
    ontological = { writes = { "tier_change", "concept_op" }, reads = { "by_kind" } },
    social   = { writes = { "contract", "reputation_change" }, reads = { "by_entity" } },
    entity   = { writes = { "slot_change", "chip_change" }, reads = { "by_entity" } },
    narrative= { writes = { "narrative_event", "panel_jump" }, reads = {} },
  },

  -- политика reversibility (A.4): эти kinds всегда irreversible=true
  irreversible = {
    "erase", "retroactive_erase", "file_delete", "save_corruption",
    "universe_reset", "world_reset", "concept_erase",
  },
  irreversible_reason = {
    erase = "существование не возвращается undo-функцией",
    file_delete = "файл удалён платформой, игровой откат невозможен",
    universe_reset = "новая вселенная — новый лог",
  },

  -- preserve_memory при rewind (Time Leap/Contessa/Balefire-жертвы помнят):
  memory_flags = { "preserves_memory", "knowledge_registry" },

  -- причинность (A.7): causals заполняет рантайм по цепочке событий удара
  causal_chains = {
    { chain = { "cast", "damage", "kill" }, note = "Саске кастанул -> попал -> смерть (дебаг GER)" },
    { chain = { "attack", "attack_hit", "life_steal_heal" } },
  },
}
