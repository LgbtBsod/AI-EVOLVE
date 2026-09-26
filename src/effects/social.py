"""Slice G1b: SOCIAL ops and RESOURCE POOLS (every number lives in lua effect_rules.lua `social`).

  reputation    per-faction standing of the CASTER (unit.external["reputation"][faction]), clamped, with named tiers; `gate` = the op is
                refused below that tier; `on_tier` = {tier_id: [ops]} run (caster -> target) when the standing ENTERS that tier.
  diplomacy     a timed relation between two factions (ceasefire | alliance | war) built on the F2 aggro / faction seams; expiry restores
                the saved faction and aggro of every member. Costs the caster; capped by `max_treaties`.
  contract      bilateral binding caster <-> target: `a_ops` / `b_ops` at signing, an optional debt (principal, `interest` {rate, every} = a
                periodic tick, capped by `max_debt_mult`), `breach` {penalty_ops} on unpaid expiry or an explicit `action = "breach"`.
                `action = "settle"` pays debt from a resource. NOT a market: no prices, no stock.
  fuel_consume  draw from a POOL of the CASTER (instant `amount`, or a burn `rate` x `duration`); `then` ops run on the target when the draw
                is granted. An overdraw goes into debt when the pool `allow_debt`s (up to `debt_limit`) and fires its `debt_effect` (chance
                rolled on the seeded stream); the end of a burn fires the pool `end_effect` (the crash).
  pool          grant | set | spend | use on a pool of the target (`use` = consume up to `count` units, `then` ops per unit, `die` = seeded roll).
Everything is opt-in and deterministic (game clock, `h.op_roll`). EffectRuntime (training room) only logs, like F1-F8.
"""
from __future__ import annotations

from typing import Any

SOCIAL_FEATURES = ("faction.treaty_duration", "economy.compound_interest", "economy.debt_tracking", "burn.duration_debt_crash",
                   "resource.granted_die_pool", "heal.lifesteal_on_hit_count", "cost.warp_perils_risk")


def cfg() -> dict:
    from .runtime import rules
    try:
        from ..content import lua_bridge
        return lua_bridge.load(lua_bridge.CONTENT / "effect_rules.lua", cache=True).get("social") or {}
    except (ImportError, RuntimeError, OSError, ValueError):
        return rules().get("social") or {}


class SocialState:
    """Timed records of the social ops; `busy()` false = `update` does nothing."""

    def __init__(self) -> None:
        self.treaties: list[dict] = []
        self.contracts: list[dict] = []
        self.burns: list[dict] = []
        self.owners: dict[int, Any] = {}       # id(entity) -> state of an owner of a regenerating pool
        self.last: float | None = None
        self.log: list[dict] = []

    def busy(self) -> bool:
        return bool(self.treaties or self.contracts or self.burns or self.owners)


def _hosted(h: Any, cx: Any, name: str, tgt: Any = None) -> bool:
    if hasattr(h, "soc_state"):
        return True
    h.op_note(cx, name, tgt, "room")
    return False


def _refuse(h: Any, why: str) -> None:
    h.soc_state().log.append({"t": h.now, "refused": why})


def _ext(st: Any) -> dict:
    return st.unit.external


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _run(h: Any, src: Any, ops: Any, tgt: Any, tag: str) -> None:
    if ops:
        h.op_run_nested(src, list(ops), tgt.entity if hasattr(tgt, "entity") else tgt, tag)


# ---------------------------------------------------------------- reputation
def _tier(c: dict, value: float) -> tuple[int, str]:
    idx = 0
    for i, t in enumerate(c["tiers"]):
        if value >= t["at"]:
            idx = i
    return idx, c["tiers"][idx]["id"]


def standing(st: Any, faction: str) -> float:
    return float((_ext(st).get("reputation") or {}).get(faction, 0.0))


def tier_id(st: Any, faction: str) -> str:
    return _tier(cfg().get("reputation") or {}, standing(st, faction))[1]


def _gate_ok(c: dict, cur: float, gate: Any) -> bool:
    ids = [t["id"] for t in c["tiers"]]
    return not gate or (gate in ids and _tier(c, cur)[0] >= ids.index(gate))


