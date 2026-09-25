-- lua_content/kinds/rules.lua — Rules Layer (ЧАСТЬ 3.2). Исполняются ДО Effect-слоя,
-- могут блокировать/менять эффекты. Handler'ы planned: ядро читает активные правила
-- (world.rules) перед диспатчем ops; точка встраивания — EffectManager.
local function k(id, fields, note)
  return { id = id, layer = "rules", handler = "planned", fields = fields, note = note }
end
return {
  k("rule_override", { "rules", "scope" }, "переопределить правило мира (jubi: physics off, ninjutsu off)"),
  k("rule_entity", { "rule" }, "правило как объект мира: можно найти и убить (Lion Heart)"),
  k("reality_marble", { "domain", "ops" }, "свой мир в области (MMK домен: внутри действуют твои законы)"),
  k("reality_by_theme", { "genre" }, "реальность под жанр (Такаба: комедия отменяет убийство)"),
  k("causality_control", { "mode" }, "управление причинностью: link/unlink событий Timeline"),
  k("reverse_causality", { "effect", "cause" }, "результат раньше причины (God Hand, Accelerator)"),
  k("global_time_scale", { "value" }, "глобальная скорость времени (world.time.scale)"),
  k("block_physics", { "what" }, "блокировать физику (Infinity: полёт игнорирует инерцию)"),
}
