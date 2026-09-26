"""
Effect Schema v1 -- reference runtime (Python)

Эталонный интерпретатор схемы Effect -> Ops[] для тестов в тренировочной
комнате. Семантика 1-в-1 совпадает с lua_gen/render:

    value = flat | pct/100 * ctx[of or stat] | ref(ctx.path)
    total = value + floor(ctx[scale.of]/scale.every) * scale.value * factor
            (steps ограничены cap/floor)

Поддерживаемые триггеры: passive(mod-модификаторы), condition(то же, пока
условие true), event(use/attack/kill/tick). Поддерживаемые ops:
mod/heal/drain/deal/set/buff/extend/remove_buff/apply_effect/kill.

Предикаты: БЕЗОПАСНЫЙ мини-язык выражений (никакого eval!). Поддерживается
грамматика: сравнения (< <= > >= == !=) над ctx.<поле>, числовыми литералами,
скобками, + - * / % ** и функциями max/min/floor/ceil/abs. Именованные
предикаты - выражения из lua_content/effect_rules.lua (predicates). Арифметика
повторяет Lua (деление на ноль -> inf/nan, а не исключение), чтобы одно и то же
условие давало один ответ в движке и здесь. Любое иное выражение отвергается PrediciationException
(ранее здесь был сырой eval, допускавший sandbox-escape через
dunder-атрибуты, например "max.__class__.__subclasses__").
"""

from __future__ import annotations

import ast
import math
import operator as _op
from functools import lru_cache
from typing import Any, Callable, Optional

from .ops import (_ALLOWED_CTX, OpCall, Periodic, Tracked, _hp_missing_below_40, apply_mod_math, apply_op,  # noqa: F401 - re-exported
                  compute_amount, ctx_get as _ctx_get, default_stat_of, derived_ctx, extend_amount, replace_contribution,
                  resolve_value, same_map)

# ---------------------------------------------------------------- stat rules

# Те же значения, что lua_content/effect_rules.lua (действуют без Lua-бэкенда)
DEFAULT_RULES: dict[str, dict] = {
    "defaults": {"max_hp": 1000.0, "max_mana": 100.0, "max_stamina": 100.0,
                 "hp_regen": 0.0, "mana_regen": 0.0, "stamina_regen": 0.0,
                 "strength": 0.0, "agility": 0.0, "intelligence": 0.0, "vitality": 0.0,
                 "wisdom": 0.0, "charisma": 0.0, "luck": 0.0, "endurance": 0.0,
                 "defense": 0.0, "tenacity": 0.0, "crit_chance": 0.0, "crit_dmg": 50.0, "aspd": 1.0,
                 "lifesteal": 0.0, "move_speed": 5.0, "attack_damage": 0.0, "spell_power": 0.0, "dodge": 0.0,
                 "attack_range": 2.0, "vision_range": 20.0},
    "resources": {"hp": {"max": "max_hp", "regen": "hp_regen"},
                  "mana": {"max": "max_mana", "regen": "mana_regen"},
                  "stamina": {"max": "max_stamina", "regen": "stamina_regen"}},
    "bounds": {"max_hp": {"min": 1}, "max_mana": {"min": 0}, "max_stamina": {"min": 0},
               "crit_chance": {"min": 0, "max": 100}, "aspd": {"min": 0.1, "max": 4}, "move_speed": {"min": 0},
               "tenacity": {"min": 0, "max": 100}, "dodge": {"min": 0, "max": 75},
               "attack_range": {"min": 0.5, "max": 30}, "vision_range": {"min": 0, "max": 80}},
    "predicates": {"low_hp_40": "ctx.hp_pct < 40"},
    "attributes": {"strength": {"attack_damage": 0.6, "max_hp": 1}, "agility": {"crit_chance": 0.15, "aspd": 0.008, "dodge": 0.1},
                   "intelligence": {"spell_power": 0.8, "max_mana": 3}, "vitality": {"max_hp": 6, "hp_regen": 0.04},
                   "wisdom": {"mana_regen": 0.08, "spell_power": 0.2, "vision_range": 0.05},
                   "endurance": {"max_stamina": 3, "stamina_regen": 0.05, "defense": 0.3},
                   "luck": {"crit_chance": 0.1, "dodge": 0.05}, "charisma": {}},
}


def _add_type_families(merged: dict, families: list) -> None:
    """Статы по типам урона: для каждого типа из lua_content/damage.lua - defaults/bounds семейств effect_rules.lua."""
    from .damage import config
    cfg = config()
    for fam in families:
        for kind in cfg.types:
            name = fam["prefix"] + kind
            merged["defaults"].setdefault(name, cfg.type_defaults[kind].get(fam.get("default_of"), 0.0))
            if fam.get("bounds"):
                merged["bounds"].setdefault(name, dict(fam["bounds"]))


@lru_cache(maxsize=1)
def rules() -> dict[str, dict]:
    """Правила статов из lua_content/effect_rules.lua поверх DEFAULT_RULES (плюс семейства статов по типам урона)."""
    merged = {k: dict(v) for k, v in DEFAULT_RULES.items()}
    try:
        from ..content import lua_bridge
        data = lua_bridge.load(lua_bridge.CONTENT / "effect_rules.lua", cache=True)
    except Exception:  # нет Lua-бэкенда или файл сломан - дефолты выше
        return merged
    for section in merged:
        merged[section].update(data.get(section) or {})
    _add_type_families(merged, data.get("families") or [])
    return merged

# ---------------------------------------------------------------- predicates

def named_predicates() -> dict[str, str]:
    """Именованные условия: имя -> выражение (lua_content/effect_rules.lua -> predicates).
    Одно определение для Python и для Lua (lua_gen кладёт их в реестр PRED файла)."""
    return dict(rules()["predicates"])

class PrediciationException(ValueError):
    """Выражение-предикат не проходит строгую whitelist-грамматику."""


# ---- безопасный AST-интерпретатор выражений предикатов -------------------

def _lua_div(a, b):
    """Lua `/`: всегда float, деление на ноль даёт ±inf или nan (Python бросает)."""
    try:
        return a / b
    except ZeroDivisionError:
        if a == 0 or math.isnan(a):
            return math.nan
        return math.copysign(math.inf, a) * math.copysign(1.0, b)


def _lua_mod(a, b):
    """Lua `%` на float - luai_nummod (lua-5.5.1/llimits.h): m = fmod(a, b), затем
    сдвиг на b, если знаки m и b разошлись. Отличие от Python - знак нуля:
    0.0 % -5.0 в Python = -0.0, в Lua = 0.0, а дальше x / ±0 даёт ±inf."""
    a, b = float(a), float(b)
    if b == 0 or math.isinf(a) or math.isnan(a) or math.isnan(b):
        return math.nan
    m = math.fmod(a, b)
    if (b < 0) if m > 0 else (m < 0 and b > 0):
        m += b
    return m


def _odd_int(y) -> bool:
    return float(y).is_integer() and int(y) % 2 == 1


def _lua_pow(a, b):
    """Lua `^` = C pow: переполнение -> inf, 0^-n -> inf, (-8)^0.5 -> nan (Python: исключение/complex).
    Порядок как в C: сначала область определения (отрицательное основание и
    нецелая степень -> nan), потом переполнение (Python для (-44.8)**82475.8
    бросает OverflowError, C даёт nan)."""
    a, b = float(a), float(b)
    if b == 2:  # luai_numpow: x^2 считается как x*x (pow может отличаться в последнем бите)
        return a * a
    if a < 0 and math.isfinite(a) and math.isfinite(b) and not b.is_integer():
        return math.nan  # pow(-inf, y) при этом +inf: проверка только для конечного основания
    try:
        r = a ** b
    except ZeroDivisionError:
        return math.copysign(math.inf, a) if _odd_int(b) else math.inf
    except OverflowError:
        return -math.inf if a < 0 and _odd_int(b) else math.inf
    return math.nan if isinstance(r, complex) else r


