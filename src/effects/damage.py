"""The damage pipeline: ONE place that turns "a hit of N points" into "this much HP lost".

Formulas live in the Rust kernel (rust_core/src/combat/mod.rs, `rust_core.resolve_hit` / `resolve_hits`); this module is
its Python twin (the SEMANTICS are defined here, and it is the fallback when rust_core is missing or too old) plus the
driver that draws the dice. Same dispatch as src/gameplay/pathfinding.py: BACKEND = "rust" | "python",
AI_EVOLVE_DAMAGE=python (or backend="python" in a call) forces the twin. tests/test_damage_pipeline.py checks the two
against each other bit for bit. Stage table, units and the roll order: docs/DAMAGE_PIPELINE.md. Numbers a designer tunes:
lua_content/damage.lua (loaded by `config()`; AI_EVOLVE_DAMAGE_LUA=path swaps the file, for tests and experiments).

The kernel is pure: `resolve_hit(params, rolls, consts) -> Outcome`. The dice are drawn by the caller, so the RNG (and
every seed) stays in Python. `rolls` = 5 uniform [0, 1) numbers; NaN = "not drawn yet". A stage that needs a NaN roll
stops with `Outcome.need = index + 1`; `roll_hit` draws exactly that one and asks again. Which rolls a hit consumes is
therefore decided by the kernel alone (a dodged hit never draws a crit roll), and a roll that no stage needs is never
drawn: with neutral stats a hit draws (dodge, crit) as before the pipeline existed, so seeds keep their traces.
"""
from __future__ import annotations

import logging
import os
from array import array
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple, Optional, Sequence

try:
    import rust_core as _rc
except ImportError:
    _rc = None

logger = logging.getLogger(__name__)

_RUST_OK = getattr(_rc, "resolve_hit", None) is not None and getattr(_rc, "resolve_hits", None) is not None

ENV = "AI_EVOLVE_DAMAGE"
LUA_ENV = "AI_EVOLVE_DAMAGE_LUA"
BACKEND = "rust" if _RUST_OK and os.environ.get(ENV, "").strip().lower() != "python" else "python"

# ---------------------------------------------------------------- the ABI (order = the Rust side, do not shuffle)

# flag bits of params.flags
F_TRUE, F_NO_CRIT, F_CERTAIN, F_BROKEN = 1, 2, 4, 8     # true damage: no armor, no min-damage floor (resist still applies)
# rolls[i]
R_ACCURACY, R_DODGE, R_BLOCK, R_CRIT, R_VARIANCE = range(5)
ROLLS = 5


class Params(NamedTuple):
    """One hit, all floats. Units in docs/DAMAGE_PIPELINE.md; neutral = the value in brackets."""
    amount: float          # points before any stage
    flags: float           # F_* bits (0)
    accuracy: float        # attacker, points of hit chance (0)
    evasion: float         # target, points of hit chance (0)
    dodge: float           # target, chance 0..1 (0)
    block_chance: float    # target, percent (0)
    block_bonus: float     # target, percent points added to the block reduction of damage.lua (0)
    crit_chance: float     # attacker, chance 0..1 (0)
    crit_mult: float       # attacker, multiplier (1.5)
    type_mod: float        # attacker, percent bonus of this damage type (0)
    resist: float          # target, percent resistance to this damage type (0)
    resist_pen: float      # attacker, percent points taken off a positive resist (0)
    armor: float           # target (0)
    pen_pct: float         # attacker, percent of armor ignored (0)
    pen_flat: float        # attacker, armor points ignored (0)
    taken: float           # target, percent more damage taken (0)


class Consts(NamedTuple):
    """The numbers of lua_content/damage.lua -> constants (see there)."""
    hit_base: float
    hit_min: float
    hit_max: float
    block_reduction: float
    armor_k: float         # 0 = subtractive armor, > 0 = percent curve k / (k + armor)
    resist_min: float
    resist_max: float
    immune_at: float
    broken_mult: float
    min_damage: float
    variance: float


