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
8. --seed сидирует и random, и RNGManager проекта. Вместе с --fast прогон
   ПОБИТОВО повторяем: fixed-step виртуальные часы (tools/probe_runtime.py)
   отвязывают dt и таймеры игры (time.time()/perf_counter()) от настенного
   времени. Без --fast dt по-прежнему плавает - только меньший разброс.
   Каждый прогон пишет repro.sh с точной командой повтора.
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
11. Кадровая аналитика: Rust (rust_core.ProbeAnalyzer, пороги - из
    lua_content/probe_config.lua) -> Pillow -> OpenCV-дополнения. 256-битный
    perceptual hash кластеризует похожие кадры: в summary.md остаются только
    визуально разные, контакт-лист собирается из них.
12. Режимы без окна: --render offscreen (скриншоты есть, окна нет; нужен
    OpenGL, на Linux - xvfb-run) и --render none (без графики вообще, работает
    в любом контейнере). Звук всегда выключен: раньше ALSA/OpenAL печатали
    ~40 строк мусора в stdout на каждый прогон.
13. Гипотезы и прогнозы (tools/probe_analysis.py, числа считает Rust -
    rust_core.RunAnalytics, пороги - lua_content/dev_tools.lua): "симптом ->
    вероятная причина -> файл" и "когда герой умрёт при таком темпе". Прогон
    складывается в SQLite (tools/probe_db.py: stats/why/predict/compare/trend).

ВАЖНО - для логических правок (формулы урона/крита, is_alive()/is_defeated,
AI-таргетинг/движение) СНАЧАЛА запускай tools/combat_smoke_test.py: без окна,
без скриншотов, доли секунды вместо реального --duration секунд с открытым
Panda3D. Он уже сейчас проверяет ровно то, что раньше приходилось выяснять
через этот файл (death-latch регрессию, floor урона, крит/додж через
CombatSystem, AI retreat/targeting). Возвращайся к dev_probe.py, когда нужна
именно визуальная/рендер/сценовая проверка, а не просто "правильно ли считает
формула".

Чтобы УПРАВЛЯТЬ игрой как игрок (spawn/attack/wait/expect) - tools/agent_play.py:
без окна, ~200x быстрее реального времени, детерминированно.

Результат одного прогона — ОДИН файл summary.md, с него и надо начинать
чтение. state.jsonl / game.log / frame_NNN.json / panda3d.log — только если
summary на что-то указывает и нужно копнуть глубже.

Использование (этот проект):
    .venv/Scripts/python.exe tools/dev_probe.py --duration 30
    .venv/Scripts/python.exe tools/dev_probe.py --action-at 1:1 --action-at 1:2 --action-at 1:3
    .venv/Scripts/python.exe tools/dev_probe.py --seed 42 --duration 20   # меньший разброс
    python tools/dev_probe.py --render none --fast --seed 42 --duration 120 --action-at 1:1  # логика, <1 с
    xvfb-run -a python tools/dev_probe.py --headless --fast --seed 42 --screenshot-interval 10

Переиспользование в другом Panda3D-проекте:
    - Всё, что касается запуска окна (screenshot+пиксельная проекция через
      game.cam/game.win, boilerplate ShowBase-задач) уже общее — не завязано
      на этот проект.
    - --entry-module/--game-class/--game-kwargs говорят инструменту, как
      импортировать и создать игру другого проекта, не трогая код инструмента.
    - Единственное, что реально завязано на модель данных ЭТОГО проекта —
      функции get_entities()/get_combat_system() в tools/probe_runtime.py
      (помечены как ADAPTER). Под другой проект достаточно поправить их так, чтобы они
      возвращали список (entity, is_player) и объект с
      register_event_handler(callback) (или None, если боёвки нет) —
      остальной код опирается только на getattr()-совместимый минимум
      (entity_id/health/max_health/x/y/node/is_alive()).

Пример под другой проект:
    .venv/Scripts/python.exe tools/dev_probe.py --entry-module app --game-class App \
        --game-kwargs '{"headless": false}'
