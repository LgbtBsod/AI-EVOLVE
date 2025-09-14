#!/usr/bin/env python3
"""Master Integrator - главный координатор всех систем
Интеграция с системой атрибутов для всех компонентов"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import *
from typing import Dict, List, Optional, Any, Tuple, Callable
import logging
import time
import math
import threading
from collections import defaultdict, deque

from src.core.component_types import BaseComponent, ComponentType, Priority, LifecycleState
from src.core.state_manager import StateManager, StateType
from src.systems.attributes.attribute_system import AttributeSystem, AttributeSet, AttributeModifier, StatModifier, BaseAttribute, DerivedStat

# Импорты всех систем
from src.systems.combat.combat_system import CombatSystem
from src.systems.skills.skill_system import SkillSystem
from src.systems.items.item_system import ItemSystem
from src.ui.unified_ui_system import UnifiedUISystem
from src.systems.ai.ai_system import AISystem
from src.systems.evolution.evolution_system import EvolutionSystem
from src.systems.dialogue.dialogue_system import DialogueSystem
from src.systems.quest.dynamic_quest_system import DynamicQuestSystem as QuestSystem
from src.systems.rendering.render_system import RenderSystem as RenderingSystem
from src.systems.content.content_system import ContentSystem
from src.systems.memory.memory_system import MemorySystem
from src.systems.crafting.crafting_system import CraftingSystem
from src.systems.trading.trading_system import TradingSystem
from src.systems.social.social_system import SocialSystem
from src.systems.world.world_manager import WorldManager
from src.systems.world.navigation_system import NavigationSystem
from src.systems.world.weather_system import WeatherSystem
from src.systems.world.day_night_cycle import DayNightCycle
from src.systems.world.season_system import SeasonSystem
from src.systems.world.environmental_effects import EnvironmentalEffects
from src.systems.visualization.unified_visualization_system import UnifiedVisualizationSystem
from src.systems.effects.effect_system import EffectSystem
from src.systems.world.unified_building_system import UnifiedBuildingSystem

logger = logging.getLogger(__name__)

# = ТИПЫ ИНТЕГРАЦИИ

class IntegrationType(Enum):
    """Типы интеграции систем"""
    DIRECT = "direct"          # Прямая интеграция
    EVENT_BASED = "event_based"  # Интеграция через события
    DATA_SHARING = "data_sharing"  # Обмен данными
    CALLBACK = "callback"      # Интеграция через callback

class SystemDependency(Enum):
    """Зависимости систем"""
    REQUIRED = "required"      # Обязательная зависимость
    OPTIONAL = "optional"      # Опциональная зависимость
    WEAK = "weak"             # Слабая зависимость

# = СТРУКТУРЫ ДАННЫХ

@dataclass
class SystemIntegration:
    """Интеграция системы"""
    system_name: str
    integration_type: IntegrationType
    dependencies: List[str] = field(default_factory=list)
    callbacks: Dict[str, Callable] = field(default_factory=dict)
    data_handlers: Dict[str, Callable] = field(default_factory=dict)
    event_handlers: Dict[str, Callable] = field(default_factory=dict)

@dataclass
class IntegrationConfig:
    """Конфигурация интеграции"""
    auto_integrate_attributes: bool = True
    enable_cross_system_modifiers: bool = True
    enable_attribute_synchronization: bool = True
    enable_performance_monitoring: bool = True
    enable_error_recovery: bool = True
    max_integration_retries: int = 3
    integration_timeout: float = 5.0

class MasterIntegrator(BaseComponent):
    """Главный координатор всех систем"""
    
    def __init__(self):
        super().__init__(
            component_id="master_integrator",
            component_type=ComponentType.SYSTEM,
            priority=Priority.CRITICAL
        )
        
        # Архитектурные компоненты
        self.state_manager: Optional[StateManager] = None
        self.attribute_system: Optional[AttributeSystem] = None
        
        # Все системы
        self.systems: Dict[str, BaseComponent] = {}
        self.system_integrations: Dict[str, SystemIntegration] = {}
        self.system_dependencies: Dict[str, List[str]] = {}
        self.system_initialization_order: List[str] = []
        
        # Интеграция с системой атрибутов
        self.attribute_integrations: Dict[str, Dict[str, Any]] = {}
        self.cross_system_modifiers: Dict[str, List[Tuple[str, AttributeModifier, StatModifier]]] = {}
        
        # Конфигурация
        self.integration_config = IntegrationConfig()
        
        # Производительность и мониторинг
        self.performance_metrics: Dict[str, Dict[str, float]] = {}
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.recovery_attempts: Dict[str, int] = defaultdict(int)
        
        # Статистика
        self.system_stats = {
            'total_systems': 0,
            'active_systems': 0,
            'integrated_systems': 0,
            'attribute_integrations': 0,
            'cross_system_modifiers': 0,
            'integration_errors': 0,
            'recovery_attempts': 0,
            'update_time': 0.0
        }
        
        # Callbacks
        self.on_system_integrated: Optional[Callable] = None
        self.on_integration_error: Optional[Callable] = None
        self.on_system_recovered: Optional[Callable] = None
        
        logger.info("Master Integrator инициализирован")
    
    def set_architecture_components(self, state_manager: StateManager, attribute_system: AttributeSystem):
        """Установка архитектурных компонентов"""
        self.state_manager = state_manager
        self.attribute_system = attribute_system
        logger.info("Архитектурные компоненты установлены в MasterIntegrator")
    
    def _register_system_states(self):
        """Регистрация состояний системы"""
        if self.state_manager:
            self.state_manager.set_state(
                f"{self.component_id}_config",
                self.integration_config.__dict__,
                StateType.SETTINGS
            )
            
            self.state_manager.set_state(
                f"{self.component_id}_stats",
                self.system_stats,
                StateType.STATISTICS
            )
            
            self.state_manager.set_state(
                f"{self.component_id}_state",
                self.state,
                StateType.SYSTEM_STATE
            )
    
    def initialize(self) -> bool:
        """Инициализация Master Integrator"""
        try:
            logger.info("Инициализация MasterIntegrator...")
            
            self._register_system_states()
            
            # Создание всех систем
            self._create_all_systems()

            # После создания систем фиксируем ссылку на AttributeSystem,
            # чтобы далее передавать ее остальным системам при установке архитектурных компонентов
            if 'attribute_system' in self.systems:
                try:
                    self.attribute_system = self.systems['attribute_system']  # type: ignore[assignment]
                except Exception:
                    logger.warning("Не удалось установить ссылку на AttributeSystem после создания систем")
            
            # Определение зависимостей
            self._define_system_dependencies()
            
            # Определение порядка инициализации
            self._calculate_initialization_order()
            
            # Инициализация систем в правильном порядке
            if not self._initialize_systems_in_order():
                return False
            
            # Интеграция систем с системой атрибутов
            if self.integration_config.auto_integrate_attributes:
                self._integrate_systems_with_attributes()
            
            self._state = LifecycleState.READY
            logger.info("MasterIntegrator инициализирован успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации MasterIntegrator: {e}")
            self._state = LifecycleState.ERROR
            return False
    
    def start(self) -> bool:
        """Запуск Master Integrator"""
        try:
            logger.info("Запуск MasterIntegrator...")
            
            if self._state != LifecycleState.READY:
                logger.error("MasterIntegrator не готов к запуску")
                return False
            
            # Запуск всех систем
            if not self._start_all_systems():
                return False
            
            self._state = LifecycleState.RUNNING
            logger.info("MasterIntegrator запущен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска MasterIntegrator: {e}")
            self._state = LifecycleState.ERROR
            return False
    
    def update(self, delta_time: float):
        """Обновление Master Integrator"""
        if self._state != LifecycleState.RUNNING:
            return
        
        try:
            start_time = time.time()
            
            # Обновление всех систем
            self._update_all_systems(delta_time)
            
            # Обновление интеграций
            self._update_integrations(delta_time)
            
            # Мониторинг производительности
            if self.integration_config.enable_performance_monitoring:
                self._update_performance_metrics(delta_time)
            
            # Восстановление после ошибок
            if self.integration_config.enable_error_recovery:
                self._attempt_error_recovery()
            
            self.system_stats['update_time'] = time.time() - start_time
            
            # Обновляем состояние в менеджере состояний
            if self.state_manager:
                self.state_manager.set_state(
                    f"{self.component_id}_stats",
                    self.system_stats,
                    StateType.STATISTICS
                )
                
        except Exception as e:
            logger.error(f"Ошибка обновления MasterIntegrator: {e}")
    
    def stop(self) -> bool:
        """Остановка Master Integrator"""
        try:
            logger.info("Остановка MasterIntegrator...")
            
            # Остановка всех систем
            self._stop_all_systems()
            
            self._state = LifecycleState.STOPPED
            logger.info("MasterIntegrator остановлен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки MasterIntegrator: {e}")
            return False
    
    def destroy(self) -> bool:
        """Уничтожение Master Integrator"""
        try:
            logger.info("Уничтожение MasterIntegrator...")
            
            # Уничтожение всех систем
            self._destroy_all_systems()
            
            self.systems.clear()
            self.system_integrations.clear()
            self.system_dependencies.clear()
            self.system_initialization_order.clear()
            self.attribute_integrations.clear()
            self.cross_system_modifiers.clear()
            self.performance_metrics.clear()
            self.error_counts.clear()
            self.recovery_attempts.clear()
            
            self._state = LifecycleState.DESTROYED
            logger.info("MasterIntegrator уничтожен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения MasterIntegrator: {e}")
            return False
    
    def _create_all_systems(self):
        """Создание всех систем"""
        try:
            # Создаем все доступные системы
            systems_to_create = {
                # Основные системы
                'attribute_system': AttributeSystem(),
                'content_system': ContentSystem(),
                'unified_visualization_system': UnifiedVisualizationSystem(),
                'rendering_system': RenderingSystem(),
                'combat_system': CombatSystem(),
                'skill_system': SkillSystem(),
                'unified_ui_system': UnifiedUISystem(),
                
                # Дополнительные системы
                'item_system': ItemSystem(),
                'ai_system': AISystem(),
                'evolution_system': EvolutionSystem(),
                'dialogue_system': DialogueSystem(),
                'quest_system': QuestSystem(),
                'memory_system': MemorySystem(),
                'crafting_system': CraftingSystem(),
                'trading_system': TradingSystem(),
                'social_system': SocialSystem(),
                'world_manager': WorldManager(),
                'navigation_system': NavigationSystem(),
                'weather_system': WeatherSystem(),
                'day_night_cycle': DayNightCycle(),
                'season_system': SeasonSystem(),
                'environmental_effects': EnvironmentalEffects(),
                'effect_system': EffectSystem(),
                'unified_building_system': UnifiedBuildingSystem()
            }
            
            for system_name, system in systems_to_create.items():
                self.systems[system_name] = system
                logger.info(f"Создана система: {system_name}")
            
            # Обновляем статистику
            self.system_stats['total_systems'] = len(self.systems)
            
        except Exception as e:
            logger.error(f"Ошибка создания систем: {e}")
    
    def _define_system_dependencies(self):
        """Определение зависимостей систем"""
        try:
            # Определяем зависимости между системами
            self.system_dependencies = {
                # Базовые системы
                'attribute_system': [],  # Базовая система, не зависит от других
                'content_system': ['attribute_system'],
                'memory_system': ['attribute_system'],
                'unified_visualization_system': ['content_system'],
                'rendering_system': ['unified_visualization_system'],
                
                # Игровые системы
                'combat_system': ['attribute_system'],
                'skill_system': ['attribute_system', 'combat_system'],
                'item_system': ['attribute_system'],
                'evolution_system': ['attribute_system', 'memory_system'],
                'ai_system': ['attribute_system', 'memory_system'],
                
                # Социальные системы
                'dialogue_system': ['memory_system'],
                'social_system': ['memory_system', 'dialogue_system'],
                'trading_system': ['item_system', 'social_system'],
                'quest_system': ['dialogue_system', 'memory_system'],
                
                # Системы мира
                'world_manager': ['content_system'],
                'navigation_system': ['world_manager'],
                'weather_system': ['world_manager'],
                'season_system': ['weather_system'],
                'day_night_cycle': ['world_manager'],
                'environmental_effects': ['weather_system', 'season_system'],
                
                # Системы крафтинга
                'crafting_system': ['item_system', 'skill_system'],
                
                # Системы эффектов
                'effect_system': ['attribute_system'],
                
                # Системы зданий
                'unified_building_system': ['world_manager', 'item_system'],
                
                # UI системы
                'unified_ui_system': ['attribute_system', 'rendering_system', 'item_system']
            }
            
            logger.info("Зависимости систем определены")
            
        except Exception as e:
            logger.error(f"Ошибка определения зависимостей: {e}")
    
    def _calculate_initialization_order(self):
        """Расчет порядка инициализации систем (топологическая сортировка)"""
        try:
            # Алгоритм Кана для топологической сортировки
            in_degree = defaultdict(int)
            graph = defaultdict(list)
            
            # Строим граф зависимостей
            for system, dependencies in self.system_dependencies.items():
                for dep in dependencies:
                    graph[dep].append(system)
                    in_degree[system] += 1
            
            # Находим системы без зависимостей
            queue = deque([system for system in self.system_dependencies.keys() 
                          if in_degree[system] == 0])
            
            order = []
            while queue:
                current = queue.popleft()
                order.append(current)
                
                # Уменьшаем степень входа для зависимых систем
                for dependent in graph[current]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
            
            # Проверяем, что все системы включены
            if len(order) != len(self.system_dependencies):
                logger.error("Обнаружен цикл в зависимостях систем")
                return False
            
            self.system_initialization_order = order
            logger.info(f"Порядок инициализации: {order}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка расчета порядка инициализации: {e}")
            return False
    
    def _initialize_systems_in_order(self) -> bool:
        """Инициализация систем в правильном порядке"""
        try:
            for system_name in self.system_initialization_order:
                if system_name not in self.systems:
                    logger.error(f"Система {system_name} не найдена")
                    return False
                
                system = self.systems[system_name]
                
                # Устанавливаем архитектурные компоненты
                if hasattr(system, 'set_architecture_components'):
                    if system_name == 'attribute_system':
                        # AttributeSystem не нуждается в других системах
                        pass
                    else:
                        # Остальные системы получают StateManager и AttributeSystem
                        system.set_architecture_components(self.state_manager, self.attribute_system)
                
                # Инициализируем систему
                if not system.initialize():
                    logger.error(f"Ошибка инициализации системы {system_name}")
                    return False
                
                logger.info(f"Система {system_name} инициализирована")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации систем: {e}")
            return False
    
    def _integrate_systems_with_attributes(self):
        """Интеграция систем с системой атрибутов"""
        try:
            # Интеграция CombatSystem с AttributeSystem
            if 'combat_system' in self.systems and 'attribute_system' in self.systems:
                combat_system = self.systems['combat_system']
                self.attribute_integrations['combat_system'] = {
                    'type': 'direct',
                    'description': 'CombatSystem использует AttributeSystem для расчета характеристик'
                }
            
            # Интеграция SkillSystem с AttributeSystem
            if 'skill_system' in self.systems and 'attribute_system' in self.systems:
                skill_system = self.systems['skill_system']
                self.attribute_integrations['skill_system'] = {
                    'type': 'direct',
                    'description': 'SkillSystem использует AttributeSystem для требований и модификаторов'
                }
            
            # Интеграция ItemSystem с AttributeSystem
            if 'item_system' in self.systems and 'attribute_system' in self.systems:
                item_system = self.systems['item_system']
                self.attribute_integrations['item_system'] = {
                    'type': 'direct',
                    'description': 'ItemSystem предоставляет модификаторы атрибутов'
                }
            
            # Интеграция UnifiedUISystem с AttributeSystem
            if 'unified_ui_system' in self.systems and 'attribute_system' in self.systems:
                self.attribute_integrations['unified_ui_system'] = {
                    'type': 'direct',
                    'description': 'UnifiedUISystem отображает характеристики и модификаторы'
                }
            
            # Интеграция AISystem с AttributeSystem
            if 'ai_system' in self.systems and 'attribute_system' in self.systems:
                ai_system = self.systems['ai_system']
                self.attribute_integrations['ai_system'] = {
                    'type': 'direct',
                    'description': 'AISystem учитывает атрибуты при принятии решений'
                }
            
            # Интеграция CraftingSystem с AttributeSystem
            if 'crafting_system' in self.systems and 'attribute_system' in self.systems:
                self.attribute_integrations['crafting_system'] = {
                    'type': 'direct',
                    'description': 'CraftingSystem использует атрибуты для требований крафтинга'
                }
            
            # Интеграция TradingSystem с AttributeSystem
            if 'trading_system' in self.systems and 'attribute_system' in self.systems:
                self.attribute_integrations['trading_system'] = {
                    'type': 'direct',
                    'description': 'TradingSystem учитывает атрибуты для торговых отношений'
                }
            
            # Интеграция SocialSystem с AttributeSystem
            if 'social_system' in self.systems and 'attribute_system' in self.systems:
                self.attribute_integrations['social_system'] = {
                    'type': 'direct',
                    'description': 'SocialSystem использует атрибуты для социальных взаимодействий'
                }
            
            # Интеграция WorldManager с AttributeSystem
            if 'world_manager' in self.systems and 'attribute_system' in self.systems:
                self.attribute_integrations['world_manager'] = {
                    'type': 'direct',
                    'description': 'WorldManager учитывает атрибуты для генерации мира'
                }
            
            # Обновляем статистику
            self.system_stats['attribute_integrations'] = len(self.attribute_integrations)
            
            logger.info(f"Интегрировано {len(self.attribute_integrations)} систем с AttributeSystem")
            
        except Exception as e:
            logger.error(f"Ошибка интеграции систем с атрибутами: {e}")
    
    def _start_all_systems(self) -> bool:
        """Запуск всех систем"""
        try:
            for system_name, system in self.systems.items():
                if not system.start():
                    logger.error(f"Ошибка запуска системы {system_name}")
                    return False
                
                logger.info(f"Система {system_name} запущена")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска систем: {e}")
            return False
    
    def _update_all_systems(self, delta_time: float):
        """Обновление всех систем"""
        try:
            for system_name, system in self.systems.items():
                try:
                    system.update(delta_time)
                except Exception as e:
                    logger.error(f"Ошибка обновления системы {system_name}: {e}")
                    self.error_counts[system_name] += 1
                    self.system_stats['integration_errors'] += 1
            
            # Обновляем статистику активных систем
            active_systems = sum(1 for system in self.systems.values() 
                               if system.state == LifecycleState.RUNNING)
            self.system_stats['active_systems'] = active_systems
            
        except Exception as e:
            logger.error(f"Ошибка обновления систем: {e}")
    
    def _update_integrations(self, delta_time: float):
        """Обновление интеграций между системами"""
        try:
            # Обновление кросс-системных модификаторов
            if self.integration_config.enable_cross_system_modifiers:
                self._update_cross_system_modifiers(delta_time)
            
            # Синхронизация атрибутов между системами
            if self.integration_config.enable_attribute_synchronization:
                self._synchronize_attributes()
            
        except Exception as e:
            logger.error(f"Ошибка обновления интеграций: {e}")
    
    def _update_cross_system_modifiers(self, delta_time: float):
        """Обновление кросс-системных модификаторов"""
        try:
            # Здесь должна быть логика обновления модификаторов,
            # которые влияют на несколько систем одновременно
            pass
            
        except Exception as e:
            logger.error(f"Ошибка обновления кросс-системных модификаторов: {e}")
    
    def _synchronize_attributes(self):
        """Синхронизация атрибутов между системами"""
        try:
            # Здесь должна быть логика синхронизации атрибутов
            # между различными системами
            pass
            
        except Exception as e:
            logger.error(f"Ошибка синхронизации атрибутов: {e}")
    
    def _update_performance_metrics(self, delta_time: float):
        """Обновление метрик производительности"""
        try:
            for system_name, system in self.systems.items():
                if hasattr(system, 'get_system_info'):
                    info = system.get_system_info()
                    self.performance_metrics[system_name] = {
                        'update_time': info.get('update_time', 0.0),
                        'state': info.get('state', 'unknown'),
                        'priority': info.get('priority', 'normal')
                    }
            
        except Exception as e:
            logger.error(f"Ошибка обновления метрик производительности: {e}")
    
    def _attempt_error_recovery(self):
        """Попытка восстановления после ошибок"""
        try:
            for system_name, error_count in self.error_counts.items():
                if error_count > 0 and system_name in self.systems:
                    system = self.systems[system_name]
                    
                    # Проверяем, не превышен ли лимит попыток восстановления
                    if self.recovery_attempts[system_name] < self.integration_config.max_integration_retries:
                        logger.warning(f"Попытка восстановления системы {system_name}")
                        
                        try:
                            # Пытаемся перезапустить систему
                            if system.stop() and system.start():
                                logger.info(f"Система {system_name} успешно восстановлена")
                                self.error_counts[system_name] = 0
                                
                                if self.on_system_recovered:
                                    self.on_system_recovered(system_name)
                            else:
                                self.recovery_attempts[system_name] += 1
                                self.system_stats['recovery_attempts'] += 1
                                
                        except Exception as e:
                            logger.error(f"Ошибка восстановления системы {system_name}: {e}")
                            self.recovery_attempts[system_name] += 1
                            self.system_stats['recovery_attempts'] += 1
            
        except Exception as e:
            logger.error(f"Ошибка попытки восстановления: {e}")
    
    def _stop_all_systems(self):
        """Остановка всех систем"""
        try:
            for system_name, system in self.systems.items():
                try:
                    system.stop()
                    logger.info(f"Система {system_name} остановлена")
                except Exception as e:
                    logger.error(f"Ошибка остановки системы {system_name}: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка остановки систем: {e}")
    
    def _destroy_all_systems(self):
        """Уничтожение всех систем"""
        try:
            for system_name, system in self.systems.items():
                try:
                    system.destroy()
                    logger.info(f"Система {system_name} уничтожена")
                except Exception as e:
                    logger.error(f"Ошибка уничтожения системы {system_name}: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения систем: {e}")
    
    def get_system(self, system_name: str) -> Optional[BaseComponent]:
        """Получение системы по имени"""
        return self.systems.get(system_name)
    
    def get_all_systems(self) -> Dict[str, BaseComponent]:
        """Получение всех систем"""
        return self.systems.copy()
    
    def get_system_info_by_name(self, system_name: str) -> Optional[Dict[str, Any]]:
        """Получение информации о системе по имени"""
        system = self.systems.get(system_name)
        if system and hasattr(system, 'get_system_info'):
            return system.get_system_info()
        return None
    
    def get_integration_info(self) -> Dict[str, Any]:
        """Получение информации об интеграциях"""
        return {
            'attribute_integrations': self.attribute_integrations,
            'cross_system_modifiers': len(self.cross_system_modifiers),
            'system_dependencies': self.system_dependencies,
            'initialization_order': self.system_initialization_order
        }
    
    def get_performance_metrics(self) -> Dict[str, Dict[str, float]]:
        """Получение метрик производительности"""
        return self.performance_metrics.copy()
    
    def reset_stats(self):
        """Сброс статистики"""
        self.system_stats = {
            'total_systems': len(self.systems),
            'active_systems': 0,
            'integrated_systems': len(self.attribute_integrations),
            'attribute_integrations': len(self.attribute_integrations),
            'cross_system_modifiers': len(self.cross_system_modifiers),
            'integration_errors': 0,
            'recovery_attempts': 0,
            'update_time': 0.0
        }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Получение информации о системе"""
        return {
            'name': self.component_id,
            'state': self.state.value,
            'priority': self.priority.value,
            'total_systems': self.system_stats['total_systems'],
            'active_systems': self.system_stats['active_systems'],
            'integrated_systems': self.system_stats['integrated_systems'],
            'attribute_integrations': self.system_stats['attribute_integrations'],
            'cross_system_modifiers': self.system_stats['cross_system_modifiers'],
            'integration_errors': self.system_stats['integration_errors'],
            'recovery_attempts': self.system_stats['recovery_attempts'],
            'update_time': self.system_stats['update_time']
        }

    def run(self):
        """Запуск главного цикла игры с окном"""
        try:
            logger.info("Запуск главного цикла игры...")
            
            # Запускаем систему рендеринга, если она есть
            if 'rendering_system' in self.systems:
                rendering_system = self.systems['rendering_system']
                if hasattr(rendering_system, 'run'):
                    logger.info("Запуск окна игры через систему рендеринга...")
                    rendering_system.run()
                else:
                    logger.warning("Система рендеринга не имеет метода run")
            else:
                logger.warning("Система рендеринга не найдена")
                
        except Exception as e:
            logger.error(f"Ошибка запуска главного цикла: {e}")
            raise
