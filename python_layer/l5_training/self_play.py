"""
Self-Play Arena для тренировки через игру против себя

Реализация:
- Турниры между разными версиями агентов
- Эло-рейтинг для оценки прогресса
- Автоматический отбор лучших моделей
- Параллельные матчи для производительности
"""

import asyncio
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import random


@dataclass
class AgentConfig:
    """Конфигурация агента для self-play"""
    model_path: str
    name: str
    elo: float = 1200.0  # Начальный рейтинг
    games_played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0


@dataclass
class MatchResult:
    """Результат матча между двумя агентами"""
    agent1_config: AgentConfig
    agent2_config: AgentConfig
    agent1_score: float  # 1 = win, 0.5 = draw, 0 = loss
    agent2_score: float
    duration_steps: int
    metadata: Dict = field(default_factory=dict)


class SelfPlayArena:
    """
    Арена для self-play тренировки
    
    Функции:
    - Организация турниров между версиями агентов
    - Расчёт Elo рейтинга
    - Отбор лучших моделей для следующего поколения
    - Параллельное выполнение матчей
    """
    
    def __init__(
        self,
        env_creator,
        num_parallel_matches: int = 4,
        elo_k_factor: float = 32.0,
        draw_threshold: float = 0.1  # Разница наград < threshold = ничья
    ):
        """
        Args:
            env_creator: Фабрика для создания сред (Gym wrapper)
            num_parallel_matches: Количество параллельных матчей
            elo_k_factor: K-фактор для расчёта Elo
            draw_threshold: Порог для определения ничьей
        """
        self.env_creator = env_creator
        self.num_parallel_matches = num_parallel_matches
        self.elo_k_factor = elo_k_factor
        self.draw_threshold = draw_threshold
        
        self.agents: List[AgentConfig] = []
        self.match_history: List[MatchResult] = []
        
    def register_agent(
        self,
        model_path: str,
        name: str,
        initial_elo: float = 1200.0
    ):
        """Зарегистрировать агента на арене"""
        agent = AgentConfig(
            model_path=model_path,
            name=name,
            elo=initial_elo
        )
        self.agents.append(agent)
        print(f"Registered agent: {name} (Elo={initial_elo})")
        
    def run_tournament(
        self,
        num_games_per_pair: int = 10,
        max_steps_per_game: int = 1000
    ) -> Dict[str, float]:
        """
        Провести турнир между всеми агентами
        
        Args:
            num_games_per_pair: Количество игр между каждой парой
            max_steps_per_game: Максимум шагов в одной игре
            
        Returns:
            Dictionary {agent_name: final_elo}
        """
        print(f"Starting tournament with {len(self.agents)} agents...")
        
        # Создание всех пар
        pairs = []
        for i in range(len(self.agents)):
            for j in range(i + 1, len(self.agents)):
                for _ in range(num_games_per_pair):
                    pairs.append((self.agents[i], self.agents[j]))
                    
        random.shuffle(pairs)
        
        # Выполнение матчей
        results = []
        for agent1, agent2 in pairs:
            result = self._run_match(agent1, agent2, max_steps_per_game)
            results.append(result)
            self._update_elo(result)
            
        # Статистика турнира
        stats = {agent.name: agent.elo for agent in self.agents}
        
        print("\n=== Tournament Results ===")
        for name, elo in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            agent = next(a for a in self.agents if a.name == name)
            print(f"{name}: Elo={elo:.1f}, W={agent.wins}, D={agent.draws}, L={agent.losses}")
            
        return stats
        
    def _run_match(
        self,
        agent1: AgentConfig,
        agent2: AgentConfig,
        max_steps: int
    ) -> MatchResult:
        """
        Провести один матч между двумя агентами
        
        Args:
            agent1: Конфигурация первого агента
            agent2: Конфигурация второго агента
            max_steps: Максимум шагов
            
        Returns:
            MatchResult с результатами
        """
        env = self.env_creator()
        
        # Загрузка моделей
        from stable_baselines3 import PPO
        model1 = PPO.load(agent1.model_path, env=env)
        model2 = PPO.load(agent2.model_path, env=env)
        
        obs = env.reset()
        total_reward1 = 0
        total_reward2 = 0
        steps = 0
        
        done = False
        while not done and steps < max_steps:
            # Действия обоих агентов
            action1, _ = model1.predict(obs, deterministic=True)
            action2, _ = model2.predict(obs, deterministic=True)
            
            # В self-play оба агента управляют разными сторонами
            # Здесь зависит от реализации среды
            obs, reward, done, info = env.step(action1)
            
            total_reward1 += reward[0] if isinstance(reward, (list, tuple)) else reward
            steps += 1
            
        # Определение победителя
        if abs(total_reward1 - total_reward2) < self.draw_threshold:
            score1, score2 = 0.5, 0.5
        elif total_reward1 > total_reward2:
            score1, score2 = 1.0, 0.0
        else:
            score1, score2 = 0.0, 1.0
            
        result = MatchResult(
            agent1_config=agent1,
            agent2_config=agent2,
            agent1_score=score1,
            agent2_score=score2,
            duration_steps=steps,
            metadata={
                'reward1': total_reward1,
                'reward2': total_reward2
            }
        )
        
        self.match_history.append(result)
        return result
        
    def _update_elo(self, result: MatchResult):
        """Обновить Elo рейтинг агентов после матча"""
        agent1 = result.agent1_config
        agent2 = result.agent2_config
        
        # Ожидаемые очки
        expected1 = 1 / (1 + 10 ** ((agent2.elo - agent1.elo) / 400))
        expected2 = 1 / (1 + 10 ** ((agent1.elo - agent2.elo) / 400))
        
        # Обновление рейтинга
        agent1.elo += self.elo_k_factor * (result.agent1_score - expected1)
        agent2.elo += self.elo_k_factor * (result.agent2_score - expected2)
        
        # Статистика
        agent1.games_played += 1
        agent2.games_played += 1
        
        if result.agent1_score > result.agent2_score:
            agent1.wins += 1
            agent2.losses += 1
        elif result.agent1_score < result.agent2_score:
            agent1.losses += 1
            agent2.wins += 1
        else:
            agent1.draws += 1
            agent2.draws += 1
            
    def get_top_agents(self, n: int = 3) -> List[AgentConfig]:
        """Получить топ-N агентов по Elo"""
        return sorted(self.agents, key=lambda a: a.elo, reverse=True)[:n]
        
    def save_checkpoint(self, path: str):
        """Сохранить состояние арены"""
        import json
        from dataclasses import asdict
        
        data = {
            'agents': [asdict(a) for a in self.agents],
            'match_count': len(self.match_history),
            'config': {
                'elo_k_factor': self.elo_k_factor,
                'draw_threshold': self.draw_threshold
            }
        }
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
            
        print(f"Arena checkpoint saved to {path}")
        
    def load_checkpoint(self, path: str):
        """Загрузить состояние арены"""
        import json
        
        with open(path, 'r') as f:
            data = json.load(f)
            
        self.agents = [AgentConfig(**a) for a in data['agents']]
        self.match_history = []  # История не восстанавливается
        
        # Восстановление конфигурации
        if 'config' in data:
            self.elo_k_factor = data['config'].get('elo_k_factor', 32.0)
            self.draw_threshold = data['config'].get('draw_threshold', 0.1)
            
        print(f"Arena checkpoint loaded from {path}")
        print(f"Loaded {len(self.agents)} agents")


async def run_self_play_training(
    arena: SelfPlayArena,
    generations: int = 10,
    checkpoint_dir: str = "self_play_checkpoints"
):
    """
    Асинхронный запуск self-play тренировки
    
    Args:
        arena: SelfPlayArena с зарегистрированными агентами
        generations: Количество поколений обучения
        checkpoint_dir: Директория для чекпоинтов
    """
    Path(checkpoint_dir).mkdir(parents=True, exist_ok=True)
    
    for gen in range(generations):
        print(f"\n=== Generation {gen + 1}/{generations} ===")
        
        # Турнир
        results = arena.run_tournament(num_games_per_pair=5)
        
        # Сохранение лучших
        top_agents = arena.get_top_agents(n=3)
        for i, agent in enumerate(top_agents):
            checkpoint_path = f"{checkpoint_dir}/gen{gen+1}_top{i+1}_{agent.name}.zip"
            # Копирование модели (требуется реализация)
            print(f"Top {i+1}: {agent.name} (Elo={agent.elo:.1f})")
            
        # Сохранение состояния арены
        arena.save_checkpoint(f"{checkpoint_dir}/arena_gen{gen+1}.json")
        
        # Здесь можно добавить логику создания новых агентов
        # на основе лучших моделей текущего поколения
