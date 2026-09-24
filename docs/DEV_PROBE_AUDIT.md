# Аудит Dev Probe (сентябрь 2026) и что добавлено

Проверялось не по документам, а прогоном: Python 3.14, Panda3D 1.10.16, Xvfb/Mesa,
с опциональными пакетами (Pillow/OpenCV) и без них, с собранным `rust_core` и без.

## Что не работало — исправлено

| # | Где | Проблема | Последствие |
|---|-----|----------|-------------|
| 1 | `tools/dev_probe.py` finish() | `summary_data` использовался внутри собственного литерала (`UnboundLocalError`), если установлен OpenCV из `tools/requirements-dev.txt` | прогон падал в конце: **ни summary.md, ни строки RESULT** |
| 2 | dev_probe, агрегаты OpenCV | визуальные метрики писались только в `frame_NNN.json`, а суммировались из списка скриншотов без них | «кадры с цифрами урона», motion, кластеры, keyframes — **всегда нули** |
| 3 | dev_probe, авто-гипотеза | `UI_RENDERING: damage numbers not visible` при любом убийстве (следствие п.2) с советами про `Canvas.active` / `DamageNumber prefab` (это Unity) ; гипотезы работали только с OpenCV | **ложная тревога в каждом прогоне с боем**, агент тратит токены впустую |
| 4 | dev_probe, вспышки/затемнения | в проверку передавался кадр-массив вместо статистики прошлого кадра | детектор никогда не срабатывал |
| 5 | dev_probe, кластеризация кадров | индекс кластера путался с индексом кадра | в summary оставались не те кадры |
| 6 | dev_probe, убийства | любое исчезновение врага (включая зачистку уровня) считалось убийством | завышенные kills |
| 7 | dev_probe, вывод | звук не выключался: ~40 строк ALSA/OpenAL в каждом прогоне (44 строки вывода, 2 полезные) | лишние токены на каждый запуск |
| 8 | dev_probe, `--seed` | dt и таймеры игры идут от настенных часов | «до/после» нельзя сравнить честно |
| 9 | dev_probe, прогон по умолчанию | враги спавнятся в ~160u от героя, за 30 с до боя не доходит | боевые метрики пустые, без подсказки почему |
| 10 | dev_probe | нужен реальный X-сервер/окно, режима без окна не было | не работает в контейнере/CI |
| 11 | `tools/plugins/agent_command_plugin.py` | поток обработки завершался при создании (`while self._running` при `_running=False`) | **ни одна команда не выполнялась**, все ждали таймаут |
| 12 | то же | обработчики вызывали несуществующие методы (`scene.spawn_enemy`, `set_weather`, `inventory`, …) и возвращали `success=True` | агенту врали об успехе |
| 13 | то же | команды выполнялись в фоновом потоке | Panda3D не потокобезопасен — риск порчи графа сцены |
| 14 | `cas_inspector_plugin`, `combat_advanced_plugin`, `cc_probe_plugin`, `training_room.py`, `training_room_demo.py`, `tests/test_training_room.py`, `tests/test_cas_engine.py` | захардкожен `'/workspace/...'` (путь чужой песочницы) | модули не импортировались, 2 тест-файла не собирались |
| 15 | `python_layer/l8_probe/config_loader.py` | `import lupa.lua_runtime` — такого модуля в lupa нет | `probe_config.lua` не загружался никогда |
| 16 | `src/scenes/menu_scene.py` | меню берёт цвет фона у окна | игра не стартовала без окна |

## Что было заявлено (Qwen), но не работало

- **Генерация скриптов с багами** — `AI-EVOLVE/tools/dev_probe/core.py:generate_bug_script` выдаёт шаблон
  с `TODO` и импортом несуществующего `game.engine.GameSession`; ничего не воспроизводит.
- **Анализ на уровне БД** — `AI-EVOLVE/tools/dev_probe/data_layer/` — отдельная SQLite предметов/скиллов,
  к игре не подключена; `test_data_layer.py` падает (`structlog` не в зависимостях).
- **Гипотезы** — см. п.3: одна ложная гипотеза + советы для чужого движка.
- **Предикты** — в dev probe не было вовсе.
- **Интерфейс управления для агентов** — Agent/Network/GM-плагины не подключены ни к игре, ни к dev_probe, и
  не работали (п.11–13). `dev_probe_async.py` («7-поточная архитектура») — заглушки:
  `_calculate_combat` возвращает константу, `_write_batch` — `pass`.
- Весь каталог `AI-EVOLVE/tools/dev_probe/` (~6k строк) — сирота: его никто не импортирует.

## Что добавлено

| Инструмент | Зачем |
|---|---|
| `tools/agent_play.py` | агент играет **действиями игрока** (spawn enemy/trap/chest, attack, interact) + `wait/until/observe/expect/report`; без окна и GPU, 60 с игры ≈ 0.2 с; детерминирован (seed по умолчанию 1); FAIL → строка `repro:`; `--serve` — пошаговая игра по HTTP |
| `tools/probe_runtime.py` | общий рантайм: режимы рендера window/offscreen/none, тихий движок, **виртуальные fixed-step часы** (побитовая повторяемость), адаптеры модели данных, `KillTracker` |
| `tools/probe_analysis.py` | гипотезы «симптом → причина → файл» для этого проекта (NO_COMBAT, CLOSE_BUT_NO_ATTACKS, HERO_NEVER_ATTACKS, HP_PINNED, HP_INVALID, HERO_STUCK, ZERO_DAMAGE_HITS, CRIT_NEVER_FIRES, ENEMY_PRESSURE, ERRORS с file:line, RENDER_BLANK) и прогнозы (ETA смерти, DPS, давление врагов, ETA уровня, TTK по типам) |
| `tools/probe_db.py` | SQLite-аналитика всех прогонов: `stats` (бой по типам врагов, hit/crit/dodge, TTK — SQL), `why`, `predict`, `compare`, `trend` (выбросы по z-score), `sql` |
| `rust_core/src/analytics` + `RunAnalytics` | ядра расчётов на Rust (регрессия, спарклайн, дистанции, окна «залип HP»/«застрял», дедуп логов); данные идут **колоночными бинарными буферами** (`array`), вся таблица героя — один вызов `scan_hero`; ~13× быстрее Python на 20k сэмплов, Python-двойники с проверкой паритета |
| `lua_content/dev_tools.lua` | пороги гипотез, клавиши игрока, лимиты агента, путь БД — без правки Python |
| dev_probe: `--render`, `--headless`, `--fast` | логика без графики за доли секунды, скриншоты без окна; кадры анализирует Rust `ProbeAnalyzer` |
| `CLAUDE.md` | шпаргалка «какой инструмент когда» — агент не тратит токены на поиск |

## Найдено новыми инструментами — вне рамок dev probe (не исправлено)

- **HERO_STUCK — баг ИИ героя**: герой доходит до *оценочной* точки выхода (`_select_best_exit_target`),
  `move_towards` останавливается в 0.1u, настоящий выход дальше `exit_reach_distance` — герой стоит
  в `seeking_exit` вечно (5 из 5 seed за 120 с игры).
- **Баланс**: по `probe_db.py stats` герой бьёт до 285 урона по врагам с 50 HP, враги — по 2.
- `tests/test_comprehensive.py` не собирается: `dependency_injector` нет в `requirements.txt`.
- 2 падения в `tests/test_training_room_effectschema.py` (strength 24 вместо 20).
- Сироты `AI-EVOLVE/tools/dev_probe/`, `tools/dev_probe_async.py`, `ai_evolve/tools/dev_probe_framework.py` —
  кандидаты на удаление.
