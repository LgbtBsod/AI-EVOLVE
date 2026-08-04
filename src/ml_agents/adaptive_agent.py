"""
Адаптивный RL-агент для обучения персонажей и врагов.
Использует глубокое обучение с подкреплением (Deep RL) для адаптации к поведению противника.
Поддерживает исследование скиллов, уклонение, блокирование и использование оружия.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum, auto
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Categorical
import logging
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Типы действий для агента."""
    MOVE_FORWARD = auto()
    MOVE_BACKWARD = auto()
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    ATTACK_MELEE = auto()
    ATTACK_RANGE = auto()
    USE_SKILL = auto()
    DODGE = auto()
    BLOCK = auto()
    INTERACT = auto()
    FLEE = auto()
    EXPLORE = auto()
    WAIT = auto()


class SkillDiscoveryState(Enum):
    """Состояние исследования скилла."""
    UNKNOWN = auto()
    DISCOVERED = auto()
    TESTED = auto()
    MASTERED = auto()
    OPTIMIZED = auto()


@dataclass(slots=True)
class SkillInfo:
    """Информация о скилле."""
    skill_id: str
    name: str
    element: str
    damage_type: str
    cooldown: float
    mana_cost: int
    discovery_state: SkillDiscoveryState = SkillDiscoveryState.UNKNOWN
    usage_count: int = 0
    success_rate: float = 0.0
    avg_damage: float = 0.0
    effectiveness_score: float = 0.0


@dataclass(slots=True)
class WeaponInfo:
    """Информация об оружии."""
    weapon_id: str
    name: str
    weapon_type: str
    damage: int
    attack_speed: float
    skills: List[str] = field(default_factory=list)
    proficiency: float = 0.0
    usage_count: int = 0


@dataclass(slots=True)
class EntityState:
    """Состояние сущности (персонажа или врага)."""
    health: float
    max_health: float
    mana: float
    max_mana: float
    stamina: float
    max_stamina: float
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    status_effects: List[str] = field(default_factory=list)
    active_buffs: List[str] = field(default_factory=list)
    active_debuffs: List[str] = field(default_factory=list)


@dataclass(slots=True)
class BattleContext:
    """Контекст боя для принятия решений."""
    self_state: EntityState
    enemy_state: EntityState
    distance_to_enemy: float
    enemy_visibility: bool
    terrain_cover: bool
    allies_nearby: int
    enemies_nearby: int
    available_skills: List[SkillInfo]
    equipped_weapon: Optional[WeaponInfo]
    environment_hazards: List[str] = field(default_factory=list)


class AdaptiveNeuralNetwork(nn.Module):
    """
    Адаптивная нейросеть для RL-агента.
    Использует архитектуру Actor-Critic с вниманием к контексту.
    """
    
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 256):
        super().__init__()
        
        # Encoder состояния
        self.state_encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU()
        )
        
        # Attention механизм для контекста
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_dim, 
            num_heads=8, 
            dropout=0.1
        )
        
        # Actor (политика)
        self.actor = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, action_dim),
            nn.Softmax(dim=-1)
        )
        
        # Critic (функция ценности)
        self.critic = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)
        )
        
        self.hidden_dim = hidden_dim
    
    def forward(self, state: torch.Tensor, context: Optional[torch.Tensor] = None):
        # Кодирование состояния
        encoded = self.state_encoder(state)
        
        # Attention если есть контекст
        if context is not None:
            encoded = encoded.unsqueeze(1)
            context_encoded = self.state_encoder(context)
            attended, _ = self.attention(encoded, context_encoded, context_encoded)
            encoded = attended.squeeze(1)
        
        # Политика и ценность
        policy = self.actor(encoded)
        value = self.critic(encoded)
        
        return policy, value


