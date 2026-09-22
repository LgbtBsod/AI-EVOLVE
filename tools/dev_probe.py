#!/usr/bin/env python3
"""Dev-инструмент, рассчитанный на чтение агентом, а не человеком за монитором.

Первая версия просто дампила сырые скриншоты + JSON состояния каждые N
секунд — чтобы понять "что произошло", их приходилось сопоставлять вручную,
это дорого по токенам. Эта версия делает всю эту работу сама:

1. Подписывается на CombatSystem.register_event_handler и считает точную
   боевую статистику (попадания/уклонения/криты/урон) — не парсит логи.
2. Раз в --sample-interval секунд (дёшево — просто числа) снимает состояние
   игрока/врагов и сама детектирует события (смерть, убийство, аномалии
   вроде зависания на низком HP) вместо дампа чисел на разбор постфактум.
3. Рисует прямо в 3D-сцене подписи над каждым юнитом (id/тип/HP) — на
   скриншоте сразу видно, кто есть кто, без сверки с JSON.
4. К каждому скриншоту пишет sidecar frame_NNN.json с проекцией каждого
   юнита в пиксели экрана — как ref_N у браузерных инструментов, только
   для 3D-сцены: не нужно на глаз определять координаты на картинке.
5. Скриншоты — по значимым событиям (старт/низкий HP/смерть/убийство/конец
   или --screenshot-interval, если нужен таймлапс), а не по таймеру всегда:
   меньше картинок — меньше токенов на разбор.
6. Собирает WARNING/ERROR из лога игры в summary.md — не нужно отдельно
   перехватывать stdout.
7. summary.md ГАРАНТИРОВАН на любом исходе — нормальном завершении,
   исключении внутри сэмплинга, Escape или закрытии окна (finish()
   вызывается один раз из try/finally вокруг game.run(), а не из середины
   логики сэмплинга) — и начинается со строки "Status: OK/CRASHED/STOPPED
   EARLY" плюс кодом возврата процесса (0 - чисто, 1 - краш), чтобы можно
   было проверить исход одной командой, не открывая файл.
8. --seed сидирует и random, и RNGManager проекта (если есть) - без этого
   два прогона "до/после фикса" нельзя честно сравнить, потому что криты/
   промахи/точки спавна каждый раз разные. ВАЖНО: это снижает разброс
   между прогонами (одинаковая стартовая точка RNG), но НЕ гарантирует
   побитово одинаковый повтор - блуждание врагов дёргает random() каждый
   игровой кадр, а dt игры завязан на реальное время рендера, которое от
   прогона к прогону чуть плавает. Честная побитовая детерминированность
   потребовала бы фиксированного шага времени (ClockObject.MNonRealTime) -
   пока не реализовано, это следующий кандидат, если понадобится точное
   сравнение "до/после".
9. (опционально, нужен Pillow: pip install -r tools/requirements-dev.txt)
   Детект "пустого"/залитого одним цветом кадра - ловит поломку рендера,
   которую внутреннее состояние игры не увидит (HP/позиции продолжают
   честно считаться, даже если окно рисует чёрный экран). Плюс
   contact_sheet.jpg (одна картинка-сетка вместо N скриншотов - открывать
   первой для общей визуальной проверки) и timelapse.gif (для человека,
   не для агента - см. комментарий у "## Screenshots" в finish()).
10. Повторы с одинаковым `kind` (например 20 тиков подряд "player dead")
    сворачиваются в списке скриншотов до первого+последнего кадра, а живой
    stdout - до 2 строк + одна пометка "further ... suppressed" (см.
    log_event). Ничего не удаляется с диска - только то, что стоит открыть
    по умолчанию.

ВАЖНО - для логических правок (формулы урона/крита, is_alive()/is_defeated,
AI-таргетинг/движение) СНАЧАЛА запускай tools/combat_smoke_test.py: без окна,
без скриншотов, доли секунды вместо реального --duration секунд с открытым
Panda3D. Он уже сейчас проверяет ровно то, что раньше приходилось выяснять
через этот файл (death-latch регрессию, floor урона, крит/додж через
CombatSystem, AI retreat/targeting). Возвращайся к dev_probe.py, когда нужна
именно визуальная/рендер/сценовая проверка, а не просто "правильно ли считает
формула".

Результат одного прогона — ОДИН файл summary.md, с него и надо начинать
чтение. state.jsonl / game.log / frame_NNN.json / panda3d.log — только если
summary на что-то указывает и нужно копнуть глубже.

Использование (этот проект):
    .venv/Scripts/python.exe tools/dev_probe.py --duration 30
    .venv/Scripts/python.exe tools/dev_probe.py --action-at 1:1 --action-at 1:2 --action-at 1:3
    .venv/Scripts/python.exe tools/dev_probe.py --seed 42 --duration 20   # воспроизводимый прогон

Переиспользование в другом Panda3D-проекте:
    - Всё, что касается запуска окна (screenshot+пиксельная проекция через
      game.cam/game.win, boilerplate ShowBase-задач) уже общее — не завязано
      на этот проект.
    - --entry-module/--game-class/--game-kwargs говорят инструменту, как
      импортировать и создать игру другого проекта, не трогая код инструмента.
    - Единственное, что реально завязано на модель данных ЭТОГО проекта —
      функции get_entities()/get_combat_system() ниже (помечены как
      ADAPTER). Под другой проект достаточно поправить их так, чтобы они
      возвращали список (entity, is_player) и объект с
      register_event_handler(callback) (или None, если боёвки нет) —
      остальной код опирается только на getattr()-совместимый минимум
      (entity_id/health/max_health/x/y/node/is_alive()).

Пример под другой проект:
    .venv/Scripts/python.exe tools/dev_probe.py --entry-module app --game-class App \
        --game-kwargs '{"headless": false}'
"""
import argparse
import importlib
import json
import logging
import random
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dev_probe_compare import diff_is_empty, diff_summaries, format_diff  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageStat
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from panda3d.core import Filename, Point2, TextNode, loadPrcFileData  # noqa: E402

