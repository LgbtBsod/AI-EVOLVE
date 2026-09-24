"""
PPO Trainer для обучения агентов

Использует Stable Baselines3 PPO с кастомными настройками:
- MultiInputPolicy для гибридных обсерваций (CNN + MLP)
- Batch inference для производительности
- Чекпоинты после каждой эпохи
"""

import torch
import torch.nn as nn
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from typing import Dict, Optional, Any
from pathlib import Path


class PPOTrainer:
    """
    PPO тренер для обучения агентов
    
    Поддерживает:
    - Гибридные обсервации (визуальные + векторные)
    - Иерархические действия
    - Кастомные reward функции
    - Чекпоинты и восстановление
    """
    
    def __init__(
        self,
        env,
        checkpoint_dir: str = "checkpoints",
        verbose: int = 1,
        **ppo_kwargs
    ):
        """
        Args:
            env: Gym environment (L4 wrapper)
            checkpoint_dir: Директория для чекпоинтов
            verbose: Уровень логирования
            **ppo_kwargs: Параметры для PPO (learning_rate, n_steps, и т.д.)
        """
        self.env = env
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        
        # Дефолтные параметры PPO
        default_kwargs = {
            "policy": "MultiInputPolicy",
            "learning_rate": 3e-4,
            "n_steps": 2048,
            "batch_size": 64,
            "n_epochs": 10,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "clip_range": 0.2,
            "ent_coef": 0.01,
            "verbose": verbose,
        }
        
        # Объединяем с пользовательскими параметрами
        config = {**default_kwargs, **ppo_kwargs}
        
        self.model = PPO(
            env=env,
            **config
        )
        
        self.current_step = 0
        
    def train(
        self,
        total_timesteps: int,
        callback: Optional[BaseCallback] = None,
        **learn_kwargs
    ):
        """
        Запуск обучения
        
        Args:
            total_timesteps: Количество шагов обучения
            callback: Кастомный колбэк (логирование, ранний стоп)
            **learn_kwargs: Дополнительные параметры для learn()
        """
        checkpoint_callback = CheckpointCallback(
            save_freq=100_000,
            save_path=str(self.checkpoint_dir),
            name_prefix="ppo_agent",
            verbose=self.verbose,
        )
        
        callbacks = [checkpoint_callback]
        if callback:
            callbacks.append(callback)
        
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=callbacks,
            **learn_kwargs
        )
        
        self.current_step = total_timesteps
        
    def save(self, path: str):
        """Сохранить модель"""
        self.model.save(path)
        print(f"Model saved to {path}")
        
    def load(self, path: str):
        """Загрузить модель"""
        self.model = PPO.load(path, env=self.env)
        print(f"Model loaded from {path}")
        
    def get_action(self, obs: Dict[str, torch.Tensor], deterministic: bool = False):
        """
        Получить действие для обсервации
        
        Args:
            obs: Обсервация (dict с 'images' и 'vectors')
            deterministic: Если True, использовать детерминированную политику
            
        Returns:
            action: Действие
            value: Value prediction
        """
        with torch.no_grad():
            action, value = self.model.policy.predict(obs, deterministic=deterministic)
        return action, value


class TrainingMonitorCallback(BaseCallback):
    """
    Колбэк для мониторинга обучения
    
    Логирует:
    - Win rate
    - Среднюю награду
    - Progress curriculum
    """
    
    def __init__(self, eval_env, eval_freq: int = 10_000, verbose: int = 1):
        super().__init__(verbose=verbose)
        self.eval_env = eval_env
        self.eval_freq = eval_freq
        self.episode_rewards = []
        self.wins = 0
        self.total_episodes = 0
        
    def _on_step(self) -> bool:
        # Логирование наград
        if 'reward' in self.locals.get('infos', [{}])[0]:
            self.episode_rewards.append(self.locals['infos'][0]['reward'])
            
        return True
        
    def _on_rollout_end(self) -> bool:
        # Оценка каждые eval_freq шагов
        if self.num_timesteps % self.eval_freq == 0:
            self._evaluate()
        return True
        
    def _evaluate(self):
        """Оценка текущей политики"""
        obs = self.eval_env.reset()
        episode_reward = 0
        done = False
        
        while not done:
            action, _ = self.training_model.predict(obs, deterministic=True)
            obs, reward, done, info = self.eval_env.step(action)
            episode_reward += reward[0]
            
            if info[0].get('is_win', False):
                self.wins += 1
            self.total_episodes += 1
            
        win_rate = self.wins / max(1, self.total_episodes)
        avg_reward = sum(self.episode_rewards[-100:]) / min(100, len(self.episode_rewards))
        
        if self.verbose > 0:
            print(f"Eval @ {self.num_timesteps}: win_rate={win_rate:.2f}, avg_reward={avg_reward:.2f}")
