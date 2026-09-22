"""
Калькулятор характеристик с поддержкой:
- Базовых атрибутов (Strength, Agility, etc.)
- Производных характеристик (HP, Mana, Damage, etc.)
- Плоских и процентных бонусов от эффектов
- Скалирования от уровня
- Модификаторов от состояния стойкости
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from enum import Enum

# Импортируем наши системы - используем абсолютные импорты для совместимости
try:
    from .effects import ActiveEffectsContainer, StatTarget, EffectType
    from .toughness import ToughnessComponent, ToughnessState
except ImportError:
    from effects import ActiveEffectsContainer, StatTarget, EffectType
    from toughness import ToughnessComponent, ToughnessState


@dataclass
class BaseAttributes:
    """Базовые атрибуты сущности"""
    strength: float = 10.0
    agility: float = 10.0
    intelligence: float = 10.0
    vitality: float = 10.0
    wisdom: float = 10.0
    charisma: float = 10.0
    luck: float = 10.0
    endurance: float = 10.0
    
    def to_dict(self) -> dict:
        return {
            "strength": self.strength,
            "agility": self.agility,
            "intelligence": self.intelligence,
            "vitality": self.vitality,
            "wisdom": self.wisdom,
            "charisma": self.charisma,
            "luck": self.luck,
            "endurance": self.endurance
        }


@dataclass
class DerivedStats:
    """Производные характеристики (рассчитываются из базовых + бонусы)"""
    # Resources
    health_max: float = 100.0
    health_current: float = 100.0
    mana_max: float = 50.0
    mana_current: float = 50.0
    stamina_max: float = 100.0
    stamina_current: float = 100.0
    toughness_max: float = 100.0
    toughness_current: float = 100.0
    
    # Combat Stats
    physical_damage: float = 10.0
    magical_damage: float = 10.0
    defense: float = 5.0
    attack_speed: float = 1.0
    critical_chance: float = 0.05
    critical_damage: float = 1.5
    dodge_chance: float = 0.0
    block_chance: float = 0.0
    magic_resistance: float = 0.0
    accuracy: float = 1.0
    
    # Special
    toughness_damage_dealt: float = 1.0  # Множитель урона по стойкости
    damage_taken_multiplier: float = 1.0  # Множитель получаемого урона
    movement_speed: float = 1.0
    
    def to_dict(self) -> dict:
        return {
            "health_max": self.health_max,
            "health_current": self.health_current,
            "mana_max": self.mana_max,
            "mana_current": self.mana_current,
            "stamina_max": self.stamina_max,
            "stamina_current": self.stamina_current,
            "toughness_max": self.toughness_max,
            "toughness_current": self.toughness_current,
            "physical_damage": self.physical_damage,
            "magical_damage": self.magical_damage,
            "defense": self.defense,
            "attack_speed": self.attack_speed,
            "critical_chance": self.critical_chance,
            "critical_damage": self.critical_damage,
            "dodge_chance": self.dodge_chance,
            "block_chance": self.block_chance,
            "magic_resistance": self.magic_resistance,
            "accuracy": self.accuracy,
            "toughness_damage_dealt": self.toughness_damage_dealt,
            "damage_taken_multiplier": self.damage_taken_multiplier,
            "movement_speed": self.movement_speed
        }


@dataclass
class ScalingConfig:
    """
    Конфигурация скалирования характеристик от уровня.
    Формула: base_value + (level * scale_per_level)
    """
    # Скалирование базовых атрибутов за уровень
    strength_per_level: float = 1.0
    agility_per_level: float = 1.0
    intelligence_per_level: float = 1.0
    vitality_per_level: float = 2.0
    wisdom_per_level: float = 1.0
    charisma_per_level: float = 0.5
    luck_per_level: float = 0.5
    endurance_per_level: float = 1.5
    
    # Скалирование производных характеристик
    health_per_vitality: float = 10.0      # 10 HP за 1 точку Vitality
    mana_per_wisdom: float = 8.0           # 8 MP за 1 точку Wisdom
    stamina_per_endurance: float = 5.0     # 5 Stamina за 1 точку Endurance
    toughness_per_endurance: float = 3.0   # 3 Toughness за 1 точку Endurance
    
    # Урон от атрибутов
    physical_damage_per_strength: float = 0.5
    magical_damage_per_intelligence: float = 0.6
    defense_per_endurance: float = 0.3
    defense_per_strength: float = 0.1
    
    # Критические шансы
    crit_chance_per_agility: float = 0.001  # 0.1% за точку ловкости
    crit_damage_per_luck: float = 0.02      # 2% за точку удачи
    
    # Dodge/Block
    dodge_per_agility: float = 0.0005       # 0.05% за точку ловкости
    block_per_strength: float = 0.0003      # 0.03% за точку силы


class StatCalculator:
    """
    Калькулятор характеристик.
    Учитывает:
    - Базовые значения
    - Скалирование от уровня
    - Плоские бонусы (Flat)
    - Процентные бонусы (Percent)
    - Состояние стойкости
    """
    
    def __init__(self, scaling_config: Optional[ScalingConfig] = None):
        self.scaling_config = scaling_config or ScalingConfig()
    
    def calculate_base_with_scaling(
        self, 
        base_value: float, 
        level: int, 
        scale_per_level: float
    ) -> float:
        """
        Рассчитывает значение с учетом скалирования от уровня.
        Формула: base_value + (level - 1) * scale_per_level
        """
        return base_value + (max(1, level) - 1) * scale_per_level
    
    def apply_effects(
        self,
        base_value: float,
        effects_container: ActiveEffectsContainer,
        stat_target: StatTarget
    ) -> float:
        """
        Применяет эффекты к характеристике.
        Сначала плоские бонусы, потом процентные.
        Формула: (base + flat_bonus) * (1 + percent_bonus)
        """
        flat_bonus, percent_bonus = effects_container.get_stat_modifier(stat_target)
        
        # Сначала добавляем плоский бонус
        after_flat = base_value + flat_bonus
        
        # Затем применяем процентный множитель
        final_value = after_flat * (1.0 + percent_bonus)
        
        return max(0.0, final_value)  # Не допускаем отрицательных значений
    
    def calculate_attributes(
        self,
        base_attrs: BaseAttributes,
        level: int,
        effects: ActiveEffectsContainer
    ) -> BaseAttributes:
        """Рассчитывает итоговые базовые атрибуты с учетом уровня и эффектов"""
        
        attrs = BaseAttributes(
            strength=self.calculate_base_with_scaling(
                base_attrs.strength, level, self.scaling_config.strength_per_level
            ),
            agility=self.calculate_base_with_scaling(
                base_attrs.agility, level, self.scaling_config.agility_per_level
            ),
            intelligence=self.calculate_base_with_scaling(
                base_attrs.intelligence, level, self.scaling_config.intelligence_per_level
            ),
            vitality=self.calculate_base_with_scaling(
                base_attrs.vitality, level, self.scaling_config.vitality_per_level
            ),
            wisdom=self.calculate_base_with_scaling(
                base_attrs.wisdom, level, self.scaling_config.wisdom_per_level
            ),
            charisma=self.calculate_base_with_scaling(
                base_attrs.charisma, level, self.scaling_config.charisma_per_level
            ),
            luck=self.calculate_base_with_scaling(
                base_attrs.luck, level, self.scaling_config.luck_per_level
            ),
            endurance=self.calculate_base_with_scaling(
                base_attrs.endurance, level, self.scaling_config.endurance_per_level
            ),
        )
        
        # Применяем эффекты к каждому атрибуту
        attrs.strength = self.apply_effects(attrs.strength, effects, StatTarget.STRENGTH)
        attrs.agility = self.apply_effects(attrs.agility, effects, StatTarget.AGILITY)
        attrs.intelligence = self.apply_effects(attrs.intelligence, effects, StatTarget.INTELLIGENCE)
        attrs.vitality = self.apply_effects(attrs.vitality, effects, StatTarget.VITALITY)
        attrs.wisdom = self.apply_effects(attrs.wisdom, effects, StatTarget.WISDOM)
        attrs.charisma = self.apply_effects(attrs.charisma, effects, StatTarget.CHARISMA)
        attrs.luck = self.apply_effects(attrs.luck, effects, StatTarget.LUCK)
        attrs.endurance = self.apply_effects(attrs.endurance, effects, StatTarget.ENDURANCE)
        
        return attrs
    
    def calculate_derived_stats(
        self,
        attributes: BaseAttributes,
        level: int,
        effects: ActiveEffectsContainer,
        toughness_component: Optional[ToughnessComponent] = None
    ) -> DerivedStats:
        """
        Рассчитывает производные характеристики на основе атрибутов.
        """
        cfg = self.scaling_config
        
        # === Ресурсы ===
        # Здоровье от Vitality
        health_base = 100.0 + (level * 5.0)  # База + скалирование от уровня
        health_from_vitality = attributes.vitality * cfg.health_per_vitality
        health_max = self.apply_effects(
            health_base + health_from_vitality, 
            effects, 
            StatTarget.HEALTH_MAX
        )
        
        # Мана от Wisdom
        mana_base = 50.0 + (level * 3.0)
        mana_from_wisdom = attributes.wisdom * cfg.mana_per_wisdom
        mana_max = self.apply_effects(
            mana_base + mana_from_wisdom,
            effects,
            StatTarget.MANA_MAX
        )
        
        # Стамина от Endurance
        stamina_base = 100.0 + (level * 2.0)
        stamina_from_endurance = attributes.endurance * cfg.stamina_per_endurance
        stamina_max = self.apply_effects(
            stamina_base + stamina_from_endurance,
            effects,
            StatTarget.STAMINA_MAX
        )
        
        # Стойкость от Endurance
        toughness_base = 100.0
        if toughness_component:
            toughness_base = toughness_component.config.max_toughness
        toughness_from_endurance = attributes.endurance * cfg.toughness_per_endurance
        toughness_max = self.apply_effects(
            toughness_base + toughness_from_endurance,
            effects,
            StatTarget.TOUGHNESS_MAX
        )
        
        # === Боевые характеристики ===
        # Физический урон от Strength
        phys_dmg_base = 10.0
        phys_dmg_from_str = attributes.strength * cfg.physical_damage_per_strength
        physical_damage = self.apply_effects(
            phys_dmg_base + phys_dmg_from_str,
            effects,
            StatTarget.PHYSICAL_DAMAGE
        )
        
        # Магический урон от Intelligence
        mage_dmg_base = 10.0
        mage_dmg_from_int = attributes.intelligence * cfg.magical_damage_per_intelligence
        magical_damage = self.apply_effects(
            mage_dmg_base + mage_dmg_from_int,
            effects,
            StatTarget.MAGICAL_DAMAGE
        )
        
        # Защита от Endurance и Strength
        defense_base = 5.0
        defense_from_end = attributes.endurance * cfg.defense_per_endurance
        defense_from_str = attributes.strength * cfg.defense_per_strength
        defense = self.apply_effects(
            defense_base + defense_from_end + defense_from_str,
            effects,
            StatTarget.DEFENSE
        )
        
        # Скорость атаки (база 1.0 атаки в секунду)
        attack_speed = self.apply_effects(1.0, effects, StatTarget.ATTACK_SPEED)
        
        # Критический шанс от Agility
        crit_chance_base = 0.05  # 5% база
        crit_chance_from_agi = attributes.agility * cfg.crit_chance_per_agility
        critical_chance = self.apply_effects(
            crit_chance_base + crit_chance_from_agi,
            effects,
            StatTarget.CRITICAL_CHANCE
        )
        critical_chance = min(critical_chance, 0.75)  # Кап 75%
        
        # Критический урон от Luck
        crit_dmg_base = 1.5  # 150%
        crit_dmg_from_luck = attributes.luck * cfg.crit_damage_per_luck
        critical_damage = self.apply_effects(
            crit_dmg_base + crit_dmg_from_luck,
            effects,
            StatTarget.CRITICAL_DAMAGE
        )
        
        # Уклонение от Agility
        dodge_chance = attributes.agility * cfg.dodge_per_agility
        dodge_chance = self.apply_effects(
            dodge_chance,
            effects,
            StatTarget.DODGE_CHANCE
        )
        dodge_chance = min(dodge_chance, 0.5)  # Кап 50%
        
        # Блок от Strength
        block_chance = attributes.strength * cfg.block_per_strength
        block_chance = self.apply_effects(
            block_chance,
            effects,
            StatTarget.BLOCK_CHANCE
        )
        block_chance = min(block_chance, 0.4)  # Кап 40%
        
        # Сопротивление магии (база + от Wisdom)
        magic_resistance = self.apply_effects(
            attributes.wisdom * 0.1,
            effects,
            StatTarget.MAGIC_RESISTANCE
        )
        
        # Точность (база 1.0)
        accuracy = self.apply_effects(1.0, effects, StatTarget.ACCURACY)
        
        # === Специальные модификаторы ===
        # Урон по стойкости
        toughness_dmg = self.apply_effects(
            1.0,
            effects,
            StatTarget.TOUGHNESS_DAMAGE_DEALT
        )
        
        # Множитель получаемого урона
        damage_taken_mult = self.apply_effects(
            1.0,
            effects,
            StatTarget.DAMAGE_TAKEN_MULTIPLIER
        )
        
        # Учитываем состояние стойкости (если есть компонент)
        if toughness_component:
            toughness_mod = toughness_component.get_damage_reduction()
            # Если отрицательный - значит урон увеличивается (состояние BROKEN)
            damage_taken_mult += toughness_mod
        
        # Скорость движения
        movement_speed = self.apply_effects(1.0, effects, StatTarget.MOVEMENT_SPEED)
        
        return DerivedStats(
            health_max=health_max,
            health_current=min(health_max, health_max),  # Полное здоровье при пересчете
            mana_max=mana_max,
            mana_current=min(mana_max, mana_max),
            stamina_max=stamina_max,
            stamina_current=min(stamina_max, stamina_max),
            toughness_max=toughness_max,
            toughness_current=min(toughness_max, toughness_max if not toughness_component else toughness_component.current_toughness),
            physical_damage=physical_damage,
            magical_damage=magical_damage,
            defense=defense,
            attack_speed=attack_speed,
            critical_chance=critical_chance,
            critical_damage=critical_damage,
            dodge_chance=dodge_chance,
            block_chance=block_chance,
            magic_resistance=magic_resistance,
            accuracy=accuracy,
            toughness_damage_dealt=toughness_dmg,
            damage_taken_multiplier=damage_taken_mult,
            movement_speed=movement_speed
        )
    
    def calculate_all(
        self,
        base_attrs: BaseAttributes,
        level: int,
        effects: ActiveEffectsContainer,
        toughness_component: Optional[ToughnessComponent] = None
    ) -> tuple[BaseAttributes, DerivedStats]:
        """Полный расчет всех характеристик"""
        attrs = self.calculate_attributes(base_attrs, level, effects)
        stats = self.calculate_derived_stats(attrs, level, effects, toughness_component)
        return attrs, stats
