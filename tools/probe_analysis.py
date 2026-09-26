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
from probe_rules import evaluate, first_say, rules_table
from probe_settings import section


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
        # конвейер урона (docs/DAMAGE_PIPELINE.md): промахи по меткости входят в dodges; блоки, снятое, пробитое - по попаданиям
        "misses": sum(1 for e in events if e.get("missed")),
        "blocks": sum(1 for e in hits if e.get("blocked")),
        "resisted": round(sum(e.get("resisted", 0.0) for e in hits), 1),
        "armored": round(sum(e.get("armor", 0.0) for e in hits), 1),
        "pierced": round(sum(e.get("pierced", 0.0) for e in hits), 1),
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
# Правила - данные (lua_content/probe_rules.lua), вычислитель - tools/probe_rules.py;
# здесь только факты (числа, которые правила сравнивают и подставляют в текст).

def _facts_errors(ctx):
    errors = ctx.get("errors") or []
    if not errors:
        return {"errors_n": 0}
    loc = error_location(ctx.get("error_text", "")) or error_location("\n".join(errors))
    return {"errors_n": len(errors), "err_first": errors[0][:160], "err_where": loc,
            "err_look": [loc] if loc else ["game.log"]}


def _hits_before_death(events, pid, death_t):
    return [e for e in events if e["target"] == pid and not e["dodged"] and death_t - 5 <= e["t"] <= death_t + 0.5]


def _facts_death(death_t, events, pid, duration):
    recent = _hits_before_death(events, pid, death_t)
    killers = Counter(e.get("source_type") or "?" for e in recent)
    early = bool(duration) and death_t < duration * 0.5
    return {"died_sev": "medium" if early else "info", "died_note": " (first half of the run)" if early else "",
            "died_killers": dict(killers.most_common(3)), "died_dmg": round(sum(e["damage"] for e in recent), 1)}


_STUCK_LOOK = {
    "seeking_exit": ["src/entities/character.py:_select_best_exit_target (target = estimated exit, "
                     "not the real one?)", "src/entities/character.py:move_towards (stops within 0.1u)"],
    "seeking_hint": ["src/entities/character.py:_select_best_hint_target",
                     "src/scenes/main_game_scene.py:_update_exit_hints (hint never consumed?)"],
}


def _facts_stuck(stuck, samples):
    t0, t1 = stuck
    at = next((s["player"] for s in samples if s.get("player") and s["t"] >= t0), {})
    ai = at.get("ai")
    return {"stuck_t0": t0, "stuck_secs": t1 - t0, "stuck_ai": ai, "stuck_pos": at.get("pos"),
            "stuck_look": _STUCK_LOOK.get(ai, ["src/entities/character.py:update_ai (exploration_target)"])}


def _facts_scan(scan, samples, events, pid, duration):
    f = {"min_near": scan["min_nearest"], "death_t": scan["death_t"], "pinned": scan["pinned"],
         "stuck": scan["stuck"], "invalid_count": scan["invalid_count"]}
    if scan["invalid_count"]:
        f["invalid_t"], f["invalid_hp"], f["invalid_mhp"] = scan["invalid_first"]
    if scan["pinned"]:
        t0, t1, f["pinned_hp"] = scan["pinned"]
        f.update(pinned_t0=t0, pinned_secs=t1 - t0)
    if scan["death_t"] is not None:
        f.update(_facts_death(scan["death_t"], events, pid, duration))
    if scan["stuck"]:
        f.update(_facts_stuck(scan["stuck"], samples))
    return f


def _facts_pressure(samples, ctx, duration):
    counts = [(s["t"], len(s.get("enemies", []))) for s in samples]
    f = {"growth": None, "kill_rate": None, "count_start": counts[0][1] if counts else None,
         "count_end": counts[-1][1] if counts else None}
    if len(counts) >= 6 and duration >= 20:
        fit = kernels.linear_fit([float(c[0]) for c in counts], [float(c[1]) for c in counts])
        f["growth"] = fit[0] * 60 if fit else 0
        f["kill_rate"] = _kill_count(ctx) / (duration / 60)
    return f


def _facts_ctx(ctx, stats):
    chance = ctx.get("player_crit_chance")
    blank = ctx.get("blank_frames")
    return {"crit_chance": chance, "crit_expected": stats["player_hits"] * chance if chance else None,
            "blank_frames": blank, "screenshots": ctx.get("screenshots"),
            "blank_sev": "high" if blank and blank >= (ctx.get("screenshots") or 1) else "medium"}


def hypotheses(samples, events, ctx=None):
    """Гипотезы, отсортированные по важности. ctx (всё опционально):
    kills (list[(t,id,type)] | int), errors (list[str]), error_text (str),
    blank_frames, screenshots, duration, player_crit_chance."""
    ctx = ctx or {}
    pid = player_id_of(samples)
    stats = combat_stats(events, pid)
    duration = ctx.get("duration") or (samples[-1]["t"] if samples else 0)
    facts = {**stats, "duration": duration, "n_samples": len(samples), **_facts_errors(ctx), **_facts_ctx(ctx, stats),
             **_facts_scan(scan_hero(samples, events), samples, events, pid, duration),
             **_facts_pressure(samples, ctx, duration)}
    return evaluate(rules_table()["hypotheses"], facts, _cfg())


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

