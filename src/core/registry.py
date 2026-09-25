"""Registry System — расширяемость движка без правки ядра (Фаза 1, п. 5.1.3).

Правило №2 из архитектуры: «Всё новое — регистрация, не правка ядра».
Персонаж/предмет/мод добавляет записи в реестры (Conditions, Selectors, Scales,
DamageTypes, Flags, Effects, Abilities...), а рантайм их только исполняет.

Особенности:
    * Именованные предикаты/селекторы/скейлы хранятся как Python-callables,
      но ССЫЛАЮТСЯ В СХЕМЕ строками ({kind="registry", name="is_night"}) —
      сериализуемость схемы сохраняется (см. src/effects/schema.py).
    * freeze() — финальная блокировка перед релизом: после неё register() падает.
    * duplicate_policy: "error" | "skip" | "override" — политика коллизий имён.
    * Ключевые домены предзарегистрированы EMPTY-дефолтами, чтобы unknown-name
      никогда не ронял бой: get_or_default.

Стандартный набор доменов (ЧАСТЬ 0.4 справочника):
    stats, resources, statuses, effects, abilities, items,
    conditions, selectors, scales, damage_types, flags, layers

Пример:
    reg = default_registries()
    reg["conditions"].register("hp_below_half", lambda ent, ctx: ent.hp < ent.max_hp * 0.5)
    ...в схеме эффекта: {"when": {"kind": "registry", "name": "hp_below_half"}}
    fn = reg["conditions"].get("hp_below_half")
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional


class RegistryError(RuntimeError):
    pass


class FrozenRegistryError(RegistryError):
    pass


class DuplicateEntryError(RegistryError):
    pass


class Registry:
    """Именованное хранилище определений одного домена."""

    def __init__(self, name: str, duplicate_policy: str = "error"):
        if duplicate_policy not in ("error", "skip", "override"):
            raise RegistryError(f"bad duplicate_policy: {duplicate_policy}")
        self.name = name
        self.duplicate_policy = duplicate_policy
        self._entries: Dict[str, Any] = {}
        self._frozen = False

    # ---------- запись ----------

    def register(self, name: str, definition: Any) -> Any:
        """Зарегистрировать определение. Расширение ядра не требуется."""
        if self._frozen:
            raise FrozenRegistryError(f"registry '{self.name}' is frozen")
        if not isinstance(name, str) or not name:
            raise RegistryError(f"registry '{self.name}': entry name must be non-empty string")
        if name in self._entries:
            if self.duplicate_policy == "error":
                raise DuplicateEntryError(f"{self.name}.{name} already registered")
            if self.duplicate_policy == "skip":
                return self._entries[name]
            # override
        self._entries[name] = definition
        return definition

    def unregister(self, name: str) -> None:
        if self._frozen:
            raise FrozenRegistryError(f"registry '{self.name}' is frozen")
        self._entries.pop(name, None)

    def freeze(self) -> None:
        """Финальная блокировка перед релизом."""
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    # ---------- чтение ----------

    def get(self, name: str) -> Any:
        try:
            return self._entries[name]
        except KeyError:
            raise RegistryError(f"{self.name}.{name}: not registered "
                                f"(known: {sorted(self._entries)[:20]})") from None

    def get_or_default(self, name: str, default: Any = None) -> Any:
        return self._entries.get(name, default)

    def has(self, name: str) -> bool:
        return name in self._entries

    def names(self) -> List[str]:
        return sorted(self._entries)

    def items(self) -> Iterable[tuple]:
        return self._entries.items()

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def __getitem__(self, name: str) -> Any:
        return self.get(name)

    def __repr__(self) -> str:
        return f"<Registry {self.name}: {len(self._entries)} entries{' FROZEN' if self._frozen else ''}>"


# --------------------------------------------------------------------------
# Реестр реестров
# --------------------------------------------------------------------------

CORE_DOMAINS = (
    "stats", "resources", "statuses", "effects", "abilities", "items",
    "conditions", "selectors", "scales", "damage_types", "flags", "layers",
)


class RegistrySet:
    """Набор доменных реестров движка: registries["conditions"].register(...)"""

    def __init__(self, domains: Iterable[str] = CORE_DOMAINS,
                 duplicate_policy: str = "error"):
        self._domains: Dict[str, Registry] = {}
        for d in domains:
            self.create_domain(d, duplicate_policy=duplicate_policy)

    def create_domain(self, name: str, duplicate_policy: str = "error") -> Registry:
        if name in self._domains:
            return self._domains[name]
        reg = Registry(name, duplicate_policy=duplicate_policy)
        self._domains[name] = reg
        return reg

    def domain(self, name: str) -> Registry:
        try:
            return self._domains[name]
        except KeyError:
            raise RegistryError(f"unknown registry domain '{name}' "
                                f"(known: {sorted(self._domains)})") from None

    def register(self, domain: str, name: str, definition: Any) -> Any:
        """Сокращение: registries.register('conditions', 'is_night', fn)."""
        return self.domain(domain).register(name, definition)

    def get(self, domain: str, name: str) -> Any:
        return self.domain(domain).get(name)

    def freeze_all(self) -> None:
        for reg in self._domains.values():
            reg.freeze()

    def domains(self) -> List[str]:
        return sorted(self._domains)

    def __getitem__(self, name: str) -> Registry:
        return self.domain(name)

    def __contains__(self, name: object) -> bool:
        return name in self._domains


# --------------------------------------------------------------------------
# Дефолтные записи ключевых доменов
# --------------------------------------------------------------------------

def _always_true(*args, **kwargs) -> bool:
    return True


def _zero_scale(*args, **kwargs) -> float:
    return 0.0


def default_registries(duplicate_policy: str = "error") -> RegistrySet:
    """RegistrySet с базовыми записями core-доменов (расширяется контентом)."""
    rs = RegistrySet(duplicate_policy=duplicate_policy)

    # Layers (ЧАСТЬ 1): имя → приоритет исполнения (меньше — раньше).
    for i, layer in enumerate(("effect", "social", "entity", "state", "world",
                               "rules", "temporal", "ontological", "meta", "narrative")):
        rs.register("layers", layer, {"priority": i})

    # DamageTypes (ЧАСТЬ 0.4): тип → свойства резистов.
    for dt in ("physical", "elemental", "chakra", "cursed_energy",
               "genjutsu", "true", "existential"):
        rs.register("damage_types", dt, {"resistible": dt not in ("true", "existential")})

    # Conditions: always + заглушки; контент добавляет свои именованные предикаты.
    rs.register("conditions", "always", _always_true)

    # Scales: flat-масштаб (игнорирует источник, возвращает factor).
    rs.register("scales", "flat", lambda value, factor=1.0, **kw: float(value) * float(factor))
    rs.register("scales", "none", _zero_scale)

    # Flags: известные bypass-флаги (значения — булевы константы-описания).
    for flag in ("bypass_infinity", "true_damage", "no_resurrection", "undodgeable"):
        rs.register("flags", flag, {"kind": "flag"})

    return rs
