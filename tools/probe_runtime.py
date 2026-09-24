#!/usr/bin/env python3
"""Общий рантайм агентских инструментов (dev_probe.py, agent_play.py).

Раньше каждый инструмент сам поднимал игру, сам разбирался со временем и
сам читал модель данных сцены. Здесь это собрано один раз:

1. configure_engine() - тихий движок: звук выключен (иначе ALSA/OpenAL
   печатают ~40 строк мусора в stderr на КАЖДЫЙ прогон в контейнере без
   звуковой карты - это чистые токены на чтение вывода), болтовня Panda3D
   уходит в файл. Режимы рендера:
     window    - обычное окно (как раньше);
     offscreen - offscreen-буфер: скриншоты есть, окна нет (нужен OpenGL -
                 драйвер или Mesa под xvfb-run);
     none      - без графики вообще: чистая логика, OpenGL не нужен, работает
                 в любом контейнере/CI, самый быстрый.
2. VirtualTime + fast-режим - игровое время отвязано от настенных часов:
   ClockObject переводится в non-real-time с фиксированным шагом 1/fps, а
   `time` в модулях игры (src.*, main) подменяется прокси, который читает
   те же часы Panda3D. Итог:
     - 60 с игры считаются за ~0.3 с (render=none) или ~4 с (offscreen);
     - прогон с --seed ПОБИТОВО повторяем: dt больше не плавает от
       загрузки машины, а таймеры спавна/кулдаунов (time.time()/
       perf_counter() в игре) идут по тому же виртуальному времени.
3. Адаптеры к модели данных AI-EVOLVE (get_scene/get_entities/...) и
   KillTracker - один источник правды для всех инструментов.

Библиотека, не CLI: см. tools/dev_probe.py и tools/agent_play.py.
"""
import importlib
import importlib.abc
import importlib.machinery
import math
import os
import random
import sys
import time as _real_time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RENDER_MODES = ("window", "offscreen", "none")
DEFAULT_FPS = 30


def _is_game_module(name):
    """Модули, чей `time` подменяется в fast-режиме: только код игры, не
    stdlib и не сами инструменты (им нужны настоящие часы для wall-time)."""
    return name == "main" or name.startswith(("src.", "game."))


def configure_engine(render="window", fast=False, fps=DEFAULT_FPS, notify_log=None):
    """Выставляет PRC-настройки Panda3D. Вызывать ДО создания ShowBase."""
    if render not in RENDER_MODES:
        raise ValueError(f"render must be one of {RENDER_MODES}, got {render!r}")
    from panda3d.core import loadPrcFileData

    loadPrcFileData("", "audio-library-name null")
    # /dev/input отсутствует в контейнерах - безобидная ошибка на каждом старте
    loadPrcFileData("", "notify-level-device fatal")
    if notify_log is not None:
        loadPrcFileData("", f"notify-output {Path(notify_log).as_posix()}")
    else:
        loadPrcFileData("", "notify-level warning")
    if render == "offscreen":
        loadPrcFileData("", "window-type offscreen")
    elif render == "none":
        loadPrcFileData("", "window-type none")
    if render != "window":
        loadPrcFileData("", "sync-video 0")
    if fast:
        loadPrcFileData("", "clock-mode non-real-time")
        loadPrcFileData("", f"clock-frame-rate {fps}")


class VirtualTime(types.ModuleType):
    """Подменяет модуль `time` внутри кода игры: time()/perf_counter()/
    monotonic() идут по кадровому времени Panda3D (в non-real-time режиме
    оно растёт ровно на 1/fps за кадр), всё остальное - настоящий `time`."""

    def __init__(self, clock):
        super().__init__("time")
        self._clock = clock
        self._wall0 = _real_time.time()
        self._perf0 = _real_time.perf_counter()

    def now(self):
        return self._clock.getFrameTime()

    def time(self):
        return self._wall0 + self.now()

    def perf_counter(self):
        return self._perf0 + self.now()

    monotonic = perf_counter

    def __getattr__(self, name):
        if _LEAKS is not None:  # opt-in leak recorder (AI_EVOLVE_LEAK_REPORT); passive, changes nothing
            _LEAKS.passthrough(name, sys._getframe(1))
        return getattr(_real_time, name)


