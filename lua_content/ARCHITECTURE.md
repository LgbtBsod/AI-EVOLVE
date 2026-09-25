# Архитектура движка эффектов: карта Lua-контента

Справочник «полного движка» (слои, kinds, Timeline, Registry) живёт здесь и в
`docs/EFFECT_SCHEMA.md`. Игровой контент — **только данные**: ни одной функции
наружу (кроме `pred`, которая экспортируется своей `src`-строкой, см.
`lib/export.lua`). Ядро (`src/core/timeline.py`, `src/core/registry.py`,
`src/effects/`) резолвит строки по реестрам и исполняет.

```
┌─────────────────────────────────────────────────────────────┐
│  NARRATIVE / META      (автор, панели, файлы) — вне игры    │  kinds/meta.lua (спеки, handlers нет)
│  ONTOLOGICAL           (бытие, концепции)                   │  kinds/ontological.lua
│  TEMPORAL              (петли, откаты, ветки)               │  kinds/temporal.lua ──► src/core/timeline.py
│  RULES                 (законы мира)                        │  rules/*.lua, effect_rules.lua
│  WORLD                 (глобальные состояния, пороги)       │  world.lua + timeline/event_kinds.lua
│  STATE                 (память, сны, сохранения)            │  timeline/snapshots.lua
│  SOCIAL / ENTITY       (контракты; слоты, колоды)           │  kinds/ (social/entity — план)
│  EFFECT                (боевые события)                     │  abilities.lua, items/, statuses/, effects/
├─────────────────────────────────────────────────────────────┤
│  TIMELINE / EVENT LOG  ← ФУНДАМЕНТ                          │  timeline/*.lua ⇄ src/core/timeline.py
│  REGISTRY SYSTEM       ← РАСШИРЯЕМОСТЬ                      │  registry.lua ⇄ src/core/registry.py
│  ENTITY / WORLD MODEL  ← ДАННЫЕ                             │  schemas/*.lua, bricks/, bestiary.lua
└─────────────────────────────────────────────────────────────┘
```

Порядок снизу вверх: без нижнего верхнее не работает. Правило №5: персонаж
добавляет **kind и записи реестров**, а не новые поля Op.

## Структура файлов

```
lua_content/
├── ARCHITECTURE.md          # этот файл — карта слоёв и стыковок
├── registry.lua             # РЕЕСТРЫ: namespaces, layers(+priority), kinds(→handler),
│                            #   damage_types, flags, triggers, selectors, value_sources,
│                            #   load_order, freeze-порядок (⇄ src/core/registry.py)
├── schema.lua               # СПРАВОЧНИК ПОЛЕЙ Effect/Op/Value/Scale/Trigger/Condition
│                            #   (чистые данные; человекочитаемый twin docs/EFFECT_SCHEMA.md)
├── kinds/                   # ВСЕ KINDS по слоям (реестр kind → handler-имя ядра).
│   ├── effect_core.lua      #   Effect Layer: урон/ресурсы, баффы/статусы, марки, зоны,
│   │                        #   существа, движение, контроль, адаптация/кража, спец
│   ├── rules.lua            #   Rules Layer: rule_override, causality_control, ...
│   ├── state.lua            #   State Layer: snapshot, restore_state, time_loop, ...
│   ├── world.lua            #   World Layer: apply_status_to_world, thresholds, ...
│   ├── temporal.lua         #   Temporal Layer: retroactive_erase, time_direction, ...
│   ├── meta.lua             #   Meta Layer: file_access, save_corruption, ... (спеки;
│   │                        #   runtime — отдельный интерфейс к платформе, не игровой)
│   ├── ontological.lua      #   Ontological: embody_concept, concept_erase, ...
│   ├── social.lua           #   Social: contract, dominance, reputation, ...
│   └── entity.lua           #   Entity: slot_system, reagent_slot, identity_source
├── schemas/                 # СХЕМЫ валидации namespace'ов (B.5 справочника)
│   ├── stats.lua            #   scope/type/min/max/default/visible
│   ├── resources.lua        #   max_stat/min/decay/visible
│   ├── statuses.lua         #   duration/purgeable/stacking/breakable_by
│   └── effects.lua          #   trigger+ops+layer required; serializable-only
├── timeline/                # КОНФИГ фундамента (данные; логика в src/core/timeline.py)
│   ├── event_kinds.lua      #   какие события пишет каждый слой (A.8), reversible-политика
│   └── snapshots.lua        #   что снимать / когда / compaction / rng-детерминизм (A.6, A.9, A.10)
├── effects/                 # ЭФФЕКТЫ-дефиниции (Effect = trigger + ops[], схема schema.lua)
│   └── lost_my_self.lua     #   пример полной регистрации берсерка (B.10): эффекты + статус
├── statuses/                # СТАТУСЫ из реестра (stun, burn, last_will ...) — пока в effects/
├── abilities.lua            # способности героя/врагов/боссов (Effect-дефиниции + range/cost/when)
├── bosses.lua, bestiary.lua, perks.lua, loot.lua, items/   # контент Effect-слоя
├── effect_rules.lua         # ПРАВИЛА СТатов: defaults, bounds, resources, attributes, predicates
├── damage.lua               # типы урона + константы конвейера одного удара
├── world.lua                # World Model: прогрессия, регионы, глобальные события
├── rules/combinations.lua   # правила генерации/валидации предметов
├── formulas/damage_curves.lua
├── lib/export.lua           # экспорт Lua → чистые данные для обоих бэкендов (mlua/lupa)
└── qa.lua, dev_tools.lua    # проверки контента
```

