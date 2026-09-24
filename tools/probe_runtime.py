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
