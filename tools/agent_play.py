#!/usr/bin/env python3
"""Агент играет в AI-EVOLVE теми же действиями, что и живой игрок.

Героем управляет ИИ игры; игрок - "дирижёр": спавнит врага/ловушку/сундук
рядом с героем (1/2/3), форсирует атаку (space) и взаимодействует (e).
Этот инструмент даёт агенту ровно эти рычаги (список клавиш - в
lua_content/dev_tools.lua: agent.player_keys), без god-mode, плюс
наблюдение и проверки - и всё это без окна и в ускоренном времени:

- render=none (по умолчанию): без графики и OpenGL, 60 с игры ~ 0.3 с;
- fixed-step виртуальное время (tools/probe_runtime.py): при одном --seed
  (по умолчанию 1) прогон ПОБИТОВО повторяем - любой FAIL воспроизводится
  командой из строки "repro:" в выводе;
- инварианты мира на каждом кадре (tools/probe_invariants.py: HP > max,
  "жив при HP 0", NaN, выход за карту, мёртвые враги в сцене...) - любое
  нарушение = FAIL с точным t (отключить: --no-invariants);
- вывод - только то, о чём спросили (observe/expect/until), и одна строка
  RESULT в конце + до 3 гипотез и прогноз. Детали - в <out>/session.json и
  в БД прогонов (tools/probe_db.py).

Команды (через ';' или с новой строки, '#' - комментарий):
    spawn enemy|trap|chest|boss [xN]   клавиши 1/2/3/4 (N раз); boss - босс текущего акта
    attack [xN]                   space: удар по ближайшему врагу в радиусе
    interact [SEC]                удерживать e SEC секунд (по умолчанию 0.5)
    wait SEC                      прокрутить игру на SEC секунд игрового времени
    until COND [max SEC]          крутить, пока COND не станет истинным (max 60 по умолчанию)
    observe                       одна строка состояния
    enemies                       ближайшие враги (тип, дистанция, HP)
    expect COND                   проверка: PASS/FAIL (FAIL -> код выхода 1)
    report                        гипотезы + прогноз на текущий момент
    story [N]                     последние N решений ИИ героя (смены ai_state; дребезг A<->B схлопнут)
    screenshot [NAME]             PNG в каталог прогона (только --render offscreen|window)

COND: `alive`, `dead`, `not alive`, `NAME OP NUMBER` (OP: < <= > >= == !=),
соединённые `and`/`or` (and сильнее). Имена: t hp max_hp hp_pct lvl xp kills
despawns enemies nearest dealt taken attacks hits crits dodges traps chests.

Примеры:
    python tools/agent_play.py "spawn enemy x3; until kills>=3 or dead max 90; observe; expect alive"
    python tools/agent_play.py --list-scenarios ; python tools/agent_play.py --scenario swarm
    python tools/agent_play.py --script scenario.play --seed 7
    python tools/agent_play.py --serve --port 8765      # пошаговая игра по HTTP:
        curl -s localhost:8765/do -d 'spawn enemy; wait 5; observe'
        curl -s localhost:8765/report ; curl -s -X POST localhost:8765/quit
    Игра стоит на паузе между запросами: время идёт только в wait/until/spawn.
"""
import argparse
import json
import logging
import math
import queue
import re
import shlex
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_analysis as analysis  # noqa: E402
import probe_runtime as runtime  # noqa: E402
from probe_invariants import InvariantChecker  # noqa: E402
from probe_settings import ROOT, qa_settings, section  # noqa: E402

PRESS_FRAMES = 2  # держим клавишу 2 кадра: сцена ловит нажатие по фронту


class ScriptError(ValueError):
    pass


# ---------------------------------------------------------------- conditions

_COND_TERM = re.compile(r"^(not\s+)?([a-z_]+)(?:\s*(<=|>=|==|!=|<|>)\s*(-?\d+(?:\.\d+)?))?$")
METRIC_NAMES = {"t", "hp", "max_hp", "hp_pct", "lvl", "xp", "kills", "despawns", "enemies", "nearest", "dealt",
                "taken", "attacks", "hits", "crits", "dodges", "traps", "chests", "alive", "dead"}


