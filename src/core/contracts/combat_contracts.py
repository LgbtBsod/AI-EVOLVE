"""
Боевые контракты для стандартизации механик боя.
Интегрируют ML-агентов для принятия решений в реальном времени.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

from src.core.contracts.smart_contracts import SmartContract, ContractResult, ContractStatus, register_contract
from src.ml_agents.adaptive_agent import (
    AdaptiveRLAgent, BattleContext, EntityState, 
    SkillInfo, WeaponInfo, ActionType, SkillDiscoveryState
)

logger = logging.getLogger(__name__)


@dataclass
class CombatAction:
    """Действие в бою."""
    action_type: ActionType
    target_id: Optional[str] = None
    skill_id: Optional[str] = None
    weapon_id: Optional[str] = None
    direction: Optional[tuple] = None
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@register_contract
class AttackContract(SmartContract):
    """
    Контракт атаки цели.
    Проверяет:
    - Дистанцию до цели
    - Линию видимости
    - Кулдауны
    - Ресурсы (мана, стамина)
    """
    
    def __init__(self, attacker_id: str, target_id: str, 
                 attack_type: str = "melee", skill_id: Optional[str] = None):
        super().__init__(f"attack_{attacker_id}_{target_id}")
        
        self.attacker_id = attacker_id
        self.target_id = target_id
        self.attack_type = attack_type
        self.skill_id = skill_id
        
        # Контекст будет установлен перед выполнением
        self.attacker_state: Optional[EntityState] = None
        self.target_state: Optional[EntityState] = None
        self.distance: float = 0.0
        self.has_los: bool = False
        self.ml_agent: Optional[AdaptiveRLAgent] = None
    
    def execute(self) -> ContractResult[Dict]:
        """Выполнить атаку."""
        if not self.attacker_state or not self.target_state:
            return ContractResult(
                success=False,
                status=ContractStatus.FAILED,
                error="Состояния сущностей не установлены"
            )
        
        # Проверка дистанции
        max_range = 2.0 if self.attack_type == "melee" else 50.0
        if self.distance > max_range:
            return ContractResult(
                success=False,
                status=ContractStatus.FAILED,
                error=f"Цель слишком далеко: {self.distance:.2f} > {max_range}"
            )
        
        # Проверка линии видимости
        if not self.has_los:
            return ContractResult(
                success=False,
                status=ContractStatus.FAILED,
                error="Нет линии видимости"
            )
        
        # Если есть ML-агент, запросить решение
        if self.ml_agent and self.skill_id:
            skill_info = self.ml_agent.skills.get(self.skill_id)
            if skill_info:
                # Обновление знаний о скилле
                self.ml_agent.update_skill_knowledge(self.skill_id, success=True)
        
        # Расчет урона
        base_damage = 10.0
        if self.attack_type == "skill" and self.skill_id:
            # TODO: Получить урон скилла из системы скиллов
            base_damage = 25.0
        
        # Модификаторы от статов
        damage_multiplier = 1.0
        if self.attacker_state.active_buffs:
            damage_multiplier += len(self.attacker_state.active_buffs) * 0.1
        
        final_damage = base_damage * damage_multiplier
        
        # Применение эффектов
        result_data = {
            'attacker_id': self.attacker_id,
            'target_id': self.target_id,
            'damage': final_damage,
            'attack_type': self.attack_type,
            'skill_id': self.skill_id,
            'critical': False,  # TODO: Расчет крита
            'blocked': False,   # TODO: Проверка блока
            'dodged': False     # TODO: Проверка уклонения
        }
        
        logger.info(f"Атака выполнена: {final_damage:.1f} урона")
        
        return ContractResult(
            success=True,
            status=ContractStatus.COMPLETED,
            data=result_data
        )


@register_contract
class DefenseContract(SmartContract):
    """
    Контракт защиты (блок/уклонение).
    Использует ML-агента для принятия решения о типе защиты.
    """
    
    def __init__(self, defender_id: str, attacker_id: str, 
                 incoming_damage: float, attack_type: str = "melee"):
        super().__init__(f"defense_{defender_id}")
        
        self.defender_id = defender_id
        self.attacker_id = attacker_id
        self.incoming_damage = incoming_damage
        self.attack_type = attack_type
        
        self.defender_state: Optional[EntityState] = None
        self.ml_agent: Optional[AdaptiveRLAgent] = None
    
    def execute(self) -> ContractResult[Dict]:
        """Выполнить защиту."""
        if not self.defender_state:
            return ContractResult(
                success=False,
                status=ContractStatus.FAILED,
                error="Состояние защитника не установлено"
            )
        
        # Решение ML-агента: блок или уклонение
        defense_action = "none"
        mitigation = 0.0
        
        if self.ml_agent:
            # Создание контекста для решения
            fake_enemy = EntityState(
                health=100, max_health=100,
                mana=100, max_mana=100,
                stamina=100, max_stamina=100,
                position=(0, 0, 0),
                velocity=(0, 0, 0)
            )
            
            context = BattleContext(
                self_state=self.defender_state,
                enemy_state=fake_enemy,
                distance_to_enemy=5.0,
                enemy_visibility=True,
                terrain_cover=False,
                allies_nearby=0,
                enemies_nearby=1,
                available_skills=[],
                equipped_weapon=None
            )
            
            action, _ = self.ml_agent.select_action(context, training=False)
            
            # Интерпретация действия
            if action == ActionType.BLOCK.value:
                defense_action = "block"
                mitigation = 0.6  # 60% снижения
            elif action == ActionType.DODGE.value:
                defense_action = "dodge"
                # Шанс уклонения зависит от стамины
                dodge_chance = min(0.8, self.defender_state.stamina / 50.0)
                if dodge_chance > 0.5:
                    mitigation = 1.0  # Полное уклонение
        
        # Применение защиты
        final_damage = self.incoming_damage * (1.0 - mitigation)
        
        result_data = {
            'defender_id': self.defender_id,
            'attacker_id': self.attacker_id,
            'incoming_damage': self.incoming_damage,
            'final_damage': final_damage,
            'mitigation': mitigation,
            'defense_action': defense_action,
            'blocked': defense_action == "block",
            'dodged': defense_action == "dodge" and mitigation == 1.0
        }
        
        logger.info(f"Защита: {defense_action}, урон снижен до {final_damage:.1f}")
        
        return ContractResult(
            success=True,
            status=ContractStatus.COMPLETED,
            data=result_data
        )


@register_contract
class SkillUsageContract(SmartContract):
    """
    Контракт использования скилла.
    Исследует неизвестные скиллы и оптимизирует использование известных.
    """
    
    def __init__(self, caster_id: str, skill_id: str, 
                 target_ids: Optional[List[str]] = None):
        super().__init__(f"skill_{caster_id}_{skill_id}")
        
        self.caster_id = caster_id
        self.skill_id = skill_id
        self.target_ids = target_ids or []
        
        self.caster_state: Optional[EntityState] = None
        self.ml_agent: Optional[AdaptiveRLAgent] = None
    
    def execute(self) -> ContractResult[Dict]:
        """Использовать скилл."""
        if not self.caster_state:
            return ContractResult(
                success=False,
                status=ContractStatus.FAILED,
                error="Состояние заклинателя не установлено"
            )
        
        if not self.ml_agent:
            return ContractResult(
                success=False,
                status=ContractStatus.FAILED,
                error="ML-агент не установлен"
            )
        
        # Проверка наличия скилла
        if self.skill_id not in self.ml_agent.skills:
            return ContractResult(
                success=False,
                status=ContractStatus.FAILED,
                error=f"Скилл {self.skill_id} не известен"
            )
        
        skill_info = self.ml_agent.skills[self.skill_id]
        
        # Проверка ресурсов
        if self.caster_state.mana < skill_info.mana_cost:
            return ContractResult(
                success=False,
                status=ContractStatus.FAILED,
                error=f"Недостаточно маны: {self.caster_state.mana} < {skill_info.mana_cost}"
            )
        
        # Проверка кулдауна (упрощенно)
        # TODO: Реальная проверка кулдаунов
        
        # Обновление состояния исследования
        old_state = skill_info.discovery_state
        if old_state == SkillDiscoveryState.UNKNOWN:
            skill_info.discovery_state = SkillDiscoveryState.DISCOVERED
            logger.info(f"Скилл {skill_info.name} открыт!")
        
        # Списание маны
        self.caster_state.mana -= skill_info.mana_cost
        
        # Эффект скилла (упрощенно)
        effect_data = {
            'skill_id': self.skill_id,
            'skill_name': skill_info.name,
            'element': skill_info.element,
            'damage_type': skill_info.damage_type,
            'targets': self.target_ids,
            'mana_cost': skill_info.mana_cost,
            'discovery_state': skill_info.discovery_state.name,
            'was_unknown': old_state == SkillDiscoveryState.UNKNOWN
        }
        
        # Запись использования для обучения
        self.ml_agent.update_skill_knowledge(self.skill_id, success=True)
        
        logger.info(f"Скилл использован: {skill_info.name} ({skill_info.discovery_state.name})")
        
        return ContractResult(
            success=True,
            status=ContractStatus.COMPLETED,
            data=effect_data
        )


class CombatContractExecutor:
    """
    Исполнитель боевых контрактов.
    Координирует выполнение цепочек контрактов в бою.
    """
    
    def __init__(self):
        self.active_combats: Dict[str, Dict] = {}
    
    def start_combat(self, combat_id: str, participants: List[str],
                    ml_agents: Dict[str, AdaptiveRLAgent]):
        """Начать бой."""
        self.active_combats[combat_id] = {
            'participants': participants,
            'ml_agents': ml_agents,
            'turn': 0,
            'actions': []
        }
        logger.info(f"Бой {combat_id} начат с участниками: {participants}")
    
    def execute_combat_round(self, combat_id: str) -> List[ContractResult]:
        """Выполнить раунд боя."""
        if combat_id not in self.active_combats:
            logger.error(f"Бой {combat_id} не найден")
            return []
        
        combat = self.active_combats[combat_id]
        results = []
        
        # Каждый участник делает действие
        for participant_id in combat['participants']:
            ml_agent = combat['ml_agents'].get(participant_id)
            
            if ml_agent:
                # TODO: Получить контекст боя и выбрать действие через ML
                # Для примера - простая атака
                pass
        
        combat['turn'] += 1
        
        return results
    
    def end_combat(self, combat_id: str, winner_id: Optional[str] = None):
        """Закончить бой."""
        if combat_id not in self.active_combats:
            return
        
        combat = self.active_combats[combat_id]
        
        # Обновление статистики ML-агентов
        for participant_id, ml_agent in combat['ml_agents'].items():
            won = participant_id == winner_id
            ml_agent.record_combat_result(
                won=won,
                damage_dealt=0,  # TODO: Подсчет урона
                damage_taken=0,
                skills_used=[]
            )
        
        del self.active_combats[combat_id]
        logger.info(f"Бой {combat_id} завершен. Победитель: {winner_id}")