def _lua_round(fn):
    """floor/ceil условия: float (как pred_lua пишет их в Lua), inf/nan - как есть
    (Python на них бросает исключение)."""
    return lambda x: float(fn(x)) if math.isfinite(x) else float(x)


_BINOPS = {ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul,
           ast.Div: _lua_div, ast.Mod: _lua_mod, ast.Pow: _lua_pow}
_CMPOPS = {ast.Lt: _op.lt, ast.LtE: _op.le, ast.Gt: _op.gt,
           ast.GtE: _op.ge, ast.Eq: _op.eq, ast.NotEq: _op.ne}
_FUNCS = {"max": max, "min": min, "floor": _lua_round(math.floor), "ceil": _lua_round(math.ceil),
          "abs": abs}


def _field(key: str) -> Callable[[dict], Any]:
    if key.startswith("_"):
        raise PrediciationException(f"private attribute {key!r} forbidden")
    derived = derived_ctx(key)

    def get(ctx):
        try:
            return ctx[key]
        except KeyError:
            if derived is not None:
                return derived(ctx)
            raise PrediciationException(f"unknown ctx field {key!r}") from None
    return get


def _compile(node) -> Callable[[dict], Any]:
    """AST условия -> замыкание ctx -> значение. Белый список узлов проверяется
    один раз при компиляции (никакого eval); вызов - только замыкания, без
    повторного обхода дерева. and/or ленивые, как в Lua."""
    if isinstance(node, ast.Expression):
        return _compile(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            v = float(node.value)  # все числа условия - float, как в Lua (pred_lua)
            return lambda ctx: v
        raise PrediciationException(f"literal {node.value!r} not allowed")
    if isinstance(node, ast.Attribute):
        # разрешено ТОЛЬКО ctx.<поле>; никаких dunder-атрибутов
        if not isinstance(node.value, ast.Name) or node.value.id != "ctx":
            raise PrediciationException("attribute access must be ctx.<field>")
        return _field(node.attr)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        fn, left, right = _BINOPS[type(node.op)], _compile(node.left), _compile(node.right)
        return lambda ctx: fn(left(ctx), right(ctx))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        inner = _compile(node.operand)
        return inner if isinstance(node.op, ast.UAdd) else (lambda ctx: -inner(ctx))
    if isinstance(node, ast.Compare):
        if any(type(o) not in _CMPOPS for o in node.ops):
            raise PrediciationException("comparison operator not allowed")
        first = _compile(node.left)
        chain = [(_CMPOPS[type(o)], _compile(c)) for o, c in zip(node.ops, node.comparators)]

        def compare(ctx):
            left = first(ctx)
            for cmp, comp in chain:
                right = comp(ctx)
                if not cmp(left, right):
                    return False
                left = right
            return True
        return compare
    if isinstance(node, ast.BoolOp):
        parts = [_compile(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return lambda ctx: all(p(ctx) for p in parts)
        return lambda ctx: any(p(ctx) for p in parts)
    if isinstance(node, ast.Call):
        fn = node.func
        # вызов разрешён только простому имени из whitelist (max/min/...);
        # ctx.foo(...) и (obj).__class__(...) — запрещены
        if not isinstance(fn, ast.Name) or fn.id not in _FUNCS or node.keywords:
            raise PrediciationException("call of non-whitelisted function")
        f, args = _FUNCS[fn.id], [_compile(a) for a in node.args]
        return lambda ctx: f(*[a(ctx) for a in args])
    if isinstance(node, ast.Name):
        raise PrediciationException(f"unknown name {node.id!r} "
                                    "(only ctx.<field> and max/min/floor/ceil/abs)")
    raise PrediciationException(f"expression element not allowed: "
                                f"{type(node).__name__}")


@lru_cache(maxsize=65536)
def compile_pred(expr: str) -> Callable[[dict], Any]:
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise PrediciationException(f"invalid predicate expression {expr!r}: {e}") from e
    return _compile(tree)


def eval_pred(pred: Optional[Any], ctx: dict) -> bool:
    """Вычислить условие (строка-выражение / имя из effect_rules.lua / callable)."""
    if not pred:
        return True
    if callable(pred):
        return bool(pred(ctx))
    pred = str(pred).strip()
    named = rules()["predicates"].get(pred)
    return bool(compile_pred(named if named is not None else pred)(ctx))


# значения (resolve_value, compute_amount ...) и обработчики операций - src/effects/ops.py

# ---------------------------------------------------------------- unit

class Unit:
    """Юнит тренировки: статы + ресурсы (hp, mana, stamina) + контекст для резолва значений.

    База, ресурсы и границы итоговых статов - lua_content/effect_rules.lua."""

    def __init__(self, name: str, max_hp: float = 1000.0, derive: bool = False, **stats):
        r = rules()
        self.name = name
        # dirty-флаг: version растёт при ЛЮБОЙ записи в base / mods (Tracked) и при touch(); от него зависит
        # кэш итоговых статов (_eff) - и кэши владельцев (EntityState.refresh)
        self.version = 0
        self._eff_memo: dict[str, float] = {}
        self._eff_ver = 0
        self._base: Tracked = Tracked(self, {k: float(v) for k, v in r["defaults"].items()})
        self._mods: Tracked = Tracked(self)      # mod-эффекты (add/sub/mul/div)
        self._base["max_hp"] = float(max_hp)
        self._base.update({k: float(v) for k, v in stats.items()})
        self.bounds: dict[str, dict] = r["bounds"]
        # производные статы от характеристик (effect_rules.lua -> attributes): стат -> [(характеристика, за очко)].
        # derive=True - игра (менеджер эффектов): сила даёт урон и HP, и hp_pct условий считается
        # от настоящего максимума. False - тренировочная комната: чистая математика предмета.
        self.derived: dict[str, list[tuple[str, float]]] = {}
        for attr, conv in ((r.get("attributes") or {}) if derive else {}).items():
            for stat, k in (conv or {}).items():
                self.derived.setdefault(stat, []).append((attr, float(k)))
        # ресурс -> {max: стат максимума, regen: стат регена в секунду}
        self.resources: dict[str, dict] = r["resources"]
        self.current_hp = self._eff("max_hp")     # hp отдельно: его читает весь код комнаты
        self.pools: dict[str, float] = {}         # прочие ресурсы: mana, stamina
        self.refill()
        self.buffs: dict[str, dict] = {}          # buff_id -> {until, ...}
        # --- новые слои примитивов аудита (mark/absorb/learn/adapt) ---
        self.marks: dict[str, dict] = {}          # mark_id -> {stacks, until}
        self.spells: list[str] = []               # выученные/скопированные техники (learn)
        self.adapt_stacks: dict[str, int] = {}    # damage_type -> число адаптаций (Mahoraga)
        self.absorbed_kinetic: float = 0.0        # Поглощающее Облако: копящийся кинетический урон
        self.absorbed_until: float = 0.0          # до какого момента окно поглощения
        self.external: dict[str, Any] = {}        # внешние слои: mahoraga (колесо), aggro (фракция/цель)
        self.alive = True
        self.kills = 0

    # dirty flag ----------------------------------------------------------
    def touch(self) -> None:
        """Вход итоговых статов изменился (base / mods / bounds / derived): кэш _eff недействителен."""
        self.version += 1

    @property
    def base(self) -> Tracked:
        return self._base

    @base.setter
    def base(self, value: dict) -> None:
        self._base = Tracked(self, value)
        self.touch()

    @property
    def mods(self) -> Tracked:
        return self._mods

    @mods.setter
    def mods(self, value: dict) -> None:
        if not same_map(value, self._mods):     # то же содержимое (в т.ч. знак нуля) - ничего не менялось
            self._mods = Tracked(self, value)
            self.touch()

    def assign_base(self, new: dict) -> None:
        """Заменить содержимое base целиком (EntityState.pull): version растёт, только если оно изменилось."""
        if not same_map(new, self._base):
            dict.clear(self._base)
            dict.update(self._base, new)
            self.touch()

    # effective stats -----------------------------------------------------
    def stat(self, key: str) -> float:
        if key in self.resources:
            return self.resource(key)
        if key == "hp_pct":
            return self.current_hp / self._eff("max_hp") * 100.0
        return self._eff(key)

    def _eff(self, key: str) -> float:
        """Итоговый стат: (base + mods + вклад характеристик) в границах. Кэш по version: пока base/mods не менялись,
        повторный вызов - чтение словаря (те же float-операции, что и при вычислении - бит-в-бит)."""
        memo = self._eff_memo
        if self._eff_ver != self.version:
            memo.clear()
            self._eff_ver = self.version
        v = memo.get(key)
        if v is None:
            v = memo[key] = self._eff_calc(key)
        return v

    def _eff_calc(self, key: str) -> float:
        base, mods = self._base, self._mods
        v = base.get(key, 0.0) + mods.get(key, 0.0)
        for attr, k in self.derived.get(key, ()):     # сила -> урон и HP, живучесть -> HP ...
            v += (base.get(attr, 0.0) + mods.get(attr, 0.0)) * k
        b = self.bounds.get(key)
        if b:
            v = min(max(v, b.get("min", -math.inf)), b.get("max", math.inf))
        return v

    def ctx(self, extra: Optional[dict] = None, now: float = 0.0) -> dict:
        """Контекст значений юнита; `now` - время хоста (метки и окно поглощения живут по нему; у Unit своих часов нет)."""
        c = {k: self._eff(k) for k in (*self.base, *self.mods) if k not in self.resources}
        c.update({name: self.resource(name) for name in self.resources})
        c.update({
            "hp_pct": self.stat("hp_pct"),
            "hp_missing": self._eff("max_hp") - self.current_hp,
            "kills": float(self.kills),
        })
        c["hp_missing_below_40"] = _hp_missing_below_40(c)
        c.update(self._layer_ctx(now))
        if extra:
            c.update(extra)
        return c

    def _layer_ctx(self, now: float) -> dict:
        """Поля ctx слоёв примитивов: absorbed_kinetic, mark_<id> (для scale/when: detonate по стакам), колесо Махораги."""
        # absorbed_kinetic: окно поглощения истекло -> накопленное сгорает (Playful Cloud отдаёт в удар)
        if self.absorbed_until and now > self.absorbed_until:
            self.absorbed_kinetic, self.absorbed_until = 0.0, 0.0
        c = {"absorbed_kinetic": self.absorbed_kinetic}
        for mid, m in self.marks.items():
            c[f"mark_{mid}"] = float(m.get("stacks", 0.0)) if m.get("until", 1e18) > now else 0.0
        # колесо Махораги как ctx-поля: scale {of="wheel"} / when "wheel >= 8" (src/core/adaptation.py)
        wh = self.external.get("mahoraga") or {}
        c["wheel"] = float(wh.get("wheel", 0))
        c["escalation_level"] = float(wh.get("escalation_level", wh.get("wheel", 0)))
        c["true_form"] = 1.0 if wh.get("true_form") else 0.0
        return c

    # resources --------------------------------------------------------------
    def resource(self, name: str) -> float:
        return self.current_hp if name == "hp" else self.pools[name]

    def max_of(self, name: str) -> float:
        return self._eff(self.resources[name]["max"])

    def set_resource(self, name: str, value: float):
        """Ресурс в пределах [0, максимум]; hp 0 = смерть."""
        value = min(max(value, 0.0), self.max_of(name))
        if name == "hp":
            self.current_hp = value
            self.alive = value > 0
        else:
            self.pools[name] = value

    def refill(self):
        """Все ресурсы, кроме hp, - до максимума (новый юнит, респавн)."""
        self.pools = {name: self.max_of(name) for name in self.resources if name != "hp"}

    def clamp_resources(self):
        """Максимум упал (мод max_hp/max_mana/max_stamina) - текущее значение не выше него."""
        for name in self.resources:
            if self.resource(name) > self.max_of(name):
                self.set_resource(name, self.max_of(name))

    def regen(self, dt: float):
        """Реген всех ресурсов за dt. Отрицательный реген - потеря (HP до 0 - смерть)."""
        for name, spec in self.resources.items():
            rate = self._eff(spec["regen"]) if spec.get("regen") else 0.0
            if rate:
                self.heal(rate * dt, name)

    # damage/heal ----------------------------------------------------------
    def deal_damage(self, amount: float, log=None):
        self.current_hp = max(0.0, self.current_hp - amount)
        if log is not None:
            log.append(amount)
        if self.current_hp <= 0:
            self.alive = False

    def heal(self, amount: float, resource: str = "hp"):
        """Лечение не воскрешает (мёртвого поднимает только set hp). Отрицательное
        лечение (hp_regen ушёл в минус) - это урон: HP не ниже 0, в 0 - смерть."""
        if resource != "hp":
            self.set_resource(resource, self.resource(resource) + amount)
        elif amount < 0:
            self.deal_damage(-amount)
        elif self.alive:
            self.current_hp = min(self._eff("max_hp"), self.current_hp + amount)


# ---------------------------------------------------------------- runtime

# строки лога тренировочной комнаты по видам записи (аргументы - как их передают обработчики ops.py)
_NOTES: dict[str, Callable[..., str]] = {
    "deal": lambda tg, res, amount: f"deal {amount:.2f} -> {tg.name} {res}={tg.resource(res):.1f}",
    "heal": lambda tg, res, amount: f"heal {amount:.2f} -> {res}={tg.resource(res):.1f}",
    "set": lambda tg, res: f"set {res}={tg.resource(res):.1f}",
    "drain_fail": lambda tg, res, cost, have: f"drain FAIL (cost {cost:.2f} > {res} {have:.1f})",
    "drain": lambda tg, res, cost: f"drain {cost:.2f} -> {res}={tg.resource(res):.1f}",
    "buff_cooldown": lambda bid: f"buff {bid} ON COOLDOWN",
    "buff": lambda bid, dur, until: f"buff {bid} +{dur:.1f}s (until {until:.1f})",
    "remove_buff": lambda bid: f"remove_buff {bid}",
    "extend_skip": lambda bid, ext, ev: f"extend {bid}: on={ext['on']} != event={ev!r} -> skip",
    "periodic": lambda kind, amount, every: f"{kind} over time {amount:.2f} every {every:g}s",
    "summon": lambda o: f"summon {o.get('summon')} x{o.get('count', 1)} (no world in training room)",
    "move": lambda o: f"move {o.get('mode')} (no world in training room)",
    # новые kinds (аудит Сукуна/Годжо/Тоджи)
    "resist": lambda tg, stat, amount: f"resist {stat} +{amount:.1f} -> {tg.name}",
    "immune": lambda tg, stat, pct: f"immune {stat} {pct:.0f}% -> {tg.name}",
    "immune_effect": lambda tg, what: f"immune effect {what} -> {tg.name}",
    "mark": lambda tg, mid, stacks: f"mark {mid}={stacks:g} -> {tg.name}",
    "detonate": lambda tg, mid, stacks: f"detonate {mid} ({stacks:g} stacks) -> {tg.name}",
    "detonate_empty": lambda tg, mid: f"detonate {mid}: no marks on {tg.name}",
    "purge": lambda tg, want, tag: f"purge {want}{'' if not tag else ':' + str(tag)} -> {tg.name}",
    "nullify": lambda tg: f"nullify -> {tg.name}",
    "cancel_technique": lambda tg: f"cancel_technique -> {tg.name}",
    "block": lambda tg, what: f"block {what} -> {tg.name}",
    "absorb_damage": lambda tg, amount, window: f"absorb {amount:.2f} (window {window:g}s) -> {tg.name}",
    "binding_vow": lambda tg, vid: f"binding_vow {vid} -> {tg.name}",
    "sever": lambda tg, what: f"sever {what} -> {tg.name}",
    "untargetable": lambda tg, by: f"untargetable by {by} -> {tg.name}",
    "learn": lambda tg, tech: f"learn {tech} -> {tg.name}",
    "learn_nothing": lambda tg: f"learn: nothing observed -> {tg.name}",
    "adapt": lambda tg, dt, stacks: f"adapt {dt} stack {stacks} -> {tg.name}",
    # Махорага (адаптация / фракция / колесо; src/core/adaptation.py)
    "adapt_excluded": lambda tg, sign: f"adapt {sign}: excluded (no self-adaptation) -> {tg.name}",
    "unadapt": lambda tg, sign, changed: f"unadapt {sign} ({'freed' if changed else 'unknown'}) -> {tg.name}",
    "reset_adaptation": lambda tg: f"reset_adaptation -> {tg.name}",
    "observe_phenomenon": lambda tg, sign, hit: f"observe {sign} hit {hit} -> {tg.name}",
    "register_phenomenon": lambda tg, sign: f"register_phenomenon {sign} -> {tg.name}",
    "use_learned_none": lambda tg: f"use_learned_technique: nothing learned -> {tg.name}",
    "use_learned_technique": lambda tg, tech: f"use_learned_technique {tech} -> {tg.name}",
    "set_faction": lambda tg, faction: f"set_faction {faction} -> {tg.name}",
    "set_aggro": lambda tg, mode: f"set_aggro {mode} -> {tg.name}",
    "set_targeting": lambda tg: f"set_targeting -> {tg.name}",
    "retarget": lambda tg, ref: f"retarget {ref} -> {tg.name}",
    "clear_aggro": lambda tg: f"clear_aggro -> {tg.name}",
    "escalate": lambda tg, level: f"escalate level {level} -> {tg.name}",
    "deescalate": lambda tg, level: f"deescalate level {level} -> {tg.name}",
    "trigger_true_form": lambda tg: f"trigger_true_form -> {tg.name}",
    "rotate_wheel": lambda tg, wheel: f"rotate_wheel {wheel} -> {tg.name}",
    "display_wheel": lambda tg, wheel, mode: f"display_wheel {wheel} mode={mode} -> {tg.name}",
    "halt_wheel": lambda tg, wheel: f"halt_wheel {wheel} -> {tg.name}",
    "form_enter": lambda fid: f"form_enter {fid}",
    "form_exit": lambda fid: f"form_exit {fid}",
    "form_blocked": lambda fid: f"form_blocked {fid}",
}


class EffectRuntime:
    """Прогон эффектов схемы по юниту. Логирует каждое действие (для теста)."""

    def __init__(self, owner: Unit, effects: list[dict], enemy: Optional[Unit] = None):
        self.owner = owner
        self.enemy = enemy
        self.effects = effects
        self.log: list[str] = []
        self.active_mod_sources: set[str] = set()
        self._ev_depth = 0          # ре-ентранс fire_event (attack -> attack_hit ...)
        # Контекст последнего нанесённого базовой атакой урона — источник для
        # value {"ref": "ctx.last_damage"} (лifesteal "от фактического урона",
        # а не от hp цели). Сбрасывается в 0 при каждом новом attack(), чтобы
        # heal по ref не суммировался с прошлым ударом.
        self.last_damage: float = 0.0
        # Флаг "цель уже убита ops-эффектом в текущем цикле атаки" (execute).
        # Единственная точка правды для kills-счётчика: run_op("kill") ставит
        # флаг и инкрементирует kills; attack() засчитывает килл сам ТОЛЬКО
        # если флаг не выставлен (смерть от базового удара). Так исключается
        # двойной подсчёт и двойное событие "kill".
        self._killed_this_attack: bool = False
        # Событийный слой mods: вклад каждой событийной mod-операции,
        # (источник, индекс) -> (юнит-цель, стат, вклад). refresh_passives()
        # пересобирает mods как событийный + пассивный слой, поэтому повторные
        # вызовы refresh идемпотентны. Повторное срабатывание ЗАМЕНЯЕТ вклад
        # операции текущим значением (Vampire's Fang: +5 и +1 за kill =>
        # 5 + kills, cap 10), а не складывает его с прошлым ударом - иначе бонус
        # рос бы с каждой атакой без предела. Цель target=enemy - это манекен.
        self._op_contrib: dict[tuple, tuple[Unit, str, float]] = {}
        # Когда бафф выдан последний раз: кулдаун живёт дольше самого баффа
        # (раньше хранился в записи баффа, которая удаляется при истечении -
        # после истечения щит выдавался снова без кулдауна)
        self._buff_granted_at: dict[str, float] = {}
        self._effect_fired_at: dict[str, float] = {}   # Effect.cooldown
        self._compiled: dict[str, Callable[[dict], Any]] = {}  # условие -> замыкание (_test)
        self._periodic: list[dict] = []                        # DoT/HoT (every + duration)
        self._last_hit_at = -1e9                               # ctx.since_hit
        self._last_attack_at = -1e9                            # ctx.since_attack
        self._buff_fields = buff_fields(effects)               # buff_id -> имя поля ctx
        self._now = 0.0
        # --- hp_cross -----------------------------------------------------
        # Зоны пересечения порога HP (kind="condition", threshold=N):
        # name -> {"above": bool | None}. None = порог ещё не наблюдали.
        self._hp_zones: dict[str, Optional[bool]] = {}
        # Активные (пересекаемые сейчас) имена зон — источник для триггера
        # {kind:"event", event:"hp_cross", cross:<name>} и фильтра "ctx.crossed".
        self.crossed: set[str] = set()

    # public API ------------------------------------------------------------
    def _test(self, pred, ctx: dict) -> bool:
        """eval_pred с кэшем рантайма: условия предмета компилируются один раз и
        не вытесняются (у предмета на 100 тыс. эффектов условий больше, чем
        вмещает общий LRU compile_pred, - он пересобирал всё на каждом событии)."""
        if not isinstance(pred, str) or not pred:
            return eval_pred(pred, ctx)
        fn = self._compiled.get(pred)
        if fn is None:
            named = rules()["predicates"].get(pred.strip())
            fn = self._compiled[pred] = compile_pred(named if named is not None else pred.strip())
        return bool(fn(ctx))

    def context(self, extra: Optional[dict] = None) -> dict:
        """Контекст условий и значений: статы владельца, enemy_* цели,
        last_damage (фактический урон последнего удара героя) и buff_<id> -
        сколько секунд осталось баффу (0 - не активен) для каждого баффа,
        который выдают эффекты: `ctx.buff_enraged > 0` включает бонусы на время баффа."""
        ctx = {**self.owner.ctx(extra, self._now), **self.target_ctx("enemy", self.enemy)}
        ctx["last_damage"] = self.last_damage
        # секунд с последнего полученного урона / нанесённого удара (перки «пока не бьют»)
        ctx["since_hit"] = min(999.0, self._now - self._last_hit_at)
        ctx["since_attack"] = min(999.0, self._now - self._last_attack_at)
        for bid, field in self._buff_fields.items():
            b = self.owner.buffs.get(bid)
            ctx[field] = max(0.0, b.get("until", 0.0) - self._now) if b else 0.0
        return ctx

    def target_ctx(self, prefix: str, t: Optional[Unit]) -> dict:
        """Контекст цели с префиксом: enemy_hp_pct, ally_hp и т.д."""
        if t is None:
            return {}
        c = t.ctx(now=self._now)
        return {f"{prefix}_{k}": v for k, v in c.items()}

    def _buff_active(self, bid: str) -> bool:
        b = self.owner.buffs.get(bid)
        return b is not None and b.get("until", 1e18) > self._now

    def _amplify(self, ef: dict, ctx: dict) -> float:
        """Effect.amplify {when | while_buff, factor, every, of}: множитель
        бонусов эффекта factor^floor(of/every), пока выполнено условие `when`
        (предикат ctx, напр. "ctx.hp <= 1") и/или активен бафф while_buff."""
        amp = ef.get("amplify")
        if not amp:
            return 1.0
        if amp.get("when") and not self._test(amp["when"], ctx):
            return 1.0
        if amp.get("while_buff") and not self._buff_active(amp["while_buff"]):
            return 1.0
        steps = math.floor(_ctx_get(ctx, amp.get("of")) / float(amp.get("every", 10)))
        return float(amp.get("factor", 2)) ** max(0, steps)

    def units(self) -> list[Unit]:
        return [u for u in (self.owner, self.enemy) if u is not None]

    def _prefix(self, unit: Unit) -> str:
        """Префикс ctx-полей юнита: свои - без префикса, врага - enemy_."""
        return "" if unit is self.owner else "enemy_"

    def _passive_layer(self, ctx: dict) -> dict[int, dict[str, float]]:
        """Пассивный слой mods по юнитам (id(unit) -> {стат: вклад}) - ЧИСТАЯ
        функция от переданного контекста (hp_pct, kills, ...): passive/condition-
        эффекты, mod-ops. Вызывается из refresh_passives()."""
        layers: dict[int, dict[str, float]] = {}
        for ef in self.effects:
            tr = ef.get("trigger", {})
            kind = tr.get("kind")
            if kind not in ("passive", "condition"):
                continue
            if kind == "condition" and not self._test(tr.get("when"), ctx):
                continue
            mult = self._amplify(ef, ctx)
            for o in ef.get("ops", []):
                if o.get("kind") != "mod":
                    continue
                unit = self._resolve_target(o.get("target", "self"))
                if unit is not None:
                    self._apply_mod(o, ctx, unit, sink=layers.setdefault(id(unit), {}), mult=mult)
        return layers

    def _event_layers(self) -> dict[int, dict[str, float]]:
        layers: dict[int, dict[str, float]] = {}
        for unit, stat, v in self._op_contrib.values():
            layer = layers.setdefault(id(unit), {})
            layer[stat] = layer.get(stat, 0.0) + v
        return layers

    def refresh_passives(self, t: float = 0.0):
        """Пересчитать mods каждого юнита = событийный слой + пассивный слой.

        Двухслойная модель mods:
          * СОБЫТИЙНЫЙ слой (`_op_contrib`) — вклад событийных mod-ops
            (напр. Vampire's Fang: strength +5, +1 за kill); повторное
            срабатывание операции заменяет её вклад;
          * ПАССИВНЫЙ слой — pure-функция состояния (_passive_layer).
        mods пересобирается с нуля при каждом вызове => refresh ИДЕМПОТЕНТЕН
        (ранее condition-эффекты со scale.of=kills применялись и в событии,
        и в refresh — стаки удваивались).
        """
        self._now = t
        event = self._event_layers()
        # Пассивный слой считается от base + событийного слоя, БЕЗ прошлого
        # пассивного вклада: иначе "+20% strength" брался от уже усиленной
        # силы (100 -> 120 -> 24% ...) - петля обратной связи.
        for unit in self.units():
            unit.mods = dict(event.get(id(unit), {}))
        ctx = self.context()
        self._scan_hp_cross(ctx, t)
        passive = self._passive_layer(ctx)
        event = self._event_layers()  # hp_cross-события выше могли его изменить
        for unit in self.units():
            merged = dict(event.get(id(unit), {}))
            for k, v in passive.get(id(unit), {}).items():
                merged[k] = merged.get(k, 0.0) + v
            unit.mods = merged
            unit.clamp_resources()

    # hp_cross ---------------------------------------------------------------
    def _hp_zone_name(self, ef: dict) -> Optional[str]:
        """Имя зоны пересечения для condition-эффекта с threshold."""
        return (ef.get("meta") or {}).get("name") or ef.get("id")

    def _scan_hp_cross(self, ctx: dict, t: float = 0.0):
        """Детектор пересечений порога HP (семантика LoL Sorrow/Deadman).

        condition-эффект с числовым полем `threshold` объявляет зону:
          above = (ctx.hp_pct >= threshold). При СМЕНЕ состояния зоны
          (первый наблюдённый переход не считается — baseline) шлётся
          событие "hp_cross" с extra {"crossed": <имя зоны>}; имя остаётся
          в self.crossed до следующего refresh (фильтр sub-effect'ов:
          trigger {"kind":"event","event":"hp_cross","cross":<имя>}).
        """
        fresh: list[tuple[str, bool]] = []
        for ef in self.effects:
            tr = ef.get("trigger", {})
            if tr.get("kind") != "condition" or "threshold" not in ef:
                continue
            name = self._hp_zone_name(ef)
            thr = float(ef["threshold"])
            above = ctx.get("hp_pct", 100.0) >= thr
            prev = self._hp_zones.get(name)
            self._hp_zones[name] = above
            if prev is not None and prev != above:
                fresh.append((name, above))
        self.crossed = {n for n, _ in fresh}
        for name, above in fresh:
            self.fire_event("hp_cross", t, extra={"crossed": name})

    def respawn_enemy(self):
        """Вернуть боевого манекена в строй (полное HP) — тренировочная
        конвенция комнаты: противник всегда доступен для следующего удара."""
        e = self.enemy
        if e is None:
            return
        # новый манекен - без дебаффов прошлого (событийный вклад по врагу сброшен)
        self._op_contrib = {k: c for k, c in self._op_contrib.items() if c[0] is not e}
        e.mods = {}
        e.current_hp = e._eff("max_hp")
        e.refill()
        e.alive = True

    def attack(self, t: float = 0.0, base_damage: Optional[float] = None):
        """Боевой цикл героя: attack -> (execute-ops) -> базовый урон по врагу
        -> attack_hit (лifesteal-эффекты)."""
        if not self.owner.alive or self.enemy is None or not self.enemy.alive:
            return
        self._killed_this_attack = False
        self._last_attack_at = t
        self.fire_event("attack", t)
        if self.enemy is None or not self.enemy.alive:
            # execute (judgement) уже сработал: kills+1 и событие kill посланы
            # из run_op("kill"); здесь — только респавн тренировочного манекена
            # и пересчёт пассивных модов (scale.of=kills обновился ДО респавна
            # следующего удара).
            if not self._killed_this_attack:
                # страховка: цель умерла не через op "kill" (например deal-ops
                # на событии attack) — засчитать килл здесь, каскад один раз
                self.owner.kills += 1
                self.log.append(f"t={t:.1f} KILL {self.enemy.name}")
                self.fire_event("kill", t)
            self.respawn_enemy()
            self.refresh_passives(t)
            return
        dmg = base_damage if base_damage is not None else self.owner._eff("attack_damage")
        self.last_damage = 0.0
        if dmg > 0:
            before = self.enemy.current_hp
            self.enemy.deal_damage(dmg)
            # фактический урон (с учётом "избытка" над нулём) — для ctx.last_damage
            self.last_damage = before - self.enemy.current_hp
            self.log.append(f"t={t:.1f} hero basic attack {dmg:.1f} "
                            f"-> {self.enemy.name} hp={self.enemy.current_hp:.1f}")
        killed = not self.enemy.alive and not self._killed_this_attack
        # Порядок каскада: сначала "attack_hit" (лifesteal видит актуальный
        # ctx.last_damage и цель ещё мёртвой не возрождена), затем kill-каскад
        # (инкремент kills, событие "kill", респавн манекена), и только потом
        # пересчёт пассивных модов — scale-источники вроде `kills` меняются
        # внутри цикла, и следующие эффекты обязаны видеть актуальные статы.
        # refresh идемпотентен (mods.clear() -> повторное применение).
        self.fire_event("attack_hit", t)
        if killed:
            # Инкремент kill-счётчика — ЕДИНСТВЕННЫЙ источник правды здесь;
            # каскад события "kill" ниже не должен повторно попадать в
            # run_op("kill") (он удвоил бы счётчик) — поэтому сам op "kill"
            # шлёт fire_event("kill") только когда жертва ещё была жива.
            self.owner.kills += 1
            self.log.append(f"t={t:.1f} KILL {self.enemy.name}")
            self.fire_event("kill", t)
            # тренировочный манекен возрождается сразу после каскада kill,
            # чтобы следующее событие attack не игнорировалось mrt.m5()
            self.respawn_enemy()
        self.refresh_passives(t)

    def receive_damage(self, amount: float, t: float = 0.0):
        """Враг бьёт героя; после урона — событие take_damage (retaliation)."""
        if not self.owner.alive:
            return
        self._now = t
        shield = next((bid for bid, b in self.owner.buffs.items()
                       if "iframe" in (b.get("flags") or []) and b.get("until", 1e18) > t), None)
        if shield is not None:
            self.log.append(f"t={t:.1f} {self.owner.name} ignores {amount:.1f} damage (iframe {shield})")
            return
        self.owner.deal_damage(amount)
        self._last_hit_at = t
        self.log.append(f"t={t:.1f} {self.owner.name} takes {amount:.1f} "
                        f"hp={self.owner.current_hp:.1f}")
        died = not self.owner.alive
        self.fire_event("take_damage", t)
        if died and not self.owner.alive:
            self.fire_event("die", t)

    def fire_event(self, event: str, t: float = 0.0, extra: Optional[dict] = None):
        ctx = self.context(extra)
        self._now = t
        # Активные баффы с extend.on == событие продлеваются (Last Will: каждый
        # kill под щитом +5 с). Раньше extend срабатывал только если сам
        # buff-op выполнялся в этом событии - kill щит не продлевал никогда.
        for bid, b in list(self.owner.buffs.items()):
            ext = b.get("extend") or {}
            if ext.get("on") == event and b.get("until", 1e18) > t:
                self._extend_buff(self.owner, bid, ext, ctx, t, f"{bid}#{event}", buff_obj=b)
        for ef in self.effects:
            tr = ef.get("trigger", {})
            if tr.get("kind") != "event" or tr.get("event") != event:
                continue
            if not self._owner_has_ok(tr, t):
                continue
            # фильтр по имени зоны пересечения для hp_cross-событий:
            # trigger {"kind":"event","event":"hp_cross","cross":"Lost My Self"}
            if tr.get("cross") and tr["cross"] not in self.crossed:
                continue
            if tr.get("filter") and not self._test(tr["filter"], ctx):
                continue
            # Effect.cooldown: событийный эффект срабатывает не чаще раза в N с
            # (раньше поле объявлялось в схеме, но рантайм его не читал)
            if ef.get("cooldown"):
                last = self._effect_fired_at.get(ef["id"])
                if last is not None and t - last < resolve_value(ef["cooldown"], ctx):
                    continue
                self._effect_fired_at[ef["id"]] = t
            self.run_ops(ef.get("ops", []), ctx, t, f"{ef['id']}#{event}",
                         event=event)
        # Событийный слой пополняет run_op("mod") - по каждой операции
        # отдельно. Раньше здесь бралась дельта owner.mods за всё событие, но
        # fire_event реентерабелен (kill, hp_cross из refresh_passives): дельта
        # внешнего события включала вклад вложенных (уже записанный ими) и
        # перестроенный пассивный слой - моды учитывались дважды
        # (Lost My Self: strength +24 вместо +20, Vampire's Fang: +11 вместо +5).
        # каскад: attack порождает attack_hit только через attack();
        # здесь — ре-ентрансные события из ops (например kill внутри fail-ветки)

    def apply_status(self, status_id: str, t: float = 0.0, stacks: int = 1) -> int:
        """Статус из lua_content/statuses на манекен (enemy): те же данные и правило стаков, что у EffectManager."""
        from . import statuses
        row = statuses.get_status(status_id)
        if statuses.resisted(self.enemy or self.owner, row["id"], lambda: 0.0):   # no rng in the room: >=100 only
            return 0
        book = self.__dict__.setdefault("_status_book", {})
        mult = statuses.duration_mult(self.enemy or self.owner, row)
        if mult <= 0.0:
            return 0
        pl = statuses.plan(book, row["id"], row, t, statuses.Apply(stacks, mult))
        src = f"status:{row['id']}"
        self._periodic = [p for p in self._periodic if p["src"] != src]
        for bid in statuses.nullify_buffs(pl.ops):
            (self.enemy or self.owner).buffs.pop(bid, None)
        self.run_ops(pl.ops, self.context(), t, src)
        return pl.stacks

    def tick(self, t: float, dt: float):
        """regen + DoT/HoT + duration-истечение баффов + tick-события."""
        self.refresh_passives(t)
        self.owner.regen(dt)
        keep = []
        for p in self._periodic:
            while p["next"] <= t and p["next"] <= p["until"] + 1e-9:
                p["next"] += p["every"]
                o, tgt = p["op"], p["target"]
                if o["kind"] == "deal":
                    tgt.deal_damage(p["amount"])
                    self.log.append(f"t={t:.1f} {p['src']} tick deal {p['amount']:.2f} -> {tgt.name} hp={tgt.current_hp:.1f}")
                else:
                    tgt.heal(p["amount"], o.get("stat") or "hp")
            if p["next"] <= p["until"] + 1e-9:
                keep.append(p)
        self._periodic = keep
        expired = [b for b, d in self.owner.buffs.items() if d.get("until", 1e18) <= t]
        for b in expired:
            self.owner.buffs.pop(b)
            self.log.append(f"t={t:.1f} buff_expired {b}")
        self.fire_event("tick", t)

    # ops -------------------------------------------------------------------
    def run_ops(self, ops: list[dict], ctx: dict, t: float, src: str,
                event: Optional[str] = None):
        for i, o in enumerate(ops):
            self.run_op(o, ctx, t, src, event=event, op_key=(src, i))

    def run_op(self, o: dict, ctx: dict, t: float, src: str,
               event: Optional[str] = None, op_key: Optional[tuple] = None):
        """Одна операция схемы на юните тренировки: `when` -> цель -> общий интерпретатор (ops.apply_op)."""
        if o.get("when") and not self._test(o["when"], ctx):
            return
        target = self._resolve_target(o.get("target", "self"))
        if target is None:
            return
        apply_op(self, OpCall(ctx=ctx, src=src, t=t, source=self.owner, event=event, key=op_key), target, o)

    # OpHost: примитивы для обработчиков ops.py (изолированный Unit + лог для теста) --------------------
    def op_stat_prefix(self, _cx: OpCall, tgt: Unit) -> str:
        return self._prefix(tgt)

    def op_periodic_ok(self, o: dict) -> bool:
        return o.get("duration") is not None

    def op_duration(self, d, ctx: dict) -> float:
        return self._duration(d, ctx)

    def op_add_periodic(self, cx: OpCall, tgt: Unit, o: dict, p: Periodic) -> None:
        self._periodic.append({"op": {k: v for k, v in o.items() if k not in ("every", "duration")},
                               "target": tgt, "amount": p.amount, "every": p.every, "next": cx.t + p.every,
                               "until": p.until, "src": cx.src})
        self.op_note(cx, "periodic", p.kind, p.amount, p.every)

    def op_resource(self, tgt: Unit, res: str) -> float:
        return tgt.resource(res)

    def op_damage(self, _cx: OpCall, tgt: Unit, _o: dict, amount: float) -> None:
        tgt.deal_damage(amount, log=self._dmg_log(tgt))

    def op_spend(self, _cx: OpCall, tgt: Unit, res: str, amount: float, _lethal: bool) -> None:
        tgt.set_resource(res, tgt.resource(res) - amount)

    def op_heal(self, _cx: OpCall, tgt: Unit, res: str, amount: float) -> None:
        tgt.heal(amount, res)

    def op_set_resource(self, cx: OpCall, tgt: Unit, stat: Optional[str], amount: float) -> None:
        if stat in tgt.resources:
            tgt.set_resource(stat, amount)
            self.op_note(cx, "set", tgt, stat)

    def op_mod(self, cx: OpCall, tgt: Unit, o: dict) -> None:
        # Событийная mod-операция задаёт СВОЙ текущий вклад: прошлый вклад этой же операции снимается,
        # новый записывается в _op_contrib. Дельта меряется вокруг одной операции: вложенные события
        # и пересборка пассивного слоя в неё не попадают.
        key = cx.key if cx.key is not None else (cx.src, id(o))
        replace_contribution(self._op_contrib, key, tgt, o.get("stat"), lambda: self._apply_mod(o, cx.ctx, tgt))
        tgt.clamp_resources()  # мод max_hp вниз: текущее HP не выше нового максимума

    def op_buffs(self, tgt: Unit) -> dict:
        return tgt.buffs

    def op_granted(self, _cx: OpCall) -> dict:
        return self._buff_granted_at

    def op_buff_record(self, cx: OpCall, o: dict, until: float, cd: Optional[float]) -> dict:
        return {"until": until, "extend": o.get("extend"), "cooldown": cd, "last_cd": cx.t,
                "flags": list(o.get("flags") or [])}

    def op_after_buff(self, cx: OpCall, tgt: Unit, bid, o: dict) -> None:
        # декларация extend внутри ops-buff: срабатывает при событии ext["on"]
        ext = o.get("extend") or {}
        if ext and cx.event and cx.event == ext.get("on"):
            self._extend_buff(tgt, bid, ext, cx.ctx, cx.t, cx.src)

    def op_extend(self, cx: OpCall, bid, ext: dict, buff: dict) -> None:
        ev = cx.event
        if ev is None and "#" in cx.src:
            # fallback: событие зашито в src вида "effect#event(.fail)"
            ev = cx.src.rsplit("#", 1)[-1].split(".", 1)[0]
        # фильтр по событию: extend срабатывает только на ext["on"]
        if ext.get("on") and ev != ext.get("on"):
            self.op_note(cx, "extend_skip", bid, ext, ev)
            return
        self._extend_buff(None, bid, ext, cx.ctx, cx.t, cx.src, buff_obj=buff)

    def op_find_effect(self, _cx: OpCall, eid) -> Optional[dict]:
        return next((e for e in self.effects if e.get("id") == eid), None)

    def op_nested(self, cx: OpCall, ops: list, suffix: str, keep_event: bool) -> None:
        self.run_ops(ops, cx.ctx, cx.t, cx.src + suffix, event=cx.event if keep_event else None)

    def op_kill(self, cx: OpCall, tgt: Unit) -> None:
        t, src = cx.t, cx.src
        was_alive = tgt.alive and tgt.current_hp > 0
        if was_alive and tgt is self.enemy:
            # фактический урон "добиания" - в ctx.last_damage: heal по ref/pct-of last_damage
            # (лайфстил на execute) считается от реального снятого HP, а не от заявленного dmg
            self.last_damage = tgt.current_hp
        tgt.deal_damage(tgt.current_hp, log=self._dmg_log(tgt))
        if not was_alive:
            return
        if tgt is self.owner:
            self.log.append(f"t={t:.1f} {src} KILL {tgt.name} (self!) -- revive/set-hp ops must follow")
            self.fire_event("die", t)
            return
        # Инкремент kills здесь - ЕДИНСТВЕННЫЙ для целей, убитых ops-эффектом (execute). Флаг сообщает
        # циклу attack(), что килл уже засчитан и событие "kill" разослано, - иначе счётчик удвоился бы.
        self.owner.kills += 1
        if tgt is self.enemy:
            self._killed_this_attack = True
        self.log.append(f"t={t:.1f} {src} KILL {tgt.name}")
        if tgt is self.enemy:
            self.fire_event("kill", t)      # каскад: kill у владельца

    def op_summon(self, cx: OpCall, o: dict) -> None:
        self.op_note(cx, "summon", o)

    def op_move(self, cx: OpCall, _tgt: Unit, o: dict) -> None:
        self.op_note(cx, "move", o)

    # --- формы (ops.py stance/transform/timed_power_up): запись формы живёт в unit.external["forms"];
    # тренировочная комната не применяет stats формы и не гасит форму по таймеру (это делает EffectManager)
    def op_forms(self, tgt: Unit) -> dict:
        return tgt.external.setdefault("forms", {})

    def op_form_mods(self, cx: OpCall, _tgt: Unit, fid: str, mods: list, until: Optional[float]) -> None:
        """Комната: моды формы не применяются (только запись формы)."""

    def op_form_clear_mods(self, cx: OpCall, _tgt: Unit, fid: str) -> None:
        """Комната: нечего снимать."""

    def op_note(self, cx: OpCall, what: str, *args) -> None:
        self.log.append(f"t={cx.t:.1f} {cx.src} " + _NOTES[what](*args))

    # --- примитивы новых kinds (ops.py: resist/immune/mark/detonate/purge/...) ---------
    def op_marks(self, tgt: Unit) -> dict:
        return tgt.marks

    def op_grant_mark(self, _cx: OpCall, tgt: Unit, mid: str, stacks: float, until: float) -> None:
        tgt.marks[mid] = {"stacks": stacks, "until": until}

    def op_spells(self, tgt: Unit) -> list:
        return tgt.spells

    def op_adapt_stacks(self, tgt: Unit) -> dict:
        return tgt.adapt_stacks

    def op_absorb_add(self, cx: OpCall, tgt: Unit, amount: float, window: float) -> None:
        if cx.t > tgt.absorbed_until:               # новое окно: счётчик обнуляется
            tgt.absorbed_kinetic = 0.0
        tgt.absorbed_kinetic += amount
        tgt.absorbed_until = max(tgt.absorbed_until, cx.t) + window

    def op_apply_mod_op(self, cx: OpCall, tgt: Unit, o: dict) -> None:
        # mod без duration: пассивный слой владельца (key по src+id операции - вклад заменяет прошлый)
        key = (cx.src, id(o)) if cx.key is None else (cx.src, f"{cx.key[1]}:{id(o)}")
        replace_contribution(self._op_contrib, key, tgt, o.get("stat"), lambda: self._apply_mod(o, cx.ctx, tgt))
        tgt.clamp_resources()

    def op_refresh(self, _cx: OpCall, tgt: Unit) -> None:
        tgt.touch()                                 # пересчёт кэша _eff после purge/правок слоёв

    def op_damage_taken(self, cx: OpCall, _tgt: Unit) -> float:
        """Тренировочная комната не ведёт список попаданий вызова: урон последнего удара героя (ctx.last_damage)."""
        return float(cx.ctx.get("last_damage", 0.0))

    # --- протокол Махораги (ops.OpHost; состояние в tgt.external, см. src/core/adaptation.py) ---
    def op_adaptation(self, _cx: OpCall, tgt: Unit) -> dict:
        return tgt.external.setdefault("mahoraga", {})

    def set_adaptation(self, _cx: OpCall, tgt: Unit, state: dict) -> None:
        tgt.external["mahoraga"] = state

    def op_aggro(self, _cx: OpCall, tgt: Unit) -> dict:
        return tgt.external.setdefault("aggro", {})

    def set_aggro(self, _cx: OpCall, tgt: Unit, **kv: Any) -> None:
        tgt.external["aggro"] = dict(kv)

    def op_nested_ops(self, cx: OpCall, _tgt: Unit, ops: list) -> None:
        self.op_nested(cx, ops, ".nested", True)


    # helpers -----------------------------------------------------------------
    def _extend_buff(self, target, bid: str, ext: dict, ctx: dict,
                     t: float, src: str, buff_obj=None):
        """Продлить бафф `bid` по extend-правилу {on, flat|pct}."""
        b = buff_obj if buff_obj is not None else target.buffs.get(bid)
        if b is None:
            return
        add = extend_amount(ext, ctx)
        b["until"] += add
        self.log.append(f"t={t:.1f} {src} extend {bid} +{add:.1f}s")

    def _default_stat(self, o: dict, unit: Unit) -> Optional[str]:
        """pct без `of` - процент от того же стата ЦЕЛИ операции."""
        return default_stat_of(o, self._prefix(unit))

    def _apply_mod(self, o: dict, ctx: dict, unit: Unit,
                   sink: Optional[dict] = None, mult: float = 1.0):
        """Применить mod-оп к юниту. sink=None -> unit.mods (событийный путь);
        sink=dict -> накопление в отдельный слой (пассивный)."""
        stat = o.get("stat")
        amount = compute_amount(o, ctx, self._default_stat(o, unit))
        mo = o.get("op") or "add"  # op не задан (или null из формы) - add; раньше мод молча не применялся
        if mo in ("add", "sub"):
            amount *= mult  # Effect.amplify (Lost My Self при 1 HP)
        apply_mod_math(unit.mods if sink is None else sink, unit.base.get(stat, 0.0), stat, mo, amount)

    def _duration(self, d, ctx) -> float:
        if d is None:
            return 10.0
        if isinstance(d, (int, float)):
            return float(d)
        if "base" in d or "flat" in d or "pct" in d:
            base = resolve_value({"flat": d.get("base", d.get("flat")),
                                  "pct": d.get("pct"), "of": d.get("of")}, ctx)
            s = d.get("scale")
            if s:
                steps = math.floor(_ctx_get(ctx, s["of"]) / float(s["every"]))
                if s.get("cap") is not None:
                    steps = min(steps, s["cap"])
                base += steps * float(s.get("value", {}).get("flat", 0)) \
                        * float(s.get("factor", 1.0))
            return base
        return resolve_value(d, ctx)

    def _resolve_target(self, name):
        if name == "self":
            return self.owner
        if name in ("enemy", "source", "area"):
            return self.enemy  # в комнате один манекен: area попадает в него
        return self.owner  # allies/allies->self в одиночном тесте

    def _owner_has_ok(self, tr: dict, t: float) -> bool:
        oh = tr.get("owner_has")
        if not oh:
            return True
        # sub-effect активен, пока родительский эффект активен (condition/passive)
        parent = next((e for e in self.effects if e.get("id") == oh), None)
        if parent is None:
            return False
        ptr = parent.get("trigger", {})
        if ptr.get("kind") == "condition":
            return self._test(ptr.get("when"), self.context())
        return True

    def _dmg_log(self, target):
        return None  # урон уже логируется в deal/kill


STEP_HELP = ("attack [DMG] | enemy_attack N | kill | tick T DT | hp PCT (HP героя в % от максимума) | "
             "set_dummy HP | <событие> (use, cast, crit, ...)")


def run_step(rt: EffectRuntime, step: str, t: float, base_damage: float = 0.0) -> float:
    """Один шаг сценария тренировочной комнаты (единый язык для билдера,
    ui_logic.run_training_room и itemcheck). Возвращает новое время."""
    parts = step.split()
    kind = parts[0] if parts else ""
    hero, dummy = rt.owner, rt.enemy
    if kind == "attack":
        rt.attack(t, base_damage=float(parts[1]) if len(parts) > 1 else base_damage)
    elif kind == "enemy_attack" and len(parts) > 1:
        rt.receive_damage(float(parts[1]), t)
    elif kind == "kill" and dummy is not None:
        # убить текущего манекена, послать kill и возродить его же (тот же объект,
        # полное HP). kills считает шаг: dummy.deal_damage не трогает hero.kills
        dummy.deal_damage(dummy.current_hp)
        hero.kills += 1
        rt.fire_event("kill", t)
        rt.respawn_enemy()
    elif kind == "tick" and len(parts) > 2:
        t += float(parts[1])
        rt.tick(t, float(parts[2]))
    elif kind == "hp" and len(parts) > 1:
        hero.alive = True
        hero.set_resource("hp", hero._eff("max_hp") * float(parts[1]) / 100.0)
        rt.refresh_passives(t)
    elif kind == "set_dummy" and len(parts) > 1 and dummy is not None:
        dummy.current_hp = float(parts[1])
        dummy.alive = dummy.current_hp > 0
    else:
        rt.fire_event(step, t)
        rt.refresh_passives(t)  # условия эффектов следят за новым состоянием
    return t


def buff_fields(effects: list[dict]) -> dict[str, str]:
    """buff_id каждой операции buff в эффектах -> поле контекста buff_<id>."""
    out: dict[str, str] = {}

    def walk(ops):
        for o in ops or []:
            if isinstance(o, dict):
                if o.get("kind") == "buff" and o.get("buff_id"):
                    out[o["buff_id"]] = "buff_" + "".join(c if c.isalnum() else "_" for c in o["buff_id"])
                walk(o.get("fail"))

    for ef in effects or []:
        if isinstance(ef, dict):
            walk(ef.get("ops"))
    return out


def sample_context(effects: Optional[list[dict]] = None) -> dict:
    """Полный контекст рантайма на юнитах по умолчанию: какие поля видят условия
    (с effects - ещё и buff_<id> баффов, которые эти эффекты выдают)."""
    return EffectRuntime(Unit("hero"), list(effects or []), enemy=Unit("enemy")).context()


def summarize(rt: EffectRuntime) -> dict:
    o = rt.owner
    return {
        "unit": o.name,
        "hp": round(o.current_hp, 2),
        "max_hp": round(o.stat("max_hp"), 2),
        "hp_pct": round(o.stat("hp_pct"), 2),
        "mods": {k: round(v, 3) for k, v in o.mods.items() if abs(v) > 1e-9},
        "buffs": {b: round(d["until"], 1) for b, d in o.buffs.items()},
        "kills": o.kills,
    }
