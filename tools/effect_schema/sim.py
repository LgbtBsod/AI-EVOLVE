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

# ---------------------------------------------------------------- stat rules

# Те же значения, что lua_content/effect_rules.lua (действуют без Lua-бэкенда)
DEFAULT_RULES: dict[str, dict] = {
    "defaults": {"max_hp": 1000.0, "max_mana": 100.0, "max_stamina": 100.0,
                 "hp_regen": 0.0, "mana_regen": 0.0, "stamina_regen": 0.0,
                 "strength": 0.0, "agility": 0.0, "intelligence": 0.0, "vitality": 0.0,
                 "wisdom": 0.0, "charisma": 0.0, "luck": 0.0, "endurance": 0.0,
                 "defense": 0.0, "tenacity": 0.0, "crit_chance": 0.0, "crit_dmg": 50.0, "aspd": 1.0,
                 "lifesteal": 0.0, "move_speed": 5.0, "attack_damage": 0.0},
    "resources": {"hp": {"max": "max_hp", "regen": "hp_regen"},
                  "mana": {"max": "max_mana", "regen": "mana_regen"},
                  "stamina": {"max": "max_stamina", "regen": "stamina_regen"}},
    "bounds": {"max_hp": {"min": 1}, "max_mana": {"min": 0}, "max_stamina": {"min": 0},
               "crit_chance": {"min": 0, "max": 100}, "aspd": {"min": 0.1}, "move_speed": {"min": 0},
               "tenacity": {"min": 0, "max": 100}},
    "predicates": {"low_hp_40": "ctx.hp_pct < 40"},
}


@lru_cache(maxsize=1)
def rules() -> dict[str, dict]:
    """Правила статов из lua_content/effect_rules.lua поверх DEFAULT_RULES."""
    merged = {k: dict(v) for k, v in DEFAULT_RULES.items()}
    try:
        from .. import lua_bridge
        data = lua_bridge.load(lua_bridge.ROOT / "lua_content" / "effect_rules.lua", cache=True)
    except Exception:  # нет Lua-бэкенда или файл сломан - дефолты выше
        return merged
    for section in merged:
        merged[section].update(data.get(section) or {})
    return merged

# ---------------------------------------------------------------- predicates

def _hp_missing_below_40(ctx) -> float:
    """Псевдо-стат: сколько % HP не хватает ПОРОГУ 40% (0..40)."""
    return max(0.0, 40.0 - ctx.get("hp_pct", 100.0))


def named_predicates() -> dict[str, str]:
    """Именованные условия: имя -> выражение (lua_content/effect_rules.lua -> predicates).
    Одно определение для Python и для Lua (lua_gen кладёт их в реестр PRED файла)."""
    return dict(rules()["predicates"])

_ALLOWED_CTX: dict[str, Callable[[dict], float]] = {
    "hp_missing_below_40": _hp_missing_below_40,
}

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
    derived = _ALLOWED_CTX.get(key)

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


# ---------------------------------------------------------------- values

def resolve_value(v: dict, ctx: dict, default_stat: Optional[str] = None) -> float:
    if v is None:
        return 0.0
    if "flat" in v and v["flat"] is not None:
        return float(v["flat"])
    if "pct" in v and v["pct"] is not None:
        of = v.get("of") or default_stat
        base = _ctx_get(ctx, of)
        return float(v["pct"]) / 100.0 * base
    if "ref" in v and v["ref"]:
        path = v["ref"]
        if path.startswith("ctx."):
            path = path[4:]
        # только dict-навигация по whitelist-полям (без getattr — см. аудит:
        # getattr допускал обход вида "__class__.__subclasses__")
        cur: Any = ctx
        for part in path.split("."):
            if not isinstance(cur, dict):
                raise KeyError(f"ref {v['ref']!r}: cannot descend into {type(cur).__name__}")
            cur = _ctx_get(cur, part)
        return float(cur)
    return 0.0


def _ctx_get(ctx: dict, key: Optional[str]) -> float:
    if key is None:
        return 0.0
    if key in ctx:
        return float(ctx[key])
    if key in _ALLOWED_CTX:
        return float(_ALLOWED_CTX[key](ctx))
    raise KeyError(f"unknown ctx field {key!r}")