class ManualTime(types.ModuleType):
    """Ручные часы для тестов: sleep(s) мгновенно сдвигает время на s.
    Подменяет `time` в коде игры и в самом тесте (tests/conftest.py,
    маркер virtual_time) - тесты с ожиданием таймеров идут без реальных пауз."""

    def __init__(self):
        super().__init__("time")
        self._wall0 = _real_time.time()
        self._perf0 = _real_time.perf_counter()
        self.elapsed = 0.0

    def advance(self, seconds):
        self.elapsed += max(0.0, float(seconds))

    sleep = advance

    def time(self):
        return self._wall0 + self.elapsed

    def perf_counter(self):
        return self._perf0 + self.elapsed

    monotonic = perf_counter

    def __getattr__(self, name):
        return getattr(_real_time, name)


class _PatchOnImport(importlib.abc.MetaPathFinder):
    """Модули игры часто импортируются лениво (внутри функций) уже после
    старта - этот finder подменяет в них `time` сразу после исполнения."""

    def __init__(self, patcher):
        self.patcher = patcher

    def find_spec(self, fullname, path, target=None):
        if not _is_game_module(fullname):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
            return None
        original = spec.loader.exec_module

        def exec_module(module, _original=original):
            _original(module)
            self.patcher.patch_module(module)

        spec.loader.exec_module = exec_module
        return spec


class TimePatcher:
    def __init__(self, shim):
        self.shim = shim
        self.patched = []
        self._finder = _PatchOnImport(self)

    def patch_module(self, module):
        if getattr(module, "time", None) is _real_time:
            module.time = self.shim
            self.patched.append(module)

    def install(self):
        for name, module in list(sys.modules.items()):
            if _is_game_module(name) and module is not None:
                self.patch_module(module)
        sys.meta_path.insert(0, self._finder)
        return self

    def uninstall(self):
        if self._finder in sys.meta_path:
            sys.meta_path.remove(self._finder)
        for module in self.patched:
            if getattr(module, "time", None) is self.shim:
                module.time = _real_time
        self.patched.clear()


def seed_everything(seed):
    """random + RNGManager проекта (им пользуется CombatSystem для крита/уклонения)."""
    if seed is None:
        return
    random.seed(seed)
    try:
        from src.core.rng_manager import RNGConfig, RNGManager, set_default_rng
        set_default_rng(RNGManager(RNGConfig(seed=seed, use_deterministic=True)))
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Leak recorder (opt-in: env AI_EVOLVE_LEAK_REPORT=<report.json>, used by `qa.py determinism`)
# ---------------------------------------------------------------------------

_LEAKS = None  # LeakRecorder while recording, else None (VirtualTime.__getattr__ checks it)

# time.* names that are constants/pure helpers, not clocks: never a leak
_TIME_BENIGN = frozenset({"struct_time", "timezone", "altzone", "daylight", "tzname", "strptime", "mktime",
                          "get_clock_info"})
_TIME_SHIMMED = ("time", "perf_counter", "monotonic")     # VirtualTime implements these itself
_TIME_NOARG_NOW = ("localtime", "gmtime", "ctime")        # current real time only when called without arguments


