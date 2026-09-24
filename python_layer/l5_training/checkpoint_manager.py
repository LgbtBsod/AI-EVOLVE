"""
Checkpoint Manager для сохранения и загрузки политик

Управление чекпоинтами:
- Автосохранение каждые N шагов
- Хранение лучших моделей по метрикам
- Версионирование чекпоинтов
- Метаданные (шаг, метрики, конфиг)
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class CheckpointMetadata:
    """Метаданные чекпоинта"""
    path: str
    step: int
    timestamp: str
    metrics: Dict[str, float]
    config: Dict[str, Any]
    is_best: bool = False


class CheckpointManager:
    """
    Менеджер чекпоинтов для ML моделей
    
    Функции:
    - Сохранение с метаданными
    - Автоудаление старых чекпоинтов
    - Отслеживание лучших моделей
    - Восстановление из чекпоинта
    """
    
    def __init__(
        self,
        checkpoint_dir: str,
        max_checkpoints: int = 10,
        metric_name: str = "win_rate",
        metric_mode: str = "max"  # "max" или "min"
    ):
        """
        Args:
            checkpoint_dir: Директория для чекпоинтов
            max_checkpoints: Максимальное количество хранимых чекпоинтов
            metric_name: Имя метрики для отслеживания лучших
            metric_mode: Режим сравнения ("max" или "min")
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_checkpoints = max_checkpoints
        self.metric_name = metric_name
        self.metric_mode = metric_mode
        
        self.best_metric = float('-inf') if metric_mode == 'max' else float('inf')
        self.checkpoints: List[CheckpointMetadata] = []
        
        # Загрузка существующих метаданных
        self._load_metadata()
        
    def save(
        self,
        model,
        step: int,
        metrics: Dict[str, float],
        config: Dict[str, Any]
    ) -> str:
        """
        Сохранить чекпоинт
        
        Args:
            model: Модель для сохранения (SB3 PPO)
            step: Текущий шаг обучения
            metrics: Метрики (win_rate, avg_reward, и т.д.)
            config: Конфигурация обучения
            
        Returns:
            path: Путь к сохранённому чекпоинту
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Определение, является ли чекпоинт лучшим
        current_metric = metrics.get(self.metric_name, 0)
        is_best = self._is_better(current_metric, self.best_metric)
        
        if is_best:
            self.best_metric = current_metric
            filename = f"best_model"
        else:
            filename = f"checkpoint_{step:08d}"
            
        path = self.checkpoint_dir / f"{filename}.zip"
        
        # Сохранение модели
        model.save(str(path))
        
        # Сохранение метаданных
        metadata = CheckpointMetadata(
            path=str(path),
            step=step,
            timestamp=timestamp,
            metrics=metrics,
            config=config,
            is_best=is_best
        )
        
        self._save_metadata(metadata)
        self.checkpoints.append(metadata)
        
        # Удаление старых чекпоинтов
        self._cleanup_old_checkpoints()
        
        print(f"Checkpoint saved: {path} (step={step}, {self.metric_name}={current_metric:.4f})")
        return str(path)
        
    def load(self, model, path: Optional[str] = None, load_best: bool = False):
        """
        Загрузить чекпоинт
        
        Args:
            model: Модель для загрузки весов
            path: Путь к чекпоинту (если None, загружается последний)
            load_best: Если True, загрузить лучший чекпоинт
        """
        if load_best:
            path = self._find_best_checkpoint()
        elif path is None:
            path = self._find_latest_checkpoint()
            
        if path is None:
            raise FileNotFoundError("No checkpoints found")
            
        model.load(path)
        print(f"Checkpoint loaded: {path}")
        return model
        
    def get_best_checkpoint(self) -> Optional[str]:
        """Получить путь к лучшему чекпоинту"""
        return self._find_best_checkpoint()
        
    def get_latest_checkpoint(self) -> Optional[str]:
        """Получить путь к последнему чекпоинту"""
        return self._find_latest_checkpoint()
        
    def list_checkpoints(self) -> List[CheckpointMetadata]:
        """Список всех чекпоинтов с метаданными"""
        return sorted(self.checkpoints, key=lambda x: x.step)
        
    def _is_better(self, current: float, best: float) -> bool:
        """Проверка, улучшилась ли метрика"""
        if self.metric_mode == 'max':
            return current > best
        else:
            return current < best
            
    def _find_best_checkpoint(self) -> Optional[str]:
        """Найти лучший чекпоинт"""
        for cp in self.checkpoints:
            if cp.is_best:
                return cp.path
        return None
        
    def _find_latest_checkpoint(self) -> Optional[str]:
        """Найти последний чекпоинт"""
        if not self.checkpoints:
            return None
        return self.checkpoints[-1].path
        
    def _save_metadata(self, metadata: CheckpointMetadata):
        """Сохранить метаданные в JSON"""
        metadata_file = self.checkpoint_dir / "metadata.json"
        
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                data = json.load(f)
        else:
            data = {"checkpoints": []}
            
        data["checkpoints"].append(asdict(metadata))
        
        with open(metadata_file, 'w') as f:
            json.dump(data, f, indent=2)
            
    def _load_metadata(self):
        """Загрузить метаданные из JSON"""
        metadata_file = self.checkpoint_dir / "metadata.json"
        
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                data = json.load(f)
                self.checkpoints = [
                    CheckpointMetadata(**cp) for cp in data["checkpoints"]
                ]
                
                # Обновление best_metric
                for cp in self.checkpoints:
                    if cp.is_best:
                        metric_value = cp.metrics.get(self.metric_name, 0)
                        if self._is_better(metric_value, self.best_metric):
                            self.best_metric = metric_value
                            
    def _cleanup_old_checkpoints(self):
        """Удалить старые чекпоинты, оставляя только последние N"""
        if len(self.checkpoints) <= self.max_checkpoints:
            return
            
        # Сортировка по шагу
        sorted_checkpoints = sorted(self.checkpoints, key=lambda x: x.step)
        
        # Удаление старых (кроме лучших)
        to_remove = sorted_checkpoints[:-self.max_checkpoints]
        
        for cp in to_remove:
            if not cp.is_best:
                try:
                    Path(cp.path).unlink()
                    self.checkpoints.remove(cp)
                    print(f"Removed old checkpoint: {cp.path}")
                except Exception as e:
                    print(f"Failed to remove {cp.path}: {e}")


def export_checkpoint_to_onnx(model, output_path: str):
    """
    Экспорт чекпоинта в ONNX формат
    
    Args:
        model: SB3 PPO модель
        output_path: Путь для сохранения ONNX файла
    """
    # TODO: Реализовать экспорт через torch.onnx.export
    # Требуется доступ к внутренней PyTorch модели
    print(f"Exporting to ONNX: {output_path}")
    raise NotImplementedError("ONNX export not yet implemented")
