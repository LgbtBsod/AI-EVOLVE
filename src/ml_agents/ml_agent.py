#!/usr/bin/env python3
"""ML-агент для обучения персонажа в AI-EVOLVE"""

import logging
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
import random
import json
import os

logger = logging.getLogger(__name__)

# ============================================================================
# ТИПЫ ДЕЙСТВИЙ
# ============================================================================

class ActionType(Enum):
    """Типы действий агента"""
    MOVE_FORWARD = 0
    MOVE_BACKWARD = 1
    MOVE_LEFT = 2
    MOVE_RIGHT = 3
    ATTACK = 4
    INTERACT = 5
    USE_SKILL = 6
    FLEE = 7
    IDLE = 8

# ============================================================================
# НАБЛЮДЕНИЯ
# ============================================================================

class Observation:
    """Наблюдение среды для агента"""
    
    def __init__(self, 
                 position: Tuple[float, float] = (0.0, 0.0),
                 health: float = 100.0,
                 mana: float = 50.0,
                 stamina: float = 100.0,
                 enemies_nearby: int = 0,
                 distance_to_nearest_enemy: float = 999.0,
                 allies_nearby: int = 0,
                 items_nearby: int = 0,
                 level: int = 1,
                 experience: float = 0.0):
        self.position = position
        self.health = health
        self.mana = mana
        self.stamina = stamina
        self.enemies_nearby = enemies_nearby
        self.distance_to_nearest_enemy = distance_to_nearest_enemy
        self.allies_nearby = allies_nearby
        self.items_nearby = items_nearby
        self.level = level
        self.experience = experience
    
    def to_vector(self) -> np.ndarray:
        """Преобразование наблюдения в вектор"""
        return np.array([
            self.position[0],
            self.position[1],
            self.health / 100.0,
            self.mana / 100.0,
            self.stamina / 100.0,
            min(self.enemies_nearby, 10) / 10.0,
            min(self.distance_to_nearest_enemy, 100) / 100.0,
            min(self.allies_nearby, 10) / 10.0,
            min(self.items_nearby, 10) / 10.0,
            min(self.level, 100) / 100.0,
            min(self.experience, 1000) / 1000.0
        ], dtype=np.float32)
    
    @classmethod
    def from_vector(cls, vector: np.ndarray) -> 'Observation':
        """Создание наблюдения из вектора"""
        return cls(
            position=(vector[0], vector[1]),
            health=vector[2] * 100.0,
            mana=vector[3] * 100.0,
            stamina=vector[4] * 100.0,
            enemies_nearby=int(vector[5] * 10),
            distance_to_nearest_enemy=vector[6] * 100.0,
            allies_nearby=int(vector[7] * 10),
            items_nearby=int(vector[8] * 10),
            level=int(vector[9] * 100),
            experience=vector[10] * 1000.0
        )

# ============================================================================
# НЕЙРОННАЯ СЕТЬ (ПРОСТАЯ)
# ============================================================================