class LeakRecorder:
    """Records where game code (src.*, main) touches nondeterminism that the virtual clock and the seeds
    do NOT cover, with caller file:line and counts:

      time.<name>      VirtualTime.__getattr__ passthroughs (time_ns, perf_counter_ns, process_time, sleep, ...)
      time.<name> real direct calls of the REAL time/perf_counter/monotonic (`from time import x` bypasses the shim)
      datetime.now/utcnow/today, os.urandom, uuid.uuid1/uuid4,
      random.Random() / random.SystemRandom() built without a seed, threading.Thread.start (target name)

    Passive: uses sys.monitoring (CALL events, filtered to game code and switched off per call site
    after the first harmless call), never patches a function, so the run behaves exactly as without it.
    Limitation: a call site that first calls something harmless and only later a leaking callable
    (dynamic dispatch) is not seen. Written as JSON at exit; `roots` is for tests."""

    TOOL_IDS = (3, 4)

    def __init__(self, path, roots=None):
        self.path = Path(path)
        self.roots = tuple(os.path.normcase(str(r)) for r in (roots or (ROOT / "src", ROOT / "main.py")))
        self.counts = {}       # (kind, where, func, detail, via) -> n
        self.notes = []
        self._files = {}       # co_filename -> bool (is game code)
        self._pass_sites = {}  # (code, lineno) -> time attr name already recorded via __getattr__
        self._tool = None
        self._targets = {}
        import threading
        self._lock = threading.Lock()

    # --- classification
    def is_game_file(self, filename):
        hit = self._files.get(filename)
        if hit is None:
            path = os.path.normcase(os.path.abspath(filename)) if filename and not filename.startswith("<") else ""
            hit = self._files[filename] = bool(path) and any(
                path == root or path.startswith(root + os.sep) for root in self.roots)
        return hit

    def _where(self, frame):
        code = frame.f_code
        path = Path(code.co_filename)
        try:
            shown = path.resolve().relative_to(ROOT).as_posix()
        except (ValueError, OSError):
            shown = path.as_posix()
        return f"{shown}:{frame.f_lineno}", getattr(code, "co_qualname", code.co_name)

    def record(self, kind, frame, detail=""):
        where, func = self._where(frame)
        caller = frame.f_back  # who asked: `RNGManager.__init__` alone says little, its constructor does
        via = self._where(caller)[0] if caller is not None and self.is_game_file(caller.f_code.co_filename) else ""
        with self._lock:
            key = (kind, where, func, detail, via)
            self.counts[key] = self.counts.get(key, 0) + 1

    def passthrough(self, name, frame):
        """VirtualTime.__getattr__ fell through to the real `time` for `name`."""
        if name.startswith("__") or name in _TIME_BENIGN or not self.is_game_file(frame.f_code.co_filename):
            return
        self._pass_sites[(frame.f_code, frame.f_lineno)] = name
        self.record(f"time.{name}", frame)

    def _build_targets(self):
        import datetime
        import random
        import secrets
        import threading
        import uuid
        t = {}
        for name in ("time_ns", "perf_counter_ns", "monotonic_ns", "process_time", "process_time_ns",
                     "thread_time", "thread_time_ns", "sleep", *_TIME_SHIMMED):
            fn = getattr(_real_time, name, None)
            if fn is not None:
                t[id(fn)] = ("time." + name + (" (real clock, bypasses the virtual one)" if name in _TIME_SHIMMED else ""),
                             name)
        for name in _TIME_NOARG_NOW:
            t[id(getattr(_real_time, name))] = (f"time.{name}()", "noarg")
        t[id(os.urandom)] = ("os.urandom", "")
        t[id(uuid.uuid1)] = ("uuid.uuid1", "")
        t[id(uuid.uuid4)] = ("uuid.uuid4", "")
        t[id(random.Random)] = ("random.Random() unseeded", "unseeded")
        t[id(random.SystemRandom)] = ("random.SystemRandom()", "")
        for name in ("token_bytes", "token_hex", "token_urlsafe"):
            t[id(getattr(secrets, name))] = (f"secrets.{name}", "")
        self._seed_func, self._global_inst = random.Random.seed, getattr(random, "_inst", None)
        self._dt_types = (datetime.datetime, datetime.date)
        self._thread_start = threading.Thread.start
        self._targets = t

    def classify(self, fn, arg0, missing, code=None, offset=0):
        """-> (kind, detail) for a call to `fn` that leaks, else None."""
        hit = self._targets.get(id(fn))
        if hit is not None:
            kind, mode = hit
            if mode == "unseeded":
                return (kind, "") if arg0 is missing or arg0 is None else None
            if mode == "noarg":
                return (kind, "") if arg0 is missing or arg0 is None else None
            return kind, ""
        owner = getattr(fn, "__self__", None)
        if owner is not None and (owner is self._dt_types[0] or owner is self._dt_types[1]) \
                and getattr(fn, "__name__", "") in ("now", "utcnow", "today"):
            return f"{owner.__name__}.{fn.__name__}", ""
        if fn is self._thread_start:  # `t.start()` is reported as (function, self) with self in arg0
            owner = arg0
        elif getattr(fn, "__func__", None) is not self._thread_start:
            # `random.seed()` arrives unpacked as (Random.seed, the hidden global instance): arg0 cannot
            # tell a seed argument from none, the CALL's oparg (argument count) can
            if fn is self._seed_func and arg0 is self._global_inst and code is not None and code.co_code[offset + 1] == 0:
                return "random.seed() unseeded", ""
            return None
        target = getattr(owner, "_target", None)
        return "threading.Thread.start", getattr(target, "__qualname__", None) or getattr(owner, "name", "?")

    # --- sys.monitoring
    def install(self):
        mon = getattr(sys, "monitoring", None)
        if mon is None:
            self.notes.append("sys.monitoring unavailable (Python < 3.12): only time.* passthroughs are recorded")
            return False
        for tool in self.TOOL_IDS:
            try:
                mon.use_tool_id(tool, "ai-evolve-leaks")
            except ValueError:
                continue
            self._tool = tool
            break
        else:
            self.notes.append("no free sys.monitoring tool id: only time.* passthroughs are recorded")
            return False
        self._build_targets()
        missing = mon.MISSING
        disable = mon.DISABLE

        def on_call(code, offset, fn, arg0):
            if not self.is_game_file(code.co_filename):
                return disable
            hit = self.classify(fn, arg0, missing, code, offset)
            if hit is None:
                return disable
            frame = sys._getframe(1)
            kind, detail = hit
            if kind.startswith("time.") and self._pass_sites.get((frame.f_code, frame.f_lineno)) == kind[5:]:
                return None  # already counted through VirtualTime.__getattr__ (`time.x()` on the shim)
            self.record(kind, frame, detail)
            return None

        mon.register_callback(self._tool, mon.events.CALL, on_call)
        mon.set_events(self._tool, mon.events.CALL)
        return True

    def uninstall(self):
        mon = getattr(sys, "monitoring", None)
        if mon is not None and self._tool is not None:
            mon.set_events(self._tool, 0)
            mon.register_callback(self._tool, mon.events.CALL, None)
            mon.free_tool_id(self._tool)
            self._tool = None

    # --- report
    def static_bindings(self):
        """Game modules holding the REAL time functions/module under another name: never virtualised."""
        found = []
        for name, module in list(sys.modules.items()):
            if module is None or not self.is_game_file(getattr(module, "__file__", None) or ""):
                continue
            for attr, value in list(vars(module).items()):
                if value is _real_time and attr != "time":
                    found.append({"module": name, "name": attr, "what": "alias of the real `time` module"})
                elif getattr(value, "__module__", None) == "time" and callable(value) and not isinstance(value, type):
                    found.append({"module": name, "name": attr, "what": f"real time.{getattr(value, '__name__', '?')}"})
        return found

    def report(self):
        findings = [{"kind": k, "where": w, "func": f, "detail": d, "via": v, "count": n}
                    for (k, w, f, d, v), n in sorted(self.counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        return {"schema": 1, "pid": os.getpid(), "findings": findings, "static": self.static_bindings(),
                "notes": self.notes}

    def write(self):
        import json
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.report(), indent=1), encoding="utf-8")
        except OSError:
            pass  # a report that cannot be written must not fail the run


