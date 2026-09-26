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
-- of: стат / ctx-поле или псевдо-стат hp_missing_below_<N> (сколько % HP не хватает до порога N%: 40 - берсерк, 35 - Бесконечность Годжо);
--     семейство определяет ops.derived_ctx - ОДНО место, им пользуются и значения (of), и условия (ctx.hp_missing_below_35 > 5)
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
    `crit_chance ∈ [0, 100]`, `aspd ≥ 0.1` …). Границы режут итоговый стат, а не бонус эффекта. Статы урона
    (`accuracy`, `evasion`, `penetration_*`, `block_*`, `resist_<тип>`, `damage_<тип>` ...) объявлены там же: `is_stat` берёт их из этого реестра,
    в `KNOWN_STATS` их нет; типы урона - `lua_content/damage.lua` (семейства `families` разворачивает `rules()`), тип удара - тег способности.
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

## Op handlers: один интерпретатор операций (`src/effects/ops.py`)

Семантика каждой операции живёт в ОДНОМ месте: `OP_HANDLERS` (ключи = `schema.OP_KINDS`, по одному маленькому
обработчику на вид; тест `tests/test_ops_table.py`). Обработчики пишутся над простыми данными (dict операции, dict
контекста из float) и над интерфейсом `OpHost` - 42 примитива `op_*`, которые даёт интерпретатор-хозяин:
`EffectRuntime` (изолированный `Unit`: тренировочная комната, кузница, `tools/effect_schema`) и `EffectManager`
(сущности игры, `EntityState`). Порядок вычислений, ветвления и арифметика - в `ops.py`; цели, области, телеграфы, зрение,
фракции остаются в менеджере. Для переноса в Rust это механический порт: dict/f64 внутрь -> dict/f64 наружу, каждый
`op_*` становится методом трейта.

Порядок одной операции (`ops.apply_op`): значение (`compute_amount`) -> DoT/HoT (`deal`/`heal` с `every`+`duration`) ->
обработчик вида. Условие `when` и выбор цели делает хозяин до вызова.

| kind | обработчик (скелет - в `ops.py`) | примитивы хозяина |
|---|---|---|
| `deal` | hp -> урон, иначе (мана/стамина) -> трата ресурса | `op_damage`, `op_spend` |
| `heal` | лечение ресурса `stat` (по умолчанию hp) | `op_heal` |
| `drain` | `amount > ресурс` -> ветка `fail`, иначе трата (до 0 HP - смерть) | `op_resource`, `op_spend`, `op_nested` |
| `set` | жёсткая установка ресурса | `op_set_resource` |
| `mod` | делегирует хозяину; арифметика `MOD_MATH` (`add sub mul div set min max`) и замена вклада (`replace_contribution*`) - общие | `op_mod` |
| `buff` | кулдаун от выдачи -> `until = max(prev.until, t) + duration` -> запись баффа | `op_buffs`, `op_granted`, `op_duration`, `op_buff_record`, `op_after_buff` |
| `extend` | найти бафф, правило `extend` операции или баффа, фильтр по событию, продлить | `op_buffs`, `op_extend` |
| `remove_buff` | снять бафф | `op_buffs` |
| `apply_effect` | найти эффект по `buff_id`, выполнить его ops (`src->id`) | `op_find_effect`, `op_nested` |
| `kill` | убить цель | `op_kill` |
| `summon`, `move` | делегируют хозяину (в комнате мира нет - только строка лога) | `op_summon`, `op_move` |

**Расхождения хозяев, сохранённые 1-в-1** (рефакторинг не меняет поведение; каждое - именованный примитив, который можно
выровнять отдельным решением с перезаписью golden; ни одно не задето контентом игры, кроме пунктов 1-2):

1. `deal hp`: комната - сырой `Unit.deal_damage`; игра - конвейер `_damage` (`docs/DAMAGE_PIPELINE.md`: меткость -> уклонение ->
   блок -> крит -> тип -> броня с пробитием -> сопротивление -> iframe -> HP -> лайфстил -> события). `heal/set/drain`: правила потолка и воскрешения у каждого свои (`Unit` / `_heal`, `_set_resource`).
2. `kill`: комната ведёт счётчик `kills`, флаг `_killed_this_attack` и события; игра - истинный урон через `_damage`.
3. `set` без `stat`: комната ничего не делает, игра ставит hp; нересурсный `stat` игра применяет к полю сущности, если оно есть.
4. DoT/HoT: комната включает его при `duration is not None`, игра - при `duration` истинном (0 - мгновенный эффект).
5. `duration`: без значения комната берёт 10 с, игра - 5 с (`DEFAULT_DEBUFF_SECONDS`); формы dict разбираются по-разному
   (`{ref}`, неизвестное `scale.of`).
