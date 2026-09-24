"""itemcheck: проверка предмета целиком - от схемы до боя - с компактным отчётом.

    check_item(item) -> Report          # item: dict {name, effects: [...]}
    python -m tools.effect_schema.itemcheck lua_content/items/x.lua
    python -m tools.effect_schema.itemcheck --forge 2000 --seed 3 [--hostile]

Проверки (каждая - одна строка отчёта, находки - отдельными строками):
  validate  - схема, ссылки apply_effect/owner_has/cross, булевость условий;
  lua       - render_item -> исполнение Lua каждым бэкендом -> те же данные;
  preds     - каждое условие предмета в Lua и в Python на случайных ctx
              (один вызов eval_preds на весь предмет и все ctx);
  sim       - сценарий боя со всеми событиями, инварианты после каждого шага
              (конечные числа, 0 <= ресурс <= максимум, границы статов, kills);
  determinism - два прогона дают одинаковый лог;
  coverage  - какие части схемы предмет задействует (и каких нет).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

if __package__ in (None, ""):  # запуск файлом: python tools/effect_schema/itemcheck.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "tools.effect_schema"

from .. import lua_bridge  # noqa: E402
from .lua_gen import render_item  # noqa: E402
from .schema import (CONTEXT_ONLY_STATS, EVENTS, FLAGS, KNOWN_STATS, OP_KINDS, OPS, RESOURCE_STATS,  # noqa: E402
                     TARGETS, TRIGGER_KINDS)
from .sim import EffectRuntime, Unit, eval_pred, named_predicates, sample_context  # noqa: E402
from .validate import validate_item  # noqa: E402

FINDINGS_SHOWN = 8


@dataclass
class Check:
    name: str
    ok: bool
    summary: str
    ms: float = 0.0
    findings: list[str] = field(default_factory=list)


@dataclass
class Report:
    item: str
    effects: int
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def lines(self, findings: int = FINDINGS_SHOWN) -> list[str]:
        out = [f"{'PASS' if self.ok else 'FAIL'} {self.item}: {self.effects} effects"]
        for c in self.checks:
            out.append(f"  {'ok ' if c.ok else 'BAD'} {c.name:<11} {c.summary}  ({c.ms:.0f} ms)")
            out += [f"      - {f}" for f in c.findings[:findings]]
            if len(c.findings) > findings:
                out.append(f"      ... {len(c.findings) - findings} more")
        return out

    def to_json(self) -> dict:
        return {"item": self.item, "effects": self.effects, "ok": self.ok,
                "checks": [c.__dict__ for c in self.checks]}


def _timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------- helpers

def _norm(value):
    """Числа -> float: Lua отдаёт 5 там, где в JSON было 5.0."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_norm(v) for v in value]
    return value


def _first_diff(a, b, path="") -> Optional[str]:
    if type(a) is not type(b):
        return f"{path or '<root>'}: {a!r} != {b!r}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}: {'missing in Lua' if k not in b else 'extra in Lua'}"
            d = _first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} items != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else f"{path}: {a!r} != {b!r}"


def predicates(item: dict) -> list[str]:
    """Все условия предмета (trigger.when/filter, amplify.when, op.when, fail.when)."""
    out: list[str] = []

    def ops(lst):
        for o in lst or []:
            if isinstance(o.get("when"), str):
                out.append(o["when"])
            ops(o.get("fail"))

    for ef in item.get("effects", []):
        tr = ef.get("trigger") or {}
        out += [tr[k] for k in ("when", "filter") if isinstance(tr.get(k), str)]
        amp = ef.get("amplify") or {}
        if isinstance(amp.get("when"), str):
            out.append(amp["when"])
        ops(ef.get("ops"))
    return list(dict.fromkeys(out))


def random_contexts(n: int, seed: int) -> list[dict]:
    """Случайные ctx по полям рантайма: обычные значения, нули, 1 HP, большие числа."""
    rng = random.Random(seed)
    fields = sorted(sample_context())
    ctxs = []
    for i in range(n):
        ctx = {}
        for f in fields:
            r = rng.random()
            ctx[f] = 0.0 if r < 0.08 else 1.0 if r < 0.14 else float(rng.choice([-5, 1e6])) if r < 0.18 \
                else round(rng.uniform(0, 1000 if "max" in f or f.endswith("hp") else 100), 3)
        ctxs.append(ctx)
    return ctxs