LOW_HP_FRACTION = 0.2
PINNED_SECONDS_THRESHOLD = 5.0


def _parse_action_at(value):
    """argparse type= for --action-at: validates SEC:KEY at parse time instead
    of blowing up later with a raw ValueError from an unpacking/float() failure
    deep inside the sampling loop."""
    sec_str, sep, key = value.partition(":")
    if not sep:
        raise argparse.ArgumentTypeError(f"expected SEC:KEY (e.g. 1.5:1), got {value!r}")
    try:
        sec = float(sec_str)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number before ':', got {sec_str!r} in {value!r}")
    if not key:
        raise argparse.ArgumentTypeError(f"KEY after ':' is empty in {value!r}")
    return (sec, key)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Agent-oriented playtest probe: annotated screenshots + one summary.md",
        epilog="For logic-only changes (combat formulas, is_alive()/is_defeated latching, AI "
               "targeting/movement math), run tools/combat_smoke_test.py FIRST instead: no window, "
               "no screenshots, sub-second. Reach for this full windowed run only when the change "
               "needs visual/rendering/timing verification.",
    )
    parser.add_argument("--duration", type=float, default=30.0, help="total seconds to run")
    parser.add_argument("--sample-interval", type=float, default=1.0, help="seconds between cheap state samples")
    parser.add_argument("--full", action="store_true", help="use the full-size map instead of the dev map")
    parser.add_argument("--out", type=str, default=None,
                         help="output directory (default: a fresh dev_probe_output/<timestamp>_xxxxxxxx/ dir)")
    parser.add_argument(
        "--action-at", action="append", default=[], type=_parse_action_at, metavar="SEC:KEY",
        help="simulate pressing KEY at time SEC (e.g. 1:1 to spawn near hero at t=1s). Repeatable.",
    )
    parser.add_argument("--screenshot-interval", type=float, default=0.0,
                         help="also take a screenshot every N seconds regardless of events (0 = events only)")
    parser.add_argument("--entry-module", type=str, default="main",
                         help="module to import for the game entry point (default: this project's main.py)")
    parser.add_argument("--game-class", type=str, default="Game",
                         help="class inside --entry-module to instantiate (default: Game)")
    parser.add_argument("--game-kwargs", type=json.loads, default=None,
                         help='JSON object of kwargs for the game class, e.g. \'{"dev_mode": true}\'. '
                              "Defaults to {\"dev_mode\": not --full} for this project. "
                              "(json.loads as the argparse type: malformed JSON fails cleanly at parse time.)")
    parser.add_argument("--seed", type=int, default=None,
                         help="seed Python's random module + the game's RNGManager (if present) to reduce "
                              "run-to-run variance for before/after comparisons. NOT byte-exact reproduction: "
                              "per-frame random calls (e.g. enemy wander jitter) still depend on wall-clock "
                              "frame timing, which isn't fixed by this flag")
    parser.add_argument("--verbosity", type=int, choices=[0, 1, 2], default=1,
                         help="stdout noise level: 0 = only the final RESULT line, 1 (default) = anomalies/"
                              "fatal errors too, 2 = every event (screenshots, kills, HP crossings). "
                              "summary.md's Timeline always has everything regardless of this flag - this "
                              "only controls what's echoed live to the console you're reading right now")
    parser.add_argument("--save-baseline", action="store_true",
                         help="also save this run's summary.json as tools/dev_probe_baseline.json. Every "
                              "later run auto-compares against it (see '## vs baseline' in summary.md) - "
                              "save once after confirming a run is good, then every subsequent run's own "
                              "output already carries the before/after verdict without a separate diff step")
    args = parser.parse_args()

    if args.duration <= 0:
        parser.error("--duration must be > 0")
    if args.sample_interval <= 0:
        parser.error("--sample-interval must be > 0")
    if args.sample_interval > args.duration:
        parser.error(f"--sample-interval ({args.sample_interval}) must be <= --duration ({args.duration}), "
                      "otherwise the run ends before a single sample is taken")
    if args.screenshot_interval < 0:
        parser.error("--screenshot-interval must be >= 0 (0 disables periodic screenshots)")
    if args.game_kwargs is not None and not isinstance(args.game_kwargs, dict):
        parser.error(f"--game-kwargs must be a JSON object, got {type(args.game_kwargs).__name__}")
    return args