6. `buff`: запись баффа в комнате несёт `cooldown`/`last_cd`; в игре кулдаун выдачи хранит заклинатель, `extend.on == событие`
   продлевает бафф сразу только в комнате, игра обновляет статы (`refresh`).
7. `extend`: комната - `flat | pct [of]` и фильтр по `event` (или по `src` вида `effect#event(.fail)`); игра - только `flat`
   и `src.endswith("#" + on)`.
8. `mod`: комната меряет вклад операции ПОСЛЕ снятия старого (п.3 уточнений), игра - ДО (при повторном срабатывании
   записывается `amount - old`; событийных untimed-модов на себя в контенте нет). Только в игре: `toward = "source"` (зрение),
   временные слои `external` (`duration` или чужая цель).

Единственные намеренные отличия от прежнего кода - там, где раньше падало исключение: `fail = nil` теперь пустая ветка
(в игре так было всегда), `every` в комнате тоже может быть Value (в игре так было всегда).

## Кэш итоговых статов (`EntityState.refresh`)

Итоговые статы сущности - функция входов: поля сущности (прокачка, реген), очки характеристик, надетое (`equipment_stats`),
временные слои (`external`, действуют пока `until > now`), правила статов (`rules()`), `Unit.base/mods`. У каждого входа
свой dirty-флаг: `EntityState.version` (Tracked-словари `equipment_stats`/`external`, `rebuild_runtime`) и `Unit.version`
(Tracked `base`/`mods`, `touch()`); поля сущности игра пишет напрямую, поэтому кэш хранит их снимок (`attrgetter`, один вызов
на кадр). Пока ни один вход не менялся, статы не пересчитываются - обновляются только ресурсы и потолки (они меняются
каждый кадр). Кэш действует лишь если прошлый расчёт был неподвижной точкой (повтор дал бы тот же результат бит-в-бит) и у
сущности нет пассивных эффектов/событийных модов (они зависят от HP, времени, баффов - считаются каждый раз). Истечение
временного слоя - вход по времени: кэш действует на `[t0, min(until))`, поэтому слой снимается в тот же кадр, что и раньше.
`EntityState.stat_cache = False` выключает кэш (тесты сравнивают результаты бит-в-бит: `tests/test_stat_cache.py`).
`Unit._eff` тоже кэшируется по `version`.

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

## Статусы (`lua_content/statuses/core_statuses.lua`, `src/effects/statuses.py`)

Статус - строка данных из существующих ops (новых видов нет): `duration` (число задаёт длительность timed-операциям без своей), `ops` (`target = "enemy"` = носитель, источник - тот, кто вешает), `stack = { max, add }` (повторное наложение: стаки += n до max, таймер заново; `add` прибавляется к `value.flat` КАЖДОЙ операции за стак: DoT = base + add * стаки), `alias`, `cc_priority` (сильнейший CC побеждает, `statuses.cc_strongest`), `cc_damage_mult` (данные; применение - S2). Наложение: `EffectManager.apply_status(target, id, source, stacks=1)` и `EffectRuntime.apply_status(id, t, stacks=1)` - один и тот же `statuses.plan`, дальше обычный `run_ops`. Сопротивление: стат носителя `status_resist_<id>` (>=100 иммунитет; иначе один бросок rng менеджера, только если стат > 0). Живой контент статусов пока не вешает. Спека: `tests/test_statuses_spec.py` (оба хоста). Планируемые kinds в строках amaterasu/tsukuyomi/infinity не валидируются.

## Status stats and CC conditions (S2)

- `cc_duration_mult` (target, default 1.0, mods add to it): x duration of CC statuses (`cc = true` rows); <= 0 = immune. Chance to resist: carrier stat `status_resist_<id>` (0..100, >= 100 immune).
- `cc_damage_mult` (attacker, default 1.0), `cc_damage_flat`, `cc_damage_reduction` (target): see docs/DAMAGE_PIPELINE.md.
- Conditions on the target (EffectManager): `has_cc` (1/0) and `cc_is_<status id>` = the winning CC by `cc_priority` (`active_cc`).

## Kind aliases (spec names)

Content may write the spec's kind names of `docs/EFFECT_SYSTEM_DESIGN.md`; `canonical_kind()` (src/effects/schema.py) maps them to the canon
op kind before validation (`validate_op`), parsing (`Op.from_json`) and dispatch (`apply_op`). Table: `lua_content/kind_aliases.lua`.

- `exact = true` (pure renames, same handler, same traces): `status`->`apply_effect`, `consume`->`drain`, `restore`->`heal`,
  `remove_effect`->`remove_buff`, `oath_binding`->`binding_vow`, `use_learned`->`use_learned_technique`, `create_minion`->`summon`,
  `nullify_technique`->`nullify`.
- `exact = false` (listed, NOT resolved, NOT counted): `dash/teleport/pull/push` need `move` + `mode=...`, `swap`, `debuff`, `erase`, `copy_technique`.
- Unknown kinds are still rejected. Yardstick: `qa.py coverage` (corpus tests/fixtures/ability_corpus.json).

