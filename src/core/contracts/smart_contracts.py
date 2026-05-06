"""
Система смарт-контрактов для стандартизации игровых механик.
Обеспечивает единый интерфейс для боя, крафта, диалогов и других систем.
Использует паттерн "Контракт" для валидации действий и их выполнения.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, TypeVar, Generic
from enum import Enum, auto
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ContractStatus(Enum):
    """Статус выполнения контракта."""
    PENDING = auto()
    VALIDATING = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    FAILED = auto()
    ROLLED_BACK = auto()


@dataclass
class ContractResult(Generic[T]):
    """Результат выполнения контракта."""
    success: bool
    status: ContractStatus
    data: Optional[T] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.success


@dataclass
class ContractCondition:
    """Условие контракта."""
    name: str
    check_func: Callable[[], bool]
    error_message: str
    is_critical: bool = True


class SmartContract(ABC):
    """
    Базовый класс смарт-контракта.
    Обеспечивает валидацию, выполнение и откат действий.
    """
    
    def __init__(self, contract_id: str, priority: int = 0):
        self.contract_id = contract_id
        self.priority = priority
        self.status = ContractStatus.PENDING
        self.conditions: List[ContractCondition] = []
        self.pre_hooks: List[Callable] = []
        self.post_hooks: List[Callable] = []
        self.rollback_hooks: List[Callable] = []
        self.context: Dict[str, Any] = {}
        
    def add_condition(self, name: str, check_func: Callable[[], bool], 
                     error_message: str, is_critical: bool = True) -> 'SmartContract':
        """Добавить условие валидации."""
        self.conditions.append(ContractCondition(
            name=name,
            check_func=check_func,
            error_message=error_message,
            is_critical=is_critical
        ))
        return self
    
    def add_pre_hook(self, func: Callable) -> 'SmartContract':
        """Добавить хук перед выполнением."""
        self.pre_hooks.append(func)
        return self
    
    def add_post_hook(self, func: Callable) -> 'SmartContract':
        """Добавить хук после выполнения."""
        self.post_hooks.append(func)
        return self
    
    def add_rollback_hook(self, func: Callable) -> 'SmartContract':
        """Добавить хук для отката."""
        self.rollback_hooks.append(func)
        return self
    
    def set_context(self, **kwargs) -> 'SmartContract':
        """Установить контекст контракта."""
        self.context.update(kwargs)
        return self
    
    def validate(self) -> ContractResult[None]:
        """Проверить все условия контракта."""
        self.status = ContractStatus.VALIDATING
        
        for condition in self.conditions:
            try:
                if not condition.check_func():
                    if condition.is_critical:
                        logger.warning(f"Критическое условие не выполнено: {condition.name}")
                        return ContractResult(
                            success=False,
                            status=ContractStatus.FAILED,
                            error=condition.error_message
                        )
                    else:
                        logger.info(f"Некритическое условие не выполнено: {condition.name}")
            except Exception as e:
                logger.error(f"Ошибка проверки условия {condition.name}: {e}")
                if condition.is_critical:
                    return ContractResult(
                        success=False,
                        status=ContractStatus.FAILED,
                        error=f"Ошибка проверки {condition.name}: {str(e)}"
                    )
        
        return ContractResult(success=True, status=ContractStatus.PENDING)
    
    @abstractmethod
    def execute(self) -> ContractResult[Any]:
        """Выполнить контракт."""
        pass
    
    def rollback(self) -> None:
        """Откатить изменения."""
        logger.info(f"Откат контракта {self.contract_id}")
        for hook in reversed(self.rollback_hooks):
            try:
                hook()
            except Exception as e:
                logger.error(f"Ошибка отката: {e}")
        self.status = ContractStatus.ROLLED_BACK
    
    def run(self) -> ContractResult[Any]:
        """Запустить контракт (валидация + выполнение)."""
        import time
        start_time = time.time()
        
        # Валидация
        validation_result = self.validate()
        if not validation_result.success:
            validation_result.execution_time = time.time() - start_time
            return validation_result
        
        # Пре-хуки
        self.status = ContractStatus.EXECUTING
        for hook in self.pre_hooks:
            try:
                hook(self.context)
            except Exception as e:
                logger.error(f"Ошибка пре-хука: {e}")
                self.rollback()
                return ContractResult(
                    success=False,
                    status=ContractStatus.FAILED,
                    error=f"Ошибка пре-хука: {str(e)}"
                )
        
        # Выполнение
        try:
            result = self.execute()
            result.execution_time = time.time() - start_time
            
            if result.success:
                # Пост-хуки
                for hook in self.post_hooks:
                    try:
                        hook(self.context, result.data)
                    except Exception as e:
                        logger.warning(f"Ошибка пост-хука: {e}")
                        result.warnings.append(f"Пост-хук failed: {str(e)}")
                
                self.status = ContractStatus.COMPLETED
            else:
                self.rollback()
                self.status = ContractStatus.FAILED
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка выполнения контракта {self.contract_id}: {e}")
            self.rollback()
            self.status = ContractStatus.FAILED
            return ContractResult(
                success=False,
                status=ContractStatus.FAILED,
                error=str(e)
            )


class ContractRegistry:
    """Реестр смарт-контрактов."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.contracts = {}
            cls._instance.executors = {}
        return cls._instance
    
    def register(self, contract_type: type, executor: Callable = None) -> None:
        """Зарегистрировать тип контракта."""
        contract_name = contract_type.__name__
        self.contracts[contract_name] = contract_type
        if executor:
            self.executors[contract_name] = executor
        logger.info(f"Зарегистрирован контракт: {contract_name}")
    
    def create(self, contract_name: str, *args, **kwargs) -> SmartContract:
        """Создать экземпляр контракта."""
        if contract_name not in self.contracts:
            raise ValueError(f"Контракт {contract_name} не найден")
        
        contract_class = self.contracts[contract_name]
        return contract_class(*args, **kwargs)
    
    def get_all_contracts(self) -> Dict[str, type]:
        """Получить все зарегистрированные контракты."""
        return self.contracts.copy()


# Декоратор для автоматической регистрации контрактов
def register_contract(executor: Callable = None):
    """Декоратор для регистрации контракта."""
    def decorator(cls):
        registry = ContractRegistry()
        registry.register(cls, executor)
        return cls
    return decorator