def parse_condition(text):
    """'kills>=3 or dead' -> [[term, ...], ...] (OR из AND-групп)."""
    text = text.replace("|", " or ").replace("&", " and ").strip()
    if not text:
        raise ScriptError("empty condition")
    groups = []
    for group in re.split(r"\s+or\s+", text):
        terms = []
        for raw in re.split(r"\s+and\s+", group.strip()):
            m = _COND_TERM.match(raw.strip())
            if not m or m.group(2) not in METRIC_NAMES:
                raise ScriptError(f"bad condition term {raw!r} (names: {', '.join(sorted(METRIC_NAMES))})")
            neg, name, op, num = m.groups()
            if op is None and name not in ("alive", "dead"):
                raise ScriptError(f"{name!r} needs a comparison, e.g. {name}>=1")
            terms.append((bool(neg), name, op, float(num) if num is not None else None))
        groups.append(terms)
    return groups


_OPS = {"<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b}


def eval_condition(groups, metrics):
    def term(neg, name, op, num):
        value = metrics.get(name)
        if op is None:
            result = bool(value)
        elif value is None:
            result = False  # nearest=None (нет врагов): любое сравнение ложно
        else:
            result = _OPS[op](value, num)
        return result != neg
    return any(all(term(*t) for t in g) for g in groups)


# ---------------------------------------------------------------- script

def parse_script(text):
    """-> [(verb, args_dict, source_text)] с валидацией ДО запуска игры."""
    agent_cfg = section("agent")
    keys = agent_cfg["player_keys"]
    max_wait, max_repeat = agent_cfg["max_wait_per_command"], agent_cfg["max_repeat"]
    commands = []
    for raw in re.split(r"[;\n]", text):
        src = raw.split("#", 1)[0].strip()
        if not src:
            continue
        verb, _, rest = src.partition(" ")
        rest = rest.strip()
        verb = verb.lower()

        def repeat(tokens):
            n = 1
            if tokens and re.fullmatch(r"x\d+", tokens[-1]):
                n = int(tokens.pop()[1:])
            if not 1 <= n <= max_repeat:
                raise ScriptError(f"{src!r}: repeat must be 1..{max_repeat}")
            return n

        if verb == "spawn":
            tokens = rest.split()
            n = repeat(tokens)
            if len(tokens) != 1 or tokens[0] not in ("enemy", "trap", "chest", "boss"):
                raise ScriptError(f"{src!r}: expected 'spawn enemy|trap|chest|boss [xN]'")
            commands.append(("press", {"key": keys[tokens[0]], "times": n, "what": tokens[0]}, src))
        elif verb == "attack":
            tokens = rest.split()
            n = repeat(tokens)
            if tokens:
                raise ScriptError(f"{src!r}: expected 'attack [xN]'")
            commands.append(("press", {"key": keys["attack"], "times": n, "what": "attack"}, src))
        elif verb == "interact":
            sec = float(rest) if rest else 0.5
            commands.append(("hold", {"key": keys["interact"], "seconds": sec}, src))
        elif verb == "wait":
            try:
                sec = float(rest)
            except ValueError:
                raise ScriptError(f"{src!r}: expected 'wait SECONDS'") from None
            if not 0 < sec <= max_wait:
                raise ScriptError(f"{src!r}: wait must be in (0, {max_wait}]")
            commands.append(("wait", {"seconds": sec}, src))
        elif verb == "until":
            m = re.match(r"^(.*?)(?:\s+max\s+(\d+(?:\.\d+)?))?$", rest)
            cond, limit = m.group(1), float(m.group(2) or 60)
            if not 0 < limit <= max_wait:
                raise ScriptError(f"{src!r}: max must be in (0, {max_wait}]")
            commands.append(("until", {"cond": parse_condition(cond), "text": cond.strip(), "max": limit}, src))
        elif verb == "expect":
            commands.append(("expect", {"cond": parse_condition(rest), "text": rest}, src))
        elif verb in ("observe", "enemies", "report"):
            commands.append((verb, {}, src))
        elif verb == "story":
            commands.append(("story", {"limit": int(rest) if rest.isdigit() else 12}, src))
        elif verb == "screenshot":
            name = rest or None
            if name and not re.fullmatch(r"[\w.-]+", name):
                raise ScriptError(f"{src!r}: screenshot name may contain only letters, digits, '.', '-', '_'")
            commands.append(("screenshot", {"name": name}, src))
        else:
            raise ScriptError(f"unknown command {verb!r} in {src!r}")
    return commands


# ---------------------------------------------------------------- session

class ErrorCollector(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.warnings, self.errors = [], []

    def emit(self, record):
        line = self.format(record)
        self.warnings.append(line)
        if record.levelno >= logging.ERROR:
            self.errors.append(line)


class PlaySession:
    def __init__(self, args, out_dir):
        self.args = args
        self.out_dir = out_dir
        self.agent_cfg = section("agent")
        self.transcript = []   # [{"cmd", "out"}]
        self.expects = []      # [(text, passed, t)]
        self.samples, self.events = [], []
        self.fatal = None
        self._setup_logging()
        self.rt = runtime.boot_game(render=args.render, fast=True, fps=args.fps, seed=args.seed,
                                    notify_log=out_dir / "panda3d.log")
        self.game = self.rt.game
        self.kills = runtime.KillTracker()
        self.story = []        # смены ai_state героя: (t, from, to, hp, nearest_type, nearest_dist)
        self._last_ai = None
        inv_cfg = qa_settings()["invariants"]
        self.invariants = InvariantChecker(inv_cfg) if inv_cfg["enabled"] and not args.no_invariants else None
        runtime.combat_recorder(self.game, self.rt.now, self.events)
        self._state_log = (out_dir / "state.jsonl").open("w", encoding="utf-8")
        self.game.taskMgr.add(self._per_frame, "agent_play_frame", sort=100)
        self.game.taskMgr.doMethodLater(args.sample_interval, self._sample_task, "agent_play_sample")
        self._record_sample()

    def _setup_logging(self):
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
        self.collector = ErrorCollector()
        self.collector.setFormatter(fmt)
        file_handler = logging.FileHandler(self.out_dir / "game.log", encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
        root.addHandler(self.collector)
        root.setLevel(logging.INFO)

    # --- game-side tasks
    def _per_frame(self, task):
        now = self.rt.now()
        self.kills.update(self.game, now)
        player = getattr(self.scene(), "player", None)
        ai = getattr(player, "ai_state", None) if player is not None else None
        if ai != self._last_ai:
            dist, enemy = runtime.nearest_enemy(self.game)
            self.story.append((round(now, 2), self._last_ai, ai, round(player.health, 1) if player else None,
                               runtime.entity_type_of(enemy, False) if enemy is not None else None,
                               round(dist, 1) if dist is not None else None))
            self._last_ai = ai
        if self.invariants is not None:
            self.invariants.check(self.game, now)
        return task.cont

    def _record_sample(self):
        s = runtime.sample_state(self.game, self.rt.now())
        if self.samples and self.samples[-1]["t"] == s["t"]:
            return  # report сразу после сэмпла того же кадра
        self.samples.append(s)
        self._state_log.write(json.dumps(s, ensure_ascii=False) + "\n")

    def _sample_task(self, task):
        self._record_sample()
        return task.again

    # --- state
    def scene(self):
        return runtime.get_scene(self.game)

    def metrics(self):
        scene = self.scene()
        player = getattr(scene, "player", None) if scene else None
        pid = runtime.entity_id_of(player) if player else None
        stats = analysis.combat_stats(self.events, pid)
        dist, _ = runtime.nearest_enemy(self.game)
        created = getattr(scene, "player_created_objects", []) if scene else []
        names = [o.getName() for o in created if hasattr(o, "getName") and not o.isEmpty()]
        alive = bool(player and player.is_alive())
        return {
            "t": round(self.rt.now(), 2),
            "hp": round(player.health, 1) if player else None,
            "max_hp": player.max_health if player else None,
            "hp_pct": round(100 * player.health / player.max_health, 1) if player else None,
            "lvl": getattr(player, "level", None), "xp": getattr(player, "experience", None),
            "alive": alive, "dead": not alive,
            "kills": len(self.kills.kills), "despawns": len(self.kills.despawns),
            "enemies": len(getattr(scene, "enemies", []) if scene else []),
            "nearest": round(dist, 1) if dist is not None else None,
            "dealt": stats["dealt"], "taken": stats["taken"], "attacks": stats["attacks"],
            "hits": stats["hits"], "crits": stats["crits"], "dodges": stats["dodges"],
            "traps": names.count("trap"), "chests": names.count("chest"),
            "ai": getattr(player, "ai_state", None),
            "pos": (round(player.x, 1), round(player.y, 1)) if player else None,
        }

    def observe_line(self):
        m = self.metrics()
        if m["hp"] is None:
            return f"t={m['t']} no hero in scene"
        near = f"{m['nearest']}u" if m["nearest"] is not None else "-"
        return (f"t={m['t']} hero {'ALIVE' if m['alive'] else 'DEAD'} hp={m['hp']:.0f}/{m['max_hp']:.0f} "
                f"lvl={m['lvl']} xp={m['xp']:.0f} ai={m['ai']} pos={m['pos']} | enemies={m['enemies']} "
                f"nearest={near} | kills={m['kills']} dealt={m['dealt']:.0f} taken={m['taken']:.0f} "
                f"| traps={m['traps']} chests={m['chests']}")

    def story_lines(self, limit=12):
        """Сжатая история решений ИИ: повторяющийся дребезг A<->B - одной строкой."""
        items, i = [], 0
        tr = self.story
        while i < len(tr):
            j = i
            while j + 1 < len(tr) and tr[j + 1][1] == tr[j][2] and tr[j + 1][2] == tr[j][1]:
                j += 1
            if j - i >= 3:
                items.append(f"t={tr[i][0]}..{tr[j][0]} {tr[i][1]}<->{tr[i][2]} flapping x{j - i + 1} (hp {tr[j][3]})")
            else:
                for t, a, b, hp, et, d in tr[i:j + 1]:
                    near = f", nearest {et} {d}u" if et else ""
                    items.append(f"t={t} {a or 'start'} -> {b} (hp {hp}{near})")
            i = j + 1
        shown = items[-limit:]
        if len(items) > len(shown):
            shown.insert(0, f"... {len(items) - len(shown)} earlier decision(s) in session.json")
        return shown or ["no AI decisions recorded"]

    def enemies_lines(self):
        scene = self.scene()
        player = getattr(scene, "player", None) if scene else None
        if player is None:
            return ["no hero"]
        rows = sorted(((math.hypot(e.x - player.x, e.y - player.y), e) for e in getattr(scene, "enemies", [])),
                      key=lambda r: r[0])
        n = self.agent_cfg["observe_nearest"]
        out = [f"{runtime.entity_type_of(e, False)} d={d:.1f} hp={e.health:.0f}/{e.max_health:.0f} "
               f"lvl={getattr(e, 'level', '?')}" for d, e in rows[:n]]
        if len(rows) > n:
            out.append(f"... +{len(rows) - n} farther")
        return out or ["no enemies"]

    def analysis_ctx(self):
        player = getattr(self.scene(), "player", None)
        return {"kills": list(self.kills.kills), "duration": self.rt.now(),
                "errors": list(self.collector.errors), "error_text": "\n".join(self.collector.errors),
                "player_crit_chance": getattr(player, "critical_chance", None)}

    def report_lines(self, limit=3):
        self._record_sample()
        ctx = self.analysis_ctx()
        hyps = analysis.hypotheses(self.samples, self.events, ctx)
        fc = analysis.forecast(self.samples, self.events, ctx)
        hp = [s["player"]["hp"] for s in self.samples if s.get("player")]
        return ([f"HP {analysis.sparkline(hp)}", "hypotheses:", *analysis.format_hypotheses(hyps, limit),
                 "forecast:", *analysis.format_forecast(fc)], hyps, fc)

    # --- actions
    def _step(self, frames):
        self.rt.step(frames)

    def press(self, key, times):
        for _ in range(times):
            self.game._set_key(key, True)
            self._step(PRESS_FRAMES)
            self.game._set_key(key, False)
            self._step(PRESS_FRAMES)

    def run_command(self, verb, a, src):
        out = []
        if verb == "press":
            self.press(a["key"], a["times"])
        elif verb == "hold":
            self.game._set_key(a["key"], True)
            self.rt.advance(a["seconds"])
            self.game._set_key(a["key"], False)
            self._step(1)
        elif verb == "wait":
            self.rt.advance(a["seconds"])
        elif verb == "until":
            start = self.rt.now()
            met = eval_condition(a["cond"], self.metrics()) or self.rt.advance(
                a["max"], stop=lambda: eval_condition(a["cond"], self.metrics()))
            waited = self.rt.now() - start
            out.append(f"until {a['text']}: " + (f"met at t={self.rt.now():.1f} (+{waited:.1f}s)" if met
                                                  else f"NOT met after {waited:.0f}s (t={self.rt.now():.1f})"))
        elif verb == "observe":
            out.append(self.observe_line())
        elif verb == "enemies":
            out.extend(self.enemies_lines())
        elif verb == "expect":
            m = self.metrics()
            ok = eval_condition(a["cond"], m)
            self.expects.append((a["text"], ok, m["t"]))
            if not ok:
                shown = {k: m[k] for k in METRIC_NAMES if k in m and k in a["text"]}
                out.append(f"FAIL expect {a['text']} at t={m['t']} ({', '.join(f'{k}={v}' for k, v in shown.items())})")
            elif self.args.verbose:
                out.append(f"PASS expect {a['text']}")
        elif verb == "report":
            out.extend(self.report_lines()[0])
        elif verb == "story":
            out.extend(self.story_lines(a["limit"]))
        elif verb == "screenshot":
            out.append(self.screenshot(a["name"]))
        self.transcript.append({"cmd": src, "t": round(self.rt.now(), 2), "out": out})
        return out

    def screenshot(self, name):
        if not self.rt.can_screenshot():
            return "screenshot skipped: --render none has no framebuffer (use --render offscreen)"
        from panda3d.core import Filename
        path = self.out_dir / f"{name or f'shot_{len(self.transcript) + 1:03d}'}.png"
        self.game.graphicsEngine.renderFrame()
        self.game.screenshot(namePrefix=Filename.from_os_specific(str(path)), defaultFilename=False)
        return f"screenshot {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"

    def execute(self, commands):
        """Выполнить список команд; возвращает строки вывода. Падение игры -> fatal."""
        lines = []
        for verb, a, src in commands:
            if self.fatal:
                break
            try:
                lines.extend(self.run_command(verb, a, src))
            except SystemExit:
                self.fatal = f"game called sys.exit() during {src!r}"
            except Exception as exc:
                tb = traceback.format_exc()
                self.fatal = f"{src!r} crashed: {exc!r} at {analysis.error_location(tb) or '?'}"
                (self.out_dir / "crash.txt").write_text(tb, encoding="utf-8")
            if self.fatal:
                lines.append(f"FATAL {self.fatal}")
        return lines

    # --- finish
    def finish(self, script_text):
        report, hyps, fc = self.report_lines(limit=3)
        self._state_log.close()
        m = self.metrics()
        failed = [e for e in self.expects if not e[1]]
        violations = self.invariants.report() if self.invariants is not None else []
        status = "CRASHED" if self.fatal else ("FAIL" if failed or self.collector.errors or violations else "OK")
        run_id = self.out_dir.name
        repro = (f"python tools/agent_play.py --seed {self.args.seed} --render {self.args.render} "
                 f"--fps {self.args.fps} {shlex.quote(script_text)}")
        session = {
            "kind": "agent_play", "status": status, "seed": self.args.seed, "render": self.args.render,
            "fps": self.args.fps, "fast": True, "script": script_text, "transcript": self.transcript,
            "expects": [{"cond": c, "passed": ok, "t": t} for c, ok, t in self.expects],
            "final": m, "errors": self.collector.errors[:20], "warning_count": len(self.collector.warnings),
            "kills_list": self.kills.kills, "despawns_list": self.kills.despawns,
            "hypotheses": hyps, "forecast": fc, "fatal": self.fatal, "repro": repro,
            "invariants": violations,
            "story": self.story,
            "wall_s": round(self.rt.wall(), 2), "analysis_backend": analysis.kernels.BACKEND,
        }
        (self.out_dir / "session.json").write_text(json.dumps(session, indent=1, default=str), encoding="utf-8")
        with (self.out_dir / "combat.jsonl").open("w", encoding="utf-8") as f:
            for e in self.events:
                f.write(json.dumps(e) + "\n")
        (self.out_dir / "repro.sh").write_text(f"#!/bin/sh\n# {status}: {run_id}\n{repro}\n", encoding="utf-8")

        from probe_db import ingest_quietly
        db_err = ingest_quietly(run_id, {
            "kind": "agent_play", "dir": str(self.out_dir), "status": status, "seed": self.args.seed,
            "duration": m["t"], "fast": True, "render": self.args.render, "errors": len(self.collector.errors),
            "warnings": len(self.collector.warnings), "crit_chance": getattr(getattr(self.scene(), "player", None),
                                                                              "critical_chance", None),
        }, self.samples, self.events, self.kills.kills, self.kills.despawns)

        passed = sum(1 for e in self.expects if e[1])
        lines = [
            f"RESULT status={status} t={m['t']}s hp={m['hp']}/{m['max_hp']} alive={m['alive']} lvl={m['lvl']} "
            f"kills={m['kills']} dealt={m['dealt']} taken={m['taken']} expects={passed}/{len(self.expects)} "
            f"errors={len(self.collector.errors)} invariants={len(violations)} wall={self.rt.wall():.2f}s",
        ]
        if violations:
            lines += self.invariants.lines()[:8]
        if self.collector.errors:
            lines += ["errors (deduped):", *(f"  {line}" for line in analysis.digest_log(self.collector.errors, 5))]
        if status != "OK" or self.args.verbose:
            lines += report
        else:  # OK: кривая HP, только важные гипотезы и прогноз-вывод
            important = [h for h in hyps if h["severity"] in ("high", "medium")]
            lines += [report[0], *(["hypotheses:", *analysis.format_hypotheses(important, 3)] if important else []),
                      *[ln for ln in report if ln.startswith("- outlook")]]
        if status != "OK":
            lines.append(f"repro: {repro}")
        if db_err:
            lines.append(f"(!) {db_err}")
        lines.append(f"details: {self.out_dir.relative_to(ROOT) if self.out_dir.is_relative_to(ROOT) else self.out_dir}"
                     f"/session.json | python tools/probe_db.py stats {run_id}")
        return status, lines

    def close(self):
        self.rt.close()


# ---------------------------------------------------------------- serve mode

def serve(session, port):
    """Пошаговая игра по HTTP. Panda3D крутится только в главном потоке,
    HTTP-потоки лишь кладут запросы в очередь и ждут ответ."""
    inbox = queue.Queue()
    transcript_text = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _reply(self, text, code=200):
            body = (text + "\n").encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _ask(self, kind, payload=""):
            box = queue.Queue(maxsize=1)
            inbox.put((kind, payload, box))
            code, text = box.get()
            self._reply(text, code)

        def do_GET(self):
            route = self.path.split("?")[0]
            if route in ("/observe", "/report", "/enemies", "/story"):
                self._ask(route[1:])
            else:
                self._reply(__doc__.split("Примеры:")[0].strip(), 200 if route == "/" else 404)

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
            route = self.path.split("?")[0]
            if route == "/do":
                self._ask("do", body)
            elif route == "/quit":
                self._ask("quit")
            else:
                self._reply("unknown route (POST /do, POST /quit, GET /observe|/report|/enemies)", 404)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"agent_play serving on http://127.0.0.1:{port}  (POST /do 'wait 5; observe' | GET /observe | "
          f"GET /report | POST /quit) - game is paused between requests", flush=True)
    status = "OK"
    try:
        while True:
            kind, payload, box = inbox.get()
            try:
                if kind == "quit":
                    status, lines = session.finish("\n".join(transcript_text))
                    box.put((200, "\n".join(lines)))
                    break
                if kind == "do":
                    commands = parse_script(payload)
                    transcript_text.append(payload.strip())
                    lines = session.execute(commands)
                    box.put((200, "\n".join(lines) if lines else f"ok t={session.rt.now():.1f}"))
                else:
                    cmd = [(kind, {}, kind)]
                    box.put((200, "\n".join(session.execute(cmd))))
            except ScriptError as exc:
                box.put((400, f"script error: {exc}"))
            except Exception as exc:
                box.put((500, f"internal error: {exc!r}"))
    finally:
        server.shutdown()
    return status


# ---------------------------------------------------------------- main

def parse_args(argv=None):
    rt_cfg = section("runtime")
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__.split("\n\n", 2)[2])
    parser.add_argument("script", nargs="?", help="inline commands separated by ';'")
    parser.add_argument("--script", dest="script_file", help="file with one command per line")
    parser.add_argument("--scenario", help="run a named scenario template from lua_content/qa.lua (script + seed)")
    parser.add_argument("--list-scenarios", action="store_true", help="print the scenario templates and exit")
    parser.add_argument("--serve", action="store_true", help="turn-based HTTP control instead of a script")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (default 1, or the scenario's seed)")
    parser.add_argument("--render", choices=runtime.RENDER_MODES, default=rt_cfg["render"],
                        help="none (default, no GPU, fastest) | offscreen (screenshots, needs OpenGL) | window")
    parser.add_argument("--fps", type=int, default=rt_cfg["fps"], help="fixed simulation step, frames per game second")
    parser.add_argument("--sample-interval", type=float, default=rt_cfg["sample_interval"])
    parser.add_argument("--out", default=None, help="output dir (default dev_probe_output/play_<time>_xxxx)")
    parser.add_argument("--verbose", "-v", action="store_true", help="print PASS lines and the full report")
    parser.add_argument("--no-invariants", action="store_true", help="skip per-frame world invariant checks")
    args = parser.parse_args(argv)
    scenarios = {sc["name"]: sc for sc in qa_settings()["scenarios"]}
    if args.list_scenarios:
        return args
    if args.scenario:
        if args.scenario not in scenarios:
            parser.error(f"unknown scenario {args.scenario!r}; known: {', '.join(scenarios)}")
        sc = scenarios[args.scenario]
        args.script = args.script or sc["script"]
        args.seed = sc["seed"] if args.seed is None else args.seed
    if args.seed is None:
        args.seed = 1
    if not args.serve and not (args.script or args.script_file):
        parser.error("give a script (inline or --script FILE), --scenario NAME or --serve")
    return args


def main(argv=None):
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        # Windows + перенаправленный вывод (так его читает агент) = cp1252:
        # спарклайны и кириллица иначе роняют print()
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    if args.list_scenarios:
        for sc in qa_settings()["scenarios"]:
            print(f"{sc['name']:16s} seed={sc['seed']:<3} {sc['script']}")
        return 0
    script_text = ""
    if not args.serve:
        script_text = Path(args.script_file).read_text(encoding="utf-8") if args.script_file else args.script
        try:
            commands = parse_script(script_text)  # ошибки скрипта - до запуска игры
        except ScriptError as exc:
            print(f"script error: {exc}")
            return 2

    if args.out:
        out_dir = Path(args.out).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        base = ROOT / "dev_probe_output"
        base.mkdir(parents=True, exist_ok=True)
        out_dir = Path(tempfile.mkdtemp(prefix=f"play_{time.strftime('%Y%m%d_%H%M%S')}_", dir=base))

    session = PlaySession(args, out_dir)
    try:
        if args.serve:
            status = serve(session, args.port)
        else:
            for line in session.execute(commands):
                print(line)
            status, lines = session.finish(script_text)
            print("\n".join(lines))
    finally:
        session.close()
    return {"OK": 0, "FAIL": 1}.get(status, 3)


if __name__ == "__main__":
    sys.exit(main())
