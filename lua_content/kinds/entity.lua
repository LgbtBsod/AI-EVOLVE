-- lua_content/kinds/entity.lua — Entity Layer (ЧАСТЬ 3.8). Определяет СТРУКТУРУ
-- персонажа: слоты (bricks/items.lua slot), колоды, реагенты. slot_change — событие журнала.
local function k(id, fields, note)
  return { id = id, layer = "entity", handler = "planned", fields = fields, note = note }
end
return {
  k("slot_system", { "slots", "capacity" }, "слоты equip (NieR chips: main/support/dead)"),
  k("reagent_slot", { "elements", "cast_from" }, "реагенты как каст (Invoker: комбинация элементов)"),
  k("identity_source", { "fields" }, "идентичность из данных (Виего: serialize entity -> possess)"),
}