def compute_amount(op: dict, ctx: dict, default_stat: Optional[str] = None) -> float:
    """Итог: base + floor(steps)*value*factor, steps из scale.
    default_stat: откуда брать pct без `of` (по умолчанию - стат операции у владельца;
    для цели-врага рантайм передаёт enemy_<стат>)."""
    default_stat = default_stat or op.get("stat")
    total = resolve_value(op.get("value"), ctx, default_stat)
    s = op.get("scale")
    if s:
        steps = _ctx_get(ctx, s["of"]) / float(s["every"])
        steps = math.floor(steps)
        if s.get("cap") is not None:
            steps = min(steps, float(s["cap"]))
        if s.get("floor") is not None:
            steps = max(steps, float(s["floor"]))
        total += steps * resolve_value(s.get("value"), ctx, default_stat) \
                 * float(s.get("factor", 1.0))
    return total


# ---------------------------------------------------------------- unit

class Unit:
    """Юнит тренировки: статы + ресурсы (hp, mana, stamina) + контекст для резолва значений.

    База, ресурсы и границы итоговых статов - lua_content/effect_rules.lua."""

    def __init__(self, name: str, max_hp: float = 1000.0, **stats):
        r = rules()
        self.name = name
        self.base: dict[str, float] = {k: float(v) for k, v in r["defaults"].items()}
        self.base["max_hp"] = float(max_hp)
        self.base.update({k: float(v) for k, v in stats.items()})
        self.bounds: dict[str, dict] = r["bounds"]
        # ресурс -> {max: стат максимума, regen: стат регена в секунду}
        self.resources: dict[str, dict] = r["resources"]
        self.mods: dict[str, float] = {}          # mod-эффекты (add/sub/mul/div)
        self.current_hp = self._eff("max_hp")     # hp отдельно: его читает весь код комнаты
        self.pools: dict[str, float] = {}         # прочие ресурсы: mana, stamina
        self.refill()
        self.buffs: dict[str, dict] = {}          # buff_id -> {until, ...}
        self.alive = True
        self.kills = 0

    # effective stats -----------------------------------------------------
    def stat(self, key: str) -> float:
        if key in self.resources:
            return self.resource(key)
        if key == "hp_pct":
            return self.current_hp / self._eff("max_hp") * 100.0
        return self._eff(key)

    def _eff(self, key: str) -> float:
        v = self.base.get(key, 0.0) + self.mods.get(key, 0.0)
        b = self.bounds.get(key)
        if b:
            v = min(max(v, b.get("min", -math.inf)), b.get("max", math.inf))
        return v

    def ctx(self, extra: Optional[dict] = None) -> dict:
        c = {k: self._eff(k) for k in (*self.base, *self.mods) if k not in self.resources}
        c.update({name: self.resource(name) for name in self.resources})
        c.update({
            "hp_pct": self.stat("hp_pct"),
            "hp_missing": self._eff("max_hp") - self.current_hp,
            "kills": float(self.kills),
        })
        c["hp_missing_below_40"] = _hp_missing_below_40(c)
        if extra:
            c.update(extra)
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
        last_damage (фактический урон последнего удара героя)."""
        ctx = {**self.owner.ctx(extra), **self.target_ctx("enemy", self.enemy)}
        ctx["last_damage"] = self.last_damage
        return ctx

    def target_ctx(self, prefix: str, t: Optional[Unit]) -> dict:
        """Контекст цели с префиксом: enemy_hp_pct, ally_hp и т.д."""
        if t is None:
            return {}
        c = t.ctx()
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

    def tick(self, t: float, dt: float):
        """regen + duration-истечение баффов + tick-события."""
        self.refresh_passives(t)
        self.owner.regen(dt)
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
        kind = o.get("kind")
        if o.get("when") and not self._test(o["when"], ctx):
            return
        target = self._resolve_target(o.get("target", "self"))
        if target is None:
            return
        amount = compute_amount(o, ctx, self._default_stat(o, target))

        if kind == "mod":
            # Событийная mod-операция задаёт СВОЙ текущий вклад: прошлый вклад
            # этой же операции снимается, новый записывается в _op_contrib.
            # Дельта меряется вокруг одной операции: вложенные события и
            # пересборка пассивного слоя в неё не попадают.
            stat = o.get("stat")
            key = op_key if op_key is not None else (src, id(o))
            old_unit, old_stat, old = self._op_contrib.get(key, (target, stat, 0.0))
            if old:
                old_unit.mods[old_stat] = old_unit.mods.get(old_stat, 0.0) - old
            before = target.mods.get(stat, 0.0)
            self._apply_mod(o, ctx, target)
            self._op_contrib[key] = (target, stat, target.mods.get(stat, 0.0) - before)
            target.clamp_resources()  # мод max_hp вниз: текущее HP не выше нового максимума
        elif kind == "heal":
            res = o.get("stat") or "hp"
            target.heal(amount, res)
            self.log.append(f"t={t:.1f} {src} heal {amount:.2f} -> {res}={target.resource(res):.1f}")
        elif kind == "deal":
            res = o.get("stat") or "hp"
            if res == "hp":
                target.deal_damage(amount, log=self._dmg_log(target))
            else:  # mana burn
                target.set_resource(res, target.resource(res) - amount)
            self.log.append(f"t={t:.1f} {src} deal {amount:.2f} -> {target.name} {res}={target.resource(res):.1f}")
        elif kind == "set":
            res = o.get("stat")
            if res in target.resources:
                target.set_resource(res, amount)
                self.log.append(f"t={t:.1f} {src} set {res}={target.resource(res):.1f}")
        elif kind == "drain":
            res = o.get("stat") or "hp"
            cost, have = amount, target.resource(res)
            if cost > have:
                self.log.append(f"t={t:.1f} {src} drain FAIL (cost {cost:.2f} > {res} {have:.1f})")
                self.run_ops(o.get("fail", []), ctx, t, src + ".fail", event=event)
            else:
                target.set_resource(res, have - cost)  # ровно до 0 HP - смерть (раньше alive оставался True)
                self.log.append(f"t={t:.1f} {src} drain {cost:.2f} -> {res}={target.resource(res):.1f}")
        elif kind == "buff":
            bid = o.get("buff_id")
            prev = target.buffs.get(bid)
            # кулдаун на повторную активацию щита/баффа
            cd = resolve_value(o.get("cooldown"), ctx) if o.get("cooldown") else None
            granted = self._buff_granted_at.get(bid)
            if cd is not None and granted is not None and t - granted < cd:
                self.log.append(f"t={t:.1f} {src} buff {bid} ON COOLDOWN")
                return
            dur = self._duration(o.get("duration"), ctx)
            until = max(prev.get("until", t) if prev else t, t) + dur
            self._buff_granted_at[bid] = t
            target.buffs[bid] = {"until": until, "extend": o.get("extend"),
                                 "cooldown": cd, "last_cd": t, "flags": list(o.get("flags") or [])}
            self.log.append(f"t={t:.1f} {src} buff {bid} +{dur:.1f}s (until {until:.1f})")
            # декларация extend внутри ops-buff: срабатывает при событии ext["on"]
            ext = o.get("extend") or {}
            if ext and event and event == ext.get("on"):
                self._extend_buff(target, bid, ext, ctx, t, src)
        elif kind == "extend":
            bid = o.get("buff_id")
            b = target.buffs.get(bid)
            if b:
                ext = o.get("extend") or b.get("extend") or {}
                ev = event
                if ev is None and "#" in src:
                    # fallback: событие зашито в src вида "effect#event(.fail)"
                    ev = src.rsplit("#", 1)[-1].split(".", 1)[0]
                # фильтр по событию: extend срабатывает только на ext["on"]
                if ext.get("on") and ev != ext.get("on"):
                    self.log.append(
                        f"t={t:.1f} {src} extend {bid}: on={ext['on']} "
                        f"!= event={ev!r} -> skip")
                    return
                self._extend_buff(target, bid, ext, ctx, t, src, buff_obj=b)
        elif kind == "remove_buff":
            target.buffs.pop(o.get("buff_id"), None)
            self.log.append(f"t={t:.1f} {src} remove_buff {o.get('buff_id')}")
        elif kind == "apply_effect":
            eid = o.get("buff_id")  # apply_effect использует buff_id как effect id
            ef = next((e for e in self.effects if e.get("id") == eid), None)
            if ef:
                self.run_ops(ef.get("ops", []), ctx, t, f"{src}->{eid}")
        elif kind == "kill":
            was_alive = target.alive and target.current_hp > 0
            if was_alive:
                # фиксируем фактический урон "добиания" в ctx.last_damage,
                # чтобы heal по ref/pct-of last_damage (лifesteal на execute)
                # считался от реального снятого HP, а не от заявленного dmg
                if target is self.enemy:
                    self.last_damage = target.current_hp
            target.deal_damage(target.current_hp, log=self._dmg_log(target))
            if was_alive:
                if target is self.owner:
                    self.log.append(f"t={t:.1f} {src} KILL {target.name} (self!)"
                                    " -- revive/set-hp ops must follow")
                    self.fire_event("die", t)
                else:
                    # Инкремент kills здесь — ЕДИНСТВЕННЫЙ для целей, убитых
                    # ops-эффектом (execute). Флаг сообщает циклу attack(),
                    # что килл уже засчитан и событие "kill" разослано, —
                    # иначе счётчик удвоился бы (см. attack()).
                    self.owner.kills += 1
                    if target is self.enemy:
                        self._killed_this_attack = True
                    self.log.append(f"t={t:.1f} {src} KILL {target.name}")
                    # каскад событий: die у жертвы / kill у владельца
                    if target is self.enemy:
                        self.fire_event("kill", t)
            # NOTE про единый счётчик kills: run_op("kill") инкрементирует
            # kills ЗДЕСЬ; цикл attack() засчитывает киллы только когда цель
            # умерла от базового удара (см. комментарий в attack()). Флаг
            # _killed_this_attack связывает оба пути и исключает двойной
            # подсчёт execute-убийств (judgement и т.п.).

    # helpers -----------------------------------------------------------------
    def _extend_buff(self, target, bid: str, ext: dict, ctx: dict,
                     t: float, src: str, buff_obj=None):
        """Продлить бафф `bid` по extend-правилу {on, flat|pct}."""
        b = buff_obj if buff_obj is not None else target.buffs.get(bid)
        if b is None:
            return
        add = resolve_value(
            {"flat": ext["flat"]} if ext.get("flat") is not None
            else {"pct": ext.get("pct"), "of": ext.get("of", "max_hp")}
            if ext.get("pct") is not None else {}, ctx)
        b["until"] += add
        self.log.append(f"t={t:.1f} {src} extend {bid} +{add:.1f}s")

    def _default_stat(self, o: dict, unit: Unit) -> Optional[str]:
        """pct без `of` - процент от того же стата ЦЕЛИ операции."""
        stat = o.get("stat")
        return stat and self._prefix(unit) + stat

    def _apply_mod(self, o: dict, ctx: dict, unit: Unit,
                   sink: Optional[dict] = None, mult: float = 1.0):
        """Применить mod-оп к юниту. sink=None -> unit.mods (событийный путь);
        sink=dict -> накопление в отдельный слой (пассивный)."""
        stat = o.get("stat")
        amount = compute_amount(o, ctx, self._default_stat(o, unit))
        mo = o.get("op") or "add"  # op не задан (или null из формы) - add; раньше мод молча не применялся
        if mo in ("add", "sub"):
            amount *= mult  # Effect.amplify (Lost My Self при 1 HP)
        dst = unit.mods if sink is None else sink
        cur = dst.get(stat, 0.0)
        base = unit.base.get(stat, 0.0)
        if mo == "add":
            dst[stat] = cur + amount
        elif mo == "sub":
            dst[stat] = cur - amount
        elif mo == "mul":
            dst[stat] = (base + cur) * amount - base
        elif mo == "div":
            dst[stat] = (base + cur) / amount - base if amount else cur
        elif mo == "set":
            dst[stat] = amount - base
        elif mo == "min":
            dst[stat] = min(base + cur, amount) - base
        elif mo == "max":
            dst[stat] = max(base + cur, amount) - base

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
        if name in ("enemy", "source"):
            return self.enemy
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


def sample_context() -> dict:
    """Полный контекст рантайма на юнитах по умолчанию: какие поля видят условия."""
    return EffectRuntime(Unit("hero"), [], enemy=Unit("enemy")).context()


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
