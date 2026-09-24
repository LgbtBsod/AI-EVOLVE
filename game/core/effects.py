"""
Модуль системы эффектов (Buffs/Debuffs).
Поддерживает:
- Плоские (Flat) и Процентные (Percent) модификаторы
- Стеки (Stacks) эффектов
- Длительность (Duration) и перманентные эффекты
- Приоритеты применения
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import time


class EffectType(Enum):
    """Тип влияния эффекта на характеристику"""
    FLAT = "flat"           # +100 HP, +10 Strength
    PERCENT = "percent"     # +10% HP, +20% Damage
    MULTIPLIER = "mult"     # Глобальный множитель (редко, но бывает)


class EffectTag(Enum):
    """
    Теги для синергии эффектов.
    Позволяют системе определять типы эффектов для модификаторов урона.
    """
    # Общая классификация
    NEGATIVE = "negative"       # Дебафф (для бонуса урона по негативкам)
    POSITIVE = "positive"       # Бафф
    
    # Crowd Control эффекты
    STUN = "stun"               # Полный паралич
    KNOCKDOWN = "knockdown"     # Опрокидывание
    DAZE = "daze"               # Замешательство (снижение точности)
    SLOW = "slow"               # Замедление
    ROOT = "root"               # Обездвиживание
    SILENCE = "silence"         # Запрет заклинаний
    FEAR = "fear"               # Бегство
    CHARM = "charm"             # Очарование
    
    # Toughness связанные
    BREAK_RELATED = "break_related"  # Эффект от пробития стойкости
    TOUGHNESS_DAMAGE = "toughness_damage"  # Влияет на стойкость
    
    # Типы урона
    PHYSICAL = "physical"
    MAGICAL = "magical"
    FIRE = "fire"
    ICE = "ice"
    LIGHTNING = "lightning"
    POISON = "poison"
    BLEED = "bleed"
    
    # Специальные
    DOT = "dot"  # Damage over Time
    HOT = "hot"  # Heal over Time


class StatTarget(Enum):
    """На какие характеристики может влиять эффект"""
    # Base Attributes
    STRENGTH = "strength"
    AGILITY = "agility"
    INTELLIGENCE = "intelligence"
    VITALITY = "vitality"
    WISDOM = "wisdom"
    CHARISMA = "charisma"
    LUCK = "luck"
    ENDURANCE = "endurance"
    
    # Derived Stats - Resources
    HEALTH = "health"
    HEALTH_MAX = "health_max"
    MANA = "mana"
    MANA_MAX = "mana_max"
    STAMINA = "stamina"
    STAMINA_MAX = "stamina_max"
    TOUGHNESS = "toughness"
    TOUGHNESS_MAX = "toughness_max"
    
    # Combat Stats
    PHYSICAL_DAMAGE = "physical_damage"
    MAGICAL_DAMAGE = "magical_damage"
    DEFENSE = "defense"
    ATTACK_SPEED = "attack_speed"
    CRITICAL_CHANCE = "critical_chance"
    CRITICAL_DAMAGE = "critical_damage"
    DODGE_CHANCE = "dodge_chance"
    BLOCK_CHANCE = "block_chance"
    MAGIC_RESISTANCE = "magic_resistance"
    ACCURACY = "accuracy"
    
    # Special Modifiers
    TOUGHNESS_DAMAGE_DEALT = "toughness_damage_dealt"      # Бонус к урону по стойкости
    TOUGHNESS_DAMAGE_TAKEN = "toughness_damage_taken"      # Модификатор урона по стойкости (дебафф)
    DAMAGE_TAKEN_MULTIPLIER = "damage_taken_multiplier"    # Модификатор входящего урона (для состояния Broken)
    DAMAGE_DEALT_MULTIPLIER = "damage_dealt_multiplier"    # Модификатор исходящего урона
    STUN_RESISTANCE = "stun_resistance"
    STATUS_RESISTANCE = "status_resistance"
    MOVEMENT_SPEED = "movement_speed"


@dataclass
class BuffEffect:
    """
    Единичный эффект (бафф или дебафф).
    
    Примеры:
    - Зелье силы: target=STRENGTH, type=FLAT, value=10, duration=60
    - Ярость берсерка: target=PHYSICAL_DAMAGE, type=PERCENT, value=0.20, duration=10, stackable=True
    - Состояние 'Сломлен': target=DAMAGE_TAKEN_MULTIPLIER, type=PERCENT, value=0.25, duration=-1 (пока не снимут)
    - Подсечка: target=MOVEMENT_SPEED, type=PERCENT, value=-1.0, duration=2, tags=[NEGATIVE, KNOCKDOWN]
    """
    id: str
    name: str
    target: StatTarget
    effect_type: EffectType
    value: float
    
    duration: float = -1.0  # -1 означает перманентный эффект
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    
    stackable: bool = False
    max_stacks: int = 99
    current_stacks: int = 1
    
    # Метаданные для визуализации или логики
    description: str = ""
    source: str = "unknown"  # Кто наложил (skill_id, item_id)
    priority: int = 0        # Приоритет при конфликте эффектов
    
    # Теги для синергий (NEGATIVE, STUN, BREAK_RELATED, etc.)
    tags: List[EffectTag] = field(default_factory=list)
    
    # Модификатор ID для группировки однотипных эффектов
    # Например, все эффекты замедления могут иметь modifier_id="movement_slow"
    # Это позволяет суммировать длительности однотипных CC эффектов
    modifier_id: Optional[str] = None

    def __post_init__(self):
        if self.duration > 0 and self.expires_at is None:
            self.expires_at = self.created_at + self.duration

    def is_expired(self) -> bool:
        if self.duration < 0:  # Перманентный
            return False
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def get_remaining_time(self) -> float:
        if self.duration < 0 or self.expires_at is None:
            return float('inf')
        return max(0.0, self.expires_at - time.time())

    def add_stack(self) -> int:
        if not self.stackable:
            return self.current_stacks
        if self.current_stacks < self.max_stacks:
            self.current_stacks += 1
        return self.current_stacks

    def remove_stack(self) -> int:
        if self.current_stacks > 1:
            self.current_stacks -= 1
        return self.current_stacks

    def get_total_value(self) -> float:
        """Возвращает значение с учетом стеков"""
        if self.effect_type == EffectType.PERCENT:
            # Проценты обычно не стакаются линейно в сложных системах, 
            # но для простоты пока сделаем линейно: 10% * 3 стака = 30%
            return self.value * self.current_stacks
        else:
            # Плоские значения стакаются линейно
            return self.value * self.current_stacks
    
    def has_tag(self, tag: EffectTag) -> bool:
        """Проверяет наличие тега у эффекта"""
        return tag in self.tags
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "target": self.target.value,
            "type": self.effect_type.value,
            "value": self.get_total_value(),
            "stacks": self.current_stacks,
            "remaining": self.get_remaining_time(),
            "is_perm": self.duration < 0,
            "tags": [t.value for t in self.tags],
            "modifier_id": self.modifier_id
        }


class ActiveEffectsContainer:
    """
    Контейнер активных эффектов сущности.
    Управляет списком баффов, их стакингом и истечением времени.
    Поддерживает синергии через теги и modifier_id.
    """
    def __init__(self):
        # Ключ: StatTarget, Значение: List[BuffEffect]
        self.effects: Dict[StatTarget, List[BuffEffect]] = {}
        # Для быстрого доступа по ID эффекта (если нужно снять конкретный)
        self.effect_map: Dict[str, BuffEffect] = {}
        
        # Индексация по modifier_id для группировки однотипных эффектов
        # Ключ: modifier_id, Значение: List[BuffEffect]
        self.modifier_index: Dict[str, List[BuffEffect]] = {}

    def add_effect(self, effect: BuffEffect) -> bool:
        """
        Добавляет эффект. Если эффект уже есть и он стакается — увеличивает стак.
        Если не стакается — заменяет (или игнорирует, в зависимости от приоритета).
        """
        target = effect.target
        
        if target not in self.effects:
            self.effects[target] = []

        # Ищем существующий эффект с таким же ID
        existing_effect = None
        for e in self.effects[target]:
            if e.id == effect.id:
                existing_effect = e
                break

        if existing_effect:
            if existing_effect.stackable:
                # Обновляем длительность если новая больше (опционально)
                if effect.duration > existing_effect.duration:
                    existing_effect.expires_at = effect.expires_at
                return bool(existing_effect.add_stack())
            else:
                # Не стакается: проверяем приоритет
                if effect.priority > existing_effect.priority:
                    # Заменяем
                    idx = self.effects[target].index(existing_effect)
                    self.effects[target][idx] = effect
                    del self.effect_map[existing_effect.id]
                    self.effect_map[effect.id] = effect
                    # Обновляем индекс modifier_id
                    self._update_modifier_index(effect, add=True)
                    self._update_modifier_index(existing_effect, add=False)
                    return True
                else:
                    return False # Старый эффект сильнее
        else:
            # Новый эффект
            self.effects[target].append(effect)
            self.effect_map[effect.id] = effect
            # Добавляем в индекс modifier_id если есть
            if effect.modifier_id:
                if effect.modifier_id not in self.modifier_index:
                    self.modifier_index[effect.modifier_id] = []
                self.modifier_index[effect.modifier_id].append(effect)
            return True
    
    def _update_modifier_index(self, effect: BuffEffect, add: bool = True):
        """Добавляет или удаляет эффект из индекса modifier_id"""
        if not effect.modifier_id:
            return
        
        if add:
            if effect.modifier_id not in self.modifier_index:
                self.modifier_index[effect.modifier_id] = []
            if effect not in self.modifier_index[effect.modifier_id]:
                self.modifier_index[effect.modifier_id].append(effect)
        else:
            if effect.modifier_id in self.modifier_index:
                if effect in self.modifier_index[effect.modifier_id]:
                    self.modifier_index[effect.modifier_id].remove(effect)
                if not self.modifier_index[effect.modifier_id]:
                    del self.modifier_index[effect.modifier_id]

    def remove_effect(self, effect_id: str) -> bool:
        """Удаляет эффект по ID"""
        if effect_id not in self.effect_map:
            return False
        
        effect = self.effect_map[effect_id]
        target = effect.target
        
        # Удаляем из индекса modifier_id
        self._update_modifier_index(effect, add=False)
        
        if effect.current_stacks > 1:
            effect.remove_stack()
            return True
        
        self.effects[target].remove(effect)
        del self.effect_map[effect_id]
        return True
    
    def get_effects_by_tag(self, tag: EffectTag) -> List[BuffEffect]:
        """Возвращает все эффекты с указанным тегом"""
        result = []
        for effects_list in self.effects.values():
            for effect in effects_list:
                if effect.has_tag(tag):
                    result.append(effect)
        return result
    
    def count_effects_by_tag(self, tag: EffectTag) -> int:
        """Подсчитывает количество эффектов с указанным тегом"""
        return len(self.get_effects_by_tag(tag))
    
    def has_negative_effects(self) -> bool:
        """Проверяет наличие негативных эффектов (дебаффов)"""
        return self.count_effects_by_tag(EffectTag.NEGATIVE) > 0
    
    def get_negative_effect_count(self) -> int:
        """Возвращает количество негативных эффектов"""
        return self.count_effects_by_tag(EffectTag.NEGATIVE)
    
    def get_cc_duration(self, cc_type: EffectTag) -> float:
        """
        Возвращает общую длительность CC эффекта определенного типа.
        Суммирует длительности всех эффектов с данным тегом (STUN, KNOCKDOWN, etc.)
        """
        total_duration = 0.0
        for effect in self.get_effects_by_tag(cc_type):
            remaining = effect.get_remaining_time()
            if remaining != float('inf'):
                total_duration += remaining
        return total_duration
    
    def get_total_cc_duration(self) -> float:
        """Возвращает суммарную длительность всех CC эффектов"""
        cc_tags = [EffectTag.STUN, EffectTag.KNOCKDOWN, EffectTag.DAZE, 
                   EffectTag.SLOW, EffectTag.ROOT, EffectTag.SILENCE,
                   EffectTag.FEAR, EffectTag.CHARM]
        
        total = 0.0
        for tag in cc_tags:
            total += self.get_cc_duration(tag)
        return total

    def update(self, dt: float):
        """
        Обновляет все эффекты, удаляет истекшие.
        Возвращает список удаленных эффектов (для логирования/событий).
        """
        removed = []
        current_time = time.time()
        
        # Копируем ключи, чтобы безопасно удалять во время итерации
        targets_to_check = list(self.effects.keys())
        
        for target in targets_to_check:
            effects_list = self.effects[target]
            expired_effects = [e for e in effects_list if e.is_expired()]
            
            for eff in expired_effects:
                self.remove_effect(eff.id)
                removed.append(eff)
            
            if not effects_list:
                del self.effects[target]
                
        return removed

    def get_stat_modifier(self, target: StatTarget) -> tuple[float, float]:
        """
        Возвращает суммарный плоский и процентный модификатор для характеристики.
        Returns: (flat_bonus, percent_bonus)
        """
        flat_sum = 0.0
        percent_sum = 0.0
        
        if target not in self.effects:
            return 0.0, 0.0
            
        for effect in self.effects[target]:
            val = effect.get_total_value()
            if effect.effect_type == EffectType.FLAT:
                flat_sum += val
            elif effect.effect_type == EffectType.PERCENT:
                percent_sum += val
                
        return flat_sum, percent_sum

    def get_all_active_effects(self) -> List[Dict]:
        """Возвращает список всех активных эффектов для UI"""
        result = []
        for target_list in self.effects.values():
            for eff in target_list:
                result.append(eff.to_dict())
        return result
