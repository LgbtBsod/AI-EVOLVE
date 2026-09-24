# Effect Schema v1: универсальная структура Effect → Ops[]

Один язык для любого предмета, скилла и эффекта: **эффект = триггер + список операций**.
Все операции (`mod`, `heal`, `drain`, `deal`, `buff`, `extend`, `set`, `kill`, …) — один и тот же
объект; различаются только `kind` и набором заполненных полей. Остальные поля — `nil`.

Реализация: `tools/effect_schema/` (`schema.py` — типы, `validate.py`, `lua_gen.py` / `lua_parse.py`
— JSON ↔ Lua, `pred_lua.py` — условия Python → Lua, `sim.py` — тренировочная комната, `catalog.py` —
шаблоны, `digest.py` — сжатый вид для агентов). Контент предметов лежит
в Lua (`lua_content/items/*.lua`). Механики проверяют исполняемые спеки, например
`tests/test_lost_my_self_spec.py`: она прогоняется и по каталогу, и по Lua-файлу предмета.

## Уровень 1: Effect

```lua
{
  id       = "lost_my_self",           -- уникальный
  tags     = {"berserk", "passive"},
  trigger  = { ... },                  -- когда эффект включён
  duration = nil | Value,              -- nil = пока trigger истинен
  cooldown = nil | Value,
  stacks   = nil | { ... },
  amplify  = nil | { when, every, of, factor },   -- см. ниже (добавлено)
  ops      = { op, op, ... },
}
```

## Уровень 2: Op

```lua
{
  kind   = "mod" | "heal" | "drain" | "deal" | "set" | "buff" | "extend" | "remove_buff" | "apply_effect" | "kill",
  target = "self" | "enemy" | "ally" | "source" | "allies",
  stat   = "hp" | "strength" | "crit_chance" | ... | nil,
  op     = "add" | "sub" | "mul" | "div" | "set" | "min" | "max",
  value  = Value,  scale = Scale,  when = pred,  fail = { op, ... },
  duration = Value, cooldown = Value, extend = { on = "kill", flat = 5 },
  buff_id = "last_will",
  flags  = { "no_crit", "true_damage", "silent", "iframe" },
}
```

## Уровень 3–5: Value, Scale, Trigger

```lua
value = { flat = 40 } | { pct = 20 } | { pct = 0.5, of = "max_hp" } | { ref = "ctx.strength" }
scale = { every = 10, of = "hp_missing_below_40", value = Value, factor = 1, cap = nil, floor = nil }
-- итог: base + floor(ctx[of] / every) * value * factor
trigger = { kind = "passive" } | { kind = "condition", when = pred } | { kind = "event", event = "attack", filter = pred, owner_has = "effect_id" }
```

## Условия (pred) и загрузка Lua

Условие пишется на Python-подмножестве: числа, `ctx.<поле>`, `+ - * / % **`, сравнения (и цепочки),
`and`/`or`, `max/min/floor/ceil/abs`. Оно обязано быть булевым: сравнение или `and`/`or` сравнений
(в Lua 0 — истина, в Python — ложь; валидатор это проверяет). В Lua генератор пишет

```lua
when = pred("ctx.hp_pct < 40", function(ctx) return (ctx.hp_pct < 40) end)
```

Движок вызывает объект как функцию (`p(ctx)` через `__call`). Инструменты читают файл через
`tools/lua_bridge.py`: Lua исполняется в песочнице (Rust/mlua, фолбэк lupa), `pred` превращается
в исходную строку, данные приходят одной JSON-строкой. Своего парсера Lua больше нет.
`lua_bridge.eval_preds(file, ctxs)` считает все условия файла в Lua на списке ctx — так тесты
проверяют, что Lua и Python считают одинаково.

## Уточнения по итогам проверки (исходный черновик их не учитывал)

Каждый пункт найден, когда описание геймдизайнера прогнали как исполняемую спеку на симуляции.

1. **`pct` без `of` — это процент от того же стата.** Так правильно для «+20% силы», но не для
   аддитивных статов. «+5% шанса крита», «+10% крит-урона» и «+5% вампиризма» — это **пункты**,
   поэтому их пишут через `flat`. С `pct` крит 10% давал +0.5 вместо +5, а вампиризм при базе 0 не рос вовсе.
2. **База для `pct`**: base + событийный слой, но *без* вклада пассивов. Иначе пассив считается от
   уже усиленного им самим значения: «+20% силы» давал 100 → 120 → 24, и так по кругу.
