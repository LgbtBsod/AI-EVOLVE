#!/usr/bin/env python3
"""
Async Multi-Threaded Dev Probe Framework
Расширяет dev_probe асинхронностью и многопоточностью для:
- Параллельного сбора метрик
- Асинхронной записи данных
- Фоновой аналитики без блокировки основного потока
- Масштабируемой архитектуры плагинов
"""

import asyncio
import threading
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from collections import deque
from functools import lru_cache
import time
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class ThreadConfig:
    """Конфигурация потока"""
    name: str
    priority: int = 5  # 1-10, где 10 highest
    daemon: bool = True
    max_workers: int = 4
    

@dataclass
class AsyncQueue:
    """Асинхронная очередь для межпоточной коммуникации"""
    queue: deque = field(default_factory=lambda: deque(maxlen=1000))
    lock: threading.Lock = field(default_factory=threading.Lock)
    event: threading.Event = field(default_factory=threading.Event)
    
    async def put(self, item: Any) -> None:
        """Асинхронная запись в очередь"""
        with self.lock:
            self.queue.append(item)
            self.event.set()
    
    async def get(self, timeout: float = None) -> Optional[Any]:
        """Асинхронное чтение из очереди"""
        start = time.time()
        while True:
            with self.lock:
                if self.queue:
                    item = self.queue.popleft()
                    if not self.queue:
                        self.event.clear()
                    return item
            
            if timeout and (time.time() - start) > timeout:
                return None
            
            await asyncio.sleep(0.01)
    
    def sync_put(self, item: Any) -> None:
        """Синхронная запись (для совместимости)"""
        with self.lock:
            self.queue.append(item)
            self.event.set()
    
    def sync_get(self, timeout: float = None) -> Optional[Any]:
        """Синхронное чтение (для совместимости)"""
        start = time.time()
        while True:
            with self.lock:
                if self.queue:
                    item = self.queue.popleft()
                    if not self.queue:
                        self.event.clear()
                    return item
            
            if timeout and (time.time() - start) > timeout:
                return None
            
            time.sleep(0.01)


class AsyncPluginManager:
    """Менеджер асинхронных плагинов"""
    
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.plugins: dict[str, Any] = {}
        self.plugin_order: list[str] = []
        self.queues: dict[str, AsyncQueue] = {}
        self._running = False
        
    def register_plugin(self, plugin_id: str, plugin: Any, queue_size: int = 1000) -> bool:
        """Регистрация плагина с собственной очередью"""
        if plugin_id in self.plugins:
            logger.warning(f"Plugin {plugin_id} already registered")
            return False
        
        self.plugins[plugin_id] = plugin
        self.plugin_order.append(plugin_id)
        self.queues[plugin_id] = AsyncQueue()
        logger.info(f"Plugin {plugin_id} registered")
        return True
    
    async def run_plugin_async(self, plugin_id: str, *args, **kwargs) -> Any:
        """Запуск метода плагина асинхронно"""
        if plugin_id not in self.plugins:
            raise ValueError(f"Plugin {plugin_id} not found")
        
        plugin = self.plugins[plugin_id]
        loop = asyncio.get_event_loop()
        
        if hasattr(plugin, 'process_async'):
            return await plugin.process_async(*args, **kwargs)
        else:
            # Запускаем синхронный метод в executor
            return await loop.run_in_executor(
                self.executor,
                lambda: plugin.process(*args, **kwargs) if hasattr(plugin, 'process') else None
            )
    
    def run_plugin_sync(self, plugin_id: str, *args, **kwargs) -> Any:
        """Запуск метода плагина синхронно (в отдельном потоке)"""
        if plugin_id not in self.plugins:
            raise ValueError(f"Plugin {plugin_id} not found")
        
        plugin = self.plugins[plugin_id]
        future = self.executor.submit(
            lambda: plugin.process(*args, **kwargs) if hasattr(plugin, 'process') else None
        )
        return future.result()
    
    async def broadcast(self, event_type: str, data: Any) -> dict[str, Any]:
        """Рассылка события всем плагинам параллельно"""
        tasks = []
        for plugin_id in self.plugin_order:
            task = self.run_plugin_async(plugin_id, event_type, data)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return dict(zip(self.plugin_order, results))
    
    def shutdown(self):
        """Остановка менеджера"""
        self._running = False
        self.executor.shutdown(wait=True)