def get_entities(game):
    """ADAPTER (project-specific): return [(entity, is_player), ...] for every unit in the scene.

    For AI-EVOLVE this reads game.scene.player/.enemies. Point this at a
    different project's scene/entity list to reuse the tool elsewhere."""
    scene = getattr(game, "scene", None)
    if scene is None:
        return []
    entities = []
    if getattr(scene, "player", None) is not None:
        entities.append((scene.player, True))
    for enemy in getattr(scene, "enemies", []):
        entities.append((enemy, False))
    return entities


def get_combat_system(game):
    """ADAPTER (project-specific): return an object with register_event_handler(callback), or None.

    Combat-event capture is skipped gracefully if this returns None."""
    return getattr(game, "combat_system", None)


class EntityLabel:
    """3D-текст над юнитом (id/тип/HP), тот же billboard-приём, что и HealthBar."""

    def __init__(self, parent, z_offset):
        self.text_node = TextNode("probe_label")
        self.text_node.setAlign(TextNode.ACenter)
        self.text_node.setTextColor(1, 1, 1, 1)
        self.text_node.setShadow(0.06, 0.06)
        self.text_node.setShadowColor(0, 0, 0, 1)
        self.path = parent.attachNewNode(self.text_node)
        self.path.setPos(0, 0, z_offset)
        self.path.setScale(0.35)
        self.path.setBillboardPointEye()
        self.path.setLightOff(1)
        self.path.setDepthWrite(False)
        self.path.setBin("fixed", 101)

    def update(self, text):
        self.text_node.setText(text)


def entity_id_of(entity):
    return getattr(entity, "entity_id", None) or f"obj_{id(entity)}"


def short_id(entity_id):
    return entity_id.rsplit("_", 1)[-1][-5:]


def label_text(entity, is_player):
    kind = "HERO" if is_player else getattr(entity, "enemy_type", entity.__class__.__name__)
    return f"{kind} #{short_id(entity_id_of(entity))}\nHP {entity.health:.0f}/{entity.max_health:.0f}"


def entity_state(entity, is_player):
    return {
        "id": entity_id_of(entity),
        "type": "hero" if is_player else getattr(entity, "enemy_type", entity.__class__.__name__),
        "hp": round(entity.health, 1),
        "max_hp": entity.max_health,
        "pos": [round(entity.x, 1), round(entity.y, 1)],
    }


def world_to_screen(game, node_path):
    """Проекция мировой позиции узла в пиксели экрана. None, если вне вида камеры."""
    cam = game.cam
    lens = cam.node().getLens()
    pos_in_cam_space = node_path.getPos(cam)
    screen_point = Point2()
    if not lens.project(pos_in_cam_space, screen_point):
        return None
    win = game.win
    x = int((screen_point.getX() + 1) / 2 * win.getXSize())
    y = int((1 - screen_point.getY()) / 2 * win.getYSize())
    return [x, y]


BLANK_FRAME_STDDEV_THRESHOLD = 2.0  # out of 0-255; a real scene has far more variance than this


def _average_hash(gray_img, size=8):
    """Cheap 64-bit perceptual hash (resize to size x size, threshold against
    the mean) - not robust like a real pHash, but enough to tell "visually
    near-identical" from "visibly different" between two frames, which is all
    the redundancy check below needs. tobytes() (not getdata(), deprecated in
    newer Pillow) gives one 0-255 byte per pixel directly for 'L' mode."""
    pixels = gray_img.resize((size, size)).tobytes()
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p >= avg:
            bits |= (1 << i)
    return bits


def _hamming(a, b):
    return bin(a ^ b).count("1")


def analyze_screenshot(path):
    """Optional (needs Pillow) visual sanity check that catches rendering
    failures game state alone can't: a crashed graphics context, an empty
    scene graph, or a window stuck on a loading/black screen all still leave
    game logic (HP, positions, combat) running fine, so state.jsonl alone
    would report a perfectly healthy run while the window shows nothing.
    Also returns a cheap perceptual hash (`phash`) so callers can tell two
    frames apart without a second image decode."""
    if not PIL_AVAILABLE:
        return {}
    try:
        with Image.open(path) as img:
            gray = img.convert("L")
            stddev = ImageStat.Stat(gray).stddev[0]
            phash = _average_hash(gray)
    except Exception:
        return {}
    return {
        "pixel_stddev": round(stddev, 2),
        "likely_blank": stddev < BLANK_FRAME_STDDEV_THRESHOLD,
        "phash": phash,
    }