class AdaptiveRLAgent:
    """
    Адаптивный RL-агент для обучения персонажей и врагов.
    Поддерживает:
    - Исследование скиллов и оружия
    - Адаптацию к поведению противника
    - Уклонение и блокирование
    - Обучение через опыт (PPO-like алгоритм)
    """
    
    def __init__(self, agent_id: str, agent_type: str = "character",
                 state_dim: int = 64, action_dim: int = 14,
                 learning_rate: float = 3e-4, gamma: float = 0.99):
        self.agent_id = agent_id
        self.agent_type = agent_type  # "character" или "enemy"
        self.action_dim = action_dim
        self.gamma = gamma
        
        # Нейросеть
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = AdaptiveNeuralNetwork(state_dim, action_dim).to(self.device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        
        # Память для обучения
        self.memory = {
            'states': [],
            'actions': [],
            'rewards': [],
            'next_states': [],
            'dones': [],
            'log_probs': []
        }
        
        # База знаний
        self.skills: Dict[str, SkillInfo] = {}
        self.weapons: Dict[str, WeaponInfo] = {}
        self.enemy_patterns: Dict[str, List[Dict]] = {}  # Паттерны поведения врагов
        self.combat_history: List[Dict] = []
        
        # Статистика
        self.total_episodes = 0
        self.total_wins = 0
        self.total_losses = 0
        self.adaptation_level = 0.0
        
        # Конфигурация исследования
        self.exploration_rate = 0.9  # Начальный epsilon
        self.exploration_decay = 0.995
        self.min_exploration = 0.01
        
        # Путь для сохранения
        self.save_path = Path(f"saves/ml_agents/{agent_id}")
        self.save_path.mkdir(parents=True, exist_ok=True)
    
    def encode_state(self, context: BattleContext) -> torch.Tensor:
        """Кодировать состояние боя в вектор."""
        # Нормализация значений
        self_health = context.self_state.health / max(context.self_state.max_health, 1)
        self_mana = context.self_state.mana / max(context.self_state.max_mana, 1)
        self_stamina = context.self_state.stamina / max(context.self_state.max_stamina, 1)
        
        enemy_health = context.enemy_state.health / max(context.enemy_state.max_health, 1)
        enemy_mana = context.enemy_state.mana / max(context.enemy_state.max_mana, 1)
        
        # Вектор состояния
        state_vector = [
            self_health, self_mana, self_stamina,
            enemy_health, enemy_mana,
            context.distance_to_enemy / 100.0,  # Нормализация дистанции
            1.0 if context.enemy_visibility else 0.0,
            1.0 if context.terrain_cover else 0.0,
            context.allies_nearby / 10.0,
            context.enemies_nearby / 10.0,
            len(context.self_state.status_effects) / 10.0,
            len(context.self_state.active_buffs) / 5.0,
            len(context.self_state.active_debuffs) / 5.0,
            len(context.available_skills) / 10.0,
            1.0 if context.equipped_weapon else 0.0,
            len(context.environment_hazards) / 5.0
        ]
        
        # Добавление информации о скиллах
        for skill in context.available_skills[:5]:  # Максимум 5 скиллов
            state_vector.extend([
                1.0 if skill.discovery_state != SkillDiscoveryState.UNKNOWN else 0.0,
                skill.usage_count / 100.0,
                skill.success_rate,
                skill.effectiveness_score
            ])
        
        # Pad до нужной размерности
        while len(state_vector) < 64:
            state_vector.append(0.0)
        
        return torch.tensor(state_vector[:64], dtype=torch.float32).to(self.device)
    
    def select_action(self, context: BattleContext, training: bool = True) -> Tuple[int, float]:
        """
        Выбрать действие на основе текущего состояния.
        Возвращает действие и его вероятность.
        """
        state = self.encode_state(context)
        
        # Exploration vs Exploitation
        if training and np.random.random() < self.exploration_rate:
            action = np.random.randint(self.action_dim)
            log_prob = 0.0
        else:
            with torch.no_grad():
                policy, _ = self.model(state)
                dist = Categorical(policy)
                action = dist.sample().item()
                log_prob = dist.log_prob(torch.tensor(action)).item()
        
        return action, log_prob
    
    def store_transition(self, state: torch.Tensor, action: int, reward: float,
                        next_state: torch.Tensor, done: bool, log_prob: float):
        """Сохранить переход для обучения."""
        self.memory['states'].append(state)
        self.memory['actions'].append(action)
        self.memory['rewards'].append(reward)
        self.memory['next_states'].append(next_state)
        self.memory['dones'].append(done)
        self.memory['log_probs'].append(log_prob)
    
    def update(self, batch_size: int = 64) -> Dict[str, float]:
        """
        Обновить модель используя PPO-like алгоритм.
        Возвращает метрики обучения.
        """
        if len(self.memory['states']) < batch_size:
            return {'loss': 0.0}
        
        # Выборка батча
        indices = np.random.choice(len(self.memory['states']), batch_size, replace=False)
        
        states = torch.stack([self.memory['states'][i] for i in indices])
        actions = torch.tensor([self.memory['actions'][i] for i in indices])
        rewards = torch.tensor([self.memory['rewards'][i] for i in indices], dtype=torch.float32)
        next_states = torch.stack([self.memory['next_states'][i] for i in indices])
        dones = torch.tensor([self.memory['dones'][i] for i in indices], dtype=torch.float32)
        old_log_probs = torch.tensor([self.memory['log_probs'][i] for i in indices])
        
        # Вычисление returns
        returns = []
        G = 0
        for reward, done in zip(reversed(rewards.tolist()), reversed(dones.tolist())):
            G = reward + self.gamma * G * (1 - done)
            returns.insert(0, G)
        returns = torch.tensor(returns, dtype=torch.float32)
        
        # Нормализация returns
        returns = (returns - returns.mean()) / (returns.std() + 1e-8)
        
        # Forward pass
        policy, values = self.model(states)
        next_policy, next_values = self.model(next_states)
        
        # Вычисление advantages
        advantages = returns - values.squeeze()
        
        # Policy loss (PPO clip)
        dist = Categorical(policy)
        log_probs = dist.log_prob(actions)
        ratios = torch.exp(log_probs - old_log_probs)
        
        surr1 = ratios * advantages
        surr2 = torch.clamp(ratios, 0.8, 1.2) * advantages
        policy_loss = -torch.min(surr1, surr2).mean()
        
        # Value loss
        value_loss = nn.MSELoss()(values.squeeze(), returns)
        
        # Entropy bonus для exploration
        entropy = dist.entropy().mean()
        
        # Total loss
        loss = policy_loss + 0.5 * value_loss - 0.01 * entropy
        
        # Backward pass
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.model.parameters(), 0.5)
        self.optimizer.step()
        
        # Очистка памяти
        self.memory = {
            'states': [], 'actions': [], 'rewards': [],
            'next_states': [], 'dones': [], 'log_probs': []
        }
        
        # Decay exploration
        self.exploration_rate = max(
            self.min_exploration,
            self.exploration_rate * self.exploration_decay
        )
        
        return {
            'loss': loss.item(),
            'policy_loss': policy_loss.item(),
            'value_loss': value_loss.item(),
            'entropy': entropy.item(),
            'exploration_rate': self.exploration_rate
        }
    
    def discover_skill(self, skill_info: SkillInfo) -> None:
        """Открыть новый скилл."""
        self.skills[skill_info.skill_id] = skill_info
        logger.info(f"Агент {self.agent_id} открыл скилл: {skill_info.name}")
    
    def update_skill_knowledge(self, skill_id: str, success: bool, damage: float = 0.0):
        """Обновить знания о скилле после использования."""
        if skill_id not in self.skills:
            return
        
        skill = self.skills[skill_id]
        skill.usage_count += 1
        
        # Обновление прогресса исследования
        if skill.discovery_state == SkillDiscoveryState.UNKNOWN:
            skill.discovery_state = SkillDiscoveryState.DISCOVERED
        elif skill.discovery_state == SkillDiscoveryState.DISCOVERED:
            skill.discovery_state = SkillDiscoveryState.TESTED
        elif skill.usage_count > 10:
            skill.discovery_state = SkillDiscoveryState.MASTERED
        elif skill.usage_count > 50:
            skill.discovery_state = SkillDiscoveryState.OPTIMIZED
        
        # Обновление статистики
        n = skill.usage_count
        skill.success_rate = (skill.success_rate * (n - 1) + (1.0 if success else 0.0)) / n
        skill.avg_damage = (skill.avg_damage * (n - 1) + damage) / n
        
        # Эффективность (комбинированный скор)
        skill.effectiveness_score = (
            skill.success_rate * 0.4 +
            min(skill.avg_damage / 100.0, 1.0) * 0.4 +
            (1.0 if skill.discovery_state == SkillDiscoveryState.OPTIMIZED else 0.5) * 0.2
        )
    
    def learn_enemy_pattern(self, enemy_id: str, behavior: Dict) -> None:
        """Изучить паттерн поведения врага."""
        if enemy_id not in self.enemy_patterns:
            self.enemy_patterns[enemy_id] = []
        
        self.enemy_patterns[enemy_id].append(behavior)
        
        # Ограничение размера истории
        if len(self.enemy_patterns[enemy_id]) > 1000:
            self.enemy_patterns[enemy_id] = self.enemy_patterns[enemy_id][-500:]
    
    def get_adaptation_strategy(self, enemy_id: str) -> Dict[str, float]:
        """Получить стратегию адаптации к конкретному врагу."""
        if enemy_id not in self.enemy_patterns or len(self.enemy_patterns[enemy_id]) < 5:
            return {'aggression': 0.5, 'caution': 0.5, 'exploration': 0.5}
        
        behaviors = self.enemy_patterns[enemy_id][-50:]  # Последние 50 встреч
        
        # Анализ паттернов
        attack_frequency = sum(b.get('attack_count', 0) for b in behaviors) / len(behaviors)
        dodge_success = sum(b.get('dodges', 0) for b in behaviors) / len(behaviors)
        avg_damage_taken = sum(b.get('damage_taken', 0) for b in behaviors) / len(behaviors)
        
        # Адаптация стратегии
        aggression = min(1.0, attack_frequency / 10.0)
        caution = min(1.0, avg_damage_taken / 50.0)
        exploration = max(0.1, 1.0 - (dodge_success * 0.8))
        
        return {
            'aggression': aggression,
            'caution': caution,
            'exploration': exploration
        }
    
    def save(self) -> None:
        """Сохранить модель и знания."""
        save_data = {
            'model_state_dict': self.model.state_dict(),
            'skills': {k: v.__dict__ for k, v in self.skills.items()},
            'weapons': {k: v.__dict__ for k, v in self.weapons.items()},
            'enemy_patterns': self.enemy_patterns,
            'combat_history': self.combat_history[-1000:],  # Последние 1000 боев
            'stats': {
                'total_episodes': self.total_episodes,
                'total_wins': self.total_wins,
                'total_losses': self.total_losses,
                'adaptation_level': self.adaptation_level,
                'exploration_rate': self.exploration_rate
            }
        }
        
        model_path = self.save_path / f"{self.agent_id}_model.pth"
        torch.save(save_data, model_path)
        logger.info(f"Агент {self.agent_id} сохранен в {model_path}")
    
    def load(self) -> bool:
        """Загрузить модель и знания."""
        model_path = self.save_path / f"{self.agent_id}_model.pth"
        
        if not model_path.exists():
            logger.warning(f"Модель агента {self.agent_id} не найдена")
            return False
        
        try:
            # PyTorch 2.x требует weights_only=False для кастомных классов
            save_data = torch.load(model_path, map_location=self.device, weights_only=False)
            
            self.model.load_state_dict(save_data['model_state_dict'])
            self.model.eval()
            
            # Восстановление знаний
            for skill_id, skill_data in save_data.get('skills', {}).items():
                self.skills[skill_id] = SkillInfo(**skill_data)
            
            for weapon_id, weapon_data in save_data.get('weapons', {}).items():
                self.weapons[weapon_id] = WeaponInfo(**weapon_data)
            
            self.enemy_patterns = save_data.get('enemy_patterns', {})
            self.combat_history = save_data.get('combat_history', [])
            
            stats = save_data.get('stats', {})
            self.total_episodes = stats.get('total_episodes', 0)
            self.total_wins = stats.get('total_wins', 0)
            self.total_losses = stats.get('total_losses', 0)
            self.adaptation_level = stats.get('adaptation_level', 0.0)
            self.exploration_rate = stats.get('exploration_rate', 0.9)
            
            logger.info(f"Агент {self.agent_id} загружен из {model_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки агента {self.agent_id}: {e}")
            return False
    
    def record_combat_result(self, won: bool, damage_dealt: float, 
                            damage_taken: float, skills_used: List[str]):
        """Записать результат боя для анализа."""
        combat_record = {
            'timestamp': len(self.combat_history),
            'won': won,
            'damage_dealt': damage_dealt,
            'damage_taken': damage_taken,
            'skills_used': skills_used,
            'adaptation_level': self.adaptation_level
        }
        
        self.combat_history.append(combat_record)
        
        if won:
            self.total_wins += 1
        else:
            self.total_losses += 1
        
        self.total_episodes += 1
        
        # Обновление уровня адаптации
        win_rate = self.total_wins / max(self.total_episodes, 1)
        self.adaptation_level = win_rate * 0.7 + (1.0 - damage_taken / 100.0) * 0.3
