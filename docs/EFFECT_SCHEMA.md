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
  kind   = "mod" | "heal" | "drain" | "deal" | "set" | "buff" | "extend" | "remove_buff" | "apply_effect" | "kill"
         | "summon" | "move",
  target = "self" | "enemy" | "ally" | "source" | "allies" | "area",
  radius = 3, center = "target" | "self",            -- для area
  affects = "all" | "others" | "enemies" | "allies", -- для area; по умолчанию all (френдли фаер)
  toward = "source",                                  -- только mod vision_range: стелс
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

## Что нашли кузница предметов и itemcheck

Кузница (`tools/effect_schema/forge.py`) собирает предмет, который задействует всю схему, плюс N
случайных эффектов со сложными условиями; `itemcheck` гоняет его от валидации до боя (см. ниже).
Каждый пункт найден так и теперь закреплён тестом (`tests/test_item_forge.py`).

9. **Ресурсы: hp, mana, stamina** — как у `Character` в игре. Текущее значение меняют только
   `heal/drain/deal/set`; максимум (`max_hp/max_mana/max_stamina`) и реген (`hp_regen/mana_regen/
   stamina_regen`, в секунду, на тике) — обычные статы для `mod`. Раньше `heal/drain` по мане молча
   били по HP, а `mod stamina` был «статом». Lost My Self даёт +10% **максимальной** стамины.
10. **`mod` пишется юниту-цели.** `target = "enemy"` вешает дебафф на врага (раньше — на героя).
    `pct` без `of` берётся от того же стата цели. Новый враг (респавн) приходит без старых дебаффов.
11. **Границы статов и значения по умолчанию** — в `lua_content/effect_rules.lua` (`max_hp ≥ 1`,
    `crit_chance ∈ [0, 100]`, `aspd ≥ 0.1` …). Границы режут итоговый стат, а не бонус эффекта.
    Когда максимум падает, текущий ресурс обрезается (раньше HP оставался выше максимума).
12. **Отрицательный реген — это урон**: HP не уходит ниже нуля, в 0 — смерть. Лечение не воскрешает.
13. **`trigger.kind = "applied"`** — эффект без своего триггера, его запускает `apply_effect`.
    Валидатор проверяет, что `apply_effect` и `owner_has` ведут на эффекты предмета и что в
    цепочках `apply_effect` нет циклов. Так нашёлся Venom Bite, чей яд `poison_stack` не был
    определён нигде: эффект молча ничего не делал.
14. **`threshold` (эффект) и `trigger.cross`** — зона `hp_cross` теперь часть схемы: раньше их
    понимал только симулятор, а генератор Lua их терял.
15. **`cooldown` эффекта исполняется**: событийный эффект срабатывает не чаще раза в N секунд.
16. **Именованные условия** (`when = "low_hp_40"`) — выражения в `effect_rules.lua → predicates`.
    Lua-файл предмета получает настоящую функцию; раньше там стояла заглушка `return true`.
17. **Числа в условиях — float в обоих языках**, симулятор считает как Lua: деление на ноль даёт
    ±inf или nan, а не исключение; `%` — это `luai_nummod` (знак нуля: `0.0 % -5` = `0.0`, а не
    `-0.0`); `(-8) ^ 0.5` = nan, `x ^ 2` = `x * x`; константы в Lua пишутся как `40.0`,
    `floor/ceil` дают float. Контекст движок передаёт float-ами. Деление на литерал 0 —
    ошибка валидации. После этих правок 40 «враждебных» сидов (≈20 тыс. условий × 300 ctx)
    дают ноль расхождений между Python, mlua и lupa.

## Дальность, обзор, стелс и френдли фаер

18. **`area` бьёт всех живых в круге** — союзников и самого заклинателя тоже (френдли фаер, всё
    по-честному). `affects` сужает круг: `others` (все, кроме заклинателя — рассекающий удар, нова
    босса вокруг себя), `enemies`, `allies`. ИИ сам решает, стоит ли бить по кругу:
    `EffectManager.area_preview(caster, ability, target)` возвращает, кого заденет. Герой не
    бросает огненный шар себе под ноги, а обычный враг не бьёт по кругу со своими, если героя
    в нём нет. Босс бьёт и по своим слугам, но не по себе.
19. **`attack_range` — стат**: дальность удара оружием (`weapon_attack.range = "attack_range"`).
    Лук даёт +7, копьё +1.5. `range` способности может быть числом, именем стата или Value
    (`{ pct = 110, of = "attack_range" }` — ближний навык бьёт на дальность оружия).
20. **`vision_range` — стат**: как далеко сущность замечает других. Единственная проверка —
    `EffectManager.can_see(observer, target)`, её спрашивают ИИ героя (видимые враги) и мозг врага.
21. **Стелс = `mod vision_range` по `area` с `toward = "source"`**: в круге обзор снижается
    только В СТОРОНУ заклинателя; остальных наблюдатель видит как прежде. Пример — «Покров тени»
    (`abilities.lua`) и «Дымовая шашка» (`game_items.lua`): круг 10–14, −75…80% на 5–6 с.
    Видимость считает математика менеджера, а не картинка: графика (полупрозрачность) рисуется
    из тех же чисел, так что проверять стелс компьютерным зрением не нужно.

22. **Атака — тот же эффект, направленный на врага.** Удар оружием — это способность оружия
    (`item.attack`), то есть обычный список операций `deal hp sub`. Как эффект доходит до цели,
    решает поле `target` операции: `enemy` бьёт одну цель (копьё `spear_thrust`, лук `bow_shot`,
    удар без оружия `weapon_attack`), `area` + `center = "self"` + `arc` — конус перед собой
    (меч `sword_swing` 110°, топор `axe_swing` 180°), `area` вокруг цели — посох `staff_blast`.
    `radius` может быть именем стата: `radius = "attack_range"` — дуга на длину клинка.
    Навыки не привязаны к форме удара оружия: у копья есть круговой `spear_sweep`.
    Менеджер подставляет удар надетого оружия вместо `weapon_attack` (`EffectManager.resolve`).

## Проверка предмета: itemcheck

```
python -m tools.effect_schema.itemcheck lua_content/items/sorrow_of_berserk.lua
python -m tools.effect_schema.itemcheck --forge 2000 --seed 3        # выковать и проверить
python -m tools.effect_schema.itemcheck --forge 300 --seed 5 --hostile   # искать расхождения Python/Lua
```

Одна строка на проверку: `validate` (схема, ссылки, булевость условий), `lua` (рендер и исполнение
каждым бэкендом — те же данные), `preds` (каждое условие в Lua и Python на случайных ctx одним
вызовом), `sim` (сценарий боя со всеми событиями, инварианты после каждого шага), `determinism`,
`coverage` (какие части схемы задействованы). Предмет на 10 тыс. эффектов проверяется за ~25 с.

## Lost My Self (Sorrow of Berserk) по дизайну

```lua
{ id = "lost_my_self", tags = {"berserk", "passive"},
  trigger = { kind = "condition", when = pred("ctx.hp_pct < 40", function(ctx) return (ctx.hp_pct < 40) end) },
  amplify = { when = "ctx.hp <= 1", every = 10, of = "hp_missing_below_40", factor = 2 },  -- при 1 HP: x8
  ops = {
    { kind = "mod", target = "self", stat = "strength",    op = "add", value = { pct = 20 } },
    { kind = "mod", target = "self", stat = "max_stamina", op = "add", value = { pct = 10 } },
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