class SimpleNeuralNetwork:
    """Простая нейронная сеть для RL"""
    
    def __init__(self, input_size: int = 11, hidden_size: int = 64, output_size: int = 9):
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size
        
        # Инициализация весов
        self.W1 = np.random.randn(input_size, hidden_size) * 0.1
        self.b1 = np.zeros((1, hidden_size))
        self.W2 = np.random.randn(hidden_size, output_size) * 0.1
        self.b2 = np.zeros((1, output_size))
        
        # Для градиентов
        self.gradients = {}
        
    def relu(self, x: np.ndarray) -> np.ndarray:
        """Функция активации ReLU"""
        return np.maximum(0, x)
    
    def softmax(self, x: np.ndarray) -> np.ndarray:
        """Функция активации Softmax"""
        exp_x = np.exp(x - np.max(x, axis=1, keepdims=True))
        return exp_x / np.sum(exp_x, axis=1, keepdims=True)
    
    def forward(self, X: np.ndarray) -> np.ndarray:
        """Прямое распространение"""
        self.z1 = X.dot(self.W1) + self.b1
        self.a1 = self.relu(self.z1)
        self.z2 = self.a1.dot(self.W2) + self.b2
        self.a2 = self.softmax(self.z2)
        return self.a2
    
    def backward(self, X: np.ndarray, y: np.ndarray, output: np.ndarray, learning_rate: float = 0.01):
        """Обратное распространение"""
        m = X.shape[0]
        
        # Градиенты для выходного слоя
        dz2 = output - y
        dW2 = (self.a1.T).dot(dz2) / m
        db2 = np.sum(dz2, axis=0, keepdims=True) / m
        
        # Градиенты для скрытого слоя
        da1 = dz2.dot(self.W2.T)
        dz1 = da1 * (self.z1 > 0)
        dW1 = (X.T).dot(dz1) / m
        db1 = np.sum(dz1, axis=0, keepdims=True) / m
        
        # Сохранение градиентов
        self.gradients = {'dW1': dW1, 'db1': db1, 'dW2': dW2, 'db2': db2}
        
        # Обновление весов
        self.W1 -= learning_rate * dW1
        self.b1 -= learning_rate * db1
        self.W2 -= learning_rate * dW2
        self.b2 -= learning_rate * db2
    
    def save(self, filepath: str):
        """Сохранение модели"""
        model_data = {
            'W1': self.W1.tolist(),
            'b1': self.b1.tolist(),
            'W2': self.W2.tolist(),
            'b2': self.b2.tolist(),
            'input_size': self.input_size,
            'hidden_size': self.hidden_size,
            'output_size': self.output_size
        }
        with open(filepath, 'w') as f:
            json.dump(model_data, f)
        logger.info(f"Модель сохранена в {filepath}")
    
    def load(self, filepath: str):
        """Загрузка модели"""
        if not os.path.exists(filepath):
            logger.warning(f"Файл модели не найден: {filepath}")
            return False
        
        with open(filepath, 'r') as f:
            model_data = json.load(f)
        
        self.W1 = np.array(model_data['W1'])
        self.b1 = np.array(model_data['b1'])
        self.W2 = np.array(model_data['W2'])
        self.b2 = np.array(model_data['b2'])
        self.input_size = model_data['input_size']
        self.hidden_size = model_data['hidden_size']
        self.output_size = model_data['output_size']
        
        logger.info(f"Модель загружена из {filepath}")
        return True

# ============================================================================
# ML АГЕНТ
# ============================================================================

