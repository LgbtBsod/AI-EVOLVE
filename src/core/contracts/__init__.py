"""
Пакет смарт-контрактов для стандартизации игровых механик.
"""

from .smart_contracts import (
    SmartContract,
    ContractResult,
    ContractStatus,
    ContractCondition,
    ContractRegistry,
    register_contract
)

from .combat_contracts import (
    AttackContract,
    DefenseContract,
    SkillUsageContract,
    CombatContractExecutor,
    CombatAction
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
