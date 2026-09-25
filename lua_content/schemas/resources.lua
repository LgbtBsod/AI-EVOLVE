-- lua_content/schemas/resources.lua — namespace resources (hp/mana/chakra/souls/lifespan).
-- Текущее значение меняют только heal/drain/deal/set; max_* и *_regen — обычные статы.
return {
  namespace = "resources",
  required  = { "max_stat" },
  fields = {
    max_stat = "имя стата-потолка (hp -> max_hp)",
    regen    = "nil | имя стата регена в секунду (hp_regen)",
    min      = "число (обычно 0)",
    decay    = "nil | число за секунду (rage гаснет)",
    visible  = "bool",
    tags     = "{string} (combat)",
  },
  planned = { "souls (Geto)", "lifespan (fuel_consume)", "cursed_energy" },
}
