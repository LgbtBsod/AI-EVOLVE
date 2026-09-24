#!/usr/bin/env python3
"""Числовые ядра анализа прогонов: Rust (rust_core.RunAnalytics), если он
собран, иначе эквивалентный Python.

Python здесь - оркестратор: tools/probe_analysis.py решает, ЧТО считать и
как это сформулировать для агента, а сами циклы по сэмплам/событиям/строкам
лога живут в rust_core/src/analytics. Python-реализации ниже - построчные
копии Rust-версий (паритет проверяется в tests/test_agent_tools.py), чтобы
инструменты работали и без собранного rust_core (CI-джоба game его не ставит).

Обмен между слоями - колоночный и бинарный: данные идут в Rust как
array('d')/array('B')/array('Q') (buffer protocol -> один memcpy на колонку
вместо конвертации каждого float-объекта). HeroTable - struct-of-arrays
таблица героя за прогон; scan_hero() отдаёт её в Rust целиком и получает
обратно одну структуру (dict) - весь разбор HP/позиции за один FFI-вызов.

BACKEND - "rust" или "python", печатается в summary для прозрачности.
"""
import math
import re
from array import array
from bisect import bisect_left

try:
    from rust_core import RunAnalytics as _rust
    BACKEND = "rust"
except ImportError:  # rust_core не собран: pip install ./rust_core
    _rust = None
    BACKEND = "python"

SPARK_CHARS = "▁▂▃▄▅▆▇█"


# ---------------------------------------------------------------- columns

def f64(values):
    """Колонка float64 для передачи в Rust (массивы/буферы проходят как есть)."""
    return values if isinstance(values, array) and values.typecode == "d" else array("d", values)


def u8(values):
    return values if isinstance(values, array) and values.typecode == "B" else array("B", (1 if v else 0 for v in values))


def u64(values):
    return values if isinstance(values, array) and values.typecode == "Q" else array("Q", values)


class HeroTable:
    """Struct-of-arrays: одна строка на сэмпл state.jsonl, в котором есть герой.
    Живые враги сэмпла i - ex/ey[offsets[i]:offsets[i+1]]."""

    __slots__ = ("ts", "hp", "max_hp", "x", "y", "alive", "offsets", "ex", "ey")

    def __init__(self):
        for name in ("ts", "hp", "max_hp", "x", "y", "ex", "ey"):
            setattr(self, name, array("d"))
        self.alive = array("B")
        self.offsets = array("Q", [0])

    @classmethod
    def from_samples(cls, samples):
        t = cls()
        for s in samples:
            p = s.get("player")
            if not p:
                continue
            t.ts.append(float(s["t"]))
            t.hp.append(float(p["hp"]))
            t.max_hp.append(float(p["max_hp"] or 0))
            t.x.append(float(p["pos"][0]))
            t.y.append(float(p["pos"][1]))
            t.alive.append(1 if p.get("alive", p["hp"] > 0) else 0)
            for e in s.get("enemies", []):
                if e.get("hp", 1) > 0:
                    t.ex.append(float(e["pos"][0]))
                    t.ey.append(float(e["pos"][1]))
            t.offsets.append(len(t.ex))
        return t

    def __len__(self):
        return len(self.ts)


# ---------------------------------------------------------------- python twins

def py_linear_fit(xs, ys):
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    mx, my = sum(xs[:n]) / n, sum(ys[:n]) / n
    sxx = sxy = 0.0
    for i in range(n):
        dx = xs[i] - mx
        sxx += dx * dx
        sxy += dx * (ys[i] - my)
    if sxx == 0.0:
        return None
    slope = sxy / sxx
    return slope, my - slope * mx


def py_sparkline(values, width=24):
    vals = [v for v in values if not math.isnan(v)]
    if not vals or width == 0:
        return ""
    if len(vals) > width:
        step = len(vals) / width
        buckets = []
        for i in range(width):
            start = int(i * step)
            end = max(int((i + 1) * step), start + 1)
            buckets.append(min(vals[start:end]))
        vals = buckets
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return (SPARK_CHARS[7] if hi > 0 else SPARK_CHARS[0]) * len(vals)
    return "".join(SPARK_CHARS[math.floor((v - lo) / (hi - lo) * 7.0 + 0.5)] for v in vals)


def py_nearest_distances(px, py, offsets, ex, ey):
    out = []
    for i in range(len(px)):
        best = math.nan
        for j in range(offsets[i], offsets[i + 1]):
            d = math.hypot(ex[j] - px[i], ey[j] - py[i])
            if math.isnan(best) or d < best:
                best = d
        out.append(best)
    return out


def py_pinned_interval(ts, hp, max_hp, alive, frac, min_seconds):
    low_since = None
    for i in range(len(ts)):
        if not alive[i] or hp[i] <= 0.0:
            low_since = None
            continue
        mhp = max_hp[i] if max_hp[i] > 0.0 else 1.0
        if hp[i] / mhp < frac:
            if low_since is None:
                low_since = ts[i]
            if ts[i] - low_since >= min_seconds:
                return (low_since, ts[i], hp[i])
        else:
            low_since = None
    return None