def start_leak_recorder():
    """Starts the recorder when env AI_EVOLVE_LEAK_REPORT names an output file (idempotent)."""
    global _LEAKS
    path = os.environ.get("AI_EVOLVE_LEAK_REPORT")
    if not path or _LEAKS is not None:
        return _LEAKS
    import atexit
    rec = LeakRecorder(path)
    rec.install()
    _LEAKS = rec
    atexit.register(rec.write)
    return rec


class Runtime:
    """Что вернул boot_game(): игра + часы (симуляционные или настоящие)."""

    def __init__(self, game, render, fast, fps, patcher):
        self.game = game
        self.render = render
        self.fast = fast
        self.fps = fps
        self.patcher = patcher
        self._t0_sim = self._frame_time()
        self._t0_wall = _real_time.perf_counter()

    def _frame_time(self):
        from panda3d.core import ClockObject
        return ClockObject.getGlobalClock().getFrameTime()

    def now(self):
        """Секунды игры с момента boot_game() - в fast-режиме виртуальные."""
        if self.fast:
            return self._frame_time() - self._t0_sim
        return _real_time.perf_counter() - self._t0_wall

    def wall(self):
        return _real_time.perf_counter() - self._t0_wall

    def step(self, frames=1):
        for _ in range(frames):
            self.game.taskMgr.step()

    def advance(self, seconds, stop=None):
        """Крутит игру `seconds` игрового времени (или пока stop() не вернёт
        True). В fast-режиме - столько кадров, сколько нужно, без ожидания."""
        end = self.now() + seconds
        while self.now() < end:
            self.game.taskMgr.step()
            if stop is not None and stop():
                return True
        return False

    def can_screenshot(self):
        return self.render != "none" and getattr(self.game, "win", None) is not None

    def close(self):
        if self.patcher is not None:
            self.patcher.uninstall()
        try:
            self.game.destroy()
        except Exception:
            pass