class Outcome(NamedTuple):
    """Everything a hit did. Flags are 0/1. `need` != 0: the kernel wants roll `need - 1`, the rest is not computed."""
    need: int
    hit: int               # the accuracy stage let it through (a dodged hit is hit=1 dodged=1)
    dodged: int
    blocked: int           # the block roll succeeded (NOT the iframe invulnerability of HitInfo.invulnerable)
    crit: int
    damage_before: float   # amount x type modifier x variance x crit, before armor / resist / block
    armor_ignored: float   # armor points removed by penetration
    armor_reduced: float   # what the armor stage took (negative armor adds)
    resisted: float        # what the resistance took (all of it for an immune target)
    blocked_amount: float  # what the block took
    final: float           # points to subtract from HP (before the HP cap and the iframe check)


PARAMS = Params._fields
CONSTS = Consts._fields
OUT_FIELDS = Outcome._fields
NAN = float("nan")

_MISS = Outcome(0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
_DODGED = _MISS._replace(hit=1, dodged=1)


# ---------------------------------------------------------------- the kernel (Python twin of rust_core/src/combat)

class _Need(Exception):
    """Internal: stage wants a roll that is not drawn yet."""

    def __init__(self, index: int):
        super().__init__(index)
        self.index = index


def _roll(rolls: Sequence[float], i: int) -> float:
    v = rolls[i]
    if v != v:
        raise _Need(i)
    return v


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


def _fmax(a: float, b: float) -> float:
    return a if a > b else b


def _stage_hit(p: Params, c: Consts, rolls: Sequence[float]) -> bool:
    chance = _clamp(c.hit_base + p.accuracy - p.evasion, c.hit_min, c.hit_max)
    return chance >= 100.0 or _roll(rolls, R_ACCURACY) < chance / 100.0


def _stage_block(p: Params, rolls: Sequence[float]) -> bool:
    return p.block_chance > 0.0 and _roll(rolls, R_BLOCK) < p.block_chance / 100.0


def _stage_amount(p: Params, c: Consts, rolls: Sequence[float], crit: bool, avoidable: bool) -> float:
    m = 1.0 + p.type_mod / 100.0
    dmg = p.amount * (m if m > 0.0 else 0.0)
    if avoidable and c.variance > 0.0:
        dmg *= 1.0 + c.variance * (2.0 * _roll(rolls, R_VARIANCE) - 1.0)
    return dmg * p.crit_mult if crit else dmg


def _armor_eff(p: Params) -> float:
    """armor x (1 - pen%) - flat, never below 0; armor <= 0 is not penetrated (it stays: extra damage, as before)."""
    if p.armor <= 0.0:
        return p.armor
    return _fmax(0.0, p.armor * (1.0 - _clamp(p.pen_pct, 0.0, 100.0) / 100.0) - _fmax(p.pen_flat, 0.0))


def _stage_armor(p: Params, c: Consts, dmg: float) -> tuple[float, float]:
    eff = _armor_eff(p)
    if c.armor_k > 0.0:
        after = dmg * (c.armor_k / (c.armor_k + _fmax(eff, -0.5 * c.armor_k)))
    else:
        after = dmg - eff
    return _fmax(c.min_damage, after), p.armor - eff


def _stage_resist(p: Params, c: Consts, dmg: float) -> Optional[float]:
    """Damage after the resistance; None = immune (raw resist >= immune_at)."""
    if p.resist >= c.immune_at:
        return None
    eff = p.resist if p.resist <= 0.0 else _fmax(0.0, p.resist - _fmax(p.resist_pen, 0.0))
    return dmg * (1.0 - _clamp(eff, c.resist_min, c.resist_max) / 100.0)


def _stage_final(p: Params, c: Consts, dmg: float, flags: int) -> float:
    mult = _fmax(1.0 + p.taken / 100.0, 0.0)
    if flags & F_BROKEN:
        mult *= c.broken_mult
    out = dmg * mult
    return out if flags & F_TRUE else _fmax(c.min_damage, out)


def _mitigate(p: Params, c: Consts, flags: int, before: float, blocked: bool) -> tuple:
    """armor -> resist -> block -> final modifiers: (armor_ignored, armor_reduced, resisted, blocked_amount, final).
    True damage skips the armor stage (and every min-damage floor) - like `true_damage` always did."""
    after_armor, ignored = (before, 0.0) if flags & F_TRUE else _stage_armor(p, c, before)
    after_resist = _stage_resist(p, c, after_armor)
    if after_resist is None:
        return ignored, before - after_armor, after_armor, 0.0, 0.0
    after_block = after_resist
    if blocked:
        after_block = after_resist * (1.0 - _clamp(c.block_reduction + p.block_bonus, 0.0, 100.0) / 100.0)
    return (ignored, before - after_armor, after_armor - after_resist, after_resist - after_block,
            _stage_final(p, c, after_block, flags))


def _resolve(p: Params, c: Consts, rolls: Sequence[float]) -> Outcome:
    flags = int(p.flags)
    avoidable = not flags & F_CERTAIN
    if avoidable:
        if not _stage_hit(p, c, rolls):
            return _MISS
        if _roll(rolls, R_DODGE) < p.dodge:
            return _DODGED
    blocked = avoidable and not flags & F_TRUE and _stage_block(p, rolls)
    crit = not flags & F_NO_CRIT and _roll(rolls, R_CRIT) < p.crit_chance
    before = _stage_amount(p, c, rolls, crit, avoidable)
    return Outcome(0, 1, 0, int(blocked), int(crit), before, *_mitigate(p, c, flags, before, blocked))


def resolve_hit_py(params: Sequence[float], rolls: Sequence[float], consts: Sequence[float]) -> Outcome:
    """The pure kernel, Python twin. `params` in PARAMS order, `rolls` = ROLLS numbers (NaN = not drawn), `consts` in
    CONSTS order. Same result as rust_core.resolve_hit."""
    try:
        return _resolve(Params(*params), Consts(*consts), rolls)
    except _Need as need:
        return _MISS._replace(need=need.index + 1)


def resolve_hits_py(params_cols: Sequence[Sequence[float]], rolls_cols: Sequence[Sequence[float]],
                    consts: Sequence[float]) -> tuple:
    """Batch twin: one column per PARAMS / roll, result = one array('d') per OUT_FIELDS."""
    c = Consts(*consts)
    out = [array("d") for _ in OUT_FIELDS]
    for row, rolls in zip(zip(*params_cols, strict=True), zip(*rolls_cols, strict=True), strict=True):
        try:
            res = _resolve(Params(*row), c, rolls)
        except _Need as need:
            res = _MISS._replace(need=need.index + 1)
        for col, v in zip(out, res, strict=True):
            col.append(float(v))
    return tuple(out)


# ---------------------------------------------------------------- dispatch

def available_backends() -> tuple:
    return ("python", "rust") if _RUST_OK else ("python",)


def _use_rust(backend: Optional[str]) -> bool:
    if backend is None:
        return BACKEND == "rust"
    if backend == "python":
        return False
    if backend == "rust":
        if not _RUST_OK:
            raise RuntimeError("rust_core has no damage kernel (cd rust_core && maturin develop --release)")
        return True
    raise ValueError(f"unknown backend {backend!r}: expected 'rust' or 'python'")


def resolve_hit(params: Sequence[float], rolls: Sequence[float], consts: Sequence[float],
                backend: Optional[str] = None) -> Outcome:
    """One hit through the kernel of the chosen backend (see the module doc)."""
    if _use_rust(backend):
        return Outcome(*_rc.resolve_hit(list(params), list(rolls), list(consts)))
    return resolve_hit_py(params, rolls, consts)


def _buffer(col: Any) -> Any:
    """The Rust batch reads buffers (array('d'), numpy); a plain list becomes an array('d')."""
    try:
        memoryview(col)
    except TypeError:
        return array("d", col)
    return col


def resolve_hits(params_cols: Sequence[Any], rolls_cols: Sequence[Any], consts: Sequence[float],
                 backend: Optional[str] = None) -> tuple:
    """Many hits from columns (array('d') / numpy / plain lists), one column per PARAMS and per roll. Rolls must be
    complete for every hit that needs them; a row with `need` != 0 lacks one. Returns one array('d') per OUT_FIELDS."""
    if _use_rust(backend):
        cols = []
        for raw in _rc.resolve_hits([_buffer(c) for c in params_cols], [_buffer(c) for c in rolls_cols], list(consts)):
            col = array("d")
            col.frombytes(raw)
            cols.append(col)
        return tuple(cols)
    return resolve_hits_py(params_cols, rolls_cols, consts)


def roll_hit(params: Sequence[float], rng: Any, consts: Sequence[float], backend: Optional[str] = None) -> Outcome:
    """Resolve one hit drawing the dice from `rng.random()` one at a time, exactly the ones the kernel asks for."""
    rolls = [NAN] * ROLLS
    while True:
        out = resolve_hit(params, rolls, consts, backend)
        if not out.need:
            return out
        rolls[out.need - 1] = rng.random()


# ---------------------------------------------------------------- config: lua_content/damage.lua

# Same data as lua_content/damage.lua (works without a Lua backend; tests/test_damage_pipeline.py keeps them equal)
DEFAULT_DATA: dict[str, Any] = {
    "default_type": "physical",
    "types": [{"id": t, "resist": 0, "mod": 0} for t in ("physical", "fire", "ice", "lightning", "poison", "holy", "dark")],
    "constants": {
        "hit": {"base": 100, "min": 5, "max": 100},
        "armor": {"curve": "subtractive", "k": 100},
        "resist": {"min": -100, "max": 90, "immune_at": 100},
        "block": {"reduction": 50},
        "broken": 1.15,
        "min_damage": 1.0,
        "variance": 0.0,
        "crit": {"default_mult": 1.5},
    },
}
CURVES = ("subtractive", "percent")


@dataclass(frozen=True)
class DamageConfig:
    """lua_content/damage.lua, resolved."""
    default_type: str
    types: tuple                 # damage type ids, damage.lua order
    type_defaults: dict          # id -> {"resist": default of resist_<id>, "mod": default of damage_<id>}
    consts: tuple                # kernel constants, CONSTS order
    crit_mult_default: float     # crit multiplier of a unit that has none


def _merge(base: dict, data: dict) -> dict:
    out = dict(base)
    for k, v in data.items():
        out[k] = _merge(base[k], v) if isinstance(base.get(k), dict) and isinstance(v, dict) else v
    return out


def config_from_data(data: Optional[dict] = None) -> DamageConfig:
    """damage.lua data (missing keys fall back to DEFAULT_DATA) -> DamageConfig; ValueError for nonsense."""
    d = _merge(DEFAULT_DATA, data or {})
    k = d["constants"]
    if k["armor"]["curve"] not in CURVES:
        raise ValueError(f"damage.lua: armor.curve {k['armor']['curve']!r} is not one of {CURVES}")
    types = [t for t in d["types"] if isinstance(t, dict) and t.get("id")]
    ids = tuple(t["id"] for t in types)
    if d["default_type"] not in ids:
        raise ValueError(f"damage.lua: default_type {d['default_type']!r} is not in types {ids}")
    consts = Consts(
        hit_base=float(k["hit"]["base"]), hit_min=float(k["hit"]["min"]), hit_max=float(k["hit"]["max"]),
        block_reduction=float(k["block"]["reduction"]),
        armor_k=float(k["armor"]["k"]) if k["armor"]["curve"] == "percent" else 0.0,
        resist_min=float(k["resist"]["min"]), resist_max=float(k["resist"]["max"]),
        immune_at=float(k["resist"]["immune_at"]),
        broken_mult=float(k["broken"]), min_damage=float(k["min_damage"]), variance=float(k["variance"]))
    return DamageConfig(default_type=d["default_type"], types=ids,
                        type_defaults={t["id"]: {"resist": float(t.get("resist", 0)), "mod": float(t.get("mod", 0))}
                                       for t in types},
                        consts=tuple(consts), crit_mult_default=float(k["crit"]["default_mult"]))


def load_config(path: Any) -> DamageConfig:
    """Config from a damage.lua file (any copy: tests tune a constant in a tmp file)."""
    from ..content import lua_bridge
    return config_from_data(lua_bridge.load(Path(path), cache=True))


@lru_cache(maxsize=1)
def config() -> DamageConfig:
    """The live config: lua_content/damage.lua (or AI_EVOLVE_DAMAGE_LUA), DEFAULT_DATA without a Lua backend."""
    try:
        from ..content import lua_bridge
        path = Path(os.environ.get(LUA_ENV) or lua_bridge.CONTENT / "damage.lua")
        return load_config(path)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:   # no Lua backend / no file: the built-in copy
        logger.warning("damage: damage.lua not loaded (%s), built-in defaults", exc)
        return config_from_data()


def damage_type(tags: Sequence[str], cfg: Optional[DamageConfig] = None) -> str:
    """Type of a hit = the first tag that names a damage type, else the default type."""
    cfg = cfg or config()
    return next((t for t in tags if t in cfg.types), cfg.default_type)


# ---------------------------------------------------------------- the hit's string flags <-> the kernel ABI

TYPE_PREFIX = "type:"                                   # a non-default damage type rides in the hit's flag set
CERTAIN_FLAGS = frozenset({"true_damage", "unavoidable", "periodic"})     # cannot miss / dodge / be blocked
NO_CRIT_FLAGS = frozenset({"no_crit", "periodic"})


def type_flags(tags: Sequence[str], cfg: Optional[DamageConfig] = None) -> set:
    """{"type:fire"} for a tag that names a non-default damage type, else {} (default type = no flag)."""
    cfg = cfg or config()
    kind = damage_type(tags, cfg)
    return set() if kind == cfg.default_type else {TYPE_PREFIX + kind}


def type_of_flags(flags: Any, cfg: Optional[DamageConfig] = None) -> str:
    """Inverse of type_flags: the damage type a hit's flag set carries."""
    cfg = cfg or config()
    return next((f[len(TYPE_PREFIX):] for f in flags if f.startswith(TYPE_PREFIX)), cfg.default_type)


def flag_bits(flags: Any, broken: bool = False) -> int:
    """Hit flag names (true_damage, no_crit, unavoidable, periodic) -> the F_* bits of Params.flags."""
    flags = frozenset(flags)
    return ((F_TRUE if "true_damage" in flags else 0) | (F_NO_CRIT if NO_CRIT_FLAGS & flags else 0)
            | (F_CERTAIN if CERTAIN_FLAGS & flags else 0) | (F_BROKEN if broken else 0))


def cc_adjust(final: float, flat: float, reduction_pct: float, mult: float) -> float:
    """Hit on a CC'd target, after the kernel (docs/DAMAGE_PIPELINE.md): (d - flat) * (1 - pct/100) * mult, >= 0.
    Defaults (0, 0, 1.0) return `final` unchanged."""
    if not flat and not reduction_pct and mult == 1.0:
        return final
    return max(0.0, (final - flat) * (1.0 - reduction_pct / 100.0)) * mult


def fill_info(info: Any, out: Outcome, kind: str) -> None:
    """Copy an Outcome into a HitInfo-like object (manager.HitInfo): the flags and the per-stage amounts."""
    info.is_dodged, info.missed = bool(out.dodged), not out.hit
    info.is_critical, info.blocked, info.hit_type = bool(out.crit), bool(out.blocked), kind
    info.damage_before, info.armor_ignored, info.armor_reduced = out.damage_before, out.armor_ignored, out.armor_reduced
    info.resisted, info.blocked_amount = out.resisted, out.blocked_amount