def py_stuck_interval(ts, xs, ys, alive, window_s, min_dist, busy_ts):
    start = count = 0
    for i in range(len(ts)):
        if not alive[i]:
            count = 0
            continue
        if count == 0:
            start = i
        count += 1
        while ts[i] - ts[start] > window_s:
            start += 1
            count -= 1
        if count >= 3 and ts[i] - ts[start] >= window_s * 0.9:
            span = max(math.hypot(xs[j] - xs[start], ys[j] - ys[start]) for j in range(start, i + 1))
            t0, t1 = ts[start], ts[i]
            k = bisect_left(busy_ts, t0)
            busy = k < len(busy_ts) and busy_ts[k] <= t1
            if span < min_dist and not busy:
                return (t0, t1)
    return None


_TIME_PREFIX = re.compile(r"^[0-9]{2}:[0-9]{2}:[0-9]{2} ")
_ALNUM_RUN = re.compile(r"[A-Za-z0-9]+")
_HEX = set("0123456789abcdefABCDEF")


def _strip_time_prefix(line):
    return line[9:] if _TIME_PREFIX.match(line) else line


def _is_hex_id(token):
    return any(c.isdigit() for c in token) and (all(c in _HEX for c in token) or token.startswith("0x"))


def py_log_template(line):
    return _ALNUM_RUN.sub(lambda m: "#" if _is_hex_id(m.group()) else m.group(), _strip_time_prefix(line))


def py_scan_hero(table, params, busy_ts):
    """Двойник analytics::scan_hero: одна структура-результат по всей таблице."""
    n = len(table.ts)
    alive = [a != 0 for a in table.alive[:n]]
    invalid_count, invalid_first, death_t = 0, None, None
    for i in range(n):
        hp, mhp = table.hp[i], table.max_hp[i]
        bad = (math.isnan(hp) or math.isnan(table.x[i]) or math.isnan(table.y[i])
               or (alive[i] and (hp > mhp + 0.01 or hp < -0.01)))
        if bad:
            invalid_count += 1
            if invalid_first is None:
                invalid_first = (table.ts[i], hp, mhp)
        if death_t is None and (not alive[i] or hp <= 0.0):
            death_t = table.ts[i]
    dists = [d for d in py_nearest_distances(table.x, table.y, table.offsets, table.ex, table.ey) if not math.isnan(d)]
    g = params.get
    return {
        "pinned": py_pinned_interval(table.ts, table.hp, table.max_hp, alive,
                                     g("low_hp_fraction", 0.2), g("pinned_seconds", 5.0)),
        "stuck": py_stuck_interval(table.ts, table.x, table.y, alive,
                                   g("stuck_seconds", 8.0), g("stuck_distance", 0.5), busy_ts),
        "death_t": death_t,
        "invalid_count": invalid_count,
        "invalid_first": invalid_first,
        "min_nearest": min(dists) if dists else None,
        "hp_sparkline": py_sparkline(table.hp, int(g("spark_width", 24))),
    }


def py_log_digest(lines, limit=10):
    order, index = [], {}
    for line in lines:
        first_line = line.strip().split("\n")[0].rstrip("\r")  # как str::lines() в Rust
        key = py_log_template(first_line)
        if key in index:
            order[index[key]][1] += 1
        else:
            index[key] = len(order)
            order.append([key, 1, _strip_time_prefix(first_line)])
    distinct = len(order)
    order.sort(key=lambda e: -e[1])
    return [(n, body) for _, n, body in order[:limit]], distinct


# ---------------------------------------------------------------- dispatch

def _pick(name, columns=()):
    """Rust-ядро, если оно есть в собранном rust_core (старая сборка без
    нового метода -> Python), иначе Python-двойник. `columns` - позиции
    аргументов-колонок, которые для Rust упаковываются в бинарные буферы."""
    py_impl = globals()[f"py_{name}"]
    rust_impl = getattr(_rust, name, None) if _rust is not None else None
    if rust_impl is None:
        return py_impl
    if not columns:
        return rust_impl

    def call(*args):
        args = list(args)
        for i, kind in columns:
            args[i] = kind(args[i])
        return rust_impl(*args)
    call.__name__ = name
    return call


linear_fit = _pick("linear_fit", [(0, f64), (1, f64)])
sparkline = _pick("sparkline", [(0, f64)])
nearest_distances = _pick("nearest_distances", [(0, f64), (1, f64), (2, u64), (3, f64), (4, f64)])
pinned_interval = _pick("pinned_interval", [(0, f64), (1, f64), (2, f64), (3, u8)])
stuck_interval = _pick("stuck_interval", [(0, f64), (1, f64), (2, f64), (3, u8), (6, f64)])
scan_hero = _pick("scan_hero", [(2, f64)])
log_template = _pick("log_template")
log_digest = _pick("log_digest")