def boot_game(render="none", fast=True, fps=DEFAULT_FPS, seed=None, notify_log=None,
              entry_module="main", game_class="Game", game_kwargs=None):
    """Поднимает игру для агента. По умолчанию: без графики, fast, dev-карта,
    сразу в игровом мире, БД в памяти (saves/ не засоряется)."""
    configure_engine(render=render, fast=fast, fps=fps, notify_log=notify_log)
    seed_everything(seed)
    start_leak_recorder()  # no-op unless AI_EVOLVE_LEAK_REPORT is set

    patcher = None
    if fast:
        from panda3d.core import ClockObject
        patcher = TimePatcher(VirtualTime(ClockObject.getGlobalClock())).install()

    if game_kwargs is None:
        game_kwargs = {"dev_mode": True, "skip_menu": True}
        if entry_module == "main" and game_class == "Game":
            game_kwargs["db_url"] = "sqlite:///:memory:"
            # память тактик врагов - только в процессе: seed = тот же прогон
            os.environ.setdefault("AI_EVOLVE_TACTICS_MEMORY", "off")
            os.environ.setdefault("AI_EVOLVE_HERO_MIND", "off")
    module = importlib.import_module(entry_module)
    game = getattr(module, game_class)(**game_kwargs)

    if fast:
        from panda3d.core import ClockObject
        clock = ClockObject.getGlobalClock()
        clock.setMode(ClockObject.MNonRealTime)
        clock.setFrameRate(fps)
    return Runtime(game, render, fast, fps, patcher)


# ---------------------------------------------------------------------------
# ADAPTER: модель данных AI-EVOLVE. Под другой проект правится только здесь.
# ---------------------------------------------------------------------------

def get_scene(game):
    """Объект с .player/.enemies или None.

    AI-EVOLVE грузится через GameCore + SceneManager: активная сцена
    (GameScene) держит сам игровой мир в .world; game.scene - запасной путь."""
    scene_manager = getattr(game, "scene_manager", None)
    get_active = getattr(scene_manager, "get_active_scene_data", None)
    if get_active is not None:
        data = get_active()
        instance = getattr(data, "instance", None) if data else None
        world = getattr(instance, "world", None)
        if world is not None:
            return world
        if instance is not None and hasattr(instance, "player"):
            return instance
    return getattr(game, "scene", None)


def get_entities(game):
    """[(entity, is_player), ...] для всех юнитов сцены."""
    scene = get_scene(game)
    if scene is None:
        return []
    entities = []
    if getattr(scene, "player", None) is not None:
        entities.append((scene.player, True))
    for enemy in getattr(scene, "enemies", []):
        entities.append((enemy, False))
    return entities