def _same(py, lua) -> bool:
    if isinstance(py, float) and isinstance(lua, float) and math.isnan(py) and math.isnan(lua):
        return True
    return py == lua


# ---------------------------------------------------------------- checks

def check_validate(item: dict) -> Check:
    errs, ms = _timed(validate_item, item)
    return Check("validate", not errs, f"{len(errs)} error(s)", ms, errs)


def check_lua(item: dict, backends: list[str]) -> tuple[Check, Optional[str]]:
    try:
        lua, ms_render = _timed(render_item, {"name": item.get("name", ""), "description": item.get("description", "")},
                                item["effects"])
    except Exception as exc:  # noqa: BLE001 - условие, которое нельзя перевести в Lua, и т.п.
        return Check("lua", False, "render failed", 0.0, [f"{type(exc).__name__}: {exc}"]), None
    expected = _norm(item["effects"])
    findings, times = [], {}
    for b in backends:
        try:
            data, ms = _timed(lua_bridge.load, lua, backend=b)
        except Exception as exc:
            findings.append(f"{b}: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        times[b] = ms
        diff = _first_diff(expected, _norm(data.get("effects", [])), "effects")
        if diff:
            findings.append(f"{b}: round-trip differs at {diff}")
    speed = ", ".join(f"{b} {ms:.0f} ms" for b, ms in times.items())
    summary = f"{len(lua) / 1024:.0f} KiB Lua, render {ms_render:.0f} ms; load: {speed or 'no backend'}"
    return Check("lua", not findings and bool(times), summary, ms_render + sum(times.values()), findings), lua


def check_preds(item: dict, lua: str, backends: list[str], samples: int, seed: int) -> Check:
    srcs = predicates(item)
    named = named_predicates()
    ctxs = random_contexts(samples, seed)
    findings: list[str] = []
    t0 = time.perf_counter()
    py_rows = []
    for ctx in ctxs:
        row = {}
        for src in srcs:
            try:
                row[src] = bool(eval_pred(src, ctx))
            except Exception as exc:  # noqa: BLE001 - любое исключение Python и есть находка
                row[src] = f"error: {type(exc).__name__}"
        py_rows.append(row)
    diverged: dict[str, str] = {}
    for b in backends:
        try:
            lua_rows = lua_bridge.eval_preds(lua, ctxs, backend=b)
        except Exception as exc:
            findings.append(f"{b}: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        for ctx, py, lr in zip(ctxs, py_rows, lua_rows):
            for src in srcs:
                if src not in lr:
                    diverged.setdefault(src, f"{b}: condition missing in Lua")
                elif not _same(py[src], lr[src]) and src not in diverged:
                    keys = [k for k in ctx if f"ctx.{k}" in src]
                    diverged[src] = f"{b}: python={py[src]!r} lua={lr[src]!r} ctx={ {k: ctx[k] for k in keys} }"
    findings += [f"{src}  ->  {why}" for src, why in diverged.items()]
    ms = (time.perf_counter() - t0) * 1000
    summary = (f"{len(srcs)} condition(s) x {samples} ctx x {len(backends)} backend(s): "
               f"{len(diverged)} diverge ({sum(1 for s in srcs if s in named)} named)")
    return Check("preds", not findings, summary, ms, findings)


SCENARIO = ["use", "attack", "attack", "enemy_attack 150", "tick 0.5 0.5", "kill", "attack",
            "hp 35", "attack", "hp 8", "attack", "hp 1", "attack", "enemy_attack 50",
            *sorted(EVENTS), "tick 2 1", "tick 4 1", "use", "hp 60", "attack", "kill", "tick 10 5"]


def _invariants(rt: EffectRuntime, step: str, prev_kills: int) -> list[str]:
    bad = []
    for u in rt.units():
        for k, v in u.mods.items():
            if not math.isfinite(v):
                bad.append(f"{step}: {u.name}.mods[{k}] = {v}")
        for k in u.base:
            v = u._eff(k)
            b = u.bounds.get(k, {})
            if not math.isfinite(v):
                bad.append(f"{step}: {u.name}.{k} = {v}")
            elif v < b.get("min", -math.inf) - 1e-9 or v > b.get("max", math.inf) + 1e-9:
                bad.append(f"{step}: {u.name}.{k} = {v} outside {b}")
        for res in u.resources:
            cur, cap = u.resource(res), u.max_of(res)
            if not (math.isfinite(cur) and -1e-9 <= cur <= cap + 1e-9):
                bad.append(f"{step}: {u.name}.{res} = {cur} not in [0, {cap}]")
        if u.alive and u.current_hp <= 0:
            bad.append(f"{step}: {u.name} alive at 0 HP")
        for bid, bf in u.buffs.items():
            if not math.isfinite(bf.get("until", 0.0)):
                bad.append(f"{step}: buff {bid} until {bf.get('until')}")
    if rt.owner.kills < prev_kills:
        bad.append(f"{step}: kills went down {prev_kills} -> {rt.owner.kills}")
    return bad


def run_scenario(item: dict, scenario: list[str] = SCENARIO) -> tuple[list[str], list[str], dict]:
    """(лог рантайма, нарушения инвариантов, итог). Шаги: событие | attack |
    enemy_attack N | kill | tick T DT | hp PCT (выставить HP героя)."""
    hero = Unit("hero", max_hp=1000.0, strength=50, endurance=40, agility=30, intelligence=20,
                defense=10, crit_chance=10, attack_damage=40)
    dummy = Unit("dummy", max_hp=5000.0, defense=5)
    rt = EffectRuntime(hero, item["effects"], enemy=dummy)
    violations: list[str] = []
    t, kills = 0.0, 0
    rt.refresh_passives(t)
    for step in scenario:
        parts = step.split()
        try:
            if parts[0] == "attack":
                rt.attack(t, base_damage=40.0)
            elif parts[0] == "enemy_attack":
                rt.receive_damage(float(parts[1]), t)
            elif parts[0] == "kill":
                dummy.deal_damage(dummy.current_hp)
                hero.kills += 1
                rt.fire_event("kill", t)
                rt.respawn_enemy()
            elif parts[0] == "tick" and len(parts) == 3:
                t += float(parts[1])
                rt.tick(t, float(parts[2]))
            elif parts[0] == "hp":
                hero.alive = True
                hero.set_resource("hp", hero._eff("max_hp") * float(parts[1]) / 100)
                rt.refresh_passives(t)
            else:
                rt.fire_event(step, t)
                rt.refresh_passives(t)
        except RecursionError:
            violations.append(f"{step}: RecursionError (effect cascade does not terminate)")
            break
        except Exception as exc:  # noqa: BLE001
            violations.append(f"{step}: {type(exc).__name__}: {str(exc)[:160]}")
            break
        violations += _invariants(rt, step, kills)
        kills = hero.kills
    from .sim import summarize
    return list(rt.log), violations, summarize(rt)


def check_sim(item: dict) -> tuple[Check, list[str]]:
    (log, violations, summary), ms = _timed(run_scenario, item)
    text = f"{len(SCENARIO)} steps, {len(log)} log lines, hero hp {summary['hp']}/{summary['max_hp']}, " \
           f"{len(summary['mods'])} stats modified, {len(summary['buffs'])} buff(s), kills {summary['kills']}"
    return Check("sim", not violations, text, ms, violations), log


def check_determinism(item: dict, first_log: list[str]) -> Check:
    (log, _v, _s), ms = _timed(run_scenario, item)
    if log == first_log:
        return Check("determinism", True, "identical log on rerun", ms)
    idx = next((i for i, (a, b) in enumerate(zip(first_log, log)) if a != b), min(len(log), len(first_log)))
    return Check("determinism", False, f"logs diverge at line {idx}", ms,
                 [f"run1: {first_log[idx] if idx < len(first_log) else '<end>'}",
                  f"run2: {log[idx] if idx < len(log) else '<end>'}"])


def coverage(item: dict) -> dict[str, tuple[set, set]]:
    """Какие значения каждого измерения схемы предмет использует: {dim: (used, all)}."""
    used: dict[str, set] = {k: set() for k in ("stats", "resources", "op_kinds", "ops", "targets", "events",
                                               "triggers", "flags", "value_forms", "features")}

    def ops(lst):
        for o in lst or []:
            used["op_kinds"].add(o.get("kind"))
            if o.get("kind") == "mod" and o.get("stat"):
                used["stats"].add(o["stat"])
            elif o.get("kind") in ("heal", "drain", "deal", "set"):
                used["resources"].add(o.get("stat") or "hp")
            if o.get("op"):
                used["ops"].add(o["op"])
            used["targets"].add(o.get("target", "self"))
            used["flags"].update(o.get("flags") or [])
            v = o.get("value") or {}
            used["value_forms"].update(["pct_of" if "pct" in v and v.get("of") else k for k in ("flat", "pct", "ref") if k in v])
            s = o.get("scale") or {}
            used["features"].update(f"scale.{k}" for k in ("cap", "floor") if s.get(k) is not None)
            if s and s.get("factor", 1) != 1:
                used["features"].add("scale.factor")
            for k in ("when", "fail", "duration", "cooldown", "extend"):
                if o.get(k):
                    used["features"].add(f"op.{k}")
            ops(o.get("fail"))

    for ef in item.get("effects", []):
        tr = ef.get("trigger") or {}
        used["triggers"].add(tr.get("kind"))
        if tr.get("event"):
            used["events"].add(tr["event"])
        for k in ("filter", "owner_has", "cross"):
            if tr.get(k):
                used["features"].add(f"trigger.{k}")
        if tr.get("when") in named_predicates():
            used["features"].add("named_predicate")
        for k in ("amplify", "threshold", "cooldown"):
            if ef.get(k) is not None:
                used["features"].add(f"effect.{k}")
        if (ef.get("amplify") or {}).get("while_buff"):
            used["features"].add("amplify.while_buff")
        ops(ef.get("ops"))
    universe = {
        "stats": set(KNOWN_STATS - CONTEXT_ONLY_STATS - RESOURCE_STATS), "resources": set(RESOURCE_STATS),
        "op_kinds": set(OP_KINDS), "ops": set(OPS), "targets": set(TARGETS), "events": set(EVENTS),
        "triggers": set(TRIGGER_KINDS), "flags": set(FLAGS), "value_forms": {"flat", "pct", "pct_of", "ref"},
        "features": {"scale.cap", "scale.floor", "scale.factor", "op.when", "op.fail", "op.duration", "op.cooldown",
                     "op.extend", "trigger.filter", "trigger.owner_has", "trigger.cross", "named_predicate",
                     "effect.amplify", "effect.threshold", "effect.cooldown", "amplify.while_buff"},
    }
    return {k: (used[k] & universe[k], universe[k]) for k in universe}


def check_coverage(item: dict) -> Check:
    cov, ms = _timed(coverage, item)
    total = sum(len(a) for _u, a in cov.values())
    hit = sum(len(u) for u, _a in cov.values())
    missing = [f"{dim}: {', '.join(sorted(a - u))}" for dim, (u, a) in cov.items() if a - u]
    # покрытие - информация, а не ошибка: обычный предмет и не должен трогать всю схему
    return Check("coverage", True, f"{hit}/{total} schema features ({hit / total:.0%})", ms, missing)


def check_item(item: dict, pred_samples: int = 200, seed: int = 0,
               backends: Optional[list[str]] = None) -> Report:
    backends = lua_bridge.available_backends() if backends is None else backends
    report = Report(item.get("name", "?"), len(item.get("effects", [])))
    report.checks.append(check_validate(item))
    lua_check, lua = check_lua(item, backends)
    report.checks.append(lua_check)
    if lua is not None:
        report.checks.append(check_preds(item, lua, backends, pred_samples, seed))
    sim_check, log = check_sim(item)
    report.checks.append(sim_check)
    report.checks.append(check_determinism(item, log))
    report.checks.append(check_coverage(item))
    return report


# ---------------------------------------------------------------- CLI

def load_any(path: str) -> dict:
    p = Path(path)
    if p.suffix == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    return lua_bridge.load(p)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("item", nargs="?", help="item .lua or .json (default: forge one)")
    ap.add_argument("--forge", type=int, metavar="N", help="forge an item with N random effects on top of full coverage")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--hostile", action="store_true", help="forge unrestricted conditions (hunt Python/Lua divergences)")
    ap.add_argument("--samples", type=int, default=200, help="random contexts for the predicate parity check")
    ap.add_argument("--backend", action="append", help="only these Lua backends (rust, lupa)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save", metavar="PATH", help="write the forged item as Lua")
    args = ap.parse_args(argv)
    if args.item:
        item = load_any(args.item)
    else:
        from .forge import forge_item
        item = forge_item(args.forge or 0, seed=args.seed, hostile=args.hostile)
        if args.save:
            Path(args.save).write_text(render_item({"name": item["name"], "description": item["description"]},
                                                   item["effects"]), encoding="utf-8")
    report = check_item(item, pred_samples=args.samples, seed=args.seed, backends=args.backend)
    print(json.dumps(report.to_json(), ensure_ascii=False) if args.json else "\n".join(report.lines()))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
