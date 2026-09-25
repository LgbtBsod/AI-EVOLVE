-- lua_content/kinds/temporal.lua — Temporal Layer (ЧАСТЬ 3.9). Поверх Timeline
-- (src/core/timeline.py: query/rewind/fork/simulate). retroactive_erase — спека Balefire.
local function k(id, handler, fields, note)
  return { id = id, layer = "temporal", handler = handler, fields = fields, note = note }
end
return {
  k("pan_temporal_control", "planned", { "scope" }, "контроль через все времена (limbo-вечность jubi)"),
  k("time_as_space", "planned", { "target" }, "время как пространство: ручное движение head (Interstellar)"),
  k("time_erase", "planned", { "duration" }, "стирание времени: промотать журнал, мир не помнит (King Crimson)"),
  k("time_direction", "planned", { "dir", "scope" }, "направление времени (Tenet inversion: world.time.direction)"),
  k("retroactive_erase", "planned", { "target", "depth", "effects" },
    "Balefire: timeline.query(source=target) -> undo цепочкой -> удалить entity из EntityManager -> commit erase reversible=false; effects={undo_actions,undo_deaths,no_resurrection}"),
}
