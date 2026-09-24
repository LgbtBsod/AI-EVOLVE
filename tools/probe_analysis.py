#!/usr/bin/env python3
"""Анализ прогона без картинок и без чтения сырых данных агентом.

Оркестрация над общим форматом данных (state.jsonl-сэмплы + боевые события
+ немного контекста) - её зовут dev_probe.py, agent_play.py и probe_db.py,
поэтому вывод одинаковый, где бы прогон ни случился. Разделение слоёв:
  - циклы по сэмплам/событиям/строкам лога -> tools/probe_kernels.py
    (rust_core.RunAnalytics или Python-двойник);
  - пороги правил -> lua_content/dev_tools.lua (секция analysis);
  - здесь - только решения и формулировки для агента.

- hypotheses(): правила "симптом -> вероятная причина -> куда смотреть в
  коде" для ЭТОГО проекта (файлы src/..., а не абстрактные советы). Каждая
  гипотеза несёт evidence - цифры, на которых она основана.
- forecast(): прогнозы линейной экстраполяцией (с указанием окна): когда
  герой умрёт при текущем темпе урона, растёт ли давление врагов, время до
  следующего уровня, средний TTK по типам врагов.
- sparkline(): кривая HP в ~24 символа вместо сотни строк JSON.
- digest_log(): WARNING/ERROR с одинаковым шаблоном схлопываются в одну
  строку со счётчиком.
"""
import math
import re
from collections import Counter, defaultdict

import probe_kernels as kernels
from probe_settings import section

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def _cfg():
    return section("analysis")


# ---------------------------------------------------------------- columns

def player_id_of(samples):
    for s in samples:
        if s.get("player"):
            return s["player"].get("id")
    return None


def _alive(p):
    return bool(p.get("alive", p["hp"] > 0))


def nearest_distances(samples):
    """[(t, distance-to-nearest-living-enemy or None)] по сэмплам с героем."""
    table = kernels.HeroTable.from_samples(samples)
    if not len(table):
        return []
    dists = kernels.nearest_distances(table.x, table.y, table.offsets, table.ex, table.ey)
    return [(t, None if math.isnan(d) else d) for t, d in zip(table.ts, dists)]


def scan_hero(samples, events=()):
    """Вся таблица героя -> одна структура (rust_core.RunAnalytics.scan_hero
    или Python-двойник): pinned/stuck/death_t/invalid/min_nearest/sparkline."""
    cfg = _cfg()
    params = {k: cfg[k] for k in ("low_hp_fraction", "pinned_seconds", "stuck_seconds", "stuck_distance")}
    params["spark_width"] = 24
    return kernels.scan_hero(kernels.HeroTable.from_samples(samples), params, sorted(e["t"] for e in events))


def sparkline(values, width=24):
    return kernels.sparkline([float(v) for v in values if v is not None], width)


def combat_stats(events, player_id):
    hits = [e for e in events if not e["dodged"]]
    stats = {
        "attacks": len(events),
        "hits": len(hits),
        "dodges": len(events) - len(hits),
        "crits": sum(1 for e in hits if e["critical"]),
        "dealt": round(sum(e["damage"] for e in hits if e["source"] == player_id), 1),
        "taken": round(sum(e["damage"] for e in hits if e["target"] == player_id), 1),
        "player_attacks": sum(1 for e in events if e["source"] == player_id),
        "player_hits": sum(1 for e in hits if e["source"] == player_id),
        "player_crits": sum(1 for e in hits if e["source"] == player_id and e["critical"]),
        "enemy_attacks": sum(1 for e in events if e["target"] == player_id),
        "zero_damage_hits": sum(1 for e in hits if e["damage"] <= 0),
        "first_t": events[0]["t"] if events else None,
    }
    taken_by, dealt_to = Counter(), Counter()
    for e in hits:
        if e["target"] == player_id:
            taken_by[e.get("source_type") or "?"] += e["damage"]
        elif e["source"] == player_id:
            dealt_to[e.get("target_type") or "?"] += e["damage"]
    stats["taken_by_type"] = {k: round(v, 1) for k, v in taken_by.most_common()}
    stats["dealt_to_type"] = {k: round(v, 1) for k, v in dealt_to.most_common()}
    return stats


def _kills_list(ctx):
    kills = ctx.get("kills")
    return kills if isinstance(kills, list) else []


def _kill_count(ctx):
    kills = ctx.get("kills")
    return len(kills) if isinstance(kills, list) else int(kills or 0)


# ---------------------------------------------------------------- logs

_TRACE_RE = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')


def digest_log(lines, limit=10):
    """Схлопывает повторы: '[x37] WARNING src.x: HP 5 below 20'."""
    digest, distinct = kernels.log_digest([str(line) for line in lines], limit)
    out = [f"[x{n}] {body}" if n > 1 else body for n, body in digest]
    if distinct > limit:
        out.append(f"... {distinct - limit} more distinct message(s)")
    return out