## Forms and movement (slice F1)

- **Alias params.** A row of `lua_content/kind_aliases.lua` may carry `params`; `ops.canonicalize_op(op)` renames the kind and fills them (the op's own fields win; a non-alias op comes back as the same object). `dash|teleport|pull|push|swap` = `move` with `mode` = the same name. `canonical_kind` still returns just the canon name.
- **`move` modes** (manager `MOVE_DEST`): `dash`=`charge` (self toward the other party, stops 1.5 short), `push`=`knockback`, `pull`, `teleport` (`to=[x,y]` or `{x,y}`, else behind the other party), `swap` (exchange positions of the target and the other party), `strafe` (the only RNG). Positions are clamped by `world.clamp_position` (arena bounds of `lua_content/world.lua`) when the world has it. The validator lists the five classic modes in its message (golden text) and additionally accepts `MOVE_MODES_SPEC`.
- **`stance` / `transform` / `timed_power_up`** (fields: `id`, `exclusive_group`, `conflict_with`, `duration`, `on_enter`, `on_exit`; `transform` also `stats` = mod-ops active while the form lasts and `abilities = {add, remove}`). Default group: `stance` / `transform` / `power_up:<id>`. A form of the same group replaces the active one: the old `on_exit` runs first, then the new `on_enter`; an active form listed in `conflict_with` (either way) blocks the new one; with a `duration` the manager reverts the form in `update` (mods removed, `on_exit` run = the aftermath of `timed_power_up`). `timed_power_up` requires `duration`. State: `unit.external["forms"]`. The game has no ability-set concept: `EffectManager.form_abilities(entity)` exposes the add/remove lists as data. The training room (`EffectRuntime`) records forms but neither applies `stats` nor expires them.

## Control (slice F2)

`hypnosis`, `command`, `possess`, `dominance`, `temptation`, `tame` (`src/effects/control.py`) share one mechanism: a record `unit.external["control"]["rec"]` = `{id, kind, controller (entity id), until, saved_aggro, saved_faction, on_exit}` plus the existing `set_aggro` seam (`aggro_mode = "<kind mode>:<action>"`, `targeting`, `target`, `controller`; hypnosis also `perception`). Fields: `duration`, `action`, `target_ref`, `targeting`, `requires = {stat, cmp: lt|le|gt|ge, vs: "source" | number}`, `chance` (tame, one seeded draw), `on_exit`.
- Gates (nothing is applied, no record): `immune` op with `effect = control` (buff `block:control`), `status_resist_<id|kind|control>` (>=100 always, 0<p<100 one seeded draw of the host RNG), `requires`.
- `possess`/`dominance`/`tame` also switch the target's faction to the caster's (`EntityState.faction`). The game has no "drive another entity" concept, so possess = faction switch + targeting override + restore.
- Ends (EffectManager.update): `until` passed or the controller dead -> aggro + faction restored, then `on_exit` (run from the released target's view: `self` = the target). A new control first restores the old one. `tame` is permanent: no record, no restore.
- EffectRuntime (training room) records and logs the control but does not expire it (same divergence as forms). Aliases: `blood_manipulation` = possess action=puppet, `enter_dream` = hypnosis perception=dream. Tests: `tests/test_effect_control_spec.py`.

## Perception (slice F3)
- Data only, on `unit.external["perception"]` (src/effects/perception.py); nothing changes unless content uses it. `perceive` (target, `duration`, `what` in hp|stats|statuses|hidden|intent, `stat_names` list): the CASTER learns about the target; read it with `EffectManager.perceived(caster)` -> `{target id: facts}` (expired records skipped, no combat state mutated).
- `reveal` (target or area, `duration`, `to` = "caster" | all): concealment is suppressed while it lasts: `untargetable:*` buffs stop excluding the entity from area selection (an area `reveal` also selects hidden entities) and the `toward = source` stealth circle no longer shortens `can_see`. Expiry restores the concealment (buffs are not deleted).
- `grant_vision` = alias of `mod` stat vision_range op add (`can_see` reads it); vision_arc / detection_range are not implemented.
- `precognition` (target self, `duration`, `cooldown`, `negate` default true, `warn` default true, `chance` default 100): before an incoming hit `EffectManager._damage` asks `perception.try_negate`; at most once per cooldown it records a warning (`EffectManager.warnings(entity)` = [{t, from}]) and negates that hit like a dodge (`dodge` event). `chance` < 100 costs one seeded RNG draw per armed hit; a failed draw does not start the cooldown. `dodge` = alias of precognition negate=true warn=false. Counter windows / `advisor` are not implemented.
- EffectRuntime (training room) records the ops but has no queries or hit hook (same divergence as forms/control). Tests: `tests/test_effect_perception_spec.py`.
