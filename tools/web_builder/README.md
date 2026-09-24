# Effect Schema Item Builder (Flet)

Визуальный конструктор предметов по схеме **Effect → Ops[]** (`docs/EFFECT_SCHEMA.md`).
Вся логика — в `tools/effect_schema/ui_logic.py`, та же, что в тестах; UI только собирает форму.

## Запуск

```bash
uv pip install -r tools/requirements-dev.txt          # flet + flet-web (не входят в зависимости игры)
python tools/web_builder/app.py                       # окно Flet
python tools/web_builder/app.py --web                 # браузер: http://localhost:8550
python tools/web_builder/app.py --web --renderer canvaskit   # если CDN Flutter недоступен
```

## Что умеет

- **Предмет = список эффектов.** «+ эффект», «удалить эффект», переключение между эффектами
  (правки сохраняются). Шаблон из каталога добавляется **вместе с зависимостями**
  (`owner_has`, `apply_effect`): Blood Price приносит Lost My Self, Venom Bite — Poison Stack.
- **Поля эффекта:** id, теги, meta.name, trigger (kind / event / when / filter / owner_has / cross),
  cooldown, threshold (зона hp_cross), amplify (when / while_buff / every / of / factor).
- **Поля операции:** kind, target, stat, op, value (flat / pct / of / ref), scale (every / of /
  value.flat / value.pct / value.of / factor / cap / floor), when, buff_id, duration, cooldown,
  extend, флаги (iframe, no_crit, silent, true_damage), fail-ветка.
- **Кнопки:** «Валидировать» (digest + JSON справа), «Собрать Lua» (Lua исполняется мостом
  `tools/lua_bridge.py`), «Тест в тренировочной комнате» (сценарий — шаги через `;`:
  `attack [DMG] | enemy_attack N | kill | tick T DT | hp PCT | set_dummy HP | <событие>`),
  «Проверить предмет (itemcheck)», «Открыть .lua» / «Сохранить .lua» (`lua_content/items/`).

## Без окна (агенты, тесты)

`tools/web_builder/headless.py` — тот же `BuilderApp` на подставной странице. Поля ищутся по
подписи, кнопки — по тексту, вызываются настоящие обработчики:

```python
from tools.web_builder.headless import UI
ui = UI()
ui.pick("Шаблон из каталога", "lost_my_self.attack")
ui.click("+ эффект").fill("effect.id *", "second_wind")
ui.pick("trigger.kind", "event").pick("trigger.event", "take_damage")
ui.pick("kind *", "drain").pick("stat", "stamina").fill("value.flat", "20")
ui.click("Проверить предмет (itemcheck)"); print(ui.status)
```

```bash
python tools/web_builder/headless.py --template lost_my_self.attack --check --room "hp 30; attack"
```

Живой веб-интерфейс через браузер (Playwright; CanvasKit и шрифт отдаются локально):

```bash
python tools/web_builder/app.py --web --renderer canvaskit &
python tools/web_builder/screenshot.py --out shot.png --template venom_bite --click "Проверить предмет (itemcheck)"
```

Тесты: `tests/test_web_builder.py` (каждый шаблон каталога проходит через форму без потерь,
предмет с нуля через поля билдера, открытие/сохранение .lua).