def _build_timelapse_gif(out_dir, frame_names, max_width=640, frame_duration_ms=400):
    """Optional (needs Pillow): stitch every captured screenshot into one GIF
    so a human can scrub through the whole run instead of opening N separate
    files. Downscaled to keep the file small - this is a scrubbing aid, not a
    replacement for the full-resolution frame_NNN.jpg files."""
    if not PIL_AVAILABLE or len(frame_names) < 2:
        return None
    frames = []
    try:
        for name in frame_names:
            with Image.open(out_dir / name) as img:
                img = img.convert("RGB")
                if img.width > max_width:
                    img = img.resize((max_width, int(img.height * max_width / img.width)))
                frames.append(img.copy())
        gif_path = out_dir / "timelapse.gif"
        frames[0].save(
            gif_path, save_all=True, append_images=frames[1:],
            duration=frame_duration_ms, loop=0, optimize=True,
        )
        return gif_path.name
    except Exception:
        return None


def _group_consecutive_by_kind(shots):
    """Collapse consecutive screenshots sharing the same non-None `kind` into
    one group. Same idea as log_event's live-suppression, applied to the
    persisted summary.md listing/contact sheet instead of stdout. Works with
    or without Pillow - grouping is driven by the `kind` tag set at the
    take_screenshot() call site (e.g. "dead_screenshot"), not pixel data."""
    groups = []
    i, n = 0, len(shots)
    while i < n:
        kind = shots[i]["kind"]
        j = i + 1
        if kind is not None:
            while j < n and shots[j]["kind"] == kind:
                j += 1
        groups.append(shots[i:j])
        i = j
    return groups


