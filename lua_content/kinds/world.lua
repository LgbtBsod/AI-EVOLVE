-- lua_content/kinds/world.lua — World Layer (ЧАСТЬ 3.4). Мир как сущность: id="world".
local function k(id, fields, note)
  return { id = id, layer = "world", handler = "planned", fields = fields, note = note }
end
return {
  k("apply_status_to_world", { "status_id", "duration" }, "статус на мир (Dragonrot, Insight)"),
  k("thresholds", { "stat", "levels", "on_cross" }, "пороги состояния мира -> глобальные события Timeline"),
  k("world_reset", { "retain", "wipe" }, "сброс мира (Made in Heaven: retain=knowledge?)"),
  k("universe_reset", { "seed" }, "сброс вселенной; irreversible"),
  k("global_event", { "kind", "data" }, "событие в Timeline всем сразу (Софон мигает)"),
}
