#!/usr/bin/env python3
"""Единая система искусственного интеллекта
Объединяет все AI возможности в одной системе с машинным обучением"""

import json
import logging
import math
import pickle
import random
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

# Импорт ML-фреймворка обязателен по ТЗ (без fallback)
import torch
from torch import nn, optim

TORCH_AVAILABLE = True

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.info("Scikit-learn не установлен - некоторые AI функции будут недоступны")

from src.core.architecture import BaseComponent, ComponentType, Priority
from src.core.constants import AIBehavior, AIState


# = ТИПЫ AI
class AIType(Enum):
    """Типы искусственного интеллекта"""
    BEHAVIOR_TREE = "behavior_tree"
    STATE_MACHINE = "state_machine"
    NEURAL_NETWORK = "neural_network"
    REINFORCEMENT_LEARNING = "reinforcement_learning"
    EVOLUTIONARY = "evolutionary"
    HYBRID = "hybrid"

class AIPriority(Enum):
    """Приоритеты AI"""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"

class MemoryType(Enum):
    """Типы памяти"""
    COMBAT = "combat"
    MOVEMENT = "movement"
    SKILL_USAGE = "skill_usage"
    ITEM_USAGE = "item_usage"
    ENVIRONMENT = "environment"
    SOCIAL = "social"

class LearningType(Enum):
    """Типы обучения"""
    SUPERVISED = "supervised"
    UNSUPERVISED = "unsupervised"
    REINFORCEMENT = "reinforcement"
    EVOLUTIONARY = "evolutionary"
    TRANSFER = "transfer"

# = НЕЙРОННЫЕ СЕТИ (PyTorch)
class AINeuralNetwork(nn.Module):
    """Нейронная сеть для принятия решений AI."""

    def __init__(self, input_size: int, hidden_size: int, output_size: int):
        super().__init__()
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.fc3 = nn.Linear(hidden_size, output_size)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.2)

    def forward(self, x):
        x = self.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.relu(self.fc2(x))
        x = self.dropout(x)
        x = self.fc3(x)
        return x

# = СТРУКТУРЫ ДАННЫХ
@dataclass
class MemoryEntry:
    """Запись в памяти"""
    memory_type: MemoryType
    timestamp: float
    context: dict[str, Any]
    action: str
    outcome: dict[str, Any]
    success: bool
    learning_value: float = 0.5  # Ценность для обучения (0.0 - 1.0)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            'memory_type': self.memory_type.value,
            'timestamp': self.timestamp,
            'context': self.context,
            'action': self.action,
            'outcome': self.outcome,
            'success': self.success,
            'learning_value': self.learning_value
        }

@dataclass
class GenerationMemory:
    """Память поколения"""
    generation_id: int
    entity_id: str
    entity_type: str
    start_time: float
    end_time: float | None = None
    total_experience: float = 0.0
    memories: list[MemoryEntry] = field(default_factory=list)
    final_stats: dict[str, Any] = field(default_factory=dict)
    cause_of_death: str | None = None

@dataclass
class AIEntity:
    """AI сущность с продвинутыми возможностями"""
    entity_id: str
    ai_type: AIType
    current_state: AIState
    priority: AIPriority
    position: tuple[float, float, float]
    target_position: tuple[float, float, float] | None = None
    target_entity: str | None = None
    health: float = 100.0
    max_health: float = 100.0
    speed: float = 1.0
    detection_range: float = 10.0
    attack_range: float = 2.0
    memory: dict[str, Any] = field(default_factory=dict)
    behavior_data: dict[str, Any] = field(default_factory=dict)
    learning_data: dict[str, Any] = field(default_factory=dict)
    neural_network: Any | None = None
    last_update: float = field(default_factory=time.time)
    experience_buffer: list[dict[str, Any]] = field(default_factory=list)
    learning_rate: float = 0.001
    exploration_rate: float = 0.1
    generation_id: int = 1
    total_experience: float = 0.0
    memory_entries: list[MemoryEntry] = field(default_factory=list)
    personality_traits: dict[str, float] = field(default_factory=dict)

@dataclass
class AIBehavior:
    """Поведение AI с машинным обучением"""
    behavior_id: str
    name: str
    description: str
    conditions: dict[str, Any] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)
    priority: int = 0
    cooldown: float = 0.0
    last_execution: float = 0.0
    success_rate: float = 0.5
    learning_enabled: bool = True
    model_path: str | None = None
    personality_requirements: dict[str, float] = field(default_factory=dict)