def op_reputation(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if not _hosted(h, cx, "reputation", tgt):
        return
    c = cfg().get("reputation") or {}
    fac = str(o.get("faction") or tgt.faction)
    reps = _ext(cx.source).setdefault("reputation", {})
    cur = float(reps.get(fac, 0.0))
    if not _gate_ok(c, cur, o.get("gate")):
        _refuse(h, f"reputation:gate:{fac}")
        return
    delta = _clamp(float(o.get("delta", 0.0)), -float(c["max_delta"]), float(c["max_delta"]))
    reps[fac] = new = _clamp(cur + delta, float(c["min"]), float(c["max"]))
    old_t, new_t = _tier(c, cur)[1], _tier(c, new)[1]
    h.op_note(cx, "reputation", tgt, fac, new_t)
    if old_t != new_t:
        _run(h, cx.source, (o.get("on_tier") or {}).get(new_t), tgt, f"reputation:{fac}:{new_t}")


# ---------------------------------------------------------------- diplomacy
def relation(h: Any, a: str, b: str) -> str | None:
    """Data for the AI: the active treaty between two factions (either order), or None."""
    for t in h.soc_state().treaties:
        if {t["a"], t["b"]} == {a, b}:
            return t["rel"]
    return None


def _enter(h: Any, cx: Any, s: Any, rel: dict, a: str) -> tuple:
    ext = _ext(s)
    saved = (s.faction, dict(ext["aggro"]) if "aggro" in ext else None)
    if rel.get("merge"):
        s.faction = a
    if rel.get("aggro_mode"):
        ag = h.op_aggro(cx, s)
        ag["aggro_mode"] = rel["aggro_mode"]
        h.set_aggro(cx, s, **ag)
    return saved


def _leave(s: Any, saved: tuple) -> None:
    s.faction = saved[0]
    if saved[1] is None:
        _ext(s).pop("aggro", None)
    else:
        _ext(s)["aggro"] = saved[1]


def _end_treaty(h: Any, t: dict) -> None:
    for s, saved in reversed(t["members"]):
        _leave(s, saved)
    h.soc_state().treaties.remove(t)


def _can_pay(h: Any, cx: Any, cost: dict | None) -> bool:
    return not cost or h.op_resource(cx.source, cost["resource"]) >= float(cost["amount"])


def _treaty_ok(h: Any, cx: Any, c: dict, rel: str, pair: tuple) -> bool:
    live = h.soc_state().treaties
    same = [t for t in live if {t["a"], t["b"]} == set(pair)]
    if rel not in (c.get("relations") or {}) or pair[0] == pair[1] or (len(live) - len(same) >= int(c["max_treaties"])):
        return False
    if not _can_pay(h, cx, c.get("cost")):
        return False
    for t in same:
        _end_treaty(h, t)
    if c.get("cost"):
        h.op_spend(cx, cx.source, c["cost"]["resource"], float(c["cost"]["amount"]), False)
    return True


def op_diplomacy(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if not _hosted(h, cx, "diplomacy", tgt):
        return
    c, rel = cfg().get("diplomacy") or {}, str(o.get("relation", "ceasefire"))
    a, b = str(o.get("a") or cx.source.faction), str(o.get("b") or tgt.faction)
    if not _treaty_ok(h, cx, c, rel, (a, b)):
        _refuse(h, f"diplomacy:{rel}")
        return
    dur = min(float(h.op_duration(o.get("duration", {"flat": 30}), cx.ctx)), float(c["max_duration"]))
    rule = c["relations"][rel]
    members = [(s, _enter(h, cx, s, rule, a)) for s in list(h.states.values()) if s.faction in (a, b)]
    h.soc_state().treaties.append({"a": a, "b": b, "rel": rel, "until": h.now + dur, "members": members})
    h.op_note(cx, "diplomacy", tgt, rel, dur)


# ---------------------------------------------------------------- contract
def debt_of(st: Any, cid: str) -> float:
    return float((_ext(st).get("debt") or {}).get(cid, 0.0))


def _sign_ok(h: Any, c: dict, cid: str) -> bool:
    live = h.soc_state().contracts
    return len(live) < int(c["max_contracts"]) and not any(k["id"] == cid for k in live)


def _sign(h: Any, cx: Any, tgt: Any, o: dict) -> None:
    c, cid = cfg().get("contract") or {}, str(o.get("id", "contract"))
    if not _sign_ok(h, c, cid) or tgt is cx.source:
        _refuse(h, f"contract:{cid}")
        return
    dur = min(float(h.op_duration(o.get("duration", {"flat": 30}), cx.ctx)), float(c["max_duration"]))
    it = o.get("interest") or {}
    rec = {"id": cid, "a": cx.source, "b": tgt, "until": h.now + dur, "principal": float(o.get("principal", 0.0)),
           "rate": float(it.get("rate", 0.0)), "every": max(float(c["min_every"]), float(it.get("every", 5.0))),
           "next": h.now + max(float(c["min_every"]), float(it.get("every", 5.0))), "breach": o.get("breach") or {}, "pay": o.get("pay_resource", "mana"),
           "fulfilled": o.get("fulfilled_ops")}
    h.soc_state().contracts.append(rec)
    if rec["principal"]:
        _ext(tgt).setdefault("debt", {})[cid] = rec["principal"]
    _run(h, cx.source, o.get("a_ops"), cx.source, f"contract:{cid}.a")
    _run(h, cx.source, o.get("b_ops"), tgt, f"contract:{cid}.b")
    h.op_note(cx, "contract", tgt, cid)


def _find(h: Any, cid: str) -> dict | None:
    return next((k for k in h.soc_state().contracts if k["id"] == cid), None)


def _close(h: Any, k: dict, why: str) -> None:
    h.soc_state().contracts.remove(k)
    (_ext(k["b"]).get("debt") or {}).pop(k["id"], None)
    h.soc_state().log.append({"t": h.now, "contract": k["id"], "closed": why})


def breach(h: Any, k: dict, why: str = "breach") -> None:
    """The breach rule: the debtor (party b) takes `penalty_ops` from the creditor; the contract closes."""
    _run(h, k["a"], k["breach"].get("penalty_ops"), k["b"], f"contract:{k['id']}.breach")
    _close(h, k, why)


def _settle(h: Any, cx: Any, o: dict) -> None:
    k = _find(h, str(o.get("id", "contract")))
    if k is None:
        _refuse(h, "contract:settle")
        return
    owed = debt_of(k["b"], k["id"])
    pay = min(owed, float(o.get("amount", owed)), float(h.op_resource(k["b"], k["pay"])))
    if pay > 0:
        h.op_spend(cx, k["b"], k["pay"], pay, False)
        _ext(k["b"])["debt"][k["id"]] = owed - pay
    if debt_of(k["b"], k["id"]) <= 1e-9:
        _run(h, k["a"], k["fulfilled"], k["b"], f"contract:{k['id']}.done")
        _close(h, k, "fulfilled")


def op_contract(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if not _hosted(h, cx, "contract", tgt):
        return
    act = o.get("action", "sign")
    if act == "sign":
        _sign(h, cx, tgt, o)
    elif act == "settle":
        _settle(h, cx, o)
    elif act == "breach" and _find(h, str(o.get("id"))) is not None:
        breach(h, _find(h, str(o["id"])))
    else:
        _refuse(h, f"contract:{act}")


def _tick_contract(h: Any, k: dict, now: float, cap: float) -> None:
    from .manager import is_alive
    if not (is_alive(k["a"].entity) and is_alive(k["b"].entity)):
        _close(h, k, "void")
        return
    owed = debt_of(k["b"], k["id"])
    while k["rate"] and owed > 0 and now >= k["next"] and k["next"] <= k["until"]:
        owed = min(owed * (1.0 + k["rate"]), k["principal"] * cap)
        k["next"] += k["every"]
    if owed > 0:
        _ext(k["b"])["debt"][k["id"]] = owed
    if now >= k["until"]:
        breach(h, k, "expired_unpaid") if owed > 1e-9 else _close(h, k, "expired")


# ---------------------------------------------------------------- pools
def _spec(name: str) -> dict | None:
    return (cfg().get("pools") or {}).get(name)


def pool(h: Any, st: Any, name: str) -> dict:
    spec = _spec(name) or {}
    p = _ext(st).setdefault("pools", {}).get(name)
    if p is None:
        p = _ext(st)["pools"][name] = {"v": float(spec.get("start", spec.get("max", 0.0))), "debt": 0.0}
    if float(spec.get("regen", 0.0)) > 0 and hasattr(h, "soc_state"):
        h.soc_state().owners[id(st.entity)] = st
    return p


def _overdraw(h: Any, cx: Any, st: Any, name: str, short: float) -> bool:
    spec, p = _spec(name) or {}, pool(h, st, name)
    if not spec.get("allow_debt") or p["debt"] + short > float(spec.get("debt_limit", 0.0)):
        return False
    fresh = p["debt"] <= 0.0
    p["v"], p["debt"] = 0.0, p["debt"] + short
    eff = spec.get("debt_effect") or {}
    if fresh and eff and h.op_roll(cx) < float(eff.get("chance", 1.0)):
        _run(h, st, eff.get("ops"), st, "pool:debt")
    return True


def draw(h: Any, cx: Any, st: Any, name: str, amount: float) -> bool:
    """Take `amount` from the pool of `st`; False = refused (unknown pool, or short and no debt room)."""
    spec = _spec(name)
    if spec is None:
        return False
    p = pool(h, st, name)
    if p["v"] >= amount:
        p["v"] -= amount
        return True
    return _overdraw(h, cx, st, name, amount - p["v"])


def op_fuel_consume(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if not _hosted(h, cx, "fuel_consume", tgt):
        return
    name = str(o.get("pool", ""))
    rate, dur = float(o.get("rate", 0.0)), float(h.op_duration(o.get("duration", {"flat": 0}), cx.ctx))
    first = rate * min(dur, 1.0) if rate else float(o.get("amount", 0.0))
    if _spec(name) is None or not draw(h, cx, cx.source, name, first):
        _refuse(h, f"fuel:{name}")
        return
    _run(h, cx.source, o.get("then"), tgt, f"fuel:{name}")
    if rate and dur > 0:
        h.soc_state().last = h.now if h.soc_state().last is None else h.soc_state().last
        h.soc_state().burns.append({"owner": cx.source, "pool": name, "rate": rate, "until": h.now + dur, "left": dur - min(dur, 1.0), "cx": cx})
    h.op_note(cx, "fuel_consume", tgt, name)


def _end_burn(h: Any, b: dict) -> None:
    h.soc_state().burns.remove(b)
    _run(h, b["owner"], (_spec(b["pool"]) or {}).get("end_effect"), b["owner"], f"fuel:{b['pool']}:end")


def _tick_burn(h: Any, b: dict, dt: float) -> None:
    step = min(dt, b["left"])
    b["left"] -= step
    if step > 0 and not draw(h, b["cx"], b["owner"], b["pool"], b["rate"] * step):
        b["left"] = 0.0
    if b["left"] <= 1e-9:
        _end_burn(h, b)


def _use(h: Any, cx: Any, tgt: Any, o: dict) -> None:
    name = str(o.get("pool", ""))
    spec, p = _spec(name) or {}, pool(h, cx.source, name)
    n = int(min(float(o.get("count", 1)), p["v"], int(spec["max"])))
    for _ in range(max(0, n)):
        p["v"] -= 1
        if o.get("die"):
            roll = int(h.op_roll(cx) * int(spec.get("die", 6))) + 1
            h.op_apply_op(cx, tgt, {"kind": "mod", "stat": o.get("stat", "attack_damage"), "op": "add", "value": {"flat": roll},
                                    "duration": o.get("duration", {"flat": 10})})
            _ext(cx.source).setdefault("dice", []).append(roll)
        _run(h, cx.source, o.get("then"), tgt, "pool:use")


def op_pool(h: Any, cx: Any, tgt: Any, o: dict, amount: float) -> None:
    if not _hosted(h, cx, "pool", tgt):
        return
    name, act, spec = str(o.get("pool", "")), o.get("action", "grant"), _spec(str(o.get("pool", "")))
    if spec is None or act not in ("grant", "set", "spend", "use"):
        _refuse(h, f"pool:{name}")
        return
    mx, val = float(spec["max"]), float(o.get("amount", 1.0))
    if act == "use":
        _use(h, cx, tgt, o)
    elif act == "spend" and not draw(h, cx, cx.source, name, val):
        _refuse(h, f"pool:spend:{name}")
    elif act in ("grant", "set"):
        p = pool(h, tgt, name)
        p["v"] = _clamp(val if act == "set" else p["v"] + val, 0.0, mx)
    h.op_note(cx, "pool", tgt, name, act)


def _regen_pool(h: Any, st: Any, name: str, p: dict, dt: float) -> bool:
    """One pool: regen repays debt first (not while burning); True = still needs regen."""
    spec = _spec(name) or {}
    if float(spec.get("regen", 0.0)) <= 0:
        return False
    if not any(b["owner"] is st and b["pool"] == name for b in h.soc_state().burns):
        gain = float(spec["regen"]) * dt
        paid = min(gain, p["debt"])
        p["debt"] -= paid
        p["v"] = min(float(spec["max"]), p["v"] + gain - paid)
    return p["v"] < float(spec["max"]) or p["debt"] > 0


def _regen(h: Any, dt: float) -> None:
    for key, st in list(h.soc_state().owners.items()):
        if not any([_regen_pool(h, st, n, p, dt) for n, p in (_ext(st).get("pools") or {}).items()]):
            h.soc_state().owners.pop(key)


def update(h: Any) -> None:
    """Per tick (game clock): treaty expiry, contract debt ticks, burns, pool regen. Idle = nothing done."""
    s = h.soc_state()
    if not s.busy():
        s.last = h.now
        return
    dt = 0.0 if s.last is None else max(0.0, h.now - s.last)
    s.last = h.now
    for t in [t for t in s.treaties if h.now >= t["until"]]:
        _end_treaty(h, t)
    cap = float((cfg().get("contract") or {}).get("max_debt_mult", 3.0))
    for k in list(s.contracts):
        _tick_contract(h, k, h.now, cap)
    for b in list(s.burns):
        _tick_burn(h, b, dt)
    _regen(h, dt)


SOCIAL_HANDLERS = {"reputation": op_reputation, "diplomacy": op_diplomacy, "contract": op_contract,
                   "fuel_consume": op_fuel_consume, "pool": op_pool}
