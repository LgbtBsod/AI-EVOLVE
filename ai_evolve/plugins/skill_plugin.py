"""
SkillPlugin - Расширенная система навыков с поддержкой:
- Cost'ов (HP, Mana, Stamina, Toughness)
- Кулдаунов и каст-таймов
- AoE (урон по области через EffectsPlugin)
- Суммонинга сущностей
- Баффов/Дебаффов (Rage, Haste, Freeze и т.д.)
- Скалирования от характеристик

Все скиллы управляются через EffectsPlugin для консистентности.
"""

import random
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from ai_evolve.core.plugin_base import PluginBase
from ai_evolve.core.event_system import EventSystem


class CostType(Enum):
    MANA = "mana"
    STAMINA = "stamina"
    HEALTH = "health"
    TOUGHNESS = "toughness"


class TargetType(Enum):
    SELF = "self"
    SINGLE_TARGET = "single_target"
    AREA = "area"
    CONE = "cone"
    LINE = "line"
    SUMMON = "summon"


@dataclass
class SkillCost:
    """Стоимость использования навыка."""
    cost_type: CostType
    amount: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cost_type": self.cost_type.value,
            "amount": self.amount
        }


@dataclass
class SkillEffect:
    """Эффект навыка (делегирование в EffectsPlugin)."""
    effect_type: str  # burn, freeze, poison, rage, haste, shield, summon, etc.
    duration: float
    magnitude: float
    area_radius: Optional[float] = None  # Для AoE
    summon_entity_type: Optional[str] = None  # Для суммонинга
    summon_count: int = 0
    damage_type: Optional[str] = None  # physical, fire, ice, lightning, etc.
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect_type": self.effect_type,
            "duration": self.duration,
            "magnitude": self.magnitude,
            "area_radius": self.area_radius,
            "summon_entity_type": self.summon_entity_type,
            "summon_count": self.summon_count,
            "damage_type": self.damage_type
        }


@dataclass
class Skill:
    """Навык сущности."""
    id: str
    name: str
    description: str
    
    # Стоимость
    costs: List[SkillCost] = field(default_factory=list)
    
    # Тайминги
    cast_time: float = 0.0  # Время применения
    cooldown: float = 5.0  # Перезарядка
    global_cooldown: float = 1.0  # Глобальный кулдаун
    
    # Таргетинг
    target_type: TargetType = TargetType.SINGLE_TARGET
    range: float = 10.0
    area_radius: float = 0.0  # Для AoE
    cone_angle: float = 0.0  # Для конусных атак
    
    # Эффекты
    effects: List[SkillEffect] = field(default_factory=list)
    
    # Скалирование
    scale_with: Dict[str, float] = field(default_factory=dict)  # stat -> multiplier
    
    # Требования
    level_requirement: int = 1
    weapon_requirement: Optional[str] = None
    
    # Состояние
    current_cooldown: float = 0.0
    is_casting: bool = False
    cast_start_time: float = 0.0
    
    def can_use(self, entity_stats: Dict[str, Any], current_time: float) -> tuple[bool, str]:
        """Проверка возможности использования навыка."""
        # Проверка кулдауна
        if self.current_cooldown > 0:
            elapsed = current_time - (self.cast_start_time + self.cast_time)
            if elapsed < self.cooldown:
                return False, f"Cooldown: {self.cooldown - elapsed:.2f}s remaining"
        
        # Проверка стоимости
        for cost in self.costs:
            stat_name = cost.cost_type.value
            current_value = entity_stats.get(stat_name, 0)
            if current_value < cost.amount:
                return False, f"Insufficient {stat_name}: need {cost.amount}, have {current_value}"
        
        # Проверка уровня
        entity_level = entity_stats.get("level", 1)
        if entity_level < self.level_requirement:
            return False, f"Level requirement: {self.level_requirement}"
        
        return True, "OK"
    
    def start_cast(self, current_time: float):
        """Начать применение навыка."""
        self.is_casting = True
        self.cast_start_time = current_time
    
    def finish_cast(self, current_time: float):
        """Завершить применение навыка."""
        self.is_casting = False
        self.current_cooldown = self.cooldown
        self.cast_start_time = current_time
    
    def update(self, delta_time: float):
        """Обновление кулдаунов."""
        if self.current_cooldown > 0:
            self.current_cooldown = max(0, self.current_cooldown - delta_time)
    
    def get_scaled_effects(self, entity_stats: Dict[str, Any]) -> List[SkillEffect]:
        """Получить эффекты со скалированием."""
        scaled_effects = []
        
        for effect in self.effects:
            scaled_effect = SkillEffect(
                effect_type=effect.effect_type,
                duration=effect.duration,
                magnitude=effect.magnitude,
                area_radius=effect.area_radius,
                summon_entity_type=effect.summon_entity_type,
                summon_count=effect.summon_count,
                damage_type=effect.damage_type
            )
            
            # Скалирование магнитуды
            for stat, multiplier in self.scale_with.items():
                stat_value = entity_stats.get(stat, 0)
                scaled_effect.magnitude += stat_value * multiplier
            
            scaled_effects.append(scaled_effect)
        
        return scaled_effects
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "costs": [cost.to_dict() for cost in self.costs],
            "cast_time": self.cast_time,
            "cooldown": self.cooldown,
            "global_cooldown": self.global_cooldown,
            "target_type": self.target_type.value,
            "range": self.range,
            "area_radius": self.area_radius,
            "cone_angle": self.cone_angle,
            "effects": [effect.to_dict() for effect in self.effects],
            "scale_with": self.scale_with,
            "level_requirement": self.level_requirement,
            "weapon_requirement": self.weapon_requirement
        }


