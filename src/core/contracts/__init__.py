"""
Contracts Package

Smart contracts for standardized game mechanics.
Provides type-safe interfaces for combat, skills, and other systems.
"""

from src.core.contracts.combat_contracts import (
    AttackContract,
    CombatAction,
    CombatContractExecutor,
    DefenseContract,
    SkillUsageContract,
)
from src.core.contracts.smart_contracts import (
    ContractResult,
    ContractStatus,
    SmartContract,
    ContractRegistry,
    register_contract,
)

__all__ = [
    # Smart Contracts Base
    "SmartContract",
    "ContractResult",
    "ContractStatus",
    "register_contract",
    "ContractRegistry",
    # Combat Contracts
    "CombatAction",
    "AttackContract",
    "DefenseContract",
    "SkillUsageContract",
    "CombatContractExecutor",
]
