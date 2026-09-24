"""
L6 - Curriculum Learning Layer

Управление сложностью обучения:
- Оценка текущего уровня агента
- Подбор подходящей сложности окружения
- Подсказки игроку-тренеру
- Прогрессия через curriculum stages
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np


class DifficultyLevel(Enum):
    """Уровни сложности"""
    TUTORIAL = "tutorial"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"
    MASTER = "master"


@dataclass
class AgentMetrics:
    """Метрики производительности агента"""
    win_rate: float = 0.0
    avg_reward: float = 0.0
    avg_steps: float = 0.0
    deaths: int = 0
    kills: int = 0
    exploration_rate: float = 0.0
    skill_usage_efficiency: float = 0.0
    
    def composite_score(self) -> float:
        """Вычислить综合ную оценку"""
        return (
            self.win_rate * 0.4 +
            self.avg_reward * 0.3 +
            self.exploration_rate * 0.2 +
            self.skill_usage_efficiency * 0.1
        )


@dataclass
class WeaknessAnalysis:
    """Анализ слабых мест агента"""
    category: str  # combat, navigation, resource_management, etc.
    severity: float  # 0.0 - 1.0
    description: str
    recommended_exercises: List[str] = field(default_factory=list)


@dataclass
class CurriculumStage:
    """Этап curriculum обучения"""
    name: str
    difficulty: DifficultyLevel
    target_metrics: Dict[str, float]
    environment_config: Dict
    min_games: int = 100
    max_games: int = 1000
    promotion_threshold: float = 0.75  # Win rate для перехода дальше
    demotion_threshold: float = 0.40   # Win rate для отката назад


class CurriculumManager:
    """
    Менеджер curriculum обучения
    
    Функции:
    - Отслеживание прогресса агента
    - Автоматическая регулировка сложности
    - Генерация подсказок для тренера
    - Анализ слабых мест
    """
    
    def __init__(self, agent_id: str):
        """
        Args:
            agent_id: Уникальный идентификатор агента
        """
        self.agent_id = agent_id
        self.current_stage_idx = 0
        self.metrics_history: List[AgentMetrics] = []
        self.games_played = 0
        self.weaknesses: List[WeaknessAnalysis] = []
        
        # Определение curriculum stages
        self.stages = self._default_curriculum()
        self.current_stage = self.stages[0]
        
    def _default_curriculum(self) -> List[CurriculumStage]:
        """Создать стандартный curriculum"""
        return [
            CurriculumStage(
                name="Tutorial",
                difficulty=DifficultyLevel.TUTORIAL,
                target_metrics={"win_rate": 0.9, "exploration_rate": 0.8},
                environment_config={
                    "enemy_count": 0,
                    "obstacles": "minimal",
                    "hints_enabled": True
                },
                min_games=50
            ),
            CurriculumStage(
                name="Basic Combat",
                difficulty=DifficultyLevel.EASY,
                target_metrics={"win_rate": 0.75, "kills": 5},
                environment_config={
                    "enemy_count": 1,
                    "enemy_ai": "passive",
                    "powerups": "frequent"
                },
                min_games=100
            ),
            CurriculumStage(
                name="Advanced Combat",
                difficulty=DifficultyLevel.MEDIUM,
                target_metrics={"win_rate": 0.65, "skill_usage_efficiency": 0.6},
                environment_config={
                    "enemy_count": 2,
                    "enemy_ai": "aggressive",
                    "powerups": "normal"
                },
                min_games=200
            ),
            CurriculumStage(
                name="Tactical Mastery",
                difficulty=DifficultyLevel.HARD,
                target_metrics={"win_rate": 0.55, "deaths": 3},
                environment_config={
                    "enemy_count": 3,
                    "enemy_ai": "tactical",
                    "powerups": "rare"
                },
                min_games=300
            ),
            CurriculumStage(
                name="Elite Challenge",
                difficulty=DifficultyLevel.EXPERT,
                target_metrics={"win_rate": 0.45, "composite_score": 0.6},
                environment_config={
                    "enemy_count": 5,
                    "enemy_ai": "coordinated",
                    "powerups": "very_rare"
                },
                min_games=500
            ),
            CurriculumStage(
                name="Master Arena",
                difficulty=DifficultyLevel.MASTER,
                target_metrics={"win_rate": 0.40, "composite_score": 0.75},
                environment_config={
                    "enemy_count": 8,
                    "enemy_ai": "optimal",
                    "powerups": "none"
                },
                min_games=1000
            )
        ]
        
    def record_game(
        self,
        metrics: AgentMetrics,
        weaknesses: Optional[List[WeaknessAnalysis]] = None
    ):
        """
        Записать результаты игры
        
        Args:
            metrics: Метрики после игры
            weaknesses: Выявленные слабые места
        """
        self.metrics_history.append(metrics)
        self.games_played += 1
        
        if weaknesses:
            self.weaknesses.extend(weaknesses)
            
        # Проверка прогресса каждые 10 игр
        if self.games_played % 10 == 0:
            self._evaluate_progress()
            
    def _evaluate_progress(self):
        """Оценить прогресс и решить о смене стадии"""
        if len(self.metrics_history) < 10:
            return
            
        # Средние метрики за последние 10 игр
        recent_metrics = self.metrics_history[-10:]
        avg_win_rate = sum(m.win_rate for m in recent_metrics) / len(recent_metrics)
        
        # Проверка на повышение
        if avg_win_rate >= self.current_stage.promotion_threshold:
            if self.current_stage_idx < len(self.stages) - 1:
                self._promote()
                
        # Проверка на понижение
        elif avg_win_rate < self.current_stage.demotion_threshold:
            if self.current_stage_idx > 0:
                self._demote()
                
    def _promote(self):
        """Повысить стадию curriculum"""
        old_stage = self.current_stage
        self.current_stage_idx += 1
        self.current_stage = self.stages[self.current_stage_idx]
        
        print(f"🎉 Agent {self.agent_id} promoted!")
        print(f"   {old_stage.name} → {self.current_stage.name}")
        print(f"   Difficulty: {old_stage.difficulty.value} → {self.current_stage.difficulty.value}")
        
    def _demote(self):
        """Понизить стадию curriculum"""
        old_stage = self.current_stage
        self.current_stage_idx -= 1
        self.current_stage = self.stages[self.current_stage_idx]
        
        print(f"📉 Agent {self.agent_id} needs more practice")
        print(f"   {old_stage.name} → {self.current_stage.name}")
        
    def get_training_hints(self) -> List[str]:
        """
        Получить подсказки для улучшения агента
        
        Returns:
            Список рекомендаций
        """
        hints = []
        
        if not self.metrics_history:
            return ["Start training to get personalized hints"]
            
        latest = self.metrics_history[-1]
        
        # Анализ по метрикам
        if latest.win_rate < 0.5:
            hints.append("Focus on survival tactics before attempting kills")
            
        if latest.deaths > 5:
            hints.append("Work on defensive positioning and retreat timing")
            
        if latest.exploration_rate < 0.5:
            hints.append("Encourage map exploration - reward visiting new areas")
            
        if latest.skill_usage_efficiency < 0.4:
            hints.append("Train skill rotation - use abilities at optimal moments")
            
        # Анализ слабостей
        for weakness in self.weaknesses[-5:]:
            if weakness.severity > 0.7:
                hints.append(f"Critical: {weakness.description}")
                hints.extend([f"  → {ex}" for ex in weakness.recommended_exercises])
                
        return hints if hints else ["Performance looks good! Continue current training."]
        
    def get_environment_config(self) -> Dict:
        """Получить конфигурацию среды для текущей стадии"""
        return self.current_stage.environment_config
        
    def get_progress_report(self) -> Dict:
        """
        Получить отчёт о прогрессе
        
        Returns:
            Dictionary с полной статистикой
        """
        if not self.metrics_history:
            return {"status": "no_data"}
            
        recent = self.metrics_history[-10:]
        
        return {
            "agent_id": self.agent_id,
            "current_stage": self.current_stage.name,
            "difficulty": self.current_stage.difficulty.value,
            "games_played": self.games_played,
            "avg_win_rate": sum(m.win_rate for m in recent) / len(recent),
            "avg_reward": sum(m.avg_reward for m in recent) / len(recent),
            "trend": self._calculate_trend(),
            "weaknesses_count": len([w for w in self.weaknesses if w.severity > 0.5]),
            "next_milestone": self._get_next_milestone()
        }
        
    def _calculate_trend(self) -> str:
        """Вычислить тренд производительности"""
        if len(self.metrics_history) < 5:
            return "insufficient_data"
            
        recent = [m.composite_score() for m in self.metrics_history[-5:]]
        older = [m.composite_score() for m in self.metrics_history[-10:-5]]
        
        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)
        
        if avg_recent > avg_older * 1.1:
            return "improving"
        elif avg_recent < avg_older * 0.9:
            return "declining"
        else:
            return "stable"
            
    def _get_next_milestone(self) -> str:
        """Получить следующую цель"""
        target = self.current_stage.target_metrics
        return f"Achieve {target.get('win_rate', 0):.0%} win rate in {self.current_stage.name}"


class PlayerCoachInterface:
    """
    Интерфейс между игроком-тренером и curriculum системой
    
    Функции:
    - Отображение подсказок игроку
    - Получение директив от игрока
    - Синхронизация эмоций с обучением
    """
    
    def __init__(self, curriculum_manager: CurriculumManager):
        self.curriculum = curriculum_manager
        self.player_directives = []
        self.emotion_modifiers = {}
        
    def get_coaching_advice(self) -> str:
        """Получить совет для игрока-тренера"""
        hints = self.curriculum.get_training_hints()
        
        if not hints:
            return "Continue observing the agent's performance."
            
        advice = f"📋 Training Advice for {self.curriculum.agent_id}:\n\n"
        for i, hint in enumerate(hints[:5], 1):
            advice += f"{i}. {hint}\n"
            
        progress = self.curriculum.get_progress_report()
        advice += f"\n📊 Progress: {progress['avg_win_rate']:.1%} win rate"
        advice += f"\n📈 Trend: {progress['trend']}"
        advice += f"\n🎯 Next goal: {progress['next_milestone']}"
        
        return advice
        
    def apply_player_directive(self, directive: str):
        """
        Применить директиву от игрока
        
        Args:
            directive: Команда от игрока (например, "focus_combat", "explore_more")
        """
        self.player_directives.append(directive)
        print(f"Player directive applied: {directive}")
        
    def set_emotion_modifier(self, emotion: str, intensity: float):
        """
        Установить модификатор эмоции
        
        Args:
            emotion: Тип эмоции (happy, frustrated, excited)
            intensity: Интенсивность (0.0 - 1.0)
        """
        self.emotion_modifiers[emotion] = intensity
        print(f"Emotion modifier: {emotion} = {intensity:.2f}")
        
        # Эмоции могут влиять на reward shaping
        # Это можно использовать для имитации human feedback