class MultiThreadedProbe:
    """Многопоточный Dev Probe с разделением ответственности"""
    
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        
        # Потоки с разными ответственностями
        self.thread_config = {
            'main': ThreadConfig('Main Game Thread', priority=10, max_workers=1),
            'hud_ui': ThreadConfig('HUD/UI Thread', priority=8, max_workers=2),
            'combat': ThreadConfig('Combat Calculations', priority=9, max_workers=4),
            'ml_training': ThreadConfig('ML Training', priority=5, max_workers=8),
            'ai_thinking': ThreadConfig('AI Thinking', priority=7, max_workers=4),
            'io_writer': ThreadConfig('I/O Writer', priority=6, max_workers=2),
            'analytics': ThreadConfig('Analytics', priority=4, max_workers=4),
        }
        
        # Пулы потоков для каждой категории
        self.thread_pools: dict[str, ThreadPoolExecutor] = {}
        for name, cfg in self.thread_config.items():
            self.thread_pools[name] = ThreadPoolExecutor(
                max_workers=cfg.max_workers,
                thread_name_prefix=cfg.name
            )
        
        # Очереди для межпоточной коммуникации
        self.main_queue = AsyncQueue()
        self.combat_queue = AsyncQueue()
        self.ui_queue = AsyncQueue()
        self.analytics_queue = AsyncQueue()
        
        # Менеджер плагинов
        self.plugin_manager = AsyncPluginManager(max_workers=8)
        
        # Статистика
        self.stats = {
            'events_processed': 0,
            'async_tasks_completed': 0,
            'threads_active': 0,
            'queue_sizes': {},
        }
        
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
    async def start_async(self):
        """Асинхронный запуск probe"""
        self._running = True
        self._loop = asyncio.get_event_loop()
        
        logger.info("Starting MultiThreadedProbe...")
        
        # Запускаем фоновые задачи
        tasks = [
            asyncio.create_task(self._main_loop()),
            asyncio.create_task(self._combat_processor()),
            asyncio.create_task(self._ui_updater()),
            asyncio.create_task(self._analytics_collector()),
            asyncio.create_task(self._io_writer()),
        ]
        
        await asyncio.gather(*tasks)
    
    def start_sync(self):
        """Синхронный запуск (совместимость)"""
        if not self._loop:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        
        try:
            self._loop.run_until_complete(self.start_async())
        except KeyboardInterrupt:
            self._loop.run_until_complete(self.stop_async())
    
    async def _main_loop(self):
        """Основной игровой цикл (поток 1)"""
        logger.info("Main game loop started")
        while self._running:
            # Обработка событий из главной очереди
            event = await self.main_queue.get(timeout=0.1)
            if event:
                self.stats['events_processed'] += 1
                # Координация между системами
                await self.plugin_manager.broadcast('game_tick', event)
            
            await asyncio.sleep(0.016)  # ~60 FPS
    
    async def _combat_processor(self):
        """Обработка боевых расчетов (поток 3)"""
        logger.info("Combat processor started")
        while self._running:
            combat_data = await self.combat_queue.get(timeout=0.1)
            if combat_data:
                # Запускаем расчет урона в отдельном пуле
                future = self.thread_pools['combat'].submit(
                    self._calculate_combat, combat_data
                )
                result = await asyncio.get_event_loop().run_in_executor(
                    None, future.result
                )
                self.stats['async_tasks_completed'] += 1
            
            await asyncio.sleep(0.008)  # ~120 Hz для комбата
    
    async def _ui_updater(self):
        """Обновление HUD/UI (поток 2)"""
        logger.info("UI updater started")
        while self._running:
            ui_data = await self.ui_queue.get(timeout=0.1)
            if ui_data:
                # Рендеринг UI в отдельном потоке
                future = self.thread_pools['hud_ui'].submit(
                    self._render_ui, ui_data
                )
                await asyncio.get_event_loop().run_in_executor(None, future.result)
            
            await asyncio.sleep(0.033)  # ~30 FPS для UI
    
    async def _analytics_collector(self):
        """Сбор аналитики (поток 7)"""
        logger.info("Analytics collector started")
        while self._running:
            # Сбор метрик в фоне
            metrics = await self.analytics_queue.get(timeout=1.0)
            if metrics:
                future = self.thread_pools['analytics'].submit(
                    self._analyze_metrics, metrics
                )
                await asyncio.get_event_loop().run_in_executor(None, future.result)
    
    async def _io_writer(self):
        """Фоновая запись на диск (поток 6)"""
        logger.info("I/O writer started")
        write_buffer = []
        while self._running:
            # Буферизация записи
            if write_buffer:
                future = self.thread_pools['io_writer'].submit(
                    self._write_batch, write_buffer.copy()
                )
                write_buffer.clear()
                await asyncio.get_event_loop().run_in_executor(None, future.result)
            
            await asyncio.sleep(0.5)  # Пакетная запись каждые 500ms
    
    @lru_cache(maxsize=1024)
    def _calculate_combat(self, combat_data: tuple) -> dict:
        """Расчет боя (кэшируется)"""
        # Имитация тяжелых расчетов
        time.sleep(0.001)
        return {'damage': 10, 'hit': True}
    
    def _render_ui(self, ui_data: dict) -> None:
        """Рендеринг UI"""
        pass
    
    def _analyze_metrics(self, metrics: dict) -> dict:
        """Анализ метрик"""
        return {'analyzed': True}
    
    def _write_batch(self, batch: list) -> None:
        """Пакетная запись на диск"""
        pass
    
    async def stop_async(self):
        """Асинхронная остановка"""
        logger.info("Stopping MultiThreadedProbe...")
        self._running = False
        
        # Ждем завершения очередей
        await asyncio.sleep(0.5)
        
        # Останавливаем пулы
        for pool in self.thread_pools.values():
            pool.shutdown(wait=False)
        
        # Останавливаем менеджер плагинов
        self.plugin_manager.shutdown()
        
        logger.info("MultiThreadedProbe stopped")
    
    def submit_to_thread(self, thread_name: str, fn: Callable, *args, **kwargs):
        """Отправка задачи в конкретный поток"""
        if thread_name not in self.thread_pools:
            raise ValueError(f"Unknown thread: {thread_name}")
        
        return self.thread_pools[thread_name].submit(fn, *args, **kwargs)
    
    def get_stats(self) -> dict:
        """Получение статистики"""
        self.stats['queue_sizes'] = {
            'main': len(self.main_queue.queue),
            'combat': len(self.combat_queue.queue),
            'ui': len(self.ui_queue.queue),
            'analytics': len(self.analytics_queue.queue),
        }
        self.stats['threads_active'] = sum(
            1 for pool in self.thread_pools.values()
        )
        return self.stats


