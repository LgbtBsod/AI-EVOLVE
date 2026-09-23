"""
Batch Inference Engine для производительного предсказания действий

Оптимизирован для:
- Одновременного предсказания для множества агентов
- Минимизации накладных расходов PyTorch
- Интеграции с Rust симуляцией
"""

import torch
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class BatchObservation:
    """Пакет обсерваций для батч-инференса"""
    images: Optional[torch.Tensor]  # [batch_size, channels, height, width]
    vectors: torch.Tensor           # [batch_size, vector_dim]
    masks: Optional[torch.Tensor]   # [batch_size, action_dim] - для валидных действий


@dataclass
class BatchActions:
    """Пакет действий от батч-инференса"""
    actions: torch.Tensor           # [batch_size, action_dim]
    values: torch.Tensor            # [batch_size] - value predictions
    logits: Optional[torch.Tensor]  # [batch_size, action_dim] - log probabilities


class BatchInferenceEngine:
    """
    Движок батч-инференса для ML агентов
    
    Оптимизации:
    - Предварительное выделение памяти
    - Градиенты отключены (no_grad)
    - AMP (Automatic Mixed Precision) для скорости
    - Кэширование промежуточных результатов
    """
    
    def __init__(
        self,
        policy,
        batch_size: int = 1024,
        device: str = "cpu",
        use_amp: bool = False
    ):
        """
        Args:
            policy: PyTorch политика (SB3 MultiInputPolicy)
            batch_size: Максимальный размер батча
            device: Устройство для инференса (cpu/cuda)
            use_amp: Использовать ли Automatic Mixed Precision
        """
        self.policy = policy
        self.batch_size = batch_size
        self.device = torch.device(device)
        self.use_amp = use_amp and device != "cpu"
        
        # Перемещение политики на устройство
        self.policy.to(self.device)
        self.policy.eval()  # Режим инференса
        
        # Предварительное выделение буферов
        self._image_buffer: Optional[torch.Tensor] = None
        self._vector_buffer: Optional[torch.Tensor] = None
        
    def predict_batch(
        self,
        observations: BatchObservation,
        deterministic: bool = True
    ) -> BatchActions:
        """
        Предсказать действия для батча обсерваций
        
        Args:
            observations: Пакет обсерваций
            deterministic: Если True, использовать детерминированную политику
            
        Returns:
            actions: Пакет действий
        """
        batch_size = observations.vectors.shape[0]
        
        # Разбиение на под-батчи если нужно
        if batch_size > self.batch_size:
            return self._predict_large_batch(observations, deterministic)
            
        with torch.no_grad():
            # Подготовка данных
            vectors = observations.vectors.to(self.device)
            
            if observations.images is not None:
                images = observations.images.to(self.device)
            else:
                images = None
                
            if observations.masks is not None:
                masks = observations.masks.to(self.device)
            else:
                masks = None
                
            # AMP контекст для ускорения
            if self.use_amp:
                with torch.autocast(device_type=self.device.type):
                    actions, values, logits = self._forward(images, vectors, masks)
            else:
                actions, values, logits = self._forward(images, vectors, masks)
                
            # Детерминизм vs сэмплирование
            if deterministic:
                if logits is not None:
                    actions = torch.argmax(logits, dim=-1)
                    
            # Перемещение обратно на CPU
            return BatchActions(
                actions=actions.cpu(),
                values=values.cpu(),
                logits=logits.cpu() if logits is not None else None
            )
            
    def _forward(
        self,
        images: Optional[torch.Tensor],
        vectors: torch.Tensor,
        masks: Optional[torch.Tensor]
    ) -> Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]:
        """
        Прямой проход через политику
        
        Returns:
            actions: Действия
            values: Value predictions
            logits: Log probabilities (для сэмплирования)
        """
        # SB3 MultiInputPolicy forward
        features = self.policy.extract_features(
            {"images": images, "vectors": vectors}
            if images is not None
            else {"vectors": vectors}
        )
        
        # Distribution forward
        distribution = self.policy.get_distribution(features)
        logits = distribution.distribution.logits if hasattr(distribution, 'distribution') else None
        
        # Сэмплирование или детерминизм
        actions = distribution.get_actions()
        
        # Value prediction
        values = self.policy.predict_values(features)
        
        # Применение масок действий (если есть)
        if masks is not None and logits is not None:
            masked_logits = logits + (1 - masks) * -1e9
            actions = torch.argmax(masked_logits, dim=-1)
            
        return actions, values.squeeze(-1), logits
        
    def _predict_large_batch(
        self,
        observations: BatchObservation,
        deterministic: bool
    ) -> BatchActions:
        """Обработка больших батчей по частям"""
        all_actions = []
        all_values = []
        all_logits = []
        
        for i in range(0, observations.vectors.shape[0], self.batch_size):
            end_idx = min(i + self.batch_size, observations.vectors.shape[0])
            
            # Срез батча
            batch_obs = BatchObservation(
                images=observations.images[i:end_idx] if observations.images is not None else None,
                vectors=observations.vectors[i:end_idx],
                masks=observations.masks[i:end_idx] if observations.masks is not None else None
            )
            
            # Рекурсивный вызов для под-батча
            result = self.predict_batch(batch_obs, deterministic)
            
            all_actions.append(result.actions)
            all_values.append(result.values)
            if result.logits is not None:
                all_logits.append(result.logits)
                
        # Конкатенация результатов
        return BatchActions(
            actions=torch.cat(all_actions, dim=0),
            values=torch.cat(all_values, dim=0),
            logits=torch.cat(all_logits, dim=0) if all_logits else None
        )
        
    def warmup(self, dummy_batch_size: int = 64):
        """
        Прогрев модели (предварительная компиляция графа)
        
        Args:
            dummy_batch_size: Размер тестового батча
        """
        print(f"Warming up inference engine with batch_size={dummy_batch_size}...")
        
        dummy_vectors = torch.randn(dummy_batch_size, 256)
        dummy_images = torch.randn(dummy_batch_size, 3, 64, 64)
        
        dummy_obs = BatchObservation(
            images=dummy_images,
            vectors=dummy_vectors,
            masks=None
        )
        
        # Несколько проходов для прогрева
        for _ in range(3):
            self.predict_batch(dummy_obs, deterministic=True)
            
        print("Inference engine warmed up!")
        
    def benchmark(
        self,
        batch_sizes: List[int] = [1, 16, 64, 256, 1024],
        num_iterations: int = 100
    ) -> Dict[int, float]:
        """
        Бенчмарк производительности
        
        Args:
            batch_sizes: Тестируемые размеры батчей
            num_iterations: Количество итераций для усреднения
            
        Returns:
            Dictionary {batch_size: avg_time_ms}
        """
        import time
        
        results = {}
        
        for batch_size in batch_sizes:
            vectors = torch.randn(batch_size, 256)
            images = torch.randn(batch_size, 3, 64, 64)
            
            obs = BatchObservation(
                images=images,
                vectors=vectors,
                masks=None
            )
            
            # Замер времени
            start = time.perf_counter()
            
            for _ in range(num_iterations):
                self.predict_batch(obs, deterministic=True)
                
            elapsed = time.perf_counter() - start
            avg_time_ms = (elapsed / num_iterations) * 1000
            
            results[batch_size] = avg_time_ms
            print(f"Batch size {batch_size}: {avg_time_ms:.3f} ms/step ({1000/avg_time_ms:.1f} steps/sec)")
            
        return results


def create_inference_engine(
    model_path: str,
    device: str = "cpu",
    batch_size: int = 1024
) -> BatchInferenceEngine:
    """
    Фабричная функция для создания inference engine
    
    Args:
        model_path: Путь к чекпоинту SB3
        device: Устройство для инференса
        batch_size: Максимальный размер батча
        
    Returns:
        BatchInferenceEngine готовый к использованию
    """
    from stable_baselines3 import PPO
    
    # Загрузка модели
    model = PPO.load(model_path, device=device)
    
    # Создание движка
    engine = BatchInferenceEngine(
        policy=model.policy,
        batch_size=batch_size,
        device=device
    )
    
    return engine