def error_location(text):
    """Самый глубокий кадр traceback внутри проекта: 'src/x.py:12 in f'."""
    frames = [(f, l, fn) for f, l, fn in _TRACE_RE.findall(text or "")
              if "site-packages" not in f and "/lib/python" not in f and "\\lib\\" not in f]
    if not frames:
        return None
    path, line, func = frames[-1]
    for marker in ("/src/", "\\src\\", "/tools/", "\\tools\\"):
        if marker in path:
            path = marker.strip("/\\") + "/" + path.split(marker, 1)[1].replace("\\", "/")
            break
    return f"{path}:{line} in {func}"


# ---------------------------------------------------------------- hypotheses

def _hyp(hid, severity, claim, evidence, look_at, next_step=None):
    return {"id": hid, "severity": severity, "claim": claim, "evidence": evidence,
            "look_at": look_at, "next": next_step}


def hypotheses(samples, events, ctx=None):
    """Гипотезы, отсортированные по важности. ctx (всё опционально):
    kills (list[(t,id,type)] | int), errors (list[str]), error_text (str),
    blank_frames, screenshots, duration, player_crit_chance."""
    ctx = ctx or {}
    cfg = _cfg()
    out = []
    pid = player_id_of(samples)
    stats = combat_stats(events, pid)
    duration = ctx.get("duration") or (samples[-1]["t"] if samples else 0)
    scan = scan_hero(samples, events)
    min_near = scan["min_nearest"]
    close = cfg["close_range"]

    if ctx.get("errors"):
        loc = error_location(ctx.get("error_text", "")) or error_location("\n".join(ctx["errors"]))
        out.append(_hyp(
            "ERRORS", "high", f"{len(ctx['errors'])} ERROR log line(s) during the run",
            {"first": ctx["errors"][0][:160], "where": loc},
            [loc] if loc else ["game.log"],
            "fix the first error; later ones are often its consequences"))

    if stats["attacks"] == 0 and duration >= 5:
        if min_near is None:
            out.append(_hyp("NO_ENEMIES", "high", "no living enemies existed during the whole run",
                            {"samples": len(samples)},
                            ["src/scenes/main_game_scene.py:_spawn_enemies/_spawn_initial_enemies"]))
        elif min_near > close:
            out.append(_hyp(
                "NO_COMBAT", "medium",
                f"no combat at all: nearest enemy never came closer than {min_near:.0f}u",
                {"min_distance": round(min_near, 1), "duration": round(duration, 1)},
                ["src/scenes/main_game_scene.py:_spawn_enemies (spawns at map edges)",
                 "src/entities/enemy.py:update_ai (detection_range)"],
                "spawn an enemy next to the hero: agent_play 'spawn enemy' or dev_probe --action-at 1:1"))
        else:
            out.append(_hyp(
                "CLOSE_BUT_NO_ATTACKS", "high",
                f"enemy was {min_near:.1f}u from the hero yet nobody attacked",
                {"min_distance": round(min_near, 1)},
                ["src/entities/character.py:update_ai", "src/entities/enemy.py:update_ai/attack",
                 "src/features/combat_plugin.py (combat_system wiring)"]))

    if stats["enemy_attacks"] and not stats["player_attacks"]:
        out.append(_hyp(
            "HERO_NEVER_ATTACKS", "high",
            f"hero was attacked {stats['enemy_attacks']}x but never attacked back",
            {"taken": stats["taken"]},
            ["src/entities/character.py:update_ai (fighting state)", "src/entities/character.py:attack"]))
    if stats["player_attacks"] and not stats["enemy_attacks"] and min_near is not None and min_near < 2:
        out.append(_hyp(
            "ENEMIES_PASSIVE", "medium",
            f"hero attacked {stats['player_attacks']}x, enemies never attacked back despite contact",
            {"min_distance": round(min_near, 1)}, ["src/entities/enemy.py:update_ai/attack"]))

    if stats["hits"] >= 5 and stats["zero_damage_hits"] / stats["hits"] > cfg["zero_damage_ratio"]:
        out.append(_hyp(
            "ZERO_DAMAGE_HITS", "medium",
            f"{stats['zero_damage_hits']}/{stats['hits']} landed hits dealt 0 damage",
            {"zero": stats["zero_damage_hits"], "hits": stats["hits"]},
            ["src/systems/combat/combat_system.py:execute_attack (defense/floor)"]))

    crit_chance = ctx.get("player_crit_chance")
    if (crit_chance and crit_chance >= cfg["crit_min_chance"]
            and stats["player_hits"] >= cfg["crit_min_hits"] and stats["player_crits"] == 0):
        out.append(_hyp(
            "CRIT_NEVER_FIRES", "medium",
            f"0 crits in {stats['player_hits']} hero hits with crit_chance={crit_chance:.0%}",
            {"expected": round(stats["player_hits"] * crit_chance, 1)},
            ["src/systems/combat/combat_system.py:execute_attack (critical roll)", "src/core/rng_manager.py"]))

    # --- HP/позиция героя: одна структура из scan_hero()
    if scan["invalid_count"]:
        t, hp, mhp = scan["invalid_first"]
        out.append(_hyp("HP_INVALID", "high", f"invalid hero HP/position in {scan['invalid_count']} sample(s)",
                        {"first_t": t, "hp": hp, "max_hp": mhp},
                        ["src/entities/character.py (health setter / level-up max_health)"]))

    if scan["pinned"]:
        t0, t1, hp = scan["pinned"]
        out.append(_hyp(
            "HP_PINNED", "high",
            f"hero stayed under {cfg['low_hp_fraction']:.0%} HP for {t1 - t0:.0f}s without dying",
            {"from_t": t0, "hp": round(hp, 1)},
            ["src/scenes/main_game_scene.py:update (health_regen)", "src/entities/character.py:is_alive/take_damage"],
            "possible death latch / regen fighting damage"))

    death_t = scan["death_t"]
    if death_t is not None:
        recent = [e for e in events if e["target"] == pid and not e["dodged"] and death_t - 5 <= e["t"] <= death_t + 0.5]
        killers = Counter(e.get("source_type") or "?" for e in recent)
        early = bool(duration) and death_t < duration * 0.5
        out.append(_hyp(
            "HERO_DIED", "medium" if early else "info",
            f"hero died at t={death_t:.1f}s" + (" (first half of the run)" if early else ""),
            {"killed_by_last5s": dict(killers.most_common(3)), "dmg_last5s": round(sum(e["damage"] for e in recent), 1)},
            ["src/entities/enemy.py (damage by type)", "src/entities/enemy.py:apply_level_bonus"]))

    if scan["stuck"]:
        t0, t1 = scan["stuck"]
        at = next((s["player"] for s in samples if s.get("player") and s["t"] >= t0), {})
        ai = at.get("ai")
        look = {
            "seeking_exit": ["src/entities/character.py:_select_best_exit_target (target = estimated exit, "
                             "not the real one?)", "src/entities/character.py:move_towards (stops within 0.1u)"],
            "seeking_hint": ["src/entities/character.py:_select_best_hint_target",
                             "src/scenes/main_game_scene.py:_update_exit_hints (hint never consumed?)"],
        }.get(ai, ["src/entities/character.py:update_ai (exploration_target)"])
        out.append(_hyp(
            "HERO_STUCK", "medium", f"hero didn't move for {t1 - t0:.0f}s and wasn't fighting",
            {"from_t": t0, "ai": ai, "pos": at.get("pos")}, look))

    kills = _kill_count(ctx)
    counts = [(s["t"], len(s.get("enemies", []))) for s in samples]
    if len(counts) >= 6 and duration >= 20:
        fit = kernels.linear_fit([float(c[0]) for c in counts], [float(c[1]) for c in counts])
        growth = fit[0] * 60 if fit else 0
        if growth >= cfg["pressure_per_min"] and kills / (duration / 60) < growth:
            out.append(_hyp(
                "ENEMY_PRESSURE", "low", f"enemy count grows +{growth:.1f}/min, kills only {kills / (duration / 60):.1f}/min",
                {"start": counts[0][1], "end": counts[-1][1]},
                ["src/scenes/main_game_scene.py (enemy_spawn_interval/max_enemies)"]))

    if ctx.get("blank_frames"):
        out.append(_hyp(
            "RENDER_BLANK", "high" if ctx["blank_frames"] >= (ctx.get("screenshots") or 1) else "medium",
            f"{ctx['blank_frames']} blank/solid-color screenshot(s) while game state looked alive",
            {"blank": ctx["blank_frames"], "screenshots": ctx.get("screenshots")},
            ["panda3d.log", "src/scenes/main_game_scene.py:_setup_camera"]))

    out.sort(key=lambda h: SEVERITY_ORDER.get(h["severity"], 9))
    return out