3. **Событийный `mod`** задаёт *текущее* значение своей операции: повторное срабатывание заменяет
   прошлый вклад, а не складывается с ним. В Vampire's Fang «+5 и +1 за kill» — это 5 + kills,
   а не рост с каждым ударом. Если нужен стек по срабатываниям — описывай его явно через `stacks`.
4. **Неуязвимость** — `flags = {"iframe"}` у `buff`: пока бафф активен, входящий урон игнорируется.
5. **`extend = { on = "kill", flat = 5 }`** у баффа срабатывает на событие `on`, пока бафф активен.
   Раньше расширение объявлялось, но к событию привязано не было.
6. **`cooldown` баффа** отсчитывается от момента выдачи и переживает истечение баффа.
   Раньше кулдаун хранился в самом баффе и пропадал вместе с ним.
7. **`amplify`** (новое поле эффекта): пока `when` истинно, *все* бонусы эффекта (`mod add/sub`)
   умножаются на `factor ^ floor(ctx[of] / every)`. Это универсальный механизм, а не поле под
   конкретный предмет: «при 1 HP всё ×2 за каждые 10%» не выражается через `scale`, потому что
   `scale` растёт линейно.
8. **Длительность щита Last Will — ровно 5 с.** Пример черновика с `duration.scale.factor = 2`
   (5 + 10 с за шаг = 35 с) противоречит дизайну: удвоение относится к бонусам при 1 HP, а не к щиту.

## Lost My Self (Sorrow of Berserk) по дизайну

```lua
{ id = "lost_my_self", tags = {"berserk", "passive"},
  trigger = { kind = "condition", when = pred("ctx.hp_pct < 40", function(ctx) return (ctx.hp_pct < 40) end) },
  amplify = { when = "ctx.hp <= 1", every = 10, of = "hp_missing_below_40", factor = 2 },  -- при 1 HP: x8
  ops = {
    { kind = "mod", target = "self", stat = "strength",    op = "add", value = { pct = 20 } },
    { kind = "mod", target = "self", stat = "stamina",     op = "add", value = { pct = 10 } },
    { kind = "mod", target = "self", stat = "crit_chance", op = "add", value = { flat = 5 },
      scale = { every = 10, of = "hp_missing_below_40", value = { flat = 5 } } },
    { kind = "mod", target = "self", stat = "crit_dmg",    op = "add", value = { flat = 10 },
      scale = { every = 10, of = "hp_missing_below_40", value = { flat = 10 } } },
    { kind = "mod", target = "self", stat = "aspd",        op = "add", value = { pct = 5 },
      scale = { every = 10, of = "hp_missing_below_40", value = { pct = 10 } } },
    { kind = "mod", target = "self", stat = "hp_regen",    op = "add", value = { flat = 0 },
      scale = { every = 10, of = "hp_missing_below_40", value = { flat = 20 } } },
    { kind = "mod", target = "self", stat = "lifesteal",   op = "add", value = { flat = 0 },
      scale = { every = 10, of = "hp_missing_below_40", value = { flat = 5 } } },
  } }

{ id = "lost_my_self.attack",
  trigger = { kind = "event", event = "attack", owner_has = "lost_my_self" },
  ops = {
    { kind = "drain", target = "self", stat = "hp", op = "sub", value = { pct = 0.5, of = "max_hp" },
      scale = { every = 10, of = "hp_missing_below_40", value = { pct = 0.5, of = "max_hp" } },
      fail = {                                               -- цена > текущего HP
        { kind = "set", target = "self", stat = "hp", op = "set", value = { flat = 1 } },
        { kind = "buff", target = "self", buff_id = "last_will", flags = {"iframe"},
          duration = { flat = 5 }, cooldown = { flat = 30 }, extend = { on = "kill", flat = 5 } } } },
    { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { pct = 1.5, of = "max_hp" },
      scale = { every = 10, of = "hp_missing_below_40", value = { pct = 1.5, of = "max_hp" } } },
  } }
```

Полная сгенерированная версия лежит в `lua_content/items/sorrow_of_berserk.lua`. Её собирает
`ui_logic.to_lua(item)` из `tools/effect_schema/catalog.py`; после правки шаблона Lua нужно
перегенерировать, иначе упадёт `test_lua_item_matches_catalog`.
