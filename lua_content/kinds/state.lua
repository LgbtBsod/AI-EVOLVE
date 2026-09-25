-- lua_content/kinds/state.lua — State Layer (ЧАСТЬ 3.3). Runtime: src/core/timeline.py
-- (capture_snapshot / restore / rewind). Op'ы тонкие: вызывают API журнала.
local function k(id, handler, fields, note)
  return { id = id, layer = "state", handler = handler, fields = fields, note = note }
end
return {
  k("snapshot", "timeline.capture_snapshot", { "tag" }, "снимок мира (serialize_fn инъектируется)"),
  k("restore_state", "timeline.restore", { "tag" }, "восстановить по снапшоту (Flowey SAVE)"),
  k("load_state", "timeline.restore", { "slot" }, "загрузить сейв с диска"),
  k("state_rewind", "timeline.rewind", { "to_tick", "options" },
    "откат: options={ preserve_memory=[...] (Time Leap помнит), create_branch, cascade, dry_run }"),
  k("time_loop", "planned", { "period", "retain" }, "петля: автоматический rewind по таймеру (Outer Wilds)"),
  k("enter_dream", "planned", { "layer_of", "ops" }, "сон: вложенный state-слой со своими правилами"),
  k("hack_consciousness", "planned", { "target", "writes" }, "взлом сознания (Inception: идея внедряется в memory)"),
  k("memory_block", "planned", { "target", "until" }, "блок памяти: knowledge_registry цели закрывается"),
  k("nonlinear_time_perception", "planned", { "target" }, "нелинейное восприятие (Dr Manhattan: читает весь лог)"),
}