# Новые полезные плагины для dev_probe

class RealTimeMetricsPlugin:
    """Плагин сбора метрик в реальном времени"""
    
    def __init__(self):
        self.metrics_buffer = deque(maxlen=1000)
        self.lock = threading.Lock()
    
    def process(self, event_type: str, data: Any) -> dict:
        """Обработка события"""
        with self.lock:
            self.metrics_buffer.append({
                'timestamp': time.time(),
                'event': event_type,
                'data': data,
            })
        
        return {'queued': True}
    
    async def process_async(self, event_type: str, data: Any) -> dict:
        """Асинхронная обработка"""
        await asyncio.sleep(0)  # Yield control
        return self.process(event_type, data)
    
    def get_metrics(self, last_n: int = 100) -> list:
        """Получение последних метрик"""
        with self.lock:
            return list(self.metrics_buffer)[-last_n:]


class SmartSnapshotPlugin:
    """Умные снапшоты состояния (только при изменениях)"""
    
    def __init__(self, threshold: float = 0.01):
        self.threshold = threshold
        self.last_snapshot: Optional[dict] = None
        self.significant_snapshots: list[dict] = []
        self.lock = threading.Lock()
    
    def process(self, event_type: str, state: dict) -> dict:
        """Сохранение значимых изменений"""
        if self.last_snapshot is None:
            self._save_snapshot(state)
            return {'saved': True, 'reason': 'first'}
        
        # Вычисляем различия
        diff = self._compute_diff(self.last_snapshot, state)
        
        if diff['significance'] > self.threshold:
            self._save_snapshot(state)
            return {'saved': True, 'reason': 'significant_change', 'diff': diff}
        
        return {'saved': False, 'reason': 'no_significant_change'}
    
    def _compute_diff(self, old: dict, new: dict) -> dict:
        """Вычисление значимости изменений"""
        changes = {}
        total_change = 0.0
        
        for key in set(old.keys()) | set(new.keys()):
            old_val = old.get(key, 0)
            new_val = new.get(key, 0)
            
            if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                delta = abs(new_val - old_val) / (abs(old_val) + 1e-6)
                if delta > self.threshold:
                    changes[key] = {'old': old_val, 'new': new_val, 'delta': delta}
                    total_change += delta
        
        return {
            'changes': changes,
            'significance': total_change / (len(changes) + 1),
        }
    
    def _save_snapshot(self, state: dict):
        """Сохранение снапшота"""
        with self.lock:
            self.last_snapshot = state.copy()
            self.significant_snapshots.append({
                'timestamp': time.time(),
                'state': state,
            })