def _build_contact_sheet(out_dir, shots, cell_width=200):
    """Optional (needs Pillow): tile representative screenshots into one grid
    image with captions, so a routine "does this run look sane" pass costs one
    Read instead of one per frame - open the matching frame_NNN.jpg at full
    resolution only when a specific cell looks wrong. `shots` should already be
    the reduced representative list (see finish()), not every raw frame - a
    long dead/pinned stretch would otherwise make the sheet as expensive to
    read as opening every frame individually."""
    if not PIL_AVAILABLE or not shots:
        return None
    try:
        thumbs = []
        for s in shots:
            with Image.open(out_dir / s["name"]) as img:
                img = img.convert("RGB")
                h = max(1, int(img.height * cell_width / img.width))
                thumbs.append((img.resize((cell_width, h)), f"{s['name']} t={s['t']:.1f}s", s["reason"][:36]))
        cols = min(4, len(thumbs))
        rows = -(-len(thumbs) // cols)
        cap_h = 32
        cell_h = thumbs[0][0].height + cap_h
        sheet = Image.new("RGB", (cell_width * cols, cell_h * rows), (25, 25, 25))
        draw = ImageDraw.Draw(sheet)
        for i, (thumb, caption, reason) in enumerate(thumbs):
            x, y = (i % cols) * cell_width, (i // cols) * cell_h
            sheet.paste(thumb, (x, y))
            draw.text((x + 3, y + thumb.height + 2), caption, fill=(255, 255, 0))
            draw.text((x + 3, y + thumb.height + 16), reason, fill=(210, 210, 210))
        sheet_path = out_dir / "contact_sheet.jpg"
        sheet.save(sheet_path, quality=85)
        return sheet_path.name
    except Exception:
        return None


class WarningCollector(logging.Handler):
    """Собирает WARNING+ из лога игры, чтобы не парсить stdout отдельно."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append(self.format(record))


def main():
    args = parse_args()
    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        # tempfile.mkdtemp atomically creates a guaranteed-new directory - a
        # plain "dev_probe_output/<timestamp>/" name collides if two runs start
        # within the same second (mkdir(exist_ok=True) would then silently mix
        # both runs' frames/state.jsonl/summary.md together).
        base_dir = ROOT / "dev_probe_output"
        base_dir.mkdir(parents=True, exist_ok=True)
        out_dir = Path(tempfile.mkdtemp(prefix=f"{time.strftime('%Y%m%d_%H%M%S')}_", dir=str(base_dir)))

    # Panda3D's own startup chatter ("Known pipe types", "all display modules
    # loaded") goes through its internal Notify system, not Python's logging -
    # WarningCollector/file_handler below never see it, so it's paid as fixed
    # stdout noise on every single run regardless of --duration. Must be set
    # before the entry module (which constructs ShowBase) is even imported.
    loadPrcFileData("", f"notify-output {(out_dir / 'panda3d.log').as_posix()}")

    log_format = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    warning_collector = WarningCollector()
    warning_collector.setFormatter(log_format)
    logging.getLogger().addHandler(warning_collector)
    file_handler = logging.FileHandler(out_dir / "game.log", encoding="utf-8")
    file_handler.setFormatter(log_format)
    logging.getLogger().addHandler(file_handler)
    # Must set this explicitly: importing --entry-module below may call its own
    # logging.basicConfig(level=INFO), which is a documented no-op once the root
    # logger already has handlers (which it does, from the two addHandler calls
    # just above) - without this line game.log would silently only ever contain
    # WARNING+ despite looking like it captures everything.
    logging.getLogger().setLevel(logging.INFO)

    if args.seed is not None:
        random.seed(args.seed)
        try:
            from src.core.rng_manager import RNGConfig, RNGManager, set_default_rng
            set_default_rng(RNGManager(RNGConfig(seed=args.seed, use_deterministic=True)))
        except ImportError:
            print("(!) src.core.rng_manager not importable - only Python's random module was seeded")

    scheduled_actions = sorted(args.action_at)  # already (float, key) tuples - validated by _parse_action_at
    fired_actions = set()

    if args.game_kwargs is not None:
        game_kwargs = args.game_kwargs  # already a dict - validated in parse_args()
    elif args.entry_module == "main" and args.game_class == "Game":
        game_kwargs = {"dev_mode": not args.full}  # this project's convention
    else:
        game_kwargs = {}

    entry_module = importlib.import_module(args.entry_module)
    game_cls = getattr(entry_module, args.game_class)
    game = game_cls(**game_kwargs)

    def simulate_key(key, pressed):
        set_key = getattr(game, "_set_key", None)
        if set_key is None:
            print(f"(!) {game_cls.__name__} has no _set_key(key, pressed) - scheduled actions are a no-op here")
            return
        set_key(key, pressed)

    start_time = time.perf_counter()

    combat_events = []
    combat_system = get_combat_system(game)
    if combat_system is not None:
        combat_system.register_event_handler(lambda info: combat_events.append({
            "t": round(time.perf_counter() - start_time, 2),
            "source": info.source, "target": info.target,
            "damage": round(info.damage, 1), "critical": info.is_critical, "dodged": info.is_dodged,
        }))

    state_log = (out_dir / "state.jsonl").open("w", encoding="utf-8")
    timeline = []
    labels = {}
    known_enemy_ids = set()
    screenshots = []
    kill_count = 0
    low_hp_since = None
    pinned_reported = False
    min_hp_seen = {"value": None, "t": None}
    sample_count = 0
    last_periodic_shot = -1e9
    death_reported = False
    death_event_count = 0
    run_state = {"completed": False, "last_elapsed": 0.0, "error": None}
    finished = {"done": False}
    blank_frame_count = 0
    live_repeat = {"kind": None, "count": 0}
    last_phash = {"value": None}

    def log_event(elapsed, text, level=2, kind=None):
        # level 0 = always printed (fatal), 1 = anomalies, 2 = routine/frequent.
        # summary.md's Timeline gets every line regardless - this only decides
        # what's echoed live, since that's what a driving agent pays to read
        # back from the tool call every single run.
        #
        # `kind`, when given, groups repeats of the "same kind of thing" (e.g.
        # every per-tick screenshot during a pinned/dead stretch): the first 2
        # print live, the 3rd prints one "suppressing further..." note, and the
        # rest are silent live (still fully in the timeline) until a different
        # kind interrupts the streak. There's no live terminal here to overwrite
        # a line on (this output is read back later from a buffered tool-call
        # result), so collapsing-after-N is the workable equivalent.
        line = f"[{elapsed:6.1f}s] {text}"
        timeline.append(line)
        if level > args.verbosity:
            return
        if kind is not None and kind == live_repeat["kind"]:
            live_repeat["count"] += 1
            if live_repeat["count"] <= 2:
                print(line)
            elif live_repeat["count"] == 3:
                print(f"[{elapsed:6.1f}s] ... further '{kind}' lines suppressed live (all still in summary.md)")
            return
        live_repeat["kind"] = kind
        live_repeat["count"] = 1
        print(line)

    def ensure_labels():
        for entity, is_player in get_entities(game):
            node = getattr(entity, "node", None)
            if not node:
                continue
            eid = entity_id_of(entity)
            if eid not in labels:
                z_offset = getattr(entity, "size", 1.0) * 1.9 + 0.55
                labels[eid] = EntityLabel(node, z_offset=z_offset)
            labels[eid].update(label_text(entity, is_player))

    def take_screenshot(elapsed, reason, kind=None):
        nonlocal blank_frame_count
        idx = len(screenshots) + 1
        shot_path = out_dir / f"frame_{idx:03d}.jpg"
        game.screenshot(namePrefix=Filename.from_os_specific(str(shot_path)), defaultFilename=False)

        visual = analyze_screenshot(shot_path)
        if visual.get("phash") is not None:
            # kind-based grouping (below/_group_consecutive_by_kind) is the
            # main redundancy signal and works without Pillow, but where a
            # phash IS available this gives a real pixel-level second opinion
            # per frame instead of leaving the computed hash unused - a small
            # Hamming distance means the frame barely changed even if its
            # `kind` differs (e.g. the tail end of a fight settling down).
            visual["visually_similar_to_previous"] = (
                last_phash["value"] is not None and _hamming(visual["phash"], last_phash["value"]) <= 4
            )
            last_phash["value"] = visual["phash"]
        if visual.get("likely_blank"):
            blank_frame_count += 1
            log_event(
                elapsed,
                f"ANOMALY: {shot_path.name} looks blank/solid-color (pixel stddev="
                f"{visual['pixel_stddev']}) - rendering may be broken even though game state looks fine",
                level=1,
            )

        entities = get_entities(game)
        sidecar = {
            "t": round(elapsed, 2),
            "reason": reason,
            "screen_size": [game.win.getXSize(), game.win.getYSize()],
            **visual,
            "entities": [
                {**entity_state(e, is_player), "screen_xy": world_to_screen(game, e.node)}
                for e, is_player in entities if getattr(e, "node", None)
            ],
        }
        (out_dir / f"frame_{idx:03d}.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        screenshots.append({"name": shot_path.name, "reason": reason, "kind": kind, "t": elapsed})
        # kind groups repeats of the SAME situation (e.g. "player dead" fires
        # every tick by design - see the no-dedup comment below) even though
        # `reason` itself carries a different HP number each time and would
        # never look like a "repeat" to a naive text comparison.
        log_event(elapsed, f"SCREENSHOT {shot_path.name} — {reason}", kind=kind)

    def sample(task):
        elapsed = time.perf_counter() - start_time
        run_state["last_elapsed"] = elapsed
        try:
            return _sample_body(elapsed, task)
        except SystemExit:
            raise
        except Exception as exc:
            # Panda3D's task manager swallows plain Exceptions raised from a task
            # callback (logs ":task(error)" and just stops rescheduling that one
            # task) instead of letting them propagate - without this, a bug in
            # here would silently hang the game forever with no summary.md ever
            # written, instead of failing loudly. sys.exit (unlike Exception) is
            # NOT swallowed, so it reliably reaches the try/finally around
            # game.run() below.
            run_state["error"] = traceback.format_exc()
            log_event(elapsed, f"FATAL: sample() crashed: {exc!r}", level=0)
            sys.exit(1)

    def _sample_body(elapsed, task):
        nonlocal low_hp_since, pinned_reported, sample_count, kill_count, last_periodic_shot, death_reported, death_event_count
        sample_count += 1

        for idx, (sec, key) in enumerate(scheduled_actions):
            if idx not in fired_actions and elapsed >= sec:
                fired_actions.add(idx)
                simulate_key(key, True)
                game.taskMgr.doMethodLater(
                    0.15, lambda k, t: (simulate_key(k, False), t.done)[1],
                    f"release_{key}_{idx}", extraArgs=[key], appendTask=True,
                )
                log_event(elapsed, f"action: pressed '{key}'")

        ensure_labels()

        entities = get_entities(game)
        player = next((e for e, is_player in entities if is_player), None)
        enemies = [e for e, is_player in entities if not is_player]

        current_enemy_ids = {entity_id_of(e) for e in enemies}
        killed_ids = known_enemy_ids - current_enemy_ids
        for enemy_id in killed_ids:
            kill_count += 1
            log_event(elapsed, f"enemy killed: ...{enemy_id[-8:]}")
        known_enemy_ids.clear()
        known_enemy_ids.update(current_enemy_ids)

        state = {
            "t": round(elapsed, 2),
            "player": entity_state(player, True) if player else None,
            "enemies": [entity_state(e, False) for e in enemies],
        }
        state_log.write(json.dumps(state, ensure_ascii=False) + "\n")
        state_log.flush()

        if sample_count == 1:
            take_screenshot(elapsed, "run start")
        elif args.screenshot_interval and (elapsed - last_periodic_shot) >= args.screenshot_interval:
            last_periodic_shot = elapsed
            take_screenshot(elapsed, "periodic")

        if player:
            hp_fraction = player.health / player.max_health
            is_dead = not player.is_alive()
            # Аномальные состояния (низкий HP, смерть) скриншотятся КАЖДЫЙ
            # тик, без дедупа - если задедупить, можно пропустить именно то,
            # что интересно: например HP, скачущее вокруг 0 туда-сюда между
            # "мёртв"/"жив" из-за какого-нибудь бага (см. историю проекта).
            # Частота и так ограничена --sample-interval, это не спам.
            if is_dead:
                if not death_reported:
                    death_reported = True
                    death_event_count += 1
                    log_event(elapsed, "ANOMALY: player died", level=1)
                take_screenshot(elapsed, "player dead", kind="dead_screenshot")
                # Смерть залипающая (Character.is_defeated) - обнуляем pinned-таймер,
                # чтобы старый low_hp_since не триггернул "pinned... without dying"
                # уже ПОСЛЕ того, как смерть уже была зафиксирована выше.
                low_hp_since = None
            else:
                death_reported = False

                if hp_fraction < LOW_HP_FRACTION:
                    if low_hp_since is None:
                        low_hp_since = elapsed
                        log_event(elapsed, f"player HP dropped below {int(LOW_HP_FRACTION * 100)}%")
                    elif not pinned_reported and elapsed - low_hp_since >= PINNED_SECONDS_THRESHOLD:
                        pinned_reported = True
                        log_event(
                            elapsed,
                            f"ANOMALY: player pinned under {int(LOW_HP_FRACTION * 100)}% HP for "
                            f"{elapsed - low_hp_since:.1f}s straight",
                            level=1,
                        )
                    take_screenshot(
                        elapsed, f"player HP below {int(LOW_HP_FRACTION * 100)}% ({player.health:.1f})",
                        kind="low_hp_screenshot",
                    )
                elif low_hp_since is not None:
                    log_event(elapsed, "player HP recovered above threshold")
                    low_hp_since = None
                    pinned_reported = False  # a second, independent low-HP episode can fire again

            if min_hp_seen["value"] is None or player.health < min_hp_seen["value"]:
                min_hp_seen["value"] = player.health
                min_hp_seen["t"] = elapsed

        if elapsed >= args.duration:
            take_screenshot(elapsed, "run end")
            run_state["completed"] = True
            sys.exit(0)
        return task.again

    def finish():
        # Called exactly once, from the try/finally around game.run() below - not
        # from _sample_body - so it fires on every exit path: normal completion,
        # an exception caught above, Escape (main.py binds it to sys.exit), or the
        # window's own close button (Panda3D's default handler also exits).
        if finished["done"]:
            return
        finished["done"] = True
        state_log.close()
        final_player = next((e for e, is_player in get_entities(game) if is_player), None)
        hits = [e for e in combat_events if not e["dodged"]]
        dodges = [e for e in combat_events if e["dodged"]]
        crits = [e for e in combat_events if e["critical"]]
        player_id = entity_id_of(final_player) if final_player else None
        dmg_dealt = sum(e["damage"] for e in hits if e["source"] == player_id)
        dmg_taken = sum(e["damage"] for e in hits if e["target"] == player_id)

        if run_state["error"]:
            status = "CRASHED"
        elif run_state["completed"]:
            status = "OK"
        else:
            status = "STOPPED EARLY"

        min_hp = min_hp_seen["value"] if min_hp_seen["value"] is not None else (final_player.health if final_player else None)
        min_hp_t = min_hp_seen["t"]
        end_hp = final_player.health if final_player else None

        # Categorized counts, not raw timestamped lines - a before/after diff
        # comparing these survives run-to-run timing jitter that would make a
        # line-by-line timeline diff flag nearly everything as "changed" just
        # because elapsed timestamps shifted a few tenths of a second.
        event_counts = {
            "enemy_killed": kill_count,
            "anomaly_died": death_event_count,
            "anomaly_pinned": 1 if pinned_reported else 0,
            "anomaly_blank_frame": blank_frame_count,
            "warning": len(warning_collector.records),
        }
        screenshot_reason_counts = dict(Counter(s["kind"] or s["reason"] for s in screenshots))

        summary_data = {
            "status": status,
            "seed": args.seed,
            "dev_map": not args.full,
            "duration_configured": args.duration,
            "elapsed": round(run_state["last_elapsed"], 2),
            "dmg_dealt": round(dmg_dealt, 2),
            "dmg_taken": round(dmg_taken, 2),
            "kill_count": kill_count,
            "hits": len(hits),
            "dodges": len(dodges),
            "crits": len(crits),
            "min_hp": round(min_hp, 2) if min_hp is not None else None,
            "min_hp_t": min_hp_t,
            "end_hp": round(end_hp, 2) if end_hp is not None else None,
            "pinned_reported": pinned_reported,
            "warning_count": len(warning_collector.records),
            "blank_frame_count": blank_frame_count,
            "sample_count": sample_count,
            "event_counts": event_counts,
            "screenshot_reason_counts": screenshot_reason_counts,
        }
        (out_dir / "summary.json").write_text(json.dumps(summary_data, indent=1), encoding="utf-8")

        baseline_path = ROOT / "tools" / "dev_probe_baseline.json"
        baseline_diff_text = None
        baseline_changed = None
        if baseline_path.exists():
            try:
                baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
                baseline_diff = diff_summaries(baseline_data, summary_data)
                baseline_diff_text = format_diff(baseline_diff, before_label="baseline", after_label="this run")
                baseline_changed = not diff_is_empty(baseline_diff)
            except Exception as exc:
                baseline_diff_text = f"(could not compare against {baseline_path.name}: {exc!r})"
        if args.save_baseline:
            baseline_path.write_text(json.dumps(summary_data, indent=1), encoding="utf-8")

        lines = [
            f"# Dev Probe Summary — {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Status: {status}" + (
                "" if status == "OK" else
                f" (stopped at t={run_state['last_elapsed']:.1f}s of {args.duration}s configured"
                f"{' - see Crash traceback below' if status == 'CRASHED' else ' - Escape or window closed?'})"
            ),
            "",
            f"Config: duration={args.duration}s dev_map={not args.full} seed={args.seed} "
            f"actions={[f'{s}s:{k}' for s, k in scheduled_actions]}",
            "",
            "## Timeline",
            *timeline,
            "",
            "## Combat totals",
            f"attacks: {len(combat_events)} ({len(hits)} hit, {len(dodges)} dodged, {len(crits)} critical)",
            f"damage dealt by player: {dmg_dealt:.1f}",
            f"damage taken by player: {dmg_taken:.1f}",
            f"enemies killed: {kill_count}",
            "",
        ]
        if final_player:
            p = final_player
            lines += [
                "## Player HP",
                f"start: {p.max_health}/{p.max_health}  min: {min_hp:.1f} (at t={min_hp_t or 0.0:.1f}s)  "
                f"end: {p.health:.1f}/{p.max_health}",
                "",
            ]
        if baseline_diff_text is not None:
            lines += ["## vs baseline (tools/dev_probe_baseline.json)", baseline_diff_text, ""]
        lines.append("## Issues detected")
        if pinned_reported:
            lines.append("- Player was pinned under low HP for an extended period without dying (see ANOMALY in timeline).")
        if warning_collector.records:
            lines.append(f"- {len(warning_collector.records)} WARNING/ERROR log line(s) captured (see below).")
        if blank_frame_count:
            lines.append(f"- {blank_frame_count} screenshot(s) looked blank/solid-color - rendering may be broken "
                          "despite game state looking healthy (needs Pillow to detect; see per-frame pixel_stddev "
                          "in frame_NNN.json).")
        elif not PIL_AVAILABLE:
            lines.append("- Blank-frame visual check skipped (Pillow not installed: pip install pillow).")
        if not pinned_reported and not warning_collector.records and not blank_frame_count and PIL_AVAILABLE:
            lines.append("- None.")
        lines.append("")
        if warning_collector.records:
            shown = warning_collector.records[:30]
            lines += ["## Warnings / errors", *shown]
            if len(warning_collector.records) > len(shown):
                lines.append(f"... {len(warning_collector.records) - len(shown)} more, truncated - see game.log")
            lines.append("")
        if run_state["error"]:
            lines += ["## Crash traceback", "```", run_state["error"].rstrip(), "```", ""]

        # Consecutive same-`kind` screenshots (e.g. a 20-tick "player dead"
        # stretch) collapse to their first+last representative here - opening
        # every one of those is rarely useful, and doing so anyway is still
        # possible: every raw frame_NNN.jpg/.json stays on disk untouched.
        groups = _group_consecutive_by_kind(screenshots)
        representative_shots = []
        lines.append("## Screenshots (each has a matching frame_NNN.json with per-entity screen_xy pixels)")
        for group in groups:
            if len(group) <= 2:
                for s in group:
                    lines.append(f"- {s['name']} — {s['reason']}")
                representative_shots.extend(group)
            else:
                first, last = group[0], group[-1]
                lines.append(f"- {first['name']} — {first['reason']}")
                lines.append(f"  ... {len(group) - 2} more '{first['kind']}' frame(s) omitted (same situation, "
                              f"still in state.jsonl/frame_NNN.jpg on disk if needed) ...")
                lines.append(f"- {last['name']} — {last['reason']}")
                representative_shots.extend([first, last])

        # For an agent's routine "does this look sane" pass: contact_sheet.jpg
        # is the one image worth Read-ing - it's built from representative_shots
        # (redundant runs already collapsed above), captioned per cell, so it
        # answers that question in one vision call instead of one per frame.
        # timelapse.gif is a human-scrubbing convenience (open in an image
        # viewer that plays GIFs) - it is NOT a substitute for contact_sheet.jpg
        # for an agent reading it back through a single-frame image Read.
        contact_sheet_name = _build_contact_sheet(out_dir, representative_shots)
        timelapse_name = _build_timelapse_gif(out_dir, [s["name"] for s in screenshots])
        lines += [
            "",
            f"Contact sheet (open this first for a whole-run visual check): {contact_sheet_name}" if contact_sheet_name
            else "Contact sheet: skipped (needs Pillow)",
            f"Timelapse GIF (human scrubbing convenience, not a whole-run overview image): {timelapse_name}"
            if timelapse_name else "Timelapse GIF: skipped (needs Pillow and 2+ screenshots)",
            "",
            f"Raw per-tick state: state.jsonl ({sample_count} samples)",
            "Full game log: game.log",
            "Panda3D's own engine output: panda3d.log",
            "Machine-readable numbers (for tools/dev_probe_diff.py or your own scripting): summary.json",
        ]

        (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
        # Always printed regardless of --verbosity: one grep-able line with the
        # handful of numbers that answer "did this run look fine" without
        # opening summary.md at all - useful for a quick before/after smoke
        # check where the agent only needs to know pass/fail, not the story.
        print(
            f"RESULT status={status} kills={kill_count} dmg_dealt={dmg_dealt:.1f} "
            f"dmg_taken={dmg_taken:.1f} warnings={len(warning_collector.records)} "
            f"blank_frames={blank_frame_count} pinned={pinned_reported} "
            f"elapsed={run_state['last_elapsed']:.1f}s"
        )
        if baseline_diff_text is not None:
            tag = "CHANGED" if baseline_changed else "no change"
            print(f"vs baseline: {tag} (see '## vs baseline' in summary.md for details)")
        if args.save_baseline:
            print(f"Saved this run as the new baseline: {baseline_path}")
        print(f"Read {out_dir / 'summary.md'} for the full story.")

    try:
        game.taskMgr.doMethodLater(args.sample_interval, sample, "dev_probe_sample")
        game.run()
    finally:
        finish()


if __name__ == "__main__":
    main()
