"""
Пакет смарт-контрактов для стандартизации игровых механик.
"""

from .combat_contracts import (
    AttackContract,
    CombatAction,
    CombatContractExecutor,
    DefenseContract,
    SkillUsageContract,
)
from .smart_contracts import (
    ContractCondition,
    ContractRegistry,
    ContractResult,
    ContractStatus,
    SmartContract,
    register_contract,
)

__all__ = [
    # Base contracts
    'SmartContract',
    'ContractResult',
    'ContractStatus',
    'ContractCondition',
    'ContractRegistry',
    'register_contract',
    
    # Combat contracts
    'AttackContract',
    'DefenseContract',
    'SkillUsageContract',
    'CombatContractExecutor',
    'CombatAction'
]