class MLAgent:
    """Агент машинного обучения для персонажа"""
    
    def __init__(self, agent_id: str = "player_agent", learning_rate: float = 0.01, 
                 discount_factor: float = 0.99, exploration_rate: float = 1.0):
        self.agent_id = agent_id
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.exploration_rate = exploration_rate
        self.exploration_decay = 0.995
        self.min_exploration = 0.01
        
        # Нейронная сеть
        self.network = SimpleNeuralNetwork()
        
        # Память для обучения
        self.memory: List[Tuple[Observation, int, float, Observation, bool]] = []
        self.memory_size = 10000
        self.batch_size = 32
        
        # Статистика
        self.total_rewards = 0.0
        self.episodes = 0
        self.wins = 0
        self.losses = 0
        
        logger.info(f"MLAgent {agent_id} инициализирован")
    
    def select_action(self, observation: Observation, training: bool = True) -> ActionType:
        """Выбор действия на основе наблюдения"""
        # Epsilon-greedy стратегия
        if training and random.random() < self.exploration_rate:
            return random.choice(list(ActionType))
        
        # Прямое распространение через сеть
        obs_vector = observation.to_vector().reshape(1, -1)
        action_probs = self.network.forward(obs_vector)[0]
        action_idx = np.argmax(action_probs)
        
        return ActionType(action_idx)
    
    def store_transition(self, state: Observation, action: int, reward: float, 
                        next_state: Observation, done: bool):
        """Сохранение перехода в память"""
        self.memory.append((state, action, reward, next_state, done))
        
        # Ограничение размера памяти
        if len(self.memory) > self.memory_size:
            self.memory.pop(0)
    
    def train(self, epochs: int = 100):
        """Обучение агента на основе памяти"""
        if len(self.memory) < self.batch_size:
            return
        
        total_loss = 0.0
        
        for epoch in range(epochs):
            # Выборка случайной пачки
            batch = random.sample(self.memory, self.batch_size)
            
            for state, action, reward, next_state, done in batch:
                # Текущее состояние
                state_vector = state.to_vector().reshape(1, -1)
                next_state_vector = next_state.to_vector().reshape(1, -1)
                
                # Предсказание текущих Q-значений
                current_q = self.network.forward(state_vector)[0]
                
                # Целевые Q-значения
                target_q = current_q.copy()
                
                if done:
                    target_q[action] = reward
                else:
                    next_q = self.network.forward(next_state_vector)[0]
                    target_q[action] = reward + self.discount_factor * np.max(next_q)
                
                # Обратное распространение
                self.network.backward(state_vector, target_q.reshape(1, -1), 
                                     current_q.reshape(1, -1), self.learning_rate)
                
                total_loss += np.mean((target_q - current_q) ** 2)
        
        # Уменьшение исследования
        self.exploration_rate = max(self.min_exploration, 
                                    self.exploration_rate * self.exploration_decay)
        
        avg_loss = total_loss / (epochs * self.batch_size)
        logger.debug(f"Обучение завершено, средний loss: {avg_loss:.4f}")
    
    def get_reward(self, event_type: str, event_data: Dict[str, Any]) -> float:
        """Расчёт награды за событие"""
        rewards = {
            'enemy_defeated': 10.0,
            'damage_dealt': 1.0,
            'damage_taken': -2.0,
            'item_collected': 5.0,
            'level_up': 20.0,
            'death': -50.0,
            'interaction': 2.0,
            'exploration': 0.5,
            'idle': -0.1
        }
        
        base_reward = rewards.get(event_type, 0.0)
        
        # Модификаторы
        if event_type == 'enemy_defeated':
            enemy_level = event_data.get('enemy_level', 1)
            base_reward *= enemy_level
        
        if event_type == 'damage_dealt':
            damage = event_data.get('damage', 0)
            base_reward = damage * 0.1
        
        if event_type == 'damage_taken':
            health_pct = event_data.get('health_percent', 100)
            if health_pct < 20:
                base_reward *= 2.0  # Больше штрафа при низком здоровье
        
        return base_reward
    
    def save(self, filepath: str):
        """Сохранение агента"""
        self.network.save(filepath)
        
        # Сохранение статистики
        stats_file = filepath.replace('.json', '_stats.json')
        stats = {
            'total_rewards': self.total_rewards,
            'episodes': self.episodes,
            'wins': self.wins,
            'losses': self.losses,
            'exploration_rate': self.exploration_rate
        }
        with open(stats_file, 'w') as f:
            json.dump(stats, f)
        
        logger.info(f"Агент сохранён в {filepath}")
    
    def load(self, filepath: str) -> bool:
        """Загрузка агента"""
        success = self.network.load(filepath)
        
        if success:
            # Загрузка статистики
            stats_file = filepath.replace('.json', '_stats.json')
            if os.path.exists(stats_file):
                with open(stats_file, 'r') as f:
                    stats = json.load(f)
                self.total_rewards = stats.get('total_rewards', 0.0)
                self.episodes = stats.get('episodes', 0)
                self.wins = stats.get('wins', 0)
                self.losses = stats.get('losses', 0)
                self.exploration_rate = stats.get('exploration_rate', 1.0)
        
        return success
    
    def reset_episode(self, won: bool = False):
        """Сброс после эпизода"""
        self.episodes += 1
        if won:
            self.wins += 1
        else:
            self.losses += 1
        
        # Очистка памяти эпизода (опционально)
        # self.memory = []
        
        logger.info(f"Эпизод {self.episodes} завершён: побед={self.wins}, поражений={self.losses}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики агента"""
        return {
            'agent_id': self.agent_id,
            'episodes': self.episodes,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': self.wins / max(1, self.episodes),
            'total_rewards': self.total_rewards,
            'avg_reward': self.total_rewards / max(1, self.episodes),
            'exploration_rate': self.exploration_rate,
            'memory_size': len(self.memory)
        }