def get_combat_system(game):
    """Объект с register_event_handler(callback) или None: единый менеджер
    эффектов игры (через него идут все удары и навыки), иначе старый CombatSystem."""
    return getattr(game, "effect_manager", None) or getattr(game, "combat_system", None)


def entity_id_of(entity):
    return getattr(entity, "entity_id", None) or f"obj_{id(entity)}"


def entity_type_of(entity, is_player):
    return "hero" if is_player else getattr(entity, "enemy_type", entity.__class__.__name__)


def entity_state(entity, is_player):
    return {
        "id": entity_id_of(entity),
        "type": entity_type_of(entity, is_player),
        "hp": round(entity.health, 1),
        "max_hp": entity.max_health,
        "pos": [round(entity.x, 1), round(entity.y, 1)],
    }


def player_state(player):
    """entity_state + то, что есть только у героя (уровень/опыт/режим ИИ)."""
    state = entity_state(player, True)
    state.update({
        "lvl": getattr(player, "level", None),
        "xp": round(getattr(player, "experience", 0) or 0, 1),
        "xp_next": getattr(player, "experience_to_next_level", None),
        "ai": getattr(player, "ai_state", None),
        "alive": bool(player.is_alive()),
    })
    return state


def sample_state(game, t):
    """Одна строка state.jsonl (общий формат dev_probe/agent_play/probe_db)."""
    entities = get_entities(game)
    player = next((e for e, is_player in entities if is_player), None)
    return {
        "t": round(t, 2),
        "player": player_state(player) if player is not None else None,
        "enemies": [entity_state(e, False) for e, is_player in entities if not is_player],
    }


class KillTracker:
    """Считает убийства покадрово. Враг, пропавший из сцены ЖИВЫМ (зачистка
    уровня при переходе к следующему, а не смерть), - это despawn, не kill:
    раньше dev_probe считал убийством любое исчезновение."""

    def __init__(self):
        self.known = {}
        self.kills = []      # [(t, entity_id, enemy_type)]
        self.despawns = []   # [(t, entity_id, enemy_type)]
        self.spawned = 0

    def update(self, game, t):
        current = {entity_id_of(e): e for e, is_player in get_entities(game) if not is_player}
        for eid, enemy in self.known.items():
            if eid in current:
                continue
            etype = entity_type_of(enemy, False)
            alive = True
            try:
                alive = enemy.is_alive()
            except Exception:
                pass
            (self.despawns if alive else self.kills).append((round(t, 2), eid, etype))
        self.spawned += sum(1 for eid in current if eid not in self.known)
        self.known = current
        return len(self.kills)


def combat_recorder(game, clock, sink):
    """Подписывается на CombatSystem; каждое событие - dict в sink (list).
    Тип источника/цели резолвится в момент события: после смерти врага по
    одному id его уже не восстановить."""
    combat_system = get_combat_system(game)
    if combat_system is None:
        return False

    def on_event(info):
        types_by_id = {entity_id_of(e): entity_type_of(e, p) for e, p in get_entities(game)}
        sink.append({
            "t": round(clock(), 2),
            "source": info.source, "target": info.target,
            "source_type": types_by_id.get(info.source), "target_type": types_by_id.get(info.target),
            "damage": round(info.damage, 1), "critical": bool(info.is_critical),
            "dodged": bool(info.is_dodged),
        })

    combat_system.register_event_handler(on_event)
    return True


def nearest_enemy(game):
    """(distance, enemy) до ближайшего живого врага или (None, None)."""
    scene = get_scene(game)
    player = getattr(scene, "player", None) if scene else None
    if player is None:
        return None, None
    best = (None, None)
    for enemy in getattr(scene, "enemies", []):
        try:
            if not enemy.is_alive():
                continue
        except Exception:
            continue
        d = math.hypot(enemy.x - player.x, enemy.y - player.y)
        if best[0] is None or d < best[0]:
            best = (d, enemy)
    return best
