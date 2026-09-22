"""
Plugin: Learning System Analyzer
Анализ механики обучения сущностей, прогрессии и получения навыков
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from .base import DevProbePlugin, PluginReport


@dataclass
class LearningMetrics:
    """Метрики обучения сущности"""
    entity_id: str
    current_level: int = 0
    experience: float = 0.0
    experience_to_next_level: float = 0.0
    skills_learned: List[str] = None
    learning_rate: float = 0.0  # XP в секунду
    anomalies_detected: List[Dict] = None
    
    def __post_init__(self):
        if self.skills_learned is None:
            self.skills_learned = []
        if self.anomalies_detected is None:
            self.anomalies_detected = []


class LearningPlugin(DevProbePlugin):
    """Плагин анализа системы обучения"""
    
    name = "learning_analyzer"
    version = "1.0.0"
    description = "Анализ механики обучения сущностей, прогрессии и навыков"
    dependencies = []
    
    def __init__(self, core):
        super().__init__(core)
        self.learning_metrics: Dict[str, LearningMetrics] = {}
        self.level_up_events: List[Dict] = []
        self.skill_acquisition_events: List[Dict] = []
        self.config = {
            "detect_level_skip": True,  # Детекция пропуска уровней
            "detect_xp_anomalies": True,  # Детекция аномалий опыта
            "detect_skill_duplicates": True,  # Детекция дубликатов навыков
            "track_learning_rate": True  # Отслеживание скорости обучения
        }
    
    def initialize(self, context: Any) -> bool:
        if not super().initialize(context):
            return False
        
        context.add_log("INFO", "Learning plugin initialized", category="learning")
        return True
    
    def execute(self, context: Any) -> Dict[str, Any]:
        """Выполнение анализа обучения"""
        start_time = time.time()
        
        results = {
            "entities_analyzed": 0,
            "level_ups_detected": len(self.level_up_events),
            "skills_acquired": len(self.skill_acquisition_events),
            "anomalies_found": 0,
            "execution_time_sec": 0
        }
        
        # Анализ каждой сущности
        for entity_id, metrics in self.learning_metrics.items():
            results["entities_analyzed"] += 1
            
            # Проверка на аномалии опыта
            if self.config["detect_xp_anomalies"]:
                if metrics.experience < 0:
                    anomaly = {
                        "anomaly_type": "negative_experience",
                        "severity": "HIGH",
                        "description": f"Отрицательный опыт: {metrics.experience}",
                        "data": {"entity_id": entity_id, "experience": metrics.experience}
                    }
                    context.add_anomaly(**anomaly)
                    metrics.anomalies_detected.append(anomaly)
                    results["anomalies_found"] += 1
                
                # Проверка на чрезмерный опыт (больше 10x от необходимого)
                if metrics.experience_to_next_level > 0:
                    ratio = metrics.experience / metrics.experience_to_next_level
                    if ratio > 10:
                        anomaly = {
                            "anomaly_type": "excessive_experience",
                            "severity": "MEDIUM",
                            "description": f"Опыт превышает необходимый в {ratio:.1f} раз",
                            "data": {"entity_id": entity_id, "ratio": ratio}
                        }
                        context.add_anomaly(**anomaly)
                        metrics.anomalies_detected.append(anomaly)
                        results["anomalies_found"] += 1
            
            # Проверка на дубликаты навыков
            if self.config["detect_skill_duplicates"]:
                skill_counts = {}
                for skill in metrics.skills_learned:
                    skill_counts[skill] = skill_counts.get(skill, 0) + 1
                
                for skill, count in skill_counts.items():
                    if count > 1:
                        anomaly = {
                            "anomaly_type": "duplicate_skill",
                            "severity": "LOW",
                            "description": f"Навык '{skill}' получен {count} раз",
                            "data": {"entity_id": entity_id, "skill": skill, "count": count}
                        }
                        context.add_anomaly(**anomaly)
                        metrics.anomalies_detected.append(anomaly)
                        results["anomalies_found"] += 1
        
        # Анализ событий повышения уровня
        for i, event in enumerate(self.level_up_events):
            if self.config["detect_level_skip"] and i > 0:
                prev_level = self.level_up_events[i-1].get("new_level", 0)
                curr_level = event.get("new_level", 0)
                
                if curr_level - prev_level > 1:
                    anomaly = {
                        "anomaly_type": "level_skip",
                        "severity": "HIGH",
                        "description": f"Пропуск уровня: с {prev_level} на {curr_level}",
                        "data": {"entity_id": event.get("entity_id"), "prev_level": prev_level, "curr_level": curr_level}
                    }
                    context.add_anomaly(**anomaly)
                    results["anomalies_found"] += 1
        
        results["execution_time_sec"] = round(time.time() - start_time, 3)
        
        context.add_log(
            "INFO",
            f"Learning analysis completed: {results['entities_analyzed']} entities, {results['anomalies_found']} anomalies",
            category="learning"
        )
        
        return results
    
    def track_entity(self, entity_id: str, level: int, experience: float, 
                     xp_to_next: float, skills: List[str]):
        """Отслеживание состояния сущности"""
        self.learning_metrics[entity_id] = LearningMetrics(
            entity_id=entity_id,
            current_level=level,
            experience=experience,
            experience_to_next_level=xp_to_next,
            skills_learned=skills.copy() if skills else []
        )
    
    def record_level_up(self, entity_id: str, old_level: int, new_level: int, 
                       experience: float):
        """Запись события повышения уровня"""
        event = {
            "timestamp": time.time(),
            "entity_id": entity_id,
            "old_level": old_level,
            "new_level": new_level,
            "experience": experience
        }
        self.level_up_events.append(event)
        
        # Обновление метрик
        if entity_id in self.learning_metrics:
            self.learning_metrics[entity_id].current_level = new_level
            self.learning_metrics[entity_id].experience = experience
    
    def record_skill_acquisition(self, entity_id: str, skill_id: str, 
                                skill_name: str, source: str = "unknown"):
        """Запись получения навыка"""
        event = {
            "timestamp": time.time(),
            "entity_id": entity_id,
            "skill_id": skill_id,
            "skill_name": skill_name,
            "source": source  # scroll, trainer, quest, etc.
        }
        self.skill_acquisition_events.append(event)
        
        # Обновление метрик
        if entity_id in self.learning_metrics:
            self.learning_metrics[entity_id].skills_learned.append(skill_id)
    
    def get_report(self, context: Any) -> Dict:
        """Генерация отчета плагина"""
        base_report = super().get_report(context)
        
        # Статистика по уровням
        level_distribution = {}
        for metrics in self.learning_metrics.values():
            lvl = metrics.current_level
            level_distribution[lvl] = level_distribution.get(lvl, 0) + 1
        
        # Статистика по навыкам
        skill_frequency = {}
        for event in self.skill_acquisition_events:
            skill = event["skill_name"]
            skill_frequency[skill] = skill_frequency.get(skill, 0) + 1
        
        top_skills = sorted(skill_frequency.items(), key=lambda x: x[1], reverse=True)[:10]
        
        base_report.update({
            "total_entities": len(self.learning_metrics),
            "total_level_ups": len(self.level_up_events),
            "total_skills_acquired": len(self.skill_acquisition_events),
            "level_distribution": level_distribution,
            "top_skills": dict(top_skills),
            "anomalies_by_type": self._count_anomalies_by_type(),
            "config": self.config
        })
        
        return base_report
    
    def _count_anomalies_by_type(self) -> Dict[str, int]:
        """Подсчет аномалий по типам"""
        type_counts = {}
        for metrics in self.learning_metrics.values():
            for anomaly in metrics.anomalies_detected:
                atype = anomaly.get("anomaly_type", anomaly.get("type", "unknown"))
                type_counts[atype] = type_counts.get(atype, 0) + 1
        return type_counts
    
    def cleanup(self, context: Any):
        """Очистка данных плагина"""
        self.learning_metrics.clear()
        self.level_up_events.clear()
        self.skill_acquisition_events.clear()
        super().cleanup(context)


# Хелперы для интеграции с игровой сессией
def simulate_learning_session(core, num_entities: int = 5, max_level: int = 10):
    """
    Симуляция сессии обучения для тестирования
    """
    import random
    
    plugin = core.plugins.get("learning_analyzer")
    if not plugin:
        raise RuntimeError("Learning plugin not enabled")
    
    context = core.context
    
    # Создание сущностей
    for i in range(num_entities):
        entity_id = f"entity_{i}"
        plugin.track_entity(entity_id, level=1, experience=0, xp_to_next=100, skills=[])
    
    # Симуляция прогрессии
    for step in range(20):
        for entity_id in list(plugin.learning_metrics.keys()):
            metrics = plugin.learning_metrics[entity_id]
            
            # Добавление опыта
            xp_gain = random.randint(50, 150)
            metrics.experience += xp_gain
            
            # Проверка повышения уровня
            if metrics.experience >= metrics.experience_to_next_level:
                old_level = metrics.current_level
                new_level = min(old_level + 1, max_level)
                
                if new_level > old_level:
                    plugin.record_level_up(entity_id, old_level, new_level, metrics.experience)
                    metrics.experience = 0
                    metrics.experience_to_next_level *= 1.5  # Усложнение
                    
                    # Шанс получения навыка при повышении уровня
                    if random.random() < 0.7:
                        skill_id = f"skill_{random.randint(1, 20)}"
                        skill_name = f"Skill {skill_id.split('_')[1]}"
                        plugin.record_skill_acquisition(
                            entity_id, skill_id, skill_name, source="level_up"
                        )
            
            # Случайное получение навыка из свитка
            if random.random() < 0.1:
                skill_id = f"scroll_skill_{random.randint(1, 10)}"
                skill_name = f"Scroll Skill {skill_id.split('_')[1]}"
                plugin.record_skill_acquisition(
                    entity_id, skill_id, skill_name, source="scroll"
                )
    
    return plugin.execute(context)