"""
import argparse
import json
import logging
import shlex
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

try:
    import cv2
    import numpy as np
    from skimage.metrics import structural_similarity as ssim_skimage
    CV2_AVAILABLE = True
    SKIMAGE_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    SKIMAGE_AVAILABLE = False

try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from panda3d.core import Filename, Point2, TextNode  # noqa: E402

import probe_analysis as analysis  # noqa: E402
import probe_runtime as runtime  # noqa: E402
# ADAPTER-функции живут в probe_runtime (общие с agent_play.py); имена
# оставлены здесь для обратной совместимости импортов из dev_probe.
from probe_runtime import (  # noqa: E402,F401
    entity_id_of, entity_state, get_combat_system, get_entities, get_scene,
)

try:  # кадровая аналитика на Rust (rust_core/src/probe), конфиг - lua_content/probe_config.lua
    from rust_core import ProbeAnalyzer as _RustProbeAnalyzer
    RUST_PROBE_AVAILABLE = True
except ImportError:
    RUST_PROBE_AVAILABLE = False

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
               "no screenshots, sub-second. To DRIVE the game like a player (spawn/attack/wait/expect) "
               "use tools/agent_play.py - windowless and ~200x faster than real time. Reach for this "
               "probe when the change needs visual/rendering verification.",
    )
    parser.add_argument("--duration", type=float, default=30.0, help="total seconds to run (game seconds with --fast)")
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
    parser.add_argument("--render", choices=runtime.RENDER_MODES, default="window",
                         help="window (default) | offscreen (no window, screenshots still work; needs OpenGL, "
                              "e.g. xvfb-run on Linux) | none (no graphics at all: logic-only, no screenshots, "
                              "works in any container)")
    parser.add_argument("--headless", action="store_true", help="shortcut for --render offscreen")
    parser.add_argument("--fast", action="store_true",
                         help="fixed-step virtual game clock: runs as fast as the machine allows (render=none: "
                              "~200x real time) and together with --seed makes runs byte-for-byte reproducible")
    parser.add_argument("--fps", type=int, default=runtime.DEFAULT_FPS,
                         help="simulation step for --fast (frames per game second)")
    parser.add_argument("--entry-module", type=str, default="main",
                         help="module to import for the game entry point (default: this project's main.py)")
    parser.add_argument("--game-class", type=str, default="Game",
                         help="class inside --entry-module to instantiate (default: Game)")
    parser.add_argument("--game-kwargs", type=json.loads, default=None,
                         help='JSON object of kwargs for the game class, e.g. \'{"dev_mode": true}\'. '
                              "Defaults to {\"dev_mode\": not --full} for this project. "
                              "(json.loads as the argparse type: malformed JSON fails cleanly at parse time.)")
    parser.add_argument("--seed", type=int, default=None,
                         help="seed Python's random module + the game's RNGManager (if present). With --fast the "
                              "run is byte-for-byte reproducible; without it per-frame dt still follows the wall "
                              "clock, so repeated runs only have reduced variance")
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
    if args.headless:
        args.render = "offscreen"

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


def short_id(entity_id):
    return entity_id.rsplit("_", 1)[-1][-5:]


def label_text(entity, is_player):
    kind = "HERO" if is_player else getattr(entity, "enemy_type", entity.__class__.__name__)
    return f"{kind} #{short_id(entity_id_of(entity))}\nHP {entity.health:.0f}/{entity.max_health:.0f}"


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
VISUAL_SIMILARITY_HASH_BITS = 16  # for perceptual hash grid size (16x16 = 256 bits)
VISUAL_SIMILARITY_HAMMING_THRESHOLD = 8  # frames with hamming distance <= this are "visually similar"
MOTION_DETECTION_THRESHOLD = 5.0  # optical flow magnitude threshold for "significant motion"
BRIGHTNESS_ANOMALY_THRESHOLD = 30.0  # stddev threshold for sudden brightness changes (flash/fade detection)
ENTITY_TRACKING_MAX_DISTANCE = 150  # max pixels between frames to consider same entity


def _perceptual_hash_imagehash(img_array, hash_type='phash'):
    """Production-grade perceptual hash using imagehash library.
    
    Offers multiple algorithms:
    - 'ahash': Average hash (fast, less robust)
    - 'phash': Perceptive hash (slower, more robust to scale/contrast)
    - 'dhash': Difference hash (good for detecting small changes)
    - 'whash': Wavelet hash (robust to compression artifacts)
    - 'colorhash': Color-sensitive hash (detects color shifts)
    
    Returns hex string hash that can be compared with hamming distance.
    Falls back to None if imagehash not available."""
    if not IMAGEHASH_AVAILABLE or img_array is None:
        return None
    
    try:
        if img_array.ndim == 3:
            img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        else:
            img_rgb = img_array
        
        pil_img = Image.fromarray(img_rgb)
        
        hash_funcs = {
            'ahash': imagehash.average_hash,
            'phash': imagehash.phash,
            'dhash': imagehash.dhash,
            'whash': imagehash.whash,
            'colorhash': imagehash.colorhash,
        }
        
        hash_func = hash_funcs.get(hash_type, imagehash.phash)
        return str(hash_func(pil_img))
    except Exception:
        return None


def _perceptual_hash_cv2(img_array, size=VISUAL_SIMILARITY_HASH_BITS):
    """OpenCV-based perceptual hash using average hash algorithm.
    
    Returns a 256-bit hash (for 16x16 grid) as an integer. More robust than
    Pillow's simple 8x8 hash, especially for game screenshots with UI elements.
    Works on BGR numpy arrays directly from OpenCV screenshot reads.
    
    Note: When imagehash library is available, prefer _perceptual_hash_imagehash
    for better robustness and multiple algorithm options."""
    if img_array.ndim == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_array
    
    resized = cv2.resize(gray, (size, size))
    avg = np.mean(resized)
    bits = (resized >= avg).flatten()
    hash_value = 0
    for i, bit in enumerate(bits):
        if bit:
            hash_value |= (1 << i)
    return hash_value


def _structural_similarity_ssim(img1_array, img2_array):
    """Fast structural similarity index (SSIM) between two frames.
    
    Returns a value between -1 and 1, where 1 means identical. Values > 0.95
    indicate visually near-identical frames suitable for deduplication.
    Uses scikit-image's production-grade implementation when available,
    falls back to OpenCV's implementation otherwise."""
    if img1_array.shape != img2_array.shape:
        return 0.0
    
    if img1_array.ndim == 3:
        img1_gray = cv2.cvtColor(img1_array, cv2.COLOR_BGR2GRAY)
        img2_gray = cv2.cvtColor(img2_array, cv2.COLOR_BGR2GRAY)
    else:
        img1_gray = img1_array
        img2_gray = img2_array
    
    if SKIMAGE_AVAILABLE:
        # Use scikit-image's production-grade SSIM with full multichannel support
        score, _ = ssim_skimage(img1_gray, img2_gray, full=True)
        return float(score)
    
    # Fallback to OpenCV-based SSIM computation
    img1_float = img1_gray.astype(np.float32) / 255.0
    img2_float = img2_gray.astype(np.float32) / 255.0
    
    C1 = 0.01 ** 2
    C2 = 0.03 ** 2
    
    mu1 = cv2.GaussianBlur(img1_float, (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(img2_float, (11, 11), 1.5)
    
    mu1_sq = mu1 ** 2
    mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2
    
    sigma1_sq = cv2.GaussianBlur(img1_float ** 2, (11, 11), 1.5) - mu1_sq
    sigma2_sq = cv2.GaussianBlur(img2_float ** 2, (11, 11), 1.5) - mu2_sq
    sigma12 = cv2.GaussianBlur(img1_float * img2_float, (11, 11), 1.5) - mu1_mu2
    
    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
               ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
    
    return float(np.mean(ssim_map))


def _compute_optical_flow(prev_frame, curr_frame):
    """Compute dense optical flow between two consecutive frames.
    
    Returns motion magnitude statistics that help agents understand
    scene dynamics without watching video. High motion = action sequence,
    low motion = idle/cutscene/stuck state.
    
    Uses Farneback dense optical flow for smooth motion fields."""
    if not CV2_AVAILABLE or prev_frame is None or curr_frame is None:
        return None
    
    try:
        if prev_frame.ndim == 3:
            prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
        else:
            prev_gray = prev_frame
            curr_gray = curr_frame
        
        # Farneback dense optical flow
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, curr_gray, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2,
            flags=0
        )
        
        # Compute motion magnitude
        magnitude, angle = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        
        return {
            "mean_magnitude": float(np.mean(magnitude)),
            "max_magnitude": float(np.max(magnitude)),
            "std_magnitude": float(np.std(magnitude)),
            "high_motion_pixels": int(np.sum(magnitude > MOTION_DETECTION_THRESHOLD)),
            "motion_ratio": float(np.sum(magnitude > MOTION_DETECTION_THRESHOLD) / magnitude.size),
        }
    except Exception:
        return None


def _detect_brightness_anomalies(img_array, prev_stats=None):
    """Detect sudden brightness changes that may indicate flashes, fades,
    or rendering issues.
    
    Returns anomaly flag and detailed stats. Helps agents catch visual
    effects or problems that game state alone won't reveal."""
    if not CV2_AVAILABLE or img_array is None:
        return {"anomaly": False}
    
    try:
        if img_array.ndim == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_array
        
        mean_val = float(np.mean(gray))
        std_val = float(np.std(gray))
        
        result = {
            "brightness_mean": round(mean_val, 2),
            "brightness_std": round(std_val, 2),
            "anomaly": False,
        }
        
        if prev_stats is not None and "brightness_mean" in prev_stats:
            delta = abs(mean_val - prev_stats["brightness_mean"])
            if delta > BRIGHTNESS_ANOMALY_THRESHOLD:
                result["anomaly"] = True
                result["brightness_delta"] = round(delta, 2)
                result["anomaly_type"] = "flash" if delta > 0 else "fade"
        
        return result
    except Exception:
        return {"anomaly": False}


def _track_entities_across_frames(prev_entities, curr_entities, prev_frame_shape, curr_frame_shape):
    """Track entities between consecutive frames using screen positions.
    
    Returns entity trajectories and lifecycle events (spawned/despawned).
    Helps agents understand entity behavior patterns without manual correlation."""
    if not prev_entities or not curr_entities:
        return {"tracked": [], "spawned": len(curr_entities), "despawned": len(prev_entities)}
    
    tracked = []
    matched_prev = set()
    matched_curr = set()
    
    for i, prev_ent in enumerate(prev_entities):
        prev_pos = prev_ent.get("screen_xy")
        if prev_pos is None:
            continue
        
        best_match = None
        best_dist = ENTITY_TRACKING_MAX_DISTANCE
        
        for j, curr_ent in enumerate(curr_entities):
            if j in matched_curr:
                continue
            
            curr_pos = curr_ent.get("screen_xy")
            if curr_pos is None:
                continue
            
            dist = ((prev_pos[0] - curr_pos[0]) ** 2 + (prev_pos[1] - curr_pos[1]) ** 2) ** 0.5
            
            if dist < best_dist:
                best_dist = dist
                best_match = j
        
        if best_match is not None:
            curr_ent = curr_entities[best_match]
            prev_id = prev_ent.get("id", f"prev_{i}")
            curr_id = curr_ent.get("id", f"curr_{best_match}")
            
            # Only track if IDs match or are close enough
            if prev_id == curr_id or best_dist < ENTITY_TRACKING_MAX_DISTANCE * 0.5:
                tracked.append({
                    "entity_id": curr_id,
                    "displacement": round(best_dist, 2),
                    "prev_hp": prev_ent.get("hp"),
                    "curr_hp": curr_ent.get("hp"),
                    "hp_change": round(curr_ent.get("hp", 0) - prev_ent.get("hp", 0), 1),
                })
                matched_prev.add(i)
                matched_curr.add(best_match)
    
    spawned = len(curr_entities) - len(matched_curr)
    despawned = len(prev_entities) - len(matched_prev)
    
    return {
        "tracked": tracked,
        "spawned": max(0, spawned),
        "despawned": max(0, despawned),
        "continuity_score": round(len(tracked) / max(len(prev_entities), len(curr_entities), 1), 2),
    }


def _detect_ui_changes(img_array, prev_ui_state=None):
    """Detect changes in UI elements (HP bars, status icons) using color segmentation.
    
    Returns a dict with detected UI state and changes. This helps agents quickly
    identify important gameplay events without parsing game state JSON.
    
    Detects:
    - HP bar changes (red/green regions)
    - Damage number pops (bright text regions)
    - Status effect icons (colored overlays)
    """
    if not CV2_AVAILABLE or img_array is None:
        return {}
    
    result = {
        "hp_bar_visible": False,
        "hp_bar_percent": None,
        "damage_numbers_detected": False,
        "status_effects_count": 0,
    }
    
    try:
        hsv = cv2.cvtColor(img_array, cv2.COLOR_BGR2HSV)
        
        lower_red = np.array([0, 70, 50])
        upper_red = np.array([15, 255, 255])
        mask1 = cv2.inRange(hsv, lower_red, upper_red)
        lower_red2 = np.array([160, 70, 50])
        upper_red2 = np.array([180, 255, 255])
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        red_mask = cv2.bitwise_or(mask1, mask2)
        
        lower_green = np.array([40, 70, 50])
        upper_green = np.array([80, 255, 255])
        green_mask = cv2.inRange(hsv, lower_green, upper_green)
        
        hp_regions = []
        for mask, color_name in [(red_mask, "red"), (green_mask, "green")]:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if 500 < area < 50000:
                    x, y, w, h = cv2.boundingRect(cnt)
                    aspect_ratio = w / float(h) if h > 0 else 0
                    if 2 < aspect_ratio < 20:
                        hp_regions.append((x, y, w, h, color_name))
                        if color_name in ("red", "green"):
                            result["hp_bar_visible"] = True
        
        if hp_regions:
            total_width = sum(r[2] for r in hp_regions)
            filled_width = sum(r[2] for r in hp_regions if r[4] == "green")
            if total_width > 0:
                result["hp_bar_percent"] = round(filled_width / total_width * 100, 1)
        
        lower_bright = np.array([0, 0, 200])
        upper_bright = np.array([20, 20, 255])
        bright_mask = cv2.inRange(hsv, lower_bright, upper_bright)
        
        bright_contours, _ = cv2.findContours(bright_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        small_bright_count = sum(1 for cnt in bright_contours if 50 < cv2.contourArea(cnt) < 2000)
        result["damage_numbers_detected"] = small_bright_count > 0
        
        lower_purple = np.array([120, 50, 50])
        upper_purple = np.array([160, 255, 255])
        purple_mask = cv2.inRange(hsv, lower_purple, upper_purple)
        
        purple_contours, _ = cv2.findContours(purple_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        icon_candidates = [cnt for cnt in purple_contours if 200 < cv2.contourArea(cnt) < 5000]
        result["status_effects_count"] = len(icon_candidates)
        
    except Exception:
        pass
    
    return result


def _cluster_similar_frames(screenshots_data, max_clusters=10):
    """Cluster visually similar frames by their wide perceptual hash (256-bit:
    Rust ProbeAnalyzer or OpenCV). Returns cluster count and, for each kept
    cluster, the index (into screenshots_data) of its first frame - agents
    open only those instead of near-duplicates. Needs no OpenCV itself."""
    valid = [(i, shot["phash_wide"]) for i, shot in enumerate(screenshots_data) if shot.get("phash_wide") is not None]
    if len(valid) < 2:
        return None
    clusters = []  # [[hashes...], representative_frame_index]
    for idx, h in valid:
        for cluster in clusters:
            if min(_hamming(h, ch) for ch in cluster[0]) <= VISUAL_SIMILARITY_HAMMING_THRESHOLD:
                cluster[0].append(h)
                break
        else:
            clusters.append([[h], idx])
    total = len(clusters)
    if total > max_clusters:
        clusters = sorted(clusters, key=lambda c: -len(c[0]))[:max_clusters]
    representatives = sorted(c[1] for c in clusters)
    return {
        "clusters": total,
        "representatives": representatives,
        "compression_ratio": round(len(valid) / max(len(representatives), 1), 2),
    }


def _hamming_cv2(a, b):
    """Compute Hamming distance between two integer hashes."""
    return bin(a ^ b).count("1")


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


_rust_probe = {"analyzer": None}


def _rust_analyzer():
    """rust_core.ProbeAnalyzer, настроенный из lua_content/probe_config.lua
    (слой контента; без Lua-бэкенда - дефолты Rust). Один экземпляр на прогон:
    он помнит предыдущий кадр для motion-метрик."""
    if not RUST_PROBE_AVAILABLE:
        return None
    if _rust_probe["analyzer"] is None:
        config = {}
        try:
            import lua_bridge
            table = lua_bridge.load(ROOT / "lua_content" / "probe_config.lua")
            for key in ("blank_frame_stddev_threshold", "visual_hash_bits", "hamming_threshold",
                        "motion_detection_threshold", "brightness_anomaly_threshold"):
                if table.get(key) is not None:
                    config[key] = table[key]
        except Exception:
            pass
        _rust_probe["analyzer"] = _RustProbeAnalyzer(config)
    return _rust_probe["analyzer"]


def analyze_screenshot(path, prev_frame_array=None, prev_brightness=None):
    """Visual sanity check that catches rendering failures game state alone
    can't: a crashed graphics context, an empty scene graph, or a window stuck
    on a loading/black screen all still leave game logic (HP, positions,
    combat) running fine, so state.jsonl alone would report a perfectly
    healthy run while the window shows nothing.

    Backends, best first (all optional, each adds to the same dict):
    - Rust (rust_core.ProbeAnalyzer, rust_core/src/probe): blank detection,
      256-bit perceptual hash (`phash_wide`), brightness, edge density and
      motion vs the previous frame - no Pillow/OpenCV needed;
    - Pillow: blank detection + cheap 64-bit `phash` (fallback);
    - OpenCV: UI colour segmentation, optical flow, 256-bit hash if Rust is absent.
    `prev_brightness` is the previous frame's brightness dict (flash/fade check)."""
    result = {}

    analyzer = _rust_analyzer()
    if analyzer is not None:
        try:
            r = analyzer.analyze_frame(Path(path).read_bytes())
            bright = r.get("brightness") or {}
            result.update({
                "pixel_stddev": round(bright.get("stddev", 0.0), 2),
                "likely_blank": bool(r.get("is_blank")),
                "brightness_stats": {"mean": round(bright.get("mean", 0.0), 2), "std": round(bright.get("stddev", 0.0), 2)},
                "edge_density": round(r.get("edge_density", 0.0), 4),
                "analysis_backend": "rust",
            })
            if r.get("perceptual_hash"):
                result["phash_wide"] = int(r["perceptual_hash"], 16)
            if r.get("motion"):
                result["motion_stats"] = r["motion"]
        except Exception as exc:
            result["rust_error"] = repr(exc)

    if PIL_AVAILABLE and "likely_blank" not in result:
        try:
            with Image.open(path) as img:
                gray = img.convert("L")
                stddev = ImageStat.Stat(gray).stddev[0]
                phash = _average_hash(gray)
            result.update({
                "pixel_stddev": round(stddev, 2),
                "likely_blank": stddev < BLANK_FRAME_STDDEV_THRESHOLD,
                "phash": phash,
                "analysis_backend": "pillow",
            })
        except Exception:
            pass

    if CV2_AVAILABLE:
        try:
            img_bgr = cv2.imread(str(path))
            if img_bgr is not None:
                result.setdefault("phash_wide", _perceptual_hash_cv2(img_bgr))
                ui_state = _detect_ui_changes(img_bgr)
                if ui_state:
                    result["ui_state"] = ui_state
                if "edge_density" not in result:
                    edges = cv2.Canny(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY), 50, 150)
                    result["edge_density"] = round(np.count_nonzero(edges) / edges.size, 4)
                if "brightness_stats" not in result:
                    b = _detect_brightness_anomalies(img_bgr)
                    result["brightness_stats"] = {"mean": b.get("brightness_mean", 0), "std": b.get("brightness_std", 0)}
                if prev_frame_array is not None and "motion_stats" not in result:
                    motion_stats = _compute_optical_flow(prev_frame_array, img_bgr)
                    if motion_stats:
                        result["motion_stats"] = motion_stats
        except Exception:
            pass

    # Flash/fade: сравнение со статистикой ПРЕДЫДУЩЕГО кадра (раньше сюда
    # передавался сам кадр-массив вместо его статистики - проверка не работала)
    cur = result.get("brightness_stats")
    if cur and prev_brightness:
        delta = abs(cur["mean"] - prev_brightness["mean"])
        if delta > BRIGHTNESS_ANOMALY_THRESHOLD:
            result["brightness_anomaly"] = {
                "anomaly": True, "delta": round(delta, 2),
                "type": "flash" if cur["mean"] > prev_brightness["mean"] else "fade",
            }
    return result


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
        self.errors = []  # ERROR+ only - any of these fails the run (see finish())

    def emit(self, record):
        line = self.format(record)
        self.records.append(line)
        if record.levelno >= logging.ERROR:
            self.errors.append(line)


TIMELINE_LINES_IN_SUMMARY = 80


def main():
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        # Windows + перенаправленный вывод (так его читает агент) = cp1252:
        # спарклайны и кириллица иначе роняют print()
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    if args.out:
        out_dir = Path(args.out).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        # tempfile.mkdtemp atomically creates a guaranteed-new directory - a
        # plain "dev_probe_output/<timestamp>/" name collides if two runs start
        # within the same second (mkdir(exist_ok=True) would then silently mix
        # both runs' frames/state.jsonl/summary.md together).
        base_dir = ROOT / "dev_probe_output"
        base_dir.mkdir(parents=True, exist_ok=True)
        out_dir = Path(tempfile.mkdtemp(prefix=f"{time.strftime('%Y%m%d_%H%M%S')}_", dir=str(base_dir)))

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

    scheduled_actions = sorted(args.action_at)  # already (float, key) tuples - validated by _parse_action_at
    fired_actions = set()

    if args.game_kwargs is not None:
        game_kwargs = args.game_kwargs  # already a dict - validated in parse_args()
    elif args.entry_module == "main" and args.game_class == "Game":
        game_kwargs = {"dev_mode": not args.full, "skip_menu": True}  # this project's convention
    else:
        game_kwargs = {}

    # Движок (звук выключен - иначе ALSA/OpenAL сыплют ~40 строк в каждый
    # прогон; болтовня Panda3D -> panda3d.log), режим рендера, fast-часы и
    # seed - всё в tools/probe_runtime.py, общем с agent_play.py.
    rt = runtime.boot_game(render=args.render, fast=args.fast, fps=args.fps, seed=args.seed,
                           notify_log=out_dir / "panda3d.log", entry_module=args.entry_module,
                           game_class=args.game_class, game_kwargs=game_kwargs)
    game = rt.game
    game_cls = type(game)
    clock = rt.now  # секунды игры: виртуальные при --fast, настенные иначе
    can_screenshot = rt.can_screenshot()

    def simulate_key(key, pressed):
        set_key = getattr(game, "_set_key", None)
        if set_key is None:
            print(f"(!) {game_cls.__name__} has no _set_key(key, pressed) - scheduled actions are a no-op here")
            return
        set_key(key, pressed)

    combat_events = []
    runtime.combat_recorder(game, clock, combat_events)
    kill_tracker = runtime.KillTracker()
    reported_kills = {"kills": 0, "despawns": 0}

    def track_kills(task):
        kill_tracker.update(game, clock())
        return task.cont

    game.taskMgr.add(track_kills, "dev_probe_kill_tracker", sort=100)

    state_log = (out_dir / "state.jsonl").open("w", encoding="utf-8")
    samples = []
    timeline = []
    labels = {}
    screenshots = []
    low_hp_since = None
    pinned_reported = False
    min_hp_seen = {"value": None, "t": None}
    sample_count = 0
    last_periodic_shot = -1e9
    death_reported = False
    death_event_count = 0
    run_state = {"completed": False, "last_elapsed": 0.0, "error": None, "exit_code": 0}
    entities_max = {"value": 0}
    finished = {"done": False}
    blank_frame_count = 0
    live_repeat = {"kind": None, "count": 0}
    last_phash = {"value": None}
    last_brightness = {"value": None}

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
        # kind interrupts the streak.
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
        # Подписи над юнитами нужны только на скриншотах
        if not can_screenshot:
            return
        for entity, is_player in get_entities(game):
            node = getattr(entity, "node", None)
            if not node:
                continue
            eid = entity_id_of(entity)
            if eid not in labels:
                z_offset = getattr(entity, "size", 1.0) * 1.9 + 0.55
                labels[eid] = EntityLabel(node, z_offset=z_offset)
            labels[eid].update(label_text(entity, is_player))

    # Track previous frame for motion detection and entity tracking
    prev_frame_array = None
    prev_entities_data = []
    entity_trajectories = []  # Accumulated entity lifecycle data

    def take_screenshot(elapsed, reason, kind=None):
        nonlocal blank_frame_count, prev_frame_array, prev_entities_data
        if not can_screenshot:
            return  # render=none: картинки нет, всё остальное (state/гипотезы) работает
        idx = len(screenshots) + 1
        shot_path = out_dir / f"frame_{idx:03d}.jpg"
        game.screenshot(namePrefix=Filename.from_os_specific(str(shot_path)), defaultFilename=False)

        visual = analyze_screenshot(shot_path, prev_frame_array=prev_frame_array,
                                    prev_brightness=last_brightness["value"])
        last_brightness["value"] = visual.get("brightness_stats")
        if CV2_AVAILABLE:
            try:
                prev_frame_array = cv2.imread(str(shot_path))
            except Exception:
                prev_frame_array = None

        cur_hash = visual.get("phash_wide", visual.get("phash"))
        if cur_hash is not None:
            # kind-based grouping is the main redundancy signal; the perceptual
            # hash is a pixel-level second opinion: a small Hamming distance
            # means the frame barely changed even if its `kind` differs.
            limit = VISUAL_SIMILARITY_HAMMING_THRESHOLD if "phash_wide" in visual else 4
            visual["visually_similar_to_previous"] = (
                last_phash["value"] is not None and _hamming(cur_hash, last_phash["value"]) <= limit
            )
            last_phash["value"] = cur_hash
        if visual.get("likely_blank"):
            blank_frame_count += 1
            log_event(
                elapsed,
                f"ANOMALY: {shot_path.name} looks blank/solid-color (pixel stddev="
                f"{visual['pixel_stddev']}) - rendering may be broken even though game state looks fine",
                level=1,
            )

        entities = get_entities(game)
        curr_entities_data = [
            {**entity_state(e, is_player), "screen_xy": world_to_screen(game, e.node)}
            for e, is_player in entities if getattr(e, "node", None)
        ]
        entity_tracking_result = None
        if prev_entities_data and curr_entities_data:
            entity_tracking_result = _track_entities_across_frames(prev_entities_data, curr_entities_data, None, None)
            if entity_tracking_result and entity_tracking_result.get("tracked"):
                entity_trajectories.append({
                    "t": round(elapsed, 2),
                    "tracked_count": len(entity_tracking_result["tracked"]),
                    "spawned": entity_tracking_result.get("spawned", 0),
                    "despawned": entity_tracking_result.get("despawned", 0),
                })
        prev_entities_data = curr_entities_data

        sidecar = {
            "t": round(elapsed, 2),
            "reason": reason,
            "screen_size": [game.win.getXSize(), game.win.getYSize()],
            **{k: v for k, v in visual.items() if k not in ("phash", "phash_wide")},
            "entities": curr_entities_data,
        }
        if entity_tracking_result:
            sidecar["entity_tracking"] = entity_tracking_result
        (out_dir / f"frame_{idx:03d}.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        # Визуальные метрики кладутся и в сам список скриншотов: раньше они
        # жили только в sidecar-файлах, и все агрегаты в finish() (кластеры,
        # keyframes, motion, damage numbers) всегда были нулями.
        screenshots.append({"name": shot_path.name, "reason": reason, "kind": kind, "t": elapsed,
                            **visual, "entity_tracking": entity_tracking_result or {}})
        log_event(elapsed, f"SCREENSHOT {shot_path.name} — {reason}", kind=kind)

    def sample(task):
        elapsed = clock()
        run_state["last_elapsed"] = elapsed
        try:
            return _sample_body(elapsed, task)
        except SystemExit:
            raise
        except Exception as exc:
            # Panda3D's task manager swallows plain Exceptions raised from a task
            # callback instead of letting them propagate - without this, a bug in
            # here would silently hang the game forever with no summary.md ever
            # written. sys.exit (unlike Exception) is NOT swallowed, so it reliably
            # reaches the try/finally around game.run() below.
            run_state["error"] = traceback.format_exc()
            log_event(elapsed, f"FATAL: sample() crashed: {exc!r}", level=0)
            sys.exit(1)

    def _sample_body(elapsed, task):
        nonlocal low_hp_since, pinned_reported, sample_count, last_periodic_shot, death_reported, death_event_count
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
        entities_max["value"] = max(entities_max["value"], len(entities))
        player = next((e for e, is_player in entities if is_player), None)

        # KillTracker (покадровый): враг, исчезнувший ЖИВЫМ (зачистка уровня),
        # - despawn, а не убийство, как раньше считалось
        for t, eid, etype in kill_tracker.kills[reported_kills["kills"]:]:
            log_event(elapsed, f"enemy killed: {etype} ...{eid[-8:]}")
        for t, eid, etype in kill_tracker.despawns[reported_kills["despawns"]:]:
            log_event(elapsed, f"enemy despawned alive: {etype} ...{eid[-8:]}")
        reported_kills["kills"], reported_kills["despawns"] = len(kill_tracker.kills), len(kill_tracker.despawns)

        state = runtime.sample_state(game, elapsed)
        samples.append(state)
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
            if is_dead:
                if not death_reported:
                    death_reported = True
                    death_event_count += 1
                    log_event(elapsed, "ANOMALY: player died", level=1)
                take_screenshot(elapsed, "player dead", kind="dead_screenshot")
                # Смерть залипающая (Character.is_defeated) - обнуляем pinned-таймер
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
            finish()
            sys.exit(run_state["exit_code"])
        return task.again

    def finish():
        # Called from _sample_body at the end AND from the try/finally around
        # game.run() - guarded, so it runs exactly once on every exit path:
        # normal completion, a crash, Escape or the window's close button.
        if finished["done"]:
            return
        finished["done"] = True
        state_log.close()

        final_player = next((e for e, is_player in get_entities(game) if is_player), None)
        player_id = entity_id_of(final_player) if final_player else analysis.player_id_of(samples)
        stats = analysis.combat_stats(combat_events, player_id)
        dmg_dealt, dmg_taken = stats["dealt"], stats["taken"]
        kill_count = len(kill_tracker.kills)
        with (out_dir / "combat.jsonl").open("w", encoding="utf-8") as f:
            for e in combat_events:
                f.write(json.dumps(e) + "\n")

        # "Completed" only means the timer ran out - the world can still be
        # empty or broken. Those runs must not read as OK.
        fail_reasons = []
        if entities_max["value"] == 0:
            fail_reasons.append("no entities seen (scene not loaded?)")
        if screenshots and blank_frame_count >= len(screenshots):
            fail_reasons.append(f"all {len(screenshots)} screenshots blank")
        if warning_collector.errors:
            fail_reasons.append(f"{len(warning_collector.errors)} ERROR log line(s)")

        if run_state["error"]:
            status = "CRASHED"
        elif run_state.get("completed"):
            status = "FAIL" if fail_reasons else "OK"
        else:
            status = "STOPPED EARLY"
        run_state["exit_code"] = {"OK": 0, "FAIL": 2}.get(status, 1)

        min_hp = min_hp_seen["value"] if min_hp_seen["value"] is not None else (final_player.health if final_player else None)
        min_hp_t = min_hp_seen["t"]
        end_hp = final_player.health if final_player else None

        # Categorized counts, not raw timestamped lines - a before/after diff
        # comparing these survives run-to-run timing jitter.
        event_counts = {
            "enemy_killed": kill_count,
            "enemy_despawned": len(kill_tracker.despawns),
            "anomaly_died": death_event_count,
            "anomaly_pinned": 1 if pinned_reported else 0,
            "anomaly_blank_frame": blank_frame_count,
            "warning": len(warning_collector.records),
        }
        screenshot_reason_counts = dict(Counter(s["kind"] or s["reason"] for s in screenshots))

        visual_analysis_summary = {}
        if screenshots:
            ui_events = sum(1 for s in screenshots if (s.get("ui_state") or {}).get("damage_numbers_detected"))
            hp_readings = sum(1 for s in screenshots if (s.get("ui_state") or {}).get("hp_bar_percent") is not None)
            edges = [s["edge_density"] for s in screenshots if s.get("edge_density") is not None]
            motion_frames = [s for s in screenshots if s.get("motion_stats")]
            ratios = [s["motion_stats"].get("motion_ratio", 0) for s in motion_frames]
            avg_motion_ratio = sum(ratios) / len(ratios) if ratios else 0.0
            visual_analysis_summary = {
                "backend": screenshots[0].get("analysis_backend"),
                "frames_with_damage_numbers": ui_events,
                "hp_bar_readings_count": hp_readings,
                "avg_edge_density": round(sum(edges) / len(edges), 4) if edges else None,
                "motion_analysis": {
                    "frames_with_motion_data": len(motion_frames),
                    "avg_motion_ratio": round(avg_motion_ratio, 4),
                    "high_motion_frames": sum(1 for r in ratios if r > 0.1),
                    "action_intensity": "high" if avg_motion_ratio > 0.15 else ("medium" if avg_motion_ratio > 0.05 else "low"),
                } if motion_frames else None,
                "brightness_anomalies": sum(1 for s in screenshots if s.get("brightness_anomaly")),
                "entity_tracking": {
                    "total_tracked_events": sum(t.get("tracked_count", 0) for t in entity_trajectories),
                    "total_spawned": sum(t.get("spawned", 0) for t in entity_trajectories),
                    "total_despawned": sum(t.get("despawned", 0) for t in entity_trajectories),
                    "tracking_samples": len(entity_trajectories),
                },
            }
            clustering_result = _cluster_similar_frames(screenshots)
            if clustering_result:
                visual_analysis_summary["frame_clustering"] = clustering_result

        analysis_ctx = {
            "kills": list(kill_tracker.kills), "duration": run_state["last_elapsed"],
            "errors": list(warning_collector.errors), "error_text": run_state["error"] or "\n".join(warning_collector.errors),
            "blank_frames": blank_frame_count, "screenshots": len(screenshots),
            "player_crit_chance": getattr(final_player, "critical_chance", None),
        }
        hyps = analysis.hypotheses(samples, combat_events, analysis_ctx)
        fc = analysis.forecast(samples, combat_events, analysis_ctx)

        repro = "python tools/dev_probe.py " + " ".join(shlex.quote(a) for a in sys.argv[1:])
        exact = args.fast and args.seed is not None

        summary_data = {
            "kind": "dev_probe",
            "status": status,
            "fail_reasons": fail_reasons,
            "entities_max": entities_max["value"],
            "error_count": len(warning_collector.errors),
            "seed": args.seed,
            "fast": args.fast,
            "render": args.render,
            "dev_map": not args.full,
            "duration_configured": args.duration,
            "elapsed": round(run_state["last_elapsed"], 2),
            "wall_s": round(rt.wall(), 2),
            "dmg_dealt": round(dmg_dealt, 2),
            "dmg_taken": round(dmg_taken, 2),
            "kill_count": kill_count,
            "despawn_count": len(kill_tracker.despawns),
            "hits": stats["hits"],
            "dodges": stats["dodges"],
            "crits": stats["crits"],
            "min_hp": round(min_hp, 2) if min_hp is not None else None,
            "min_hp_t": min_hp_t,
            "end_hp": round(end_hp, 2) if end_hp is not None else None,
            "pinned_reported": pinned_reported,
            "warning_count": len(warning_collector.records),
            "blank_frame_count": blank_frame_count,
            "sample_count": sample_count,
            "event_counts": event_counts,
            "screenshot_reason_counts": screenshot_reason_counts,
            "visual_analysis": visual_analysis_summary,
            "hypotheses": hyps,
            "forecast": fc,
            "kills_list": kill_tracker.kills,
            "analysis_backend": analysis.kernels.BACKEND,
            "repro": repro,
            "repro_exact": exact,
        }
        (out_dir / "summary.json").write_text(json.dumps(summary_data, indent=1, default=str), encoding="utf-8")
        (out_dir / "repro.sh").write_text(
            f"#!/bin/sh\n# {status}; {'exact replay (--fast + --seed)' if exact else 'approximate: add --fast --seed N for an exact replay'}\n{repro}\n",
            encoding="utf-8")

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
            baseline_path.write_text(json.dumps(summary_data, indent=1, default=str), encoding="utf-8")

        from probe_db import ingest_quietly
        db_err = ingest_quietly(out_dir.name, {
            "kind": "dev_probe", "dir": str(out_dir), "status": status, "seed": args.seed,
            "duration": round(run_state["last_elapsed"], 2), "fast": args.fast, "render": args.render,
            "errors": len(warning_collector.errors), "warnings": len(warning_collector.records),
            "crit_chance": getattr(final_player, "critical_chance", None),
        }, samples, combat_events, kill_tracker.kills, kill_tracker.despawns)

        hp_curve = analysis.sparkline([s["player"]["hp"] for s in samples if s.get("player")])
        shown_timeline = timeline[:TIMELINE_LINES_IN_SUMMARY]
        if len(timeline) > len(shown_timeline):
            (out_dir / "timeline.txt").write_text("\n".join(timeline), encoding="utf-8")
            shown_timeline.append(f"... {len(timeline) - len(shown_timeline)} more line(s) in timeline.txt")

        lines = [
            f"# Dev Probe Summary — {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Status: {status}" + (
                "" if status == "OK" else
                f" ({'; '.join(fail_reasons)})" if status == "FAIL" else
                f" (stopped at t={run_state['last_elapsed']:.1f}s of {args.duration}s configured"
                f"{' - see Crash traceback below' if status == 'CRASHED' else ' - Escape or window closed?'})"
            ),
            "",
            *(["## Errors (deduplicated)", *analysis.digest_log(warning_collector.errors, 10), ""]
              if warning_collector.errors else []),
            f"Config: duration={args.duration}s dev_map={not args.full} seed={args.seed} render={args.render} "
            f"fast={args.fast} actions={[f'{s}s:{k}' for s, k in scheduled_actions]} (wall {rt.wall():.1f}s)",
            "",
            "## Hypotheses (auto, rule-based - verify before fixing)",
            *analysis.format_hypotheses(hyps),
            "",
            "## Forecast",
            *analysis.format_forecast(fc),
            "",
            "## Timeline",
            *shown_timeline,
            "",
            "## Combat totals",
            f"attacks: {stats['attacks']} ({stats['hits']} hit, {stats['dodges']} dodged, {stats['crits']} critical)"
            + (f"; pipeline: {stats['misses']} missed, {stats['blocks']} blocked, {stats['resisted']} resisted, "
               f"{stats['armored']} soaked by armor, {stats['pierced']} armor pierced"
               if stats["misses"] or stats["blocks"] or stats["resisted"] or stats["pierced"] else ""),
            f"damage dealt by player: {dmg_dealt:.1f}" + (f"  by type: {stats['dealt_to_type']}" if stats["dealt_to_type"] else ""),
            f"damage taken by player: {dmg_taken:.1f}" + (f"  by type: {stats['taken_by_type']}" if stats["taken_by_type"] else ""),
            f"enemies killed: {kill_count} (+{len(kill_tracker.despawns)} despawned alive)",
            "",
        ]
        if final_player:
            p = final_player
            lines += [
                "## Player HP",
                f"curve: {hp_curve}",
                f"start: {p.max_health}/{p.max_health}  min: {min_hp:.1f} (at t={min_hp_t or 0.0:.1f}s)  "
                f"end: {p.health:.1f}/{p.max_health}",
                "",
            ]
        if baseline_diff_text is not None:
            lines += ["## vs baseline (tools/dev_probe_baseline.json)", baseline_diff_text, ""]
        if warning_collector.records:
            lines += ["## Warnings / errors (deduplicated, full text in game.log)",
                      *analysis.digest_log(warning_collector.records, 15), ""]
        if run_state["error"]:
            lines += ["## Crash traceback", "```", run_state["error"].rstrip(), "```", ""]

        # Consecutive same-`kind` screenshots collapse to first+last; frames the
        # perceptual-hash clustering marks as near-duplicates are skipped too.
        # Every raw frame_NNN.jpg/.json stays on disk untouched.
        representative_shots = []
        if screenshots:
            clustering = visual_analysis_summary.get("frame_clustering")
            keep = set(clustering["representatives"]) if clustering and len(screenshots) > 3 else None
            index_of = {id(s): i for i, s in enumerate(screenshots)}
            lines.append("## Screenshots (each has a matching frame_NNN.json with per-entity screen_xy pixels)")
            for group in _group_consecutive_by_kind(screenshots):
                if keep is not None:
                    group = [g for g in group if index_of[id(g)] in keep] or group[:1]
                if len(group) <= 2:
                    for s in group:
                        lines.append(f"- {s['name']} — {s['reason']}")
                    representative_shots.extend(group)
                else:
                    first, last = group[0], group[-1]
                    lines.append(f"- {first['name']} — {first['reason']}")
                    lines.append(f"  ... {len(group) - 2} more '{first['kind']}' frame(s) omitted (same situation) ...")
                    lines.append(f"- {last['name']} — {last['reason']}")
                    representative_shots.extend([first, last])
            if clustering:
                lines.append(f"- visual clustering: {clustering['clusters']} distinct looks among {len(screenshots)} "
                             f"frames ({clustering['compression_ratio']}x redundancy)")
        elif not can_screenshot:
            lines.append("## Screenshots: none (render=none - logic-only run; use --render offscreen for images)")

        # contact_sheet.jpg is the one image worth Read-ing for a routine "does
        # this look sane" pass; timelapse.gif is a human scrubbing convenience.
        contact_sheet_name = _build_contact_sheet(out_dir, representative_shots)
        timelapse_name = _build_timelapse_gif(out_dir, [s["name"] for s in screenshots])
        lines += [
            "",
            f"Contact sheet (open this first for a whole-run visual check): {contact_sheet_name}" if contact_sheet_name
            else "Contact sheet: skipped (no screenshots or Pillow missing)",
            f"Timelapse GIF (human scrubbing convenience): {timelapse_name}" if timelapse_name
            else "Timelapse GIF: skipped",
            "",
            f"Raw per-tick state: state.jsonl ({sample_count} samples); combat events: combat.jsonl",
            "Full game log: game.log; Panda3D's own engine output: panda3d.log",
            f"Repro ({'exact' if exact else 'approximate - add --fast --seed N for exact'}): {repro}",
            f"DB analytics: python tools/probe_db.py stats {out_dir.name}  (why / predict / compare / trend)"
            + (f"  (!) {db_err}" if db_err else ""),
        ]
        (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

        # Always printed regardless of --verbosity: one grep-able line.
        print(
            f"RESULT status={status} kills={kill_count} dmg_dealt={dmg_dealt:.1f} "
            f"dmg_taken={dmg_taken:.1f} warnings={len(warning_collector.records)} "
            f"blank_frames={blank_frame_count} pinned={pinned_reported} "
            f"entities_max={entities_max['value']} errors={len(warning_collector.errors)} "
            f"elapsed={run_state['last_elapsed']:.1f}s wall={rt.wall():.1f}s"
            + (f" reasons=\"{'; '.join(fail_reasons)}\"" if fail_reasons else "")
        )
        top = [h for h in hyps if h["severity"] in ("high", "medium")][:2]
        for h in top:
            print(f"  hypothesis [{h['severity']}] {h['id']}: {h['claim']}")
        if baseline_diff_text is not None:
            tag = "CHANGED" if baseline_changed else "no change"
            print(f"vs baseline: {tag} (see '## vs baseline' in summary.md for details)")
        if args.save_baseline:
            print(f"Saved this run as the new baseline: {baseline_path}")
        if status != "OK":
            print(f"repro: {repro}")
        print(f"Read {out_dir / 'summary.md'} for the full story.")

    try:
        game.taskMgr.doMethodLater(args.sample_interval, sample, "dev_probe_sample")
        game.run()
    finally:
        finish()


if __name__ == "__main__":
    main()