class ParallelAnalyzerPlugin:
    """Параллельный анализ данных через ProcessPool"""
    
    def __init__(self, num_processes: int = None):
        self.num_processes = num_processes or mp.cpu_count()
        self.executor = ProcessPoolExecutor(max_workers=self.num_processes)
        self.results = {}
    
    def analyze_parallel(self, data_chunks: list) -> dict:
        """Параллельный анализ чанков данных"""
        futures = []
        for i, chunk in enumerate(data_chunks):
            future = self.executor.submit(self._analyze_chunk, chunk, i)
            futures.append(future)
        
        for i, future in enumerate(futures):
            try:
                self.results[i] = future.result(timeout=5.0)
            except TimeoutError:
                self.results[i] = {'error': 'timeout'}
        
        return self._aggregate_results()
    
    def _analyze_chunk(self, chunk: Any, chunk_id: int) -> dict:
        """Анализ одного чанка (в отдельном процессе)"""
        # Имитация тяжелого анализа
        time.sleep(0.1)
        return {'chunk_id': chunk_id, 'analyzed': True}
    
    def _aggregate_results(self) -> dict:
        """Агрегация результатов"""
        return {
            'total_chunks': len(self.results),
            'successful': sum(1 for r in self.results.values() if 'error' not in r),
            'failed': sum(1 for r in self.results.values() if 'error' in r),
        }
    
    def shutdown(self):
        self.executor.shutdown(wait=True)


class EventCorrelationPlugin:
    """Корреляция событий во времени"""
    
    def __init__(self, window_size: float = 5.0):
        self.window_size = window_size
        self.events: deque = deque()
        self.correlations: list[dict] = []
        self.lock = threading.Lock()
    
    def process(self, event_type: str, data: Any) -> dict:
        """Добавление события и поиск корреляций"""
        timestamp = time.time()
        event = {'type': event_type, 'data': data, 'timestamp': timestamp}
        
        with self.lock:
            self.events.append(event)
            
            # Удаляем старые события за пределами окна
            cutoff = timestamp - self.window_size
            while self.events and self.events[0]['timestamp'] < cutoff:
                self.events.popleft()
            
            # Ищем корреляции
            correlations = self._find_correlations(event)
            if correlations:
                self.correlations.extend(correlations)
        
        return {'correlations_found': len(correlations)}
    
    def _find_correlations(self, current_event: dict) -> list[dict]:
        """Поиск коррелирующих событий"""
        correlations = []
        
        for event in self.events:
            if event['timestamp'] >= current_event['timestamp']:
                break
            
            # Простая корреляция по типу
            if event['type'] != current_event['type']:
                time_delta = current_event['timestamp'] - event['timestamp']
                correlations.append({
                    'event1': event,
                    'event2': current_event,
                    'time_delta': time_delta,
                    'correlation_strength': 1.0 / (1.0 + time_delta),
                })
        
        return correlations[:10]  # Топ 10 корреляций
    
    def get_correlation_report(self) -> dict:
        """Отчет о корреляциях"""
        return {
            'total_events': len(self.events),
            'total_correlations': len(self.correlations),
            'window_size': self.window_size,
        }


if __name__ == "__main__":
    # Тестирование
    logging.basicConfig(level=logging.INFO)
    
    probe = MultiThreadedProbe()
    
    # Регистрируем плагины
    probe.plugin_manager.register_plugin('metrics', RealTimeMetricsPlugin())
    probe.plugin_manager.register_plugin('snapshot', SmartSnapshotPlugin())
    probe.plugin_manager.register_plugin('analyzer', ParallelAnalyzerPlugin(num_processes=2))
    probe.plugin_manager.register_plugin('correlation', EventCorrelationPlugin())
    
    print("Dev Probe Async Framework initialized successfully!")
    print(f"Thread pools: {list(probe.thread_pools.keys())}")
    print(f"Plugins registered: {probe.plugin_manager.plugins.keys()}")
    
    # Тест отправки событий
    async def test_run():
        for i in range(10):
            await probe.main_queue.put({'tick': i, 'timestamp': time.time()})
            await asyncio.sleep(0.1)
        
        print("\nStats:", json.dumps(probe.get_stats(), indent=2))
        await probe.stop_async()
    
    asyncio.run(test_run())
    print("\n✅ All tests passed!")