class SkillManager:
    """Менеджер навыков сущности."""
    
    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        self.skills: Dict[str, Skill] = {}
        self.skill_queue: List[Skill] = []
        self.current_skill: Optional[Skill] = None
        self.last_skill_time: float = 0.0
        self.global_cooldown: float = 0.0
    
    def add_skill(self, skill: Skill):
        """Добавить навык."""
        self.skills[skill.id] = skill
    
    def remove_skill(self, skill_id: str):
        """Удалить навык."""
        if skill_id in self.skills:
            del self.skills[skill_id]
    
    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Получить навык по ID."""
        return self.skills.get(skill_id)
    
    def can_use_skill(self, skill_id: str, entity_stats: Dict[str, Any], 
                     current_time: float) -> tuple[bool, str]:
        """Проверка доступности навыка."""
        if skill_id not in self.skills:
            return False, f"Skill {skill_id} not found"
        
        skill = self.skills[skill_id]
        
        # Проверка глобального кулдауна
        if self.global_cooldown > 0:
            return False, f"Global cooldown: {self.global_cooldown:.2f}s"
        
        # Проверка текущего каста
        if self.current_skill and self.current_skill.is_casting:
            return False, "Already casting"
        
        return skill.can_use(entity_stats, current_time)
    
    def use_skill(self, skill_id: str, target: Any, entity_stats: Dict[str, Any],
                 current_time: float) -> tuple[bool, List[Dict[str, Any]]]:
        """Использовать навык."""
        can_use, reason = self.can_use_skill(skill_id, entity_stats, current_time)
        if not can_use:
            return False, [{"type": "error", "message": reason}]
        
        skill = self.skills[skill_id]
        
        # Начало каста
        if skill.cast_time > 0:
            skill.start_cast(current_time)
            self.current_skill = skill
            return True, [{"type": "cast_start", "skill_id": skill_id}]
        
        # Мгновенное применение
        return self._execute_skill(skill, target, entity_stats, current_time)
    
    def _execute_skill(self, skill: Skill, target: Any, entity_stats: Dict[str, Any],
                      current_time: float) -> tuple[bool, List[Dict[str, Any]]]:
        """Выполнить навык."""
        results = []
        
        # Применение стоимости
        for cost in skill.costs:
            stat_name = cost.cost_type.value
            # В реальной игре здесь будет вычитание из характеристик сущности
            results.append({
                "type": "cost_applied",
                "stat": stat_name,
                "amount": cost.amount
            })
        
        # Получение скалированных эффектов
        scaled_effects = skill.get_scaled_effects(entity_stats)
        
        # Применение эффектов через EventsPlugin (делегирование)
        for effect in scaled_effects:
            results.append({
                "type": "effect_applied",
                "effect": effect.to_dict(),
                "target": target,
                "area_radius": skill.area_radius if skill.target_type == TargetType.AREA else None
            })
        
        # Завершение каста
        skill.finish_cast(current_time)
        self.current_skill = None
        self.global_cooldown = skill.global_cooldown
        
        results.append({
            "type": "skill_used",
            "skill_id": skill.id,
            "target": target
        })
        
        return True, results
    
    def update(self, delta_time: float, current_time: float):
        """Обновление менеджера навыков."""
        # Обновление всех навыков
        for skill in self.skills.values():
            skill.update(delta_time)
        
        # Обновление глобального кулдауна
        if self.global_cooldown > 0:
            self.global_cooldown = max(0, self.global_cooldown - delta_time)
        
        # Проверка текущего каста
        if self.current_skill and self.current_skill.is_casting:
            cast_elapsed = current_time - self.current_skill.cast_start_time
            if cast_elapsed >= self.current_skill.cast_time:
                # Каст завершён, выполняем навык
                # В реальной игре нужен target и entity_stats
                pass


# Базовые шаблоны навыков
SKILL_TEMPLATES = {
    "basic_attack": Skill(
        id="basic_attack",
        name="Базовая атака",
        description="Простая атака оружием",
        costs=[SkillCost(CostType.STAMINA, 5)],
        cast_time=0.0,
        cooldown=1.0,
        target_type=TargetType.SINGLE_TARGET,
        range=5.0,
        effects=[SkillEffect("physical_damage", 0.0, 10.0)]
    ),
    
    "fireball": Skill(
        id="fireball",
        name="Огненный шар",
        description="Запускает огненный шар во врага",
        costs=[SkillCost(CostType.MANA, 20)],
        cast_time=1.0,
        cooldown=3.0,
        target_type=TargetType.SINGLE_TARGET,
        range=20.0,
        area_radius=3.0,
        effects=[
            SkillEffect("burn", 5.0, 15.0, damage_type="fire"),
            SkillEffect("magic_damage", 0.0, 50.0, damage_type="fire")
        ],
        scale_with={"intelligence": 0.5}
    ),
    
    "rage": Skill(
        id="rage",
        name="Ярость",
        description="Входит в состояние ярости, увеличивая урон",
        costs=[SkillCost(CostType.HEALTH, 10)],
        cast_time=0.5,
        cooldown=30.0,
        target_type=TargetType.SELF,
        effects=[SkillEffect("rage", 10.0, 1.5)]  # 50% увеличение урона на 10 сек
    ),
    
    "summon_minion": Skill(
        id="summon_minion",
        name="Призыв прислужника",
        description="Призывает прислужника для помощи в бою",
        costs=[SkillCost(CostType.MANA, 50), SkillCost(CostType.STAMINA, 20)],
        cast_time=3.0,
        cooldown=60.0,
        target_type=TargetType.SUMMON,
        range=5.0,
        effects=[
            SkillEffect("summon", 30.0, 0.0, summon_entity_type="minion", summon_count=1)
        ],
        scale_with={"intelligence": 0.3, "strength": 0.2}
    ),
    
    "blizzard": Skill(
        id="blizzard",
        name="Ледяная буря",
        description="Создаёт ледяную бурю в области",
        costs=[SkillCost(CostType.MANA, 40)],
        cast_time=2.0,
        cooldown=15.0,
        target_type=TargetType.AREA,
        range=15.0,
        area_radius=8.0,
        effects=[
            SkillEffect("freeze", 2.0, 0.5, area_radius=8.0, damage_type="ice"),
            SkillEffect("magic_damage", 0.0, 30.0, area_radius=8.0, damage_type="ice")
        ],
        scale_with={"intelligence": 0.6}
    ),
    
    "heal": Skill(
        id="heal",
        name="Исцеление",
        description="Восстанавливает здоровье",
        costs=[SkillCost(CostType.MANA, 25)],
        cast_time=1.5,
        cooldown=8.0,
        target_type=TargetType.SINGLE_TARGET,
        range=10.0,
        effects=[SkillEffect("heal", 0.0, 50.0)],
        scale_with={"intelligence": 0.4, "spirit": 0.3}
    ),
    
    "shield_bash": Skill(
        id="shield_bash",
        name="Удар щитом",
        description="Оглушает врага ударом щита",
        costs=[SkillCost(CostType.STAMINA, 15)],
        cast_time=0.0,
        cooldown=10.0,
        target_type=TargetType.SINGLE_TARGET,
        range=3.0,
        effects=[
            SkillEffect("stun", 2.0, 0.0),
            SkillEffect("physical_damage", 0.0, 20.0)
        ],
        scale_with={"strength": 0.5}
    ),
    
    "whirlwind": Skill(
        id="whirlwind",
        name="Вихрь",
        description="Атакует всех врагов вокруг",
        costs=[SkillCost(CostType.STAMINA, 30)],
        cast_time=0.0,
        cooldown=12.0,
        target_type=TargetType.AREA,
        range=0.0,
        area_radius=5.0,
        effects=[
            SkillEffect("physical_damage", 0.0, 40.0, area_radius=5.0)
        ],
        scale_with={"strength": 0.4, "agility": 0.2}
    )
}


class SkillPlugin(PluginBase):
    """Плагин управления навыками."""
    
    name = "skill"
    version = "1.0.0"
    description = "Система навыков с поддержкой AoE, суммонинга и баффов"
    
    dependencies = ["effects", "combat"]
    
    def __init__(self):
        super().__init__()
        self.skill_managers: Dict[str, SkillManager] = {}
        self.templates: Dict[str, Skill] = SKILL_TEMPLATES.copy()
    
    def initialize(self, config: Dict[str, Any], game_core: Any) -> bool:
        """Инициализация плагина."""
        try:
            self.game_core = game_core
            self.event_system = EventSystem.get_instance()
            
            # Регистрация обработчиков событий
            self.event_system.subscribe("entity.create", self._on_entity_create)
            self.event_system.subscribe("entity.destroy", self._on_entity_destroy)
            self.event_system.subscribe("combat.update", self._on_combat_update)
            
            self.logger.info("SkillPlugin initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize SkillPlugin: {e}")
            return False
    
    def _on_entity_create(self, event_data: Dict[str, Any]):
        """Создание сущности - добавление менеджера навыков."""
        entity_id = event_data.get("entity_id")
        if entity_id and entity_id not in self.skill_managers:
            self.skill_managers[entity_id] = SkillManager(entity_id)
            
            # Добавление базовых навыков (можно кастомизировать)
            manager = self.skill_managers[entity_id]
            for skill_id, skill in self.templates.items():
                # В реальной игре здесь будет логика добавления конкретных навыков
                pass
            
            self.logger.debug(f"Created skill manager for entity {entity_id}")
    
    def _on_entity_destroy(self, event_data: Dict[str, Any]):
        """Уничтожение сущности - удаление менеджера навыков."""
        entity_id = event_data.get("entity_id")
        if entity_id in self.skill_managers:
            del self.skill_managers[entity_id]
            self.logger.debug(f"Removed skill manager for entity {entity_id}")
    
    def _on_combat_update(self, event_data: Dict[str, Any]):
        """Обновление боя - обновление навыков."""
        delta_time = event_data.get("delta_time", 0.016)
        current_time = event_data.get("current_time", time.time())
        
        for manager in self.skill_managers.values():
            manager.update(delta_time, current_time)
    
    def add_skill_to_entity(self, entity_id: str, skill: Skill):
        """Добавить навык сущности."""
        if entity_id not in self.skill_managers:
            self.skill_managers[entity_id] = SkillManager(entity_id)
        
        self.skill_managers[entity_id].add_skill(skill)
        self.logger.info(f"Added skill {skill.name} to entity {entity_id}")
    
    def use_skill(self, entity_id: str, skill_id: str, target: Any, 
                 entity_stats: Dict[str, Any]) -> tuple[bool, List[Dict[str, Any]]]:
        """Использовать навык сущностью."""
        if entity_id not in self.skill_managers:
            return False, [{"type": "error", "message": f"Entity {entity_id} has no skill manager"}]
        
        current_time = time.time()
        manager = self.skill_managers[entity_id]
        
        success, results = manager.use_skill(skill_id, target, entity_stats, current_time)
        
        if success:
            # Событие использования навыка
            self.event_system.emit("skill.used", {
                "entity_id": entity_id,
                "skill_id": skill_id,
                "target": target,
                "results": results
            })
        
        return success, results
    
    def get_entity_skills(self, entity_id: str) -> List[Dict[str, Any]]:
        """Получить список навыков сущности."""
        if entity_id not in self.skill_managers:
            return []
        
        return [skill.to_dict() for skill in self.skill_managers[entity_id].skills.values()]
    
    def register_skill_template(self, skill: Skill):
        """Зарегистрировать шаблон навыка."""
        self.templates[skill.id] = skill
        self.logger.info(f"Registered skill template: {skill.name}")
    
    def shutdown(self):
        """Завершение работы плагина."""
        self.skill_managers.clear()
        self.logger.info("SkillPlugin shutdown complete")