## Стыковка Lua ⇄ Python (Registry)

| Namespace в `registry.lua` | Реестр в `default_registries()` (`src/core/registry.py`) |
|---|---|
| `layers` (name, priority, runtime) | `reg["layers"]` |
| `kinds` (kind → layer, handler, fields) | `reg["effects"]` + диспатч `src/effects/ops.py::OP_HANDLERS` |
| `damage_types` | `reg["damage_types"]` (+ `lua_content/damage.lua` — числа конвейера) |
| `flags` | `reg["flags"]` (`bypass_infinity`, `true_damage`, `no_resurrection`, `undodgeable`) |
| `triggers` | `reg`-домен `conditions`/рантайм триггеры `src/effects/manager.py` |
| `selectors` (`self/enemy/area+radius+arc/affects`) | селекторы менеджера + `reg["selectors"]` |
| `value_sources` (`of=`: max_hp, attack_damage…) | `reg["scales"]` + `compute_amount` в `src/effects/ops.py` |
| `conditions` (именованные pred в `effect_rules.lua → predicates`) | `reg["conditions"]` (`{kind="registry", name=...}` в схеме) |
| `stats` / `resources` (bounds/defaults) | `effect_rules.lua` ⇄ `rules()` ядра |

Порядок загрузки (`load_order` в `registry.lua`, B.6): примитивы →
селекторы/статусы/слои → эффекты/способности → предметы → rules/meta/ontologies.
Перед матчем — `freeze_all()`; редактор работает на unfrozen.

## Timeline (фундамент)

Реализация: `src/core/timeline.py` — Event (tick/source/target/kind/data/
causals/reversible), commit/rewind (снапшот → undo-цепочка → move-head),
capture_snapshot/restore, fork/simulate/merge_back, link_causal/ancestors,
to_json/from_json, attach_event_system. Undo-функции НЕ в событии
(сериализуемость!) — их выдаёт UndoProvider при откате (A.4: идемпотентна,
не триггерит события, откатывает только своё).

Конфиг со стороны контента:
* `timeline/event_kinds.lua` — кто что пишет (A.8) и что irreversible
  (file_delete, erase, universe_reset — блокируют rewind за себя);
* `timeline/snapshots.lua` — периодичность, differential-снапшоты,
  compaction/rolling window (A.9), RNG как событие `rng_roll` (A.10).

Примеры спеков слоёв поверх Timeline — в `docs/EFFECT_SCHEMA.md`-стиле, в
`kinds/temporal.lua` (balefire: retroactive_erase) и `effects/lost_my_self.lua`
(Lost My Self + Last Will целиком через реестры, без правок ядра).

## Что пока только спецификации (handler'ы ядра не написаны)

Rules/State/World/Temporal/Ontological/Social/Meta-kinds зарегистрированы в
`kinds/*` с полем `runtime`: ядро при встрече незарегистрированного handler'а
пишет warning и пропускает op (не роняет бой). Priority реализации —
ЧАСТЬ 5 исходного справочника (Фаза 2: damage pipeline/status/mark/zone;
Фаза 3: rules/state/world/temporal; Фазы 4–5: ontological/social/entity/meta).
