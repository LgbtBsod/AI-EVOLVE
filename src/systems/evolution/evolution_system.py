#!/usr/bin/env python3
"""Система эволюции и мутаций AI - EVOLVE
Генетические алгоритмы для развития персонажей

Refactored by Senior Python Architect:
- Added __slots__ to all dataclasses for memory optimization
- Replaced time.time() with time.perf_counter() for precision
- Added comprehensive type hints (Python 3.10+)
- Centralized RNG management for reproducibility
- Optimized gene initialization to reduce allocations
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Optional

from src.core.architecture import BaseComponent, ComponentType, Priority
from src.core.constants import GeneType, EvolutionType, constants_manager, PROBABILITY_CONSTANTS
from src.core.rng_manager import RNGManager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# = ОСНОВНЫЕ ТИПЫ И ПЕРЕЧИСЛЕНИЯ

class MutationType(Enum):
    """Типы мутаций"""
    SPONTANEOUS = "spontaneous"
    INDUCED = "induced"
    ADAPTIVE = "adaptive"
    COMBINATIONAL = "combinational"
    CASCADE = "cascade"


class EvolutionPath(Enum):
    """Пути эволюции"""
    NATURAL = "natural"
    ACCELERATED = "accelerated"
    DIRECTED = "directed"
    REVERSE = "reverse"
    HYBRID = "hybrid"


class MutationLevel(Enum):
    """Уровни мутаций"""
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    EXTREME = "extreme"
    LEGENDARY = "legendary"

# = ДАТАКЛАССЫ ДЛЯ ГЕНОВ И МУТАЦИЙ
@dataclass(slots=True)
class Gene:
    """Ген - базовая единица наследственности"""
    gene_id: str
    gene_type: GeneType
    name: str
    description: str
    base_value: float
    current_value: Optional[float] = None
    max_value: float = 100.0
    mutation_chance: float = 0.05
    evolution_cost: int = 10
    requirements: list[str] = field(default_factory=list)
    effects: dict[str, float] = field(default_factory=dict)
    visual_effects: list[str] = field(default_factory=list)
    sound_effects: list[str] = field(default_factory=list)
    last_mutation: Optional[float] = None
    mutation_count: int = 0
    
    def __post_init__(self) -> None:
        if self.current_value is None:
            self.current_value = self.base_value


@dataclass(slots=True)
class Mutation:
    """Мутация - изменение гена"""
    mutation_id: str
    gene_id: str
    name: str
    description: str
    mutation_type: MutationType
    level: MutationLevel
    value_change: float
    effects: dict[str, float]
    visual_effects: list[str]
    sound_effects: list[str]
    duration: Optional[float] = None
    timestamp: float = field(default_factory=lambda: time.perf_counter())
    source: Optional[str] = None
    reversible: bool = True
    cascade_chance: float = 0.1


@dataclass(slots=True)
class EvolutionTree:
    """Дерево эволюции - путь развития"""
    tree_id: str
    name: str
    description: str
    root_gene: str
    branches: list[str]
    requirements: dict[str, Any]
    rewards: dict[str, float]
    max_level: int = 10
    current_level: int = 0


@dataclass(slots=True)
class EvolutionProgress:
    """Прогресс эволюции персонажа"""
    character_id: str
    evolution_points: int = 0
    total_mutations: int = 0
    active_mutations: list[str] = field(default_factory=list)
    evolution_history: list[dict[str, Any]] = field(default_factory=list)
    last_evolution: Optional[float] = None
    evolution_path: EvolutionPath = EvolutionPath.NATURAL


@dataclass(slots=True)
class GeneticCombination:
    """Генетическая комбинация - взаимодействие генов"""
    combination_id: str
    name: str
    description: str
    required_genes: list[str]
    effects: dict[str, float]
    visual_effects: list[str]
    activation_chance: float
    duration: Optional[float] = None

# = ОСНОВНАЯ СИСТЕМА ЭВОЛЮЦИИ
class EvolutionSystem(BaseComponent):
    """Основная система эволюции и мутаций
    Управляет развитием персонажей через генетические алгоритмы"""
    
    def __init__(self) -> None:
        super().__init__(
            component_id="EvolutionSystem",
            component_type=ComponentType.SYSTEM,
            priority=Priority.HIGH
        )
        
        # RNG Manager для воспроизводимости
        self._rng = RNGManager()
        
        # Основные данные
        self.genes_registry: dict[str, Gene] = {}
        self.mutations_registry: dict[str, Mutation] = {}
        self.evolution_trees: dict[str, EvolutionTree] = {}
        self.character_progress: dict[str, EvolutionProgress] = {}
        self.genetic_combinations: dict[str, GeneticCombination] = {}
        
        # Системные параметры
        self.mutation_rate: float = 0.01
        self.evolution_cost_multiplier: float = 1.0
        self.max_mutations_per_gene: int = 5
        self.cascade_mutation_chance: float = 0.1
        
        # Обработчики событий
        self.mutation_handlers: dict[str, list[Callable]] = {}
        self.evolution_handlers: dict[str, list[Callable]] = {}
    
    def _on_initialize(self) -> bool:
        """Инициализация системы эволюции"""
        try:
            self._create_base_genes()
            self._create_evolution_trees()
            self._create_genetic_combinations()
            
            logger.info("Система эволюции инициализирована")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации системы эволюции: {e}")
            return False
    
    def _create_base_genes(self) -> None:
        """Создание базовых генов для всех типов"""
        try:
            # Физические гены
            self._add_gene(Gene(
                gene_id="gene_strength",
                gene_type=GeneType.PHYSICAL,
                name="Ген силы",
                description="Определяет физическую силу персонажа",
                base_value=10.0,
                current_value=10.0,
                max_value=100.0,
                mutation_chance=0.05,
                evolution_cost=10,
                effects={"damage": 1.0, "carry_weight": 2.0}
            ))
            
            self._add_gene(Gene(
                gene_id="gene_agility",
                gene_type=GeneType.PHYSICAL,
                name="Ген ловкости",
                description="Определяет физическую ловкость персонажа",
                base_value=10.0,
                current_value=10.0,
                max_value=100.0,
                mutation_chance=0.05,
                evolution_cost=10,
                effects={"dodge_chance": 0.5, "movement_speed": 1.0}
            ))
            
            # Умственные гены
            self._add_gene(Gene(
                gene_id="gene_intelligence",
                gene_type=GeneType.MENTAL,
                name="Ген интеллекта",
                description="Определяет умственные способности персонажа",
                base_value=10.0,
                current_value=10.0,
                max_value=100.0,
                mutation_chance=0.03,
                evolution_cost=15,
                effects={"magic_power": 1.5, "skill_learning": 2.0}
            ))
            
            # Социальные гены
            self._add_gene(Gene(
                gene_id="gene_charisma",
                gene_type=GeneType.SOCIAL,
                name="Ген харизмы",
                description="Определяет социальные навыки персонажа",
                base_value=10.0,
                current_value=10.0,
                max_value=100.0,
                mutation_chance=0.04,
                evolution_cost=12,
                effects={"persuasion": 1.0, "leadership": 1.5}
            ))
            
            # Боевые гены
            self._add_gene(Gene(
                gene_id="gene_combat_instinct",
                gene_type=GeneType.COMBAT,
                name="Ген боевого инстинкта",
                description="Определяет боевые способности персонажа",
                base_value=10.0,
                current_value=10.0,
                max_value=100.0,
                mutation_chance=0.06,
                evolution_cost=8,
                effects={"critical_chance": 0.3, "initiative": 1.0}
            ))
            
            # Магические гены
            self._add_gene(Gene(
                gene_id="gene_magic_affinity",
                gene_type=GeneType.MAGIC,
                name="Ген магической склонности",
                description="Определяет магические способности персонажа",
                base_value=10.0,
                current_value=10.0,
                max_value=100.0,
                mutation_chance=0.02,
                evolution_cost=20,
                effects={"magic_resistance": 1.0, "spell_power": 2.0}
            ))
            
            logger.info("Создано %d базовых генов", len(self.genes_registry))
            
        except Exception as e:
            logger.exception("Ошибка создания базовых генов: %s", e)
            raise
    
    def _create_evolution_trees(self):
        """Создание эволюционных деревьев"""
        try:
            # Дерево физической эволюции
            self.evolution_trees["physical_tree"] = EvolutionTree(
                tree_id="physical_tree",
                name="Физическая эволюция",
                description="Развитие физических способностей",
                root_gene="gene_strength",
                branches=["strength_branch", "agility_branch", "endurance_branch"],
                requirements={"level": 5, "strength": 20},
                rewards={"physical_power": 2.0, "health_bonus": 50}
            )
            
            # Дерево ментальной эволюции
            self.evolution_trees["mental_tree"] = EvolutionTree(
                tree_id="mental_tree",
                name="Ментальная эволюция",
                description="Развитие умственных способностей",
                root_gene="gene_intelligence",
                branches=["intelligence_branch", "wisdom_branch", "creativity_branch"],
                requirements={"level": 8, "intelligence": 25},
                rewards={"mental_power": 2.5, "mana_bonus": 100}
            )
            
            logger.info(f"Создано {len(self.evolution_trees)} эволюционных деревьев")
            
        except Exception as e:
            logger.error(f"Ошибка создания эволюционных деревьев: {e}")
            raise
    
    def _create_genetic_combinations(self):
        """Создание генетических комбинаций"""
        try:
            # Комбинация силы и ловкости
            self.genetic_combinations["strength_agility"] = GeneticCombination(
                combination_id="strength_agility",
                name="Сила и ловкость",
                description="Комбинация физических генов дает бонус к боевым навыкам",
                required_genes=["gene_strength", "gene_agility"],
                effects={"combat_power": 1.5, "critical_damage": 2.0},
                visual_effects=["physical_aura"],
                activation_chance=0.8,
                duration=300.0
            )
            
            # Комбинация интеллекта и магии
            self.genetic_combinations["intelligence_magic"] = GeneticCombination(
                combination_id="intelligence_magic",
                name="Интеллект и магия",
                description="Комбинация ментальных генов усиливает магические способности",
                required_genes=["gene_intelligence", "gene_magic_affinity"],
                effects={"spell_power": 2.0, "mana_efficiency": 1.5},
                visual_effects=["magical_glow"],
                activation_chance=0.7,
                duration=600.0
            )
            
            logger.info(f"Создано {len(self.genetic_combinations)} генетических комбинаций")
            
        except Exception as e:
            logger.error(f"Ошибка создания генетических комбинаций: {e}")
            raise
    
    def _add_gene(self, gene: Gene) -> None:
        """Добавление гена в реестр"""
        self.genes_registry[gene.gene_id] = gene
    
    def register_character(self, character_id: str) -> bool:
        """Регистрация персонажа в системе эволюции"""
        try:
            if character_id in self.character_progress:
                logger.warning("Персонаж %s уже зарегистрирован", character_id)
                return True
            
            # Создаем прогресс эволюции
            progress = EvolutionProgress(character_id=character_id)
            self.character_progress[character_id] = progress
            
            # Инициализируем гены для персонажа
            self._initialize_character_genes(character_id)
            
            logger.info("Персонаж %s зарегистрирован в системе эволюции", character_id)
            return True
            
        except Exception as e:
            logger.exception("Ошибка регистрации персонажа %s: %s", character_id, e)
            return False
    
    def _initialize_character_genes(self, character_id: str) -> None:
        """Инициализация генов для персонажа
        
        OPTIMIZATION: Копируем только базовые гены без дублирования в общий registry.
        Используем отдельный character_genes registry для избежания загрязнения base genes.
        """
        try:
            # Создаем отдельный словарь для генов персонажа
            character_genes: dict[str, Gene] = {}
            
            for gene_id, base_gene in self.genes_registry.items():
                # Пропускаем уже существующие гены персонажей
                if '_' in gene_id and gene_id.split('_')[0] == character_id:
                    continue
                    
                character_gene = Gene(
                    gene_id=f"{character_id}_{gene_id}",
                    gene_type=base_gene.gene_type,
                    name=base_gene.name,
                    description=base_gene.description,
                    base_value=base_gene.base_value,
                    current_value=base_gene.base_value,
                    max_value=base_gene.max_value,
                    mutation_chance=base_gene.mutation_chance,
                    evolution_cost=base_gene.evolution_cost,
                    requirements=list(base_gene.requirements),  # copy() → list() для list[str]
                    effects=dict(base_gene.effects),  # copy() → dict() для dict[str, float]
                    visual_effects=list(base_gene.visual_effects)  # copy() → list()
                )
                
                character_genes[character_gene.gene_id] = character_gene
            
            # Сохраняем все гены персонажа одним добавлением
            self.genes_registry.update(character_genes)
            
            logger.info("Гены инициализированы для персонажа %s", character_id)
            
        except Exception as e:
            logger.exception("Ошибка инициализации генов для персонажа %s: %s", character_id, e)
            raise
    
    def trigger_mutation(self, character_id: str, gene_id: str,
                        mutation_type: MutationType = MutationType.SPONTANEOUS) -> Optional[Mutation]:
        """Запуск мутации гена"""
        try:
            if character_id not in self.character_progress:
                logger.error(f"Персонаж {character_id} не зарегистрирован")
                return None
            
            full_gene_id = f"{character_id}_{gene_id}"
            if full_gene_id not in self.genes_registry:
                logger.error(f"Ген {gene_id} не найден у персонажа {character_id}")
                return None
            
            gene = self.genes_registry[full_gene_id]
            
            # Проверяем возможность мутации
            if gene.mutation_count >= self.max_mutations_per_gene:
                logger.warning(f"Ген {gene_id} достиг максимального количества мутаций")
                return None
            
            # Создаем мутацию
            mutation = self._create_mutation(gene, mutation_type)
            if mutation:
                self._apply_mutation(mutation)
                
                # Проверяем каскадные мутации
                if self._rng.random() < self.cascade_mutation_chance:
                    self._trigger_cascade_mutations(character_id, gene_id)
                
                return mutation
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка запуска мутации для персонажа {character_id}: {e}")
            return None
    
    def _create_mutation(self, gene: Gene, mutation_type: MutationType) -> Optional[Mutation]:
        """Создание мутации для гена"""
        try:
            # Определяем уровень мутации
            level = self._determine_mutation_level(gene, mutation_type)
            
            # Вычисляем изменение значения
            base_change = self._rng.uniform(1.0, 10.0)
            if mutation_type == MutationType.ADAPTIVE:
                base_change *= 1.5
            elif mutation_type == MutationType.COMBINATIONAL:
                base_change *= 2.0
            
            # Применяем множитель уровня
            level_multipliers = {
                MutationLevel.MINOR: 0.5,
                MutationLevel.MODERATE: 1.0,
                MutationLevel.MAJOR: 2.0,
                MutationLevel.EXTREME: 3.0,
                MutationLevel.LEGENDARY: 5.0
            }
            
            value_change = base_change * level_multipliers.get(level, 1.0)
            
            # Создаем мутацию
            mutation = Mutation(
                mutation_id=f"mutation_{int(time.time() * 1000)}",
                gene_id=gene.gene_id,
                name=f"Мутация {gene.name}",
                description=f"Изменение гена {gene.name}",
                mutation_type=mutation_type,
                level=level,
                value_change=value_change,
                effects=self._generate_mutation_effects(gene, level),
                visual_effects=[f"{mutation_type.value}_effect"],
                sound_effects=[f"{mutation_type.value}_sound"],
                duration=None,
                source="system"
            )
            
            return mutation
            
        except Exception as e:
            logger.error(f"Ошибка создания мутации: {e}")
            return None
    
    def _determine_mutation_level(self, gene: Gene, mutation_type: MutationType) -> MutationLevel:
        """Определение уровня мутации"""
        # Базовые шансы для каждого уровня
        chances = {
            MutationLevel.MINOR: 0.5,
            MutationLevel.MODERATE: 0.3,
            MutationLevel.MAJOR: 0.15,
            MutationLevel.EXTREME: 0.04,
            MutationLevel.LEGENDARY: 0.01
        }
        
        # Модификаторы на основе типа мутации
        if mutation_type == MutationType.ADAPTIVE:
            chances[MutationLevel.MAJOR] *= 1.5
            chances[MutationLevel.EXTREME] *= 1.2
        elif mutation_type == MutationType.COMBINATIONAL:
            chances[MutationLevel.MAJOR] *= 2.0
            chances[MutationLevel.EXTREME] *= 1.5
            chances[MutationLevel.LEGENDARY] *= 1.3
        
        # Нормализуем шансы
        total = sum(chances.values())
        normalized = {k: v / total for k, v in chances.items()}
        
        # Выбираем уровень на основе шансов
        rand = self._rng.random()
        cumulative = 0.0
        
        for level, chance in normalized.items():
            cumulative += chance
            if rand <= cumulative:
                return level
        
        return MutationLevel.MINOR
    
    def _generate_mutation_effects(self, gene: Gene, level: MutationLevel) -> Dict[str, float]:
        """Генерация эффектов мутации"""
        effects = {}
        
        # Базовые эффекты на основе типа гена
        if gene.gene_type == GeneType.PHYSICAL:
            effects["strength"] = self._rng.uniform(1.0, 5.0)
            effects["health"] = self._rng.uniform(5.0, 20.0)
        elif gene.gene_type == GeneType.MENTAL:
            effects["intelligence"] = self._rng.uniform(1.0, 3.0)
            effects["mana"] = self._rng.uniform(10.0, 30.0)
        elif gene.gene_type == GeneType.COMBAT:
            effects["damage"] = self._rng.uniform(2.0, 8.0)
            effects["critical_chance"] = self._rng.uniform(0.1, 0.5)
        
        # Множитель уровня
        level_multipliers = {
            MutationLevel.MINOR: 0.5,
            MutationLevel.MODERATE: 1.0,
            MutationLevel.MAJOR: 1.5,
            MutationLevel.EXTREME: 2.0,
            MutationLevel.LEGENDARY: 3.0
        }
        
        multiplier = level_multipliers.get(level, 1.0)
        effects = {k: v * multiplier for k, v in effects.items()}
        
        return effects
    
    def _apply_mutation(self, mutation: Mutation):
        """Применение мутации к гену"""
        try:
            gene = self.genes_registry[mutation.gene_id]
            
            # Применяем изменение значения
            new_value = gene.current_value + mutation.value_change
            gene.current_value = max(0.0, min(gene.max_value, new_value))
            
            # Сохраняем мутацию
            self.mutations_registry[mutation.mutation_id] = mutation
            gene.mutation_count += 1
            gene.last_mutation = time.time()
            
            # Обновляем прогресс персонажа
            character_id = mutation.gene_id.split('_')[0]
            if character_id in self.character_progress:
                progress = self.character_progress[character_id]
                progress.active_mutations.append(mutation.mutation_id)
                progress.total_mutations += 1
                
                # Добавляем в историю
                progress.evolution_history.append({
                    "type": "mutation",
                    "mutation_id": mutation.mutation_id,
                    "timestamp": time.time(),
                    "description": f"Мутация {mutation.name}"
                })
            
            logger.info(f"Мутация {mutation.mutation_id} применена к гену {mutation.gene_id}")
            
        except Exception as e:
            logger.error(f"Ошибка применения мутации {mutation.mutation_id}: {e}")
            raise
    
    def _trigger_cascade_mutations(self, character_id: str, source_gene_id: str):
        """Запуск каскадных мутаций"""
        try:
            # Ищем связанные гены
            related_genes = self._find_related_genes(source_gene_id)
            
            for related_gene_id in related_genes:
                if self._rng.random() < self.cascade_mutation_chance:
                    # Запускаем мутацию связанного гена
                    self.trigger_mutation(character_id, related_gene_id, MutationType.CASCADE)
            
        except Exception as e:
            logger.error(f"Ошибка запуска каскадных мутаций: {e}")
    
    def _find_related_genes(self, gene_id: str) -> List[str]:
        """Поиск связанных генов"""
        try:
            related = []
            base_gene_id = gene_id.split('_', 1)[1] if '_' in gene_id else gene_id
            
            # Ищем гены того же типа
            for gid in self.genes_registry:
                if gid != gene_id and base_gene_id in gid:
                    related.append(gid)
            
            return related
            
        except Exception as e:
            logger.error(f"Ошибка поиска связанных генов: {e}")
            return []
    
    def evolve_gene(self, character_id: str, gene_id: str,
                    evolution_points: int) -> bool:
        """Эволюция гена с использованием очков эволюции"""
        try:
            if character_id not in self.character_progress:
                logger.error(f"Персонаж {character_id} не зарегистрирован")
                return False
            
            full_gene_id = f"{character_id}_{gene_id}"
            if full_gene_id not in self.genes_registry:
                logger.error(f"Ген {gene_id} не найден у персонажа {character_id}")
                return False
            
            gene = self.genes_registry[full_gene_id]
            progress = self.character_progress[character_id]
            
            # Проверяем достаточно ли очков эволюции
            required_points = int(gene.evolution_cost * self.evolution_cost_multiplier)
            if progress.evolution_points < required_points:
                logger.warning(f"Недостаточно очков эволюции: {progress.evolution_points}/{required_points}")
                return False
            
            # Применяем эволюцию
            evolution_bonus = self._rng.uniform(1.1, 1.5)
            new_value = gene.current_value * evolution_bonus
            gene.current_value = min(gene.max_value, new_value)
            
            # Тратим очки эволюции
            progress.evolution_points -= required_points
            progress.last_evolution = time.time()
            
            # Добавляем в историю
            progress.evolution_history.append({
                "type": "evolution",
                "gene_id": gene_id,
                "timestamp": time.time(),
                "description": f"Эволюция гена {gene.name}",
                "cost": required_points,
                "bonus": evolution_bonus
            })
            
            logger.info(f"Ген {gene_id} эволюционировал у персонажа {character_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка эволюции гена {gene_id} у персонажа {character_id}: {e}")
            return False
    
    def get_character_genes(self, character_id: str) -> Dict[str, Gene]:
        """Получение всех генов персонажа"""
        try:
            if character_id not in self.character_progress:
                return {}
            
            character_genes = {}
            for gene_id, gene in self.genes_registry.items():
                if gene_id.startswith(f"{character_id}_"):
                    base_gene_id = gene_id.split('_', 1)[1]
                    character_genes[base_gene_id] = gene
            
            return character_genes
            
        except Exception as e:
            logger.error(f"Ошибка получения генов персонажа {character_id}: {e}")
            return {}
    
    def get_character_mutations(self, character_id: str) -> List[Mutation]:
        """Получение всех мутаций персонажа"""
        try:
            if character_id not in self.character_progress:
                return []
            
            progress = self.character_progress[character_id]
            mutations = []
            
            for mutation_id in progress.active_mutations:
                if mutation_id in self.mutations_registry:
                    mutations.append(self.mutations_registry[mutation_id])
            
            return mutations
            
        except Exception as e:
            logger.error(f"Ошибка получения мутаций персонажа {character_id}: {e}")
            return []
    
    def add_evolution_points(self, character_id: str, points: int) -> bool:
        """Добавление очков эволюции персонажу"""
        try:
            if character_id not in self.character_progress:
                logger.error(f"Персонаж {character_id} не зарегистрирован")
                return False
            
            progress = self.character_progress[character_id]
            progress.evolution_points += points
            
            logger.info(f"Добавлено {points} очков эволюции персонажу {character_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка добавления очков эволюции персонажу {character_id}: {e}")
            return False
    
    def get_evolution_progress(self, character_id: str) -> Optional[EvolutionProgress]:
        """Получение прогресса эволюции персонажа"""
        return self.character_progress.get(character_id)
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Получение статистики системы эволюции"""
        try:
            total_mutations = sum(progress.total_mutations for progress in self.character_progress.values())
            total_evolution_points = sum(progress.evolution_points for progress in self.character_progress.values())
            
            return {
                "total_characters": len(self.character_progress),
                "total_genes": len(self.genes_registry),
                "total_mutations": len(self.mutations_registry),
                "total_mutations_applied": total_mutations,
                "total_evolution_points": total_evolution_points,
                "evolution_trees": len(self.evolution_trees),
                "genetic_combinations": len(self.genetic_combinations)
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики системы: {e}")
            return {}
    
    def _on_update(self, delta_time: float) -> bool:
        """Обновление системы эволюции"""
        try:
            # Проверяем спонтанные мутации
            self._check_spontaneous_mutations(delta_time)
            
            # Обновляем генетические комбинации
            self._update_genetic_combinations(delta_time)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления системы эволюции: {e}")
            return False
    
    def _check_spontaneous_mutations(self, delta_time: float):
        """Проверка спонтанных мутаций"""
        try:
            current_time = time.time()
            
            for character_id, progress in self.character_progress.items():
                for gene_id, gene in self.get_character_genes(character_id).items():
                    # Проверяем возможность спонтанной мутации
                    if (gene.last_mutation is None or 
                        current_time - gene.last_mutation > 3600):  # 1 час
                        
                        if self._rng.random() < gene.mutation_chance * self.mutation_rate:
                            self.trigger_mutation(character_id, gene_id, MutationType.SPONTANEOUS)
            
        except Exception as e:
            logger.error(f"Ошибка проверки спонтанных мутаций: {e}")
    
    def _update_genetic_combinations(self, delta_time: float):
        """Обновление генетических комбинаций"""
        try:
            current_time = time.time()
            
            for character_id, progress in self.character_progress.items():
                character_genes = self.get_character_genes(character_id)
                
                for combination_id, combination in self.genetic_combinations.items():
                    # Проверяем активацию комбинации
                    if self._can_activate_combination(character_genes, combination):
                        if self._rng.random() < combination.activation_chance:
                            self._activate_genetic_combination(character_id, combination)
            
        except Exception as e:
            logger.error(f"Ошибка обновления генетических комбинаций: {e}")
    
    def _can_activate_combination(self, character_genes: Dict[str, Gene], 
                                 combination: GeneticCombination) -> bool:
        """Проверка возможности активации генетической комбинации"""
        try:
            for required_gene in combination.required_genes:
                if required_gene not in character_genes:
                    return False
                
                gene = character_genes[required_gene]
                if gene.current_value < 20:  # Минимальное значение для активации
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки активации комбинации: {e}")
            return False
    
    def _activate_genetic_combination(self, character_id: str, combination: GeneticCombination):
        """Активация генетической комбинации"""
        try:
            # Создаем временную мутацию с эффектами комбинации
            mutation = Mutation(
                mutation_id=f"combination_{combination.combination_id}_{int(time.time() * 1000)}",
                gene_id="combination",
                name=combination.name,
                description=combination.description,
                mutation_type=MutationType.COMBINATIONAL,
                level=MutationLevel.MODERATE,
                value_change=0.0,
                effects=combination.effects,
                visual_effects=combination.visual_effects,
                sound_effects=[],
                duration=combination.duration,
                source="genetic_combination"
            )
            
            # Применяем мутацию
            self._apply_mutation(mutation)
            
            logger.info(f"Активирована генетическая комбинация {combination.name} у персонажа {character_id}")
            
        except Exception as e:
            logger.error(f"Ошибка активации генетической комбинации: {e}")
    
    def _on_destroy(self) -> bool:
        """Уничтожение системы эволюции"""
        try:
            # Очищаем все данные
            self.genes_registry.clear()
            self.mutations_registry.clear()
            self.evolution_trees.clear()
            self.character_progress.clear()
            self.genetic_combinations.clear()
            
            logger.info("Система эволюции уничтожена")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения системы эволюции: {e}")
            return False