def format_hypotheses(hyps, limit=None):
    limit = limit or _cfg()["hypotheses_shown"]
    if not hyps:
        return ["- none (no rule fired)"]
    lines = []
    for h in hyps[:limit]:
        ev = ", ".join(f"{k}={v}" for k, v in h["evidence"].items() if v not in (None, {}, []))
        lines.append(f"- [{h['severity']}] {h['id']}: {h['claim']}" + (f" ({ev})" if ev else ""))
        if h["look_at"]:
            lines.append(f"  look at: {'; '.join(str(x) for x in h['look_at'])}")
        if h.get("next"):
            lines.append(f"  next: {h['next']}")
    if len(hyps) > limit:
        lines.append(f"- ... {len(hyps) - limit} more (lower severity) in the JSON output")
    return lines


# ---------------------------------------------------------------- forecast

def forecast(samples, events, ctx=None):
    """Прогнозы + ключевые числа (dict); format_forecast() - текст."""
    ctx = ctx or {}
    cfg = _cfg()
    res = {}
    alive = [s for s in samples if s.get("player") and _alive(s["player"])]
    duration = ctx.get("duration") or (samples[-1]["t"] if samples else 0)
    pid = player_id_of(samples)
    stats = combat_stats(events, pid)

    if len(alive) >= 3:
        t_end = alive[-1]["t"]
        win = max(cfg["forecast_window_min"], min(cfg["forecast_window_max"], (t_end - alive[0]["t"]) * 0.4))
        tail = [s for s in alive if s["t"] >= t_end - win]
        fit = kernels.linear_fit([float(s["t"]) for s in tail], [float(s["player"]["hp"]) for s in tail])
        if fit:
            slope = fit[0]
            res["hp_slope_per_s"] = round(slope, 2)
            res["hp_window_s"] = round(win, 1)
            if slope < -0.05:
                res["death_eta_s"] = round(tail[-1]["player"]["hp"] / -slope, 1)
        xp_pts = [(float(s["t"]), float(s["player"]["xp"])) for s in tail if s["player"].get("xp") is not None]
        xp_fit = kernels.linear_fit([p[0] for p in xp_pts], [p[1] for p in xp_pts]) if len(xp_pts) >= 2 else None
        last = tail[-1]["player"]
        if xp_fit and xp_fit[0] > 0 and last.get("xp_next") and last.get("xp") is not None and last["xp_next"] > last["xp"]:
            res["level_up_eta_s"] = round((last["xp_next"] - last["xp"]) / xp_fit[0], 1)

    if duration > 0:
        res["dps_dealt"] = round(stats["dealt"] / duration, 2)
        res["dps_taken"] = round(stats["taken"] / duration, 2)
        res["kills_per_min"] = round(_kill_count(ctx) / (duration / 60), 2)

    counts = [(float(s["t"]), float(len(s.get("enemies", [])))) for s in samples]
    fit = kernels.linear_fit([c[0] for c in counts], [c[1] for c in counts]) if len(counts) >= 3 else None
    if fit:
        res["enemy_trend_per_min"] = round(fit[0] * 60, 2)

    # TTK по типам: от первого появления в сэмплах до смерти (KillTracker)
    first_seen = {}
    for s in samples:
        for e in s.get("enemies", []):
            first_seen.setdefault(e["id"], s["t"])
    hits_on = Counter(e["target"] for e in events if not e["dodged"] and e["source"] == pid)
    ttk, htk = defaultdict(list), defaultdict(list)
    for t, eid, etype in _kills_list(ctx):
        if eid in first_seen:
            ttk[etype].append(t - first_seen[eid])
        if hits_on.get(eid):
            htk[etype].append(hits_on[eid])
    if ttk:
        res["ttk_by_type_s"] = {k: round(sum(v) / len(v), 1) for k, v in ttk.items()}
    if htk:
        res["hits_to_kill_by_type"] = {k: round(sum(v) / len(v), 1) for k, v in htk.items()}

    if "death_eta_s" in res:
        res["outlook"] = f"hero projected to die in ~{res['death_eta_s']:.0f}s at the current damage rate"
    elif "hp_slope_per_s" in res:
        res["outlook"] = "hero HP stable or recovering at the current pressure"
    return res


def format_forecast(fc):
    if not fc:
        return ["- not enough samples"]
    lines = []
    if "outlook" in fc:
        lines.append(f"- outlook: {fc['outlook']} (linear fit over last {fc.get('hp_window_s')}s, "
                     f"HP {fc.get('hp_slope_per_s'):+}/s)")
    if "dps_dealt" in fc:
        lines.append(f"- DPS dealt/taken: {fc['dps_dealt']}/{fc['dps_taken']}")
    if "enemy_trend_per_min" in fc:
        lines.append(f"- enemies {fc['enemy_trend_per_min']:+}/min vs kills {fc.get('kills_per_min', 0)}/min")
    if "level_up_eta_s" in fc:
        lines.append(f"- next hero level in ~{fc['level_up_eta_s']:.0f}s")
    if "ttk_by_type_s" in fc:
        htk = fc.get("hits_to_kill_by_type", {})
        parts = [f"{k} {v}s" + (f"/{htk[k]} hits" if k in htk else "") for k, v in fc["ttk_by_type_s"].items()]
        lines.append(f"- time-to-kill by type (spawn->death): {', '.join(parts)}")
    return lines or ["- not enough data"]