@dataclass
class AIDecision:
    """Решение AI с уверенностью"""
    entity_id: str
    behavior_id: str
    action: str
    target: str | None = None
    position: tuple[float, float, float] | None = None
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)
    learning_data: dict[str, Any] = field(default_factory=dict)
    personality_influence: dict[str, float] = field(default_factory=dict)

@dataclass
class LearningExperience:
    """Опыт для обучения"""
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool
    timestamp: float = field(default_factory=time.time)

# = НАСТРОЙКИ AI
@dataclass
class AISettings:
    """Настройки AI системы"""
    update_interval: float = 0.1
    max_entities: int = 1000
    max_threads: int = 4
    enable_multithreading: bool = True
    enable_learning: bool = True
    enable_memory: bool = True
    enable_adaptation: bool = True
    enable_neural_networks: bool = TORCH_AVAILABLE
    enable_reinforcement_learning: bool = True
    enable_evolutionary_learning: bool = True
    learning_rate: float = 0.001
    exploration_rate: float = 0.1
    experience_buffer_size: int = 10000
    batch_size: int = 32
    target_update_frequency: int = 1000
    model_save_frequency: int = 10000
    memory_decay_rate: float = 0.95
    personality_adaptation_rate: float = 0.01

# = ЕДИНАЯ AI СИСТЕМА
class AISystem(BaseComponent):
    """Единая система искусственного интеллекта с машинным обучением"""
    
    def __init__(self):
        super().__init__(
            component_id="AISystem",
            component_type=ComponentType.SYSTEM,
            priority=Priority.HIGH
        )
        
        # Настройки системы
        self.settings = AISettings()
        
        # AI сущности
        self.ai_entities: dict[str, AIEntity] = {}
        self.entity_behaviors: dict[str, list[AIBehavior]] = {}
        
        # Поведения и решения
        self.behaviors: dict[str, AIBehavior] = {}
        self.decisions: list[AIDecision] = []
        
        # Машинное обучение
        self.global_memory: dict[str, Any] = {}
        self.experience_pool: dict[str, list[LearningExperience]] = {}
        self.learning_data: dict[str, Any] = {}
        self.models: dict[str, Any] = {}
        self.scalers: dict[str, Any] = {}
        
        # Память поколений
        self.generation_memories: dict[int, GenerationMemory] = {}
        self.current_generation: int = 1
        
        # Многопоточность
        self.executor: ThreadPoolExecutor | None = None
        self.update_thread: threading.Thread | None = None
        self.running = False
        
        # Статистика
        self.stats = {
            "total_entities": 0,
            "active_entities": 0,
            "decisions_made": 0,
            "learning_events": 0,
            "model_updates": 0,
            "memory_entries": 0,
            "generations": 0,
            "update_time": 0.0
        }
        
        # Callbacks
        self.behavior_callbacks: dict[str, Callable] = {}
        self.decision_callbacks: list[Callable] = []
        self.learning_callbacks: list[Callable] = []
        self.memory_callbacks: list[Callable] = []
        
        self.logger = logging.getLogger(__name__)
    
    def _on_initialize(self) -> bool:
        """Инициализация AI системы"""
        try:
            # Инициализация поведений
            self._initialize_behaviors()
            
            # Инициализация машинного обучения
            if self.settings.enable_learning:
                self._initialize_machine_learning()
            
            # Создание пула потоков
            if self.settings.enable_multithreading:
                self.executor = ThreadPoolExecutor(max_workers=self.settings.max_threads)
            
            # Инициализация памяти
            if self.settings.enable_memory:
                self._initialize_memory()
            
            self.logger.info("AISystem инициализирован")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка инициализации AISystem: {e}")
            return False
    
    def _initialize_behaviors(self):
        """Инициализация продвинутых поведений"""
        # Поведение патрулирования с обучением
        self.behaviors["patrol"] = AIBehavior(
            behavior_id="patrol",
            name="Патрулирование",
            description="Патрулирование территории с адаптивным маршрутом",
            conditions={"state": AIState.IDLE, "has_target": False},
            actions=["move_to_point", "look_around", "adapt_route"],
            priority=1,
            learning_enabled=True,
            personality_requirements={"curiosity": 0.3, "discipline": 0.5}
        )
        
        # Поведение преследования с предсказанием
        self.behaviors["chase"] = AIBehavior(
            behavior_id="chase",
            name="Преследование",
            description="Преследование цели с предсказанием движения",
            conditions={"has_target": True, "target_in_range": True},
            actions=["move_to_target", "predict_target_movement", "cut_off_escape"],
            priority=5,
            learning_enabled=True,
            personality_requirements={"aggression": 0.6, "persistence": 0.7}
        )
        
        # Поведение атаки с тактикой
        self.behaviors["attack"] = AIBehavior(
            behavior_id="attack",
            name="Атака",
            description="Тактическая атака с адаптацией к противнику",
            conditions={"target_in_attack_range": True},
            actions=["analyze_target", "choose_attack_pattern", "adapt_strategy"],
            priority=10,
            learning_enabled=True,
            personality_requirements={"aggression": 0.8, "intelligence": 0.6}
        )
        
        # Поведение бегства с планированием
        self.behaviors["flee"] = AIBehavior(
            behavior_id="flee",
            name="Бегство",
            description="Тактическое бегство с поиском укрытия",
            conditions={"health_low": True, "threat_detected": True},
            actions=["assess_threat", "find_best_escape_route", "use_cover"],
            priority=8,
            learning_enabled=True,
            personality_requirements={"caution": 0.7, "intelligence": 0.5}
        )
        
        # Поведение поиска с исследованием
        self.behaviors["search"] = AIBehavior(
            behavior_id="search",
            name="Поиск",
            description="Интеллектуальный поиск с анализом окружения",
            conditions={"lost_target": True, "has_search_area": True},
            actions=["explore_area", "investigate_sounds", "track_clues"],
            priority=3,
            learning_enabled=True,
            personality_requirements={"curiosity": 0.6, "patience": 0.5}
        )
    
    def _initialize_machine_learning(self):
        """Инициализация машинного обучения"""
        try:
            # Создание моделей для каждого поведения
            for behavior_id in self.behaviors.keys():
                self._create_behavior_model(behavior_id)
            
            # Инициализация скейлеров
            if SKLEARN_AVAILABLE:
                for behavior_id in self.behaviors.keys():
                    self.scalers[behavior_id] = StandardScaler()
            
            self.logger.info("Машинное обучение инициализировано")
            
        except Exception as e:
            self.logger.error(f"Ошибка инициализации машинного обучения: {e}")
    
    def _create_behavior_model(self, behavior_id: str):
        """Создание модели для поведения"""
        try:
            if TORCH_AVAILABLE and self.settings.enable_neural_networks:
                # Нейронная сеть PyTorch
                input_size = 20  # Размер входного вектора состояния
                hidden_size = 64
                output_size = len(self.behaviors[behavior_id].actions)
                
                model = AINeuralNetwork(input_size, hidden_size, output_size)
                optimizer = optim.Adam(model.parameters(), lr=self.settings.learning_rate)
                
                self.models[behavior_id] = {
                    'model': model,
                    'optimizer': optimizer,
                    'type': 'pytorch'
                }
                
            elif SKLEARN_AVAILABLE:
                # Scikit-learn модели
                self.models[behavior_id] = {
                    'model': RandomForestClassifier(n_estimators=100, random_state=42),
                    'type': 'sklearn'
                }
                
            else:
                # Простая модель на основе правил
                self.models[behavior_id] = {
                    'model': None,
                    'type': 'rule_based'
                }
                
        except Exception as e:
            self.logger.error(f"Ошибка создания модели для {behavior_id}: {e}")
    
    def _initialize_memory(self):
        """Инициализация продвинутой памяти"""
        self.global_memory = {
            "threats": {},
            "resources": {},
            "territories": {},
            "allies": {},
            "enemies": {},
            "patterns": {},
            "success_rates": {},
            "learning_progress": {},
            "personality_trends": {}
        }
    
    def register_entity(self, entity_id: str, ai_type: AIType, 
                       position: tuple[float, float, float], **kwargs) -> bool:
        """Регистрация AI сущности с машинным обучением"""
        try:
            if len(self.ai_entities) >= self.settings.max_entities:
                self.logger.warning(f"Достигнут лимит AI сущностей: {self.settings.max_entities}")
                return False
            
            # Инициализация черт личности
            personality_traits = {
                "aggression": random.uniform(0.1, 0.9),
                "caution": random.uniform(0.1, 0.9),
                "curiosity": random.uniform(0.1, 0.9),
                "intelligence": random.uniform(0.1, 0.9),
                "discipline": random.uniform(0.1, 0.9),
                "persistence": random.uniform(0.1, 0.9),
                "patience": random.uniform(0.1, 0.9)
            }
            
            # Создание AI сущности
            entity = AIEntity(
                entity_id=entity_id,
                ai_type=ai_type,
                current_state=AIState.IDLE,
                priority=AIPriority.NORMAL,
                position=position,
                personality_traits=personality_traits,
                generation_id=self.current_generation,
                **kwargs
            )
            
            # Инициализация нейронной сети для сущности
            if self.settings.enable_neural_networks and TORCH_AVAILABLE:
                entity.neural_network = self._create_entity_neural_network()
            
            self.ai_entities[entity_id] = entity
            self.entity_behaviors[entity_id] = []
            
            # Добавление поведений
            for behavior in self.behaviors.values():
                self.entity_behaviors[entity_id].append(behavior)
            
            # Инициализация буфера опыта
            entity.experience_buffer = []
            
            self.stats["total_entities"] += 1
            self.stats["active_entities"] += 1
            
            self.logger.info(f"Зарегистрирована AI сущность {entity_id} с чертами личности")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка регистрации AI сущности {entity_id}: {e}")
            return False
    
    def _create_entity_neural_network(self):
        """Создание нейронной сети для сущности"""
        if not TORCH_AVAILABLE:
            return None
            
        try:
            input_size = 15  # Состояние сущности
            hidden_size = 32
            output_size = 8  # Количество возможных действий
            
            model = AINeuralNetwork(input_size, hidden_size, output_size)
            return model
            
        except Exception as e:
            self.logger.error(f"Ошибка создания нейронной сети: {e}")
            return None
    
    def make_decision(self, entity_id: str) -> AIDecision | None:
        """Принятие решения с использованием машинного обучения и личности"""
        try:
            if entity_id not in self.ai_entities:
                return None
            
            entity = self.ai_entities[entity_id]
            behaviors = self.entity_behaviors.get(entity_id, [])
            
            # Получение состояния сущности
            state = self._get_entity_state_vector(entity)
            
            # Выбор поведения с учетом личности
            best_behavior = self._select_behavior_with_personality(entity, behaviors, state)
            
            if not best_behavior:
                return None
            
            # Выбор действия с помощью ML
            action, confidence = self._select_action_ml(entity, best_behavior, state)
            
            # Создание решения
            decision = AIDecision(
                entity_id=entity_id,
                behavior_id=best_behavior.behavior_id,
                action=action,
                confidence=confidence,
                learning_data={
                    'state': state,
                    'behavior_selected': best_behavior.behavior_id,
                    'action_selected': action
                },
                personality_influence=entity.personality_traits.copy()
            )
            
            # Обновление времени выполнения
            best_behavior.last_execution = time.time()
            
            # Добавление в список решений
            self.decisions.append(decision)
            self.stats["decisions_made"] += 1
            
            # Уведомление о решении
            self._notify_decision_made(decision)
            
            return decision
            
        except Exception as e:
            self.logger.error(f"Ошибка принятия решения для {entity_id}: {e}")
            return None
    
    def _select_behavior_with_personality(self, entity: AIEntity, behaviors: list[AIBehavior], 
                                        state: np.ndarray) -> AIBehavior | None:
        """Выбор поведения с учетом личности и условий"""
        try:
            available_behaviors = []
            
            for behavior in behaviors:
                if self._check_behavior_conditions(entity, behavior):
                    # Проверка требований личности
                    if self._check_personality_requirements(entity, behavior):
                        available_behaviors.append(behavior)
            
            if not available_behaviors:
                return None
            
            # Использование ML для выбора поведения
            if len(available_behaviors) > 1 and entity.neural_network:
                behavior_scores = self._predict_behavior_scores(entity, available_behaviors, state)
                best_behavior = available_behaviors[np.argmax(behavior_scores)]
            else:
                # Простой выбор по приоритету
                best_behavior = max(available_behaviors, key=lambda b: b.priority)
            
            return best_behavior
            
        except Exception as e:
            self.logger.error(f"Ошибка выбора поведения: {e}")
            return None
    
    def _check_personality_requirements(self, entity: AIEntity, behavior: AIBehavior) -> bool:
        """Проверка требований личности для поведения"""
        try:
            for trait, required_value in behavior.personality_requirements.items():
                if trait in entity.personality_traits:
                    if entity.personality_traits[trait] < required_value:
                        return False
            return True
        except Exception as e:
            self.logger.error(f"Ошибка проверки требований личности: {e}")
            return True
    
    def _get_entity_state_vector(self, entity: AIEntity) -> np.ndarray:
        """Получение вектора состояния сущности"""
        try:
            # Базовые характеристики
            state = [
                entity.health / entity.max_health,
                entity.speed,
                entity.detection_range,
                entity.attack_range,
                float(bool(entity.target_entity)),
                float(bool(entity.target_position)),
                time.time() - entity.last_update,
                len(entity.memory),
                len(entity.experience_buffer),
                entity.learning_rate,
                entity.exploration_rate
            ]
            
            # Позиция (нормализованная)
            if entity.position:
                state.extend([entity.position[0] / 1000.0, entity.position[1] / 1000.0, entity.position[2] / 1000.0])
            else:
                state.extend([0.0, 0.0, 0.0])
            
            # Целевая позиция
            if entity.target_position:
                state.extend([entity.target_position[0] / 1000.0, entity.target_position[1] / 1000.0])
            else:
                state.extend([0.0, 0.0])
            
            return np.array(state, dtype=np.float32)
            
        except Exception as e:
            self.logger.error(f"Ошибка получения вектора состояния: {e}")
            return np.zeros(15, dtype=np.float32)
    
    def _check_behavior_conditions(self, entity: AIEntity, behavior: AIBehavior) -> bool:
        """Проверка условий поведения"""
        try:
            for condition, value in behavior.conditions.items():
                if condition == "state" and entity.current_state != value or condition == "has_target" and bool(entity.target_entity) != value:
                    return False
                elif condition == "target_in_range" and entity.target_position:
                    distance = self._calculate_distance(entity.position, entity.target_position)
                    if distance > entity.detection_range:
                        return False
                elif condition == "target_in_attack_range" and entity.target_position:
                    distance = self._calculate_distance(entity.position, entity.target_position)
                    if distance > entity.attack_range:
                        return False
                elif condition == "health_low" and entity.health > entity.max_health * 0.3:
                    return False
                elif condition == "threat_detected":
                    # Проверка наличия угроз в памяти
                    threats = self.global_memory.get("threats", {})
                    if not threats:
                        return False
                elif condition == "lost_target" and entity.target_entity:
                    return False
                elif condition == "has_search_area":
                    # Проверка наличия области поиска
                    return True  # Упрощенная проверка
            
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка проверки условий поведения: {e}")
            return False
    
    def _calculate_distance(self, pos1: tuple[float, float, float], 
                           pos2: tuple[float, float, float]) -> float:
        """Расчет расстояния между точками"""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(pos1, pos2)))
    
    def _select_action_ml(self, entity: AIEntity, behavior: AIBehavior, 
                          state: np.ndarray) -> tuple[str, float]:
        """Выбор действия с помощью машинного обучения"""
        try:
            if not behavior.actions:
                return "idle", 1.0
            
            # Использование модели поведения
            if behavior.behavior_id in self.models:
                model_info = self.models[behavior.behavior_id]
                
                if model_info['type'] == 'pytorch' and TORCH_AVAILABLE:
                    action_idx, confidence = self._predict_action_pytorch(model_info, state)
                elif model_info['type'] == 'sklearn' and SKLEARN_AVAILABLE:
                    action_idx, confidence = self._predict_action_sklearn(model_info, state)
                else:
                    # Простой выбор
                    action_idx = random.randint(0, len(behavior.actions) - 1)
                    confidence = 1.0
                
                action = behavior.actions[action_idx] if action_idx < len(behavior.actions) else behavior.actions[0]
                return action, confidence
            
            # Резервный выбор
            action = random.choice(behavior.actions)
            return action, 1.0
            
        except Exception as e:
            self.logger.error(f"Ошибка выбора действия: {e}")
            return "idle", 1.0
    
    def _predict_behavior_scores(self, entity: AIEntity, behaviors: list[AIBehavior], 
                                state: np.ndarray) -> np.ndarray:
        """Предсказание оценок для поведений"""
        try:
            if entity.neural_network and TORCH_AVAILABLE:
                with torch.no_grad():
                    state_tensor = torch.FloatTensor(state).unsqueeze(0)
                    scores = entity.neural_network(state_tensor)
                    return scores.numpy().flatten()
            else:
                # Простые оценки на основе приоритетов
                return np.array([b.priority for b in behaviors])
                
        except Exception as e:
            self.logger.error(f"Ошибка предсказания оценок: {e}")
            return np.array([1.0] * len(behaviors))
    
    def _predict_action_pytorch(self, model_info: dict[str, Any], state: np.ndarray) -> tuple[int, float]:
        """Предсказание действия с помощью PyTorch"""
        try:
            model = model_info['model']
            with torch.no_grad():
                state_tensor = torch.FloatTensor(state).unsqueeze(0)
                output = model(state_tensor)
                probabilities = torch.softmax(output, dim=1)
                action_idx = torch.argmax(probabilities).item()
                confidence = probabilities[0][action_idx].item()
                return action_idx, confidence
                
        except Exception as e:
            self.logger.error(f"Ошибка предсказания PyTorch: {e}")
            return 0, 1.0
    
    def _predict_action_sklearn(self, model_info: dict[str, Any], state: np.ndarray) -> tuple[int, float]:
        """Предсказание действия с помощью Scikit-learn"""
        try:
            model = model_info['model']
            if hasattr(model, 'predict_proba'):
                probabilities = model.predict_proba(state.reshape(1, -1))
                action_idx = np.argmax(probabilities)
                confidence = probabilities[0][action_idx]
                return action_idx, confidence
            else:
                action_idx = model.predict(state.reshape(1, -1))[0]
                return action_idx, 1.0
                
        except Exception as e:
            self.logger.error(f"Ошибка предсказания Scikit-learn: {e}")
            return 0, 1.0
    
    def add_memory_entry(self, entity_id: str, memory_type: MemoryType, context: dict[str, Any], 
                        action: str, outcome: dict[str, Any], success: bool, learning_value: float = 0.5):
        """Добавление записи в память сущности"""
        try:
            if entity_id not in self.ai_entities:
                return
            
            entity = self.ai_entities[entity_id]
            
            # Создание записи памяти
            memory_entry = MemoryEntry(
                memory_type=memory_type,
                timestamp=time.time(),
                context=context,
                action=action,
                outcome=outcome,
                success=success,
                learning_value=learning_value
            )
            
            # Добавление в память сущности
            entity.memory_entries.append(memory_entry)
            
            # Обновление статистики
            self.stats["memory_entries"] += 1
            
            # Адаптация личности на основе опыта
            self._adapt_personality(entity, memory_entry)
            
            # Уведомление о новой записи памяти
            self._notify_memory_entry_added(entity, memory_entry)
            
        except Exception as e:
            self.logger.error(f"Ошибка добавления записи памяти: {e}")
    
    def _adapt_personality(self, entity: AIEntity, memory_entry: MemoryEntry):
        """Адаптация личности на основе опыта"""
        try:
            adaptation_rate = self.settings.personality_adaptation_rate
            
            if memory_entry.memory_type == MemoryType.COMBAT:
                if memory_entry.success:
                    entity.personality_traits["aggression"] += adaptation_rate
                    entity.personality_traits["caution"] -= adaptation_rate * 0.5
                else:
                    entity.personality_traits["caution"] += adaptation_rate
                    entity.personality_traits["aggression"] -= adaptation_rate * 0.5
            
            elif memory_entry.memory_type == MemoryType.MOVEMENT:
                if memory_entry.success:
                    entity.personality_traits["persistence"] += adaptation_rate
                else:
                    entity.personality_traits["patience"] += adaptation_rate
            
            elif memory_entry.memory_type == MemoryType.ENVIRONMENT:
                if memory_entry.success:
                    entity.personality_traits["curiosity"] += adaptation_rate
                    entity.personality_traits["intelligence"] += adaptation_rate * 0.5
            
            # Ограничение значений в диапазоне [0.1, 0.9]
            for trait in entity.personality_traits:
                entity.personality_traits[trait] = max(0.1, min(0.9, entity.personality_traits[trait]))
                
        except Exception as e:
            self.logger.error(f"Ошибка адаптации личности: {e}")
    
    def add_experience(self, entity_id: str, state: np.ndarray, action: int, 
                      reward: float, next_state: np.ndarray, done: bool):
        """Добавление опыта для обучения"""
        try:
            if entity_id not in self.ai_entities:
                return
            
            entity = self.ai_entities[entity_id]
            
            # Создание опыта
            experience = LearningExperience(
                state=state,
                action=action,
                reward=reward,
                next_state=next_state,
                done=done
            )
            
            # Добавление в буфер опыта
            entity.experience_buffer.append(experience)
            
            # Ограничение размера буфера
            if len(entity.experience_buffer) > self.settings.experience_buffer_size:
                entity.experience_buffer.pop(0)
            
            # Обучение модели
            if len(entity.experience_buffer) >= self.settings.batch_size:
                self._train_entity_model(entity)
            
            self.stats["learning_events"] += 1
            
        except Exception as e:
            self.logger.error(f"Ошибка добавления опыта: {e}")
    
    def _train_entity_model(self, entity: AIEntity):
        """Обучение модели сущности"""
        try:
            if not entity.neural_network or not TORCH_AVAILABLE:
                return
            
            # Подготовка данных
            batch = random.sample(entity.experience_buffer, 
                                min(self.settings.batch_size, len(entity.experience_buffer)))
            
            states = torch.FloatTensor([exp.state for exp in batch])
            actions = torch.LongTensor([exp.action for exp in batch])
            rewards = torch.FloatTensor([exp.reward for exp in batch])
            next_states = torch.FloatTensor([exp.next_state for exp in batch])
            dones = torch.BoolTensor([exp.done for exp in batch])
            
            # Обучение
            optimizer = optim.Adam(entity.neural_network.parameters(), lr=entity.learning_rate)
            criterion = nn.MSELoss()
            
            # Q-learning обновление
            current_q_values = entity.neural_network(states)
            next_q_values = entity.neural_network(next_states)
            
            target_q_values = current_q_values.clone()
            for i in range(len(batch)):
                if dones[i]:
                    target_q_values[i][actions[i]] = rewards[i]
                else:
                    target_q_values[i][actions[i]] = rewards[i] + 0.99 * torch.max(next_q_values[i])
            
            loss = criterion(current_q_values, target_q_values)
            
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            self.stats["model_updates"] += 1
            
        except Exception as e:
            self.logger.error(f"Ошибка обучения модели: {e}")
    
    def start_new_generation(self):
        """Начало нового поколения"""
        try:
            # Сохранение памяти текущего поколения
            if self.ai_entities:
                generation_memory = GenerationMemory(
                    generation_id=self.current_generation,
                    entity_id="generation",
                    entity_type="generation",
                    start_time=time.time(),
                    end_time=time.time(),
                    total_experience=sum(entity.total_experience for entity in self.ai_entities.values()),
                    memories=[mem for entity in self.ai_entities.values() for mem in entity.memory_entries],
                    final_stats=self.get_statistics()
                )
                
                self.generation_memories[self.current_generation] = generation_memory
            
            # Увеличение номера поколения
            self.current_generation += 1
            self.stats["generations"] += 1
            
            self.logger.info(f"Начато новое поколение: {self.current_generation}")
            
        except Exception as e:
            self.logger.error(f"Ошибка начала нового поколения: {e}")
    
    def save_models(self, path: str):
        """Сохранение моделей"""
        try:
            save_path = Path(path)
            save_path.mkdir(parents=True, exist_ok=True)
            
            for behavior_id, model_info in self.models.items():
                if model_info['type'] == 'pytorch' and TORCH_AVAILABLE:
                    torch.save(model_info['model'].state_dict(), 
                             save_path / f"{behavior_id}_model.pth")
                elif model_info['type'] == 'sklearn' and SKLEARN_AVAILABLE:
                    with open(save_path / f"{behavior_id}_model.pkl", 'wb') as f:
                        pickle.dump(model_info['model'], f)
            
            # Сохранение скейлеров
            for behavior_id, scaler in self.scalers.items():
                with open(save_path / f"{behavior_id}_scaler.pkl", 'wb') as f:
                    pickle.dump(scaler, f)
            
            # Сохранение памяти поколений
            with open(save_path / "generation_memories.json", 'w') as f:
                json.dump({str(k): v.__dict__ for k, v in self.generation_memories.items()}, f, indent=2)
            
            self.logger.info(f"Модели и память сохранены в {path}")
            
        except Exception as e:
            self.logger.error(f"Ошибка сохранения моделей: {e}")
    
    def load_models(self, path: str):
        """Загрузка моделей"""
        try:
            load_path = Path(path)
            
            for behavior_id, model_info in self.models.items():
                if model_info['type'] == 'pytorch' and TORCH_AVAILABLE:
                    model_path = load_path / f"{behavior_id}_model.pth"
                    if model_path.exists():
                        model_info['model'].load_state_dict(torch.load(model_path))
                        
                elif model_info['type'] == 'sklearn' and SKLEARN_AVAILABLE:
                    model_path = load_path / f"{behavior_id}_model.pkl"
                    if model_path.exists():
                        with open(model_path, 'rb') as f:
                            model_info['model'] = pickle.load(f)
            
            # Загрузка скейлеров
            for behavior_id in self.scalers.keys():
                scaler_path = load_path / f"{behavior_id}_scaler.pkl"
                if scaler_path.exists():
                    with open(scaler_path, 'rb') as f:
                        self.scalers[behavior_id] = pickle.load(f)
            
            # Загрузка памяти поколений
            memories_path = load_path / "generation_memories.json"
            if memories_path.exists():
                with open(memories_path, 'r') as f:
                    memories_data = json.load(f)
                    for gen_id, gen_data in memories_data.items():
                        self.generation_memories[int(gen_id)] = GenerationMemory(**gen_data)
            
            self.logger.info(f"Модели и память загружены из {path}")
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки моделей: {e}")
    
    def get_statistics(self) -> dict[str, Any]:
        """Получение статистики AI системы"""
        return {
            "total_entities": self.stats["total_entities"],
            "active_entities": self.stats["active_entities"],
            "decisions_made": self.stats["decisions_made"],
            "learning_events": self.stats["learning_events"],
            "model_updates": self.stats["model_updates"],
            "memory_entries": self.stats["memory_entries"],
            "generations": self.stats["generations"],
            "update_time": self.stats["update_time"],
            "behaviors_count": len(self.behaviors),
            "memory_size": len(self.global_memory),
            "models_count": len(self.models),
            "current_generation": self.current_generation,
            "ml_frameworks": {
                "pytorch": TORCH_AVAILABLE,
                "sklearn": SKLEARN_AVAILABLE
            }
        }
    
    def add_behavior_callback(self, behavior_id: str, callback: Callable):
        """Добавление callback для поведения"""
        self.behavior_callbacks[behavior_id] = callback
    
    def add_decision_callback(self, callback: Callable):
        """Добавление callback для решений"""
        self.decision_callbacks.append(callback)
    
    def add_learning_callback(self, callback: Callable):
        """Добавление callback для обучения"""
        self.learning_callbacks.append(callback)
    
    def add_memory_callback(self, callback: Callable):
        """Добавление callback для памяти"""
        self.memory_callbacks.append(callback)
    
    def _notify_decision_made(self, decision: AIDecision):
        """Уведомление о принятом решении"""
        for callback in self.decision_callbacks:
            try:
                callback(decision)
            except Exception as e:
                self.logger.error(f"Ошибка в callback решения: {e}")
    
    def _notify_memory_entry_added(self, entity: AIEntity, memory_entry: MemoryEntry):
        """Уведомление о новой записи памяти"""
        for callback in self.memory_callbacks:
            try:
                callback(entity, memory_entry)
            except Exception as e:
                self.logger.error(f"Ошибка в callback памяти: {e}")
    
    def get_entity_state(self, entity_id: str) -> AIEntity | None:
        """Получение состояния AI сущности"""
        return self.ai_entities.get(entity_id)
    
    def get_all_entities(self) -> dict[str, AIEntity]:
        """Получение всех AI сущностей"""
        return self.ai_entities.copy()
    
    def clear_memory(self):
        """Очистка памяти"""
        self.global_memory.clear()
        self.experience_pool.clear()
        self.learning_data.clear()
        self.logger.info("Память AI системы очищена")
    
    def _on_destroy(self):
        """Уничтожение AI системы"""
        self.running = False
        
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=5.0)
        
        if self.executor:
            self.executor.shutdown(wait=True)
        
        self.ai_entities.clear()
        self.entity_behaviors.clear()
        self.behaviors.clear()
        self.decisions.clear()
        self.global_memory.clear()
        self.experience_pool.clear()
        self.learning_data.clear()
        self.models.clear()
        self.scalers.clear()
        self.generation_memories.clear()
        
        self.logger.info("AISystem уничтожен")
