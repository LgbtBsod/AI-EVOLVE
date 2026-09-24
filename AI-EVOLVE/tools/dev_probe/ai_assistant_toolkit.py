"""
AI Assistant Toolkit - набор утилит для ускорения работы AI-агентов с проектом.

Этот модуль предоставляет инструменты для:
1. Предиктивной аналитики тестов
2. Быстрого выявления аномалий в логах
3. Генерации сжатых отчетов для экономии токенов
4. Автоматического приоритизирования проблем
5. Визуализации трендов и паттернов
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
from pathlib import Path
from enum import Enum


class PriorityLevel(Enum):
    """Уровни приоритета проблем."""
    CRITICAL = "critical"  # Требует немедленного внимания
    HIGH = "high"  # Важно исправить скоро
    MEDIUM = "medium"  # Стоит исправить
    LOW = "low"  # Можно исправить позже
    INFO = "info"  # Информационное сообщение


@dataclass
class TokenBudget:
    """Трекер использования токенов для оптимизации отчетов."""
    max_tokens: int = 8000
    used_tokens: int = 0
    compression_ratio: float = 1.0
    
    def estimate_tokens(self, text: str) -> int:
        """Оценить количество токенов в тексте (примерно 4 символа = 1 токен)."""
        return len(text) // 4
    
    def can_fit(self, text: str) -> bool:
        """Проверить, поместится ли текст в бюджет."""
        return self.estimate_tokens(text) <= (self.max_tokens - self.used_tokens)
    
    def add(self, text: str):
        """Добавить текст к использованным токенам."""
        self.used_tokens += self.estimate_tokens(text)
    
    def reset(self):
        """Сбросить счетчик."""
        self.used_tokens = 0
        self.compression_ratio = 1.0


@dataclass
class IssueReport:
    """Структурированный отчет о проблеме для быстрой обработки агентом."""
    issue_id: str
    title: str
    priority: PriorityLevel
    category: str  # "toughness", "effects", "combat", "performance", "anomaly"
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    estimated_fix_time: str = ""  # "5min", "1h", "1d"
    related_files: List[str] = field(default_factory=list)
    
    def to_compact_dict(self) -> Dict[str, Any]:
        """Сжатое представление для экономии токенов."""
        return {
            "id": self.issue_id,
            "title": self.title,
            "priority": self.priority.value,
            "category": self.category,
            "desc": self.description[:200],  # Ограничить длину
            "fix": self.recommendation[:100],
            "files": self.related_files[:3],  # Только топ-3 файла
        }


@dataclass
class TrendAnalysis:
    """Анализ трендов для предиктивной аналитики."""
    metric_name: str
    values: List[float] = field(default_factory=list)
    trend_direction: str = "stable"  # "increasing", "decreasing", "stable"
    anomaly_detected: bool = False
    prediction_next: Optional[float] = None
    confidence: float = 0.0
    
    def analyze(self) -> 'TrendAnalysis':
        """Провести анализ тренда."""
        if len(self.values) < 2:
            return self
        
        # Простой линейный тренд
        n = len(self.values)
        x_mean = (n - 1) / 2
        y_mean = sum(self.values) / n
        
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(self.values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator != 0:
            slope = numerator / denominator
            
            # Определить направление тренда
            threshold = y_mean * 0.1  # 10% от среднего
            if slope > threshold:
                self.trend_direction = "increasing"
            elif slope < -threshold:
                self.trend_direction = "decreasing"
            
            # Предсказать следующее значение
            self.prediction_next = self.values[-1] + slope
            self.confidence = min(0.9, len(self.values) / 10)  # Уверенность растет с данными
        
        # Детекция аномалий (выход за 2 сигмы)
        if len(self.values) >= 5:
            mean = sum(self.values) / len(self.values)
            variance = sum((v - mean) ** 2 for v in self.values) / len(self.values)
            std_dev = variance ** 0.5
            
            if std_dev > 0:
                last_value = self.values[-1]
                if abs(last_value - mean) > 2 * std_dev:
                    self.anomaly_detected = True
        
        return self


class AIAssistantToolkit:
    """Основной класс инструментария для AI-агентов."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path("./ai_toolkit_output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.token_budget = TokenBudget()
        self.issues: List[IssueReport] = []
        self.trends: Dict[str, TrendAnalysis] = {}
        self.session_stats = {
            "start_time": time.time(),
            "snapshots_analyzed": 0,
            "events_processed": 0,
            "anomalies_detected": 0,
        }
        
        # Кэш для часто используемых данных
        self.data_cache: Dict[str, Any] = {}
        self.cache_hits = 0
        self.cache_misses = 0
    
    def get_cached(self, key: str, default: Any = None) -> Any:
        """Получить данные из кэша."""
        if key in self.data_cache:
            self.cache_hits += 1
            return self.data_cache[key]
        self.cache_misses += 1
        return default
    
    def set_cached(self, key: str, value: Any, ttl_seconds: int = 300):
        """Сохранить данные в кэш с TTL."""
        self.data_cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl_seconds,
        }
    
    def _cleanup_cache(self):
        """Очистить просроченные записи кэша."""
        now = time.time()
        expired = [k for k, v in self.data_cache.items() if v.get("expires_at", 0) < now]
        for k in expired:
            del self.data_cache[k]
    
    def prioritize_issues(self, issues: List[IssueReport]) -> List[IssueReport]:
        """Приоритизировать список проблем."""
        priority_order = {
            PriorityLevel.CRITICAL: 0,
            PriorityLevel.HIGH: 1,
            PriorityLevel.MEDIUM: 2,
            PriorityLevel.LOW: 3,
            PriorityLevel.INFO: 4,
        }
        return sorted(issues, key=lambda x: priority_order[x.priority])
    
    def generate_compact_report(
        self, 
        issues: List[IssueReport],
        include_details: bool = False,
        max_issues: int = 10,
    ) -> str:
        """
        Сгенерировать сжатый отчет для экономии токенов.
        
        Args:
            issues: Список проблем
            include_details: Включать ли полные детали
            max_issues: Максимальное количество проблем в отчете
        
        Returns:
            Сжатый JSON-отчет
        """
        prioritized = self.prioritize_issues(issues)[:max_issues]
        
        if include_details:
            report_data = {
                "summary": {
                    "total_issues": len(issues),
                    "critical": sum(1 for i in issues if i.priority == PriorityLevel.CRITICAL),
                    "high": sum(1 for i in issues if i.priority == PriorityLevel.HIGH),
                    "by_category": self._group_by_category(issues),
                },
                "issues": [i.to_compact_dict() for i in prioritized],
                "trends": {
                    name: {
                        "direction": t.trend_direction,
                        "anomaly": t.anomaly_detected,
                        "prediction": t.prediction_next,
                    }
                    for name, t in self.trends.items()
                },
                "session_stats": self.session_stats,
            }
        else:
            # Ultra-compact режим
            report_data = {
                "summary": f"{len(issues)} issues ({sum(1 for i in issues if i.priority == PriorityLevel.CRITICAL)} crit)",
                "top_issues": [
                    f"[{i.priority.value.upper()}] {i.title}"
                    for i in prioritized[:5]
                ],
                "action_required": any(i.priority in [PriorityLevel.CRITICAL, PriorityLevel.HIGH] for i in issues),
            }
        
        report_json = json.dumps(report_data, indent=2, default=str)
        self.token_budget.add(report_json)
        
        return report_json
    
    def _group_by_category(self, issues: List[IssueReport]) -> Dict[str, int]:
        """Сгруппировать проблемы по категориям."""
        groups = defaultdict(int)
        for issue in issues:
            groups[issue.category] += 1
        return dict(groups)
    
    def detect_anomalies_in_metrics(
        self, 
        metrics: Dict[str, List[float]],
        sensitivity: float = 2.0,
    ) -> List[IssueReport]:
        """
        Автоматически обнаружить аномалии в метриках.
        
        Args:
            metrics: Словарь {имя_метрики: [значения]}
            sensitivity: Чувствительность детекции (в сигмах)
        
        Returns:
            Список обнаруженных аномалий
        """
        anomalies = []
        
        for metric_name, values in metrics.items():
            if len(values) < 5:
                continue
            
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            std_dev = variance ** 0.5
            
            if std_dev == 0:
                continue
            
            for i, value in enumerate(values):
                z_score = abs(value - mean) / std_dev
                
                if z_score > sensitivity:
                    severity = PriorityLevel.CRITICAL if z_score > 4 else (
                        PriorityLevel.HIGH if z_score > 3 else PriorityLevel.MEDIUM
                    )
                    
                    anomalies.append(IssueReport(
                        issue_id=f"anomaly_{metric_name}_{i}",
                        title=f"Аномалия в {metric_name}",
                        priority=severity,
                        category="anomaly",
                        description=f"Значение {value:.2f} отклоняется от нормы ({mean:.2f} ± {std_dev:.2f})",
                        evidence={
                            "index": i,
                            "value": value,
                            "mean": mean,
                            "std_dev": std_dev,
                            "z_score": z_score,
                        },
                        recommendation=f"Проверить логи вокруг индекса {i}",
                    ))
        
        self.session_stats["anomalies_detected"] += len(anomalies)
        return anomalies
    
    def analyze_test_results(
        self, 
        test_output: str,
        previous_results: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Проанализировать результаты тестов и выявить регрессии.
        
        Args:
            test_output: Вывод тестов (pytest output)
            previous_results: Результаты предыдущего запуска
        
        Returns:
            Анализ результатов с выявленными проблемами
        """
        lines = test_output.split('\n')
        
        passed = 0
        failed = 0
        errors = []
        slow_tests = []
        
        for line in lines:
            if 'PASSED' in line:
                passed += 1
            elif 'FAILED' in line:
                failed += 1
                errors.append(line.strip())
            elif 'ERROR' in line:
                errors.append(line.strip())
            elif 'slow' in line.lower() or 'duration' in line.lower():
                slow_tests.append(line.strip())
        
        total = passed + failed
        success_rate = passed / total if total > 0 else 0
        
        result = {
            "passed": passed,
            "failed": failed,
            "total": total,
            "success_rate": success_rate,
            "errors": errors[:10],  # Ограничить количество ошибок
            "regressions": [],
        }
        
        # Выявить регрессии если есть предыдущие результаты
        if previous_results:
            prev_passed = previous_results.get("passed", 0)
            if passed < prev_passed:
                result["regressions"].append({
                    "type": "test_failures",
                    "message": f"Регрессия: {prev_passed - passed} тестов стали падать",
                    "priority": PriorityLevel.HIGH.value,
                })
        
        # Сохранить для сравнения в будущем
        self.set_cached("last_test_results", result)
        
        return result
    
    def track_trend(self, metric_name: str, value: float) -> TrendAnalysis:
        """Отследить значение метрики и обновить тренд."""
        if metric_name not in self.trends:
            self.trends[metric_name] = TrendAnalysis(metric_name=metric_name)
        
        self.trends[metric_name].values.append(value)
        
        # Ограничить историю последними 100 значениями
        if len(self.trends[metric_name].values) > 100:
            self.trends[metric_name].values = self.trends[metric_name].values[-100:]
        
        return self.trends[metric_name].analyze()
    
    def generate_quick_summary(self) -> str:
        """Сгенерировать быструю сводку состояния проекта."""
        critical_count = sum(1 for i in self.issues if i.priority == PriorityLevel.CRITICAL)
        high_count = sum(1 for i in self.issues if i.priority == PriorityLevel.HIGH)
        
        anomalies = sum(1 for t in self.trends.values() if t.anomaly_detected)
        
        summary_lines = [
            "=== QUICK PROJECT SUMMARY ===",
            f"Issues: {len(self.issues)} total ({critical_count} critical, {high_count} high)",
            f"Anomalies detected: {anomalies}",
            f"Session duration: {time.time() - self.session_stats['start_time']:.1f}s",
            f"Cache efficiency: {self.cache_hits / (self.cache_hits + self.cache_misses):.1%}" if (self.cache_hits + self.cache_misses) > 0 else "Cache: N/A",
        ]
        
        if critical_count > 0:
            summary_lines.append("\n⚠️ CRITICAL ISSUES:")
            for issue in self.issues:
                if issue.priority == PriorityLevel.CRITICAL:
                    summary_lines.append(f"  - {issue.title}")
        
        return "\n".join(summary_lines)
    
    def export_report(self, filename: str = "ai_assistant_report.json"):
        """Экспортировать полный отчет в файл."""
        report_path = self.output_dir / filename
        
        report_data = {
            "generated_at": time.time(),
            "session_stats": self.session_stats,
            "issues": [i.to_compact_dict() for i in self.issues],
            "trends": {
                name: {
                    "values": t.values[-20:],  # Последние 20 значений
                    "direction": t.trend_direction,
                    "anomaly": t.anomaly_detected,
                    "prediction": t.prediction_next,
                }
                for name, t in self.trends.items()
            },
            "token_usage": {
                "budget": self.token_budget.max_tokens,
                "used": self.token_budget.used_tokens,
                "compression": self.token_budget.compression_ratio,
            },
        }
        
        with open(report_path, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        return report_path
    
    def add_issue(
        self,
        title: str,
        priority: PriorityLevel,
        category: str,
        description: str,
        recommendation: str = "",
        related_files: Optional[List[str]] = None,
    ) -> IssueReport:
        """Добавить проблему в список."""
        issue = IssueReport(
            issue_id=f"issue_{len(self.issues) + 1}",
            title=title,
            priority=priority,
            category=category,
            description=description,
            recommendation=recommendation,
            related_files=related_files or [],
        )
        self.issues.append(issue)
        return issue
    
    def clear_session(self):
        """Очистить сессию для нового анализа."""
        self.issues.clear()
        self.trends.clear()
        self.data_cache.clear()
        self.token_budget.reset()
        self.session_stats = {
            "start_time": time.time(),
            "snapshots_analyzed": 0,
            "events_processed": 0,
            "anomalies_detected": 0,
        }


# Готовые шаблоны отчетов для разных сценариев
REPORT_TEMPLATES = {
    "test_run": """
## Тесты: {passed}/{total} passed ({success_rate:.1%})
{regressions}
### Ошибки:
{errors}
""",
    "anomaly_detection": """
## Обнаружено аномалий: {count}
{anomalies}
### Требуется внимание:
{critical_items}
""",
    "trend_analysis": """
## Тренды метрик:
{trends}
### Прогнозы:
{predictions}
""",
}


def create_toolkit(output_dir: Optional[Path] = None) -> AIAssistantToolkit:
    """Фабричная функция для создания инструментария."""
    return AIAssistantToolkit(output_dir=output_dir)