def _forecast_trend(res, tail, win):
    fit = kernels.linear_fit([float(s["t"]) for s in tail], [float(s["player"]["hp"]) for s in tail])
    if fit:
        res["hp_slope_per_s"] = round(fit[0], 2)
        res["hp_window_s"] = round(win, 1)
        if fit[0] < -0.05:
            res["death_eta_s"] = round(tail[-1]["player"]["hp"] / -fit[0], 1)
            res["eta_basis"] = f"HP trend over last {win:.0f}s"


def _forecast_recent(res, tail, events, pid, recent):
    # Бэктест (6 seed, смерть в рое врагов): тренд HP по окну опаздывает -
    # урон в бою нарастает; темп урона по боевым событиям за последние
    # forecast_recent_s секунд даёт ошибку ~8% времени жизни против ~34%.
    t_end = tail[-1]["t"]
    taken = sum(e["damage"] for e in events if e["target"] == pid and not e["dodged"] and t_end - recent < e["t"] <= t_end)
    if taken > 0:
        res["recent_dps_taken"] = round(taken / recent, 2)
        res["death_eta_s"] = round(tail[-1]["player"]["hp"] / (taken / recent), 1)
        res["eta_basis"] = f"damage taken in the last {recent:g}s"


def _forecast_hp(res, alive, events, pid, cfg):
    t_end = alive[-1]["t"]
    win = max(cfg["forecast_window_min"], min(cfg["forecast_window_max"], (t_end - alive[0]["t"]) * 0.4))
    tail = [s for s in alive if s["t"] >= t_end - win]
    _forecast_trend(res, tail, win)
    _forecast_recent(res, tail, events, pid, cfg.get("forecast_recent_s", 3.0))
    _forecast_level(res, tail)


def _xp_slope(tail):
    pts = [(float(s["t"]), float(s["player"]["xp"])) for s in tail if s["player"].get("xp") is not None]
    fit = kernels.linear_fit([p[0] for p in pts], [p[1] for p in pts]) if len(pts) >= 2 else None
    return fit[0] if fit else None


def _forecast_level(res, tail):
    slope = _xp_slope(tail)
    last = tail[-1]["player"]
    if slope and slope > 0 and last.get("xp_next") and last.get("xp") is not None and last["xp_next"] > last["xp"]:
        res["level_up_eta_s"] = round((last["xp_next"] - last["xp"]) / slope, 1)


def _first_seen(samples):
    first_seen = {}
    for s in samples:
        for e in s.get("enemies", []):
            first_seen.setdefault(e["id"], s["t"])
    return first_seen


def _forecast_ttk(res, samples, events, pid, ctx):
    """TTK по типам: от первого появления в сэмплах до смерти (KillTracker)."""
    first_seen = _first_seen(samples)
    hits_on = Counter(e["target"] for e in events if not e["dodged"] and e["source"] == pid)
    ttk, htk = defaultdict(list), defaultdict(list)
    for t, eid, etype in _kills_list(ctx):
        if eid in first_seen:
            ttk[etype].append(t - first_seen[eid])
        if hits_on.get(eid):
            htk[etype].append(hits_on[eid])
    for key, groups in (("ttk_by_type_s", ttk), ("hits_to_kill_by_type", htk)):
        if groups:
            res[key] = {k: round(sum(v) / len(v), 1) for k, v in groups.items()}


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
        _forecast_hp(res, alive, events, pid, cfg)
    if duration > 0:
        res["dps_dealt"] = round(stats["dealt"] / duration, 2)
        res["dps_taken"] = round(stats["taken"] / duration, 2)
        res["kills_per_min"] = round(_kill_count(ctx) / (duration / 60), 2)
    counts = [(float(s["t"]), float(len(s.get("enemies", [])))) for s in samples]
    fit = kernels.linear_fit([c[0] for c in counts], [c[1] for c in counts]) if len(counts) >= 3 else None
    if fit:
        res["enemy_trend_per_min"] = round(fit[0] * 60, 2)
    _forecast_ttk(res, samples, events, pid, ctx)
    outlook = first_say(rules_table()["outlook"], res)
    if outlook:
        res["outlook"] = outlook
    return res


def format_forecast(fc):
    if not fc:
        return ["- not enough samples"]
    lines = []
    if "outlook" in fc:
        lines.append(f"- outlook: {fc['outlook']}; HP trend {fc.get('hp_slope_per_s'):+}/s over {fc.get('hp_window_s')}s"
                     + (f", recent damage {fc['recent_dps_taken']}/s" if "recent_dps_taken" in fc else ""))
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
