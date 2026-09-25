-- lua_content/schemas/statuses.lua — namespace statuses (stun, burn, amaterasu, last_will).
-- Дефиниция статуса = Effect + правила наслаивания (stacking/purgeable).
return {
  namespace = "statuses",
  required  = { "purgeable", "stacking" },
  fields = {
    duration    = "'required' | 'optional' (должен ли кастер передавать duration)",
    tick        = "nil | интервал тикающих ops (burn наносит урон раз в tick)",
    ops         = "{Op} — что делает статус",
    on_enter    = "nil | {Op}", on_exit = "nil | {Op}",
    breakable_by= "nil | { 'damage', 'purge', action } (стан сломается уроном)",
    purgeable   = "bool — снимается ли op purge",
    stacking    = "'replace' | 'refresh' | 'extend' | 'stack'",
  },
}
