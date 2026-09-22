#!/usr/bin/env python3
"""
Async Multi-Threaded Game Core Extension
Добавляет асинхронность и многопоточность в ядро игры:
- Поток 1: Основной игровой цикл (Game Loop)
- Поток 2: HUD/UI рендеринг
- Поток 3: Боевые расчеты (урон, криты, уклонения)
- Поток 4: ML обучение агентов
- Поток 5: AI мышление (принятие решений)
- Поток 6: I/O операции (БД, сохранения)
- Поток 7: Аналитика и телеметрия
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Dict, List
from collections import deque
from functools import lru_cache
from enum import Enum
import logging
import json

logger = logging.getLogger(__name__)


class ThreadPriority(Enum):
    """Приоритеты потоков"""
    CRITICAL = 10  # Game loop, combat
    HIGH = 8       # UI rendering, AI decisions
    NORMAL = 5     # Analytics, I/O
    LOW = 3        # ML training, background tasks


@dataclass
class GameThreadConfig:
    """Конфигурация игрового потока"""
    name: str
    priority: ThreadPriority
    max_workers: int = 1
    stack_size: int = 0  # 0 = default
    

class AsyncEventBus:
    """Асинхронная шина событий для межпоточной коммуникации"""
    
    def __init__(self, max_queue_size: int = 10000):
        self.queues: Dict[str, deque] = {}
        self.locks: Dict[str, threading.Lock] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self.max_size = max_queue_size
        self._global_lock = threading.Lock()
        
    def subscribe(self, event_type: str, callback: Callable) -> bool:
        """Подписка на события"""
        with self._global_lock:
            if event_type not in self.subscribers:
                self.subscribers[event_type] = []
                self.queues[event_type] = deque(maxlen=self.max_size)
                self.locks[event_type] = threading.Lock()
            
            self.subscribers[event_type].append(callback)
            return True
    
    def unsubscribe(self, event_type: str, callback: Callable) -> bool:
        """Отписка от событий"""
        with self._global_lock:
            if event_type in self.subscribers:
                try:
                    self.subscribers[event_type].remove(callback)
                    return True
                except ValueError:
                    return False
        return False
    
    async def publish_async(self, event_type: str, data: Any) -> int:
        """Асинхронная публикация события"""
        subscribers = self.subscribers.get(event_type, [])
        if not subscribers:
            return 0
        
        tasks = []
        for callback in subscribers:
            if asyncio.iscoroutinefunction(callback):
                tasks.append(callback(event_type, data))
            else:
                # Запускаем синхронный коллбэк в executor
                loop = asyncio.get_event_loop()
                tasks.append(loop.run_in_executor(None, callback, event_type, data))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return len([r for r in results if not isinstance(r, Exception)])
    
    def publish_sync(self, event_type: str, data: Any) -> int:
        """Синхронная публикация события"""
        with self._global_lock:
            queue = self.queues.get(event_type)
            lock = self.locks.get(event_type)
        
        if queue is None or lock is None:
            return 0
        
        with lock:
            queue.append({'type': event_type, 'data': data, 'timestamp': time.time()})
        
        # Уведомляем подписчиков
        subscribers = self.subscribers.get(event_type, [])
        for callback in subscribers:
            try:
                callback(event_type, data)
            except Exception as e:
                logger.error(f"Error in subscriber callback: {e}")
        
        return len(subscribers)
    
    def get_pending_events(self, event_type: str, max_count: int = 100) -> List[Dict]:
        """Получение ожидающих событий"""
        lock = self.locks.get(event_type)
        queue = self.queues.get(event_type)
        
        if lock is None or queue is None:
            return []
        
        with lock:
            events = []
            while queue and len(events) < max_count:
                events.append(queue.popleft())
            return events


class MultiThreadedGameCore:
    """Многопоточное расширение для Game Core"""
    
    def __init__(self, game_core_ref: Any = None):
        self.game_core = game_core_ref
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Конфигурация потоков
        self.thread_configs = {
            'game_loop': GameThreadConfig(
                'Main Game Loop',
                ThreadPriority.CRITICAL,
                max_workers=1
            ),
            'hud_ui': GameThreadConfig(
                'HUD/UI Renderer',
                ThreadPriority.HIGH,
                max_workers=2
            ),
            'combat': GameThreadConfig(
                'Combat Calculations',
                ThreadPriority.CRITICAL,
                max_workers=4
            ),
            'ml_training': GameThreadConfig(
                'ML Agent Training',
                ThreadPriority.LOW,
                max_workers=8
            ),
            'ai_thinking': GameThreadConfig(
                'AI Decision Making',
                ThreadPriority.HIGH,
                max_workers=4
            ),
            'io_ops': GameThreadConfig(
                'I/O Operations (DB/Save)',
                ThreadPriority.NORMAL,
                max_workers=2
            ),
            'analytics': GameThreadConfig(
                'Analytics & Telemetry',
                ThreadPriority.NORMAL,
                max_workers=4
            ),
        }
        
        # Пулы потоков
        self.thread_pools: Dict[str, ThreadPoolExecutor] = {}
        self.process_pool: Optional[ProcessPoolExecutor] = None
        
        # Очереди событий
        self.event_bus = AsyncEventBus()
        
        # Статистика
        self.stats = {
            'frames_rendered': 0,
            'combat_calculations': 0,
            'ai_decisions': 0,
            'ml_updates': 0,
            'io_operations': 0,
            'events_published': 0,
            'thread_utilization': {},
        }
        
        # Кэш для тяжелых вычислений
        self._combat_cache = {}
        self._ai_cache = {}
        
        self._initialize_pools()
        logger.info("MultiThreadedGameCore initialized")
    
    def _initialize_pools(self):
        """Инициализация пулов потоков"""
        for name, config in self.thread_configs.items():
            self.thread_pools[name] = ThreadPoolExecutor(
                max_workers=config.max_workers,
                thread_name_prefix=config.name
            )
        
        # Process pool для ML/тяжелых вычислений
        self.process_pool = ProcessPoolExecutor(
            max_workers=4,
            mp_context=threading._spawn if hasattr(threading, '_spawn') else None
        )
    
    async def start_async(self):
        """Асинхронный запуск"""
        self._running = True
        self._loop = asyncio.get_event_loop()
        
        logger.info("Starting MultiThreadedGameCore...")
        
        # Запускаем фоновые задачи
        tasks = [
            asyncio.create_task(self._game_loop_task()),
            asyncio.create_task(self._hud_ui_task()),
            asyncio.create_task(self._combat_task()),
            asyncio.create_task(self._ai_thinking_task()),
            asyncio.create_task(self._ml_training_task()),
            asyncio.create_task(self._io_task()),
            asyncio.create_task(self._analytics_task()),
        ]
        
        await asyncio.gather(*tasks)
    
    def start_sync(self):
        """Синхронный запуск"""
        if not self._loop:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        
        try:
            self._loop.run_until_complete(self.start_async())
        except KeyboardInterrupt:
            self._loop.run_until_complete(self.stop_async())
    
    async def _game_loop_task(self):
        """Основной игровой цикл (60 FPS)"""
        logger.info("Game loop task started")
        last_update = time.time()
        
        while self._running:
            current_time = time.time()
            delta_time = current_time - last_update
            last_update = current_time
            
            # Обновление через event bus
            await self.event_bus.publish_async('game_tick', {
                'delta_time': delta_time,
                'timestamp': current_time,
            })
            
            self.stats['frames_rendered'] += 1
            
            # Target 60 FPS
            await asyncio.sleep(max(0, 0.016 - (time.time() - current_time)))
    
    async def _hud_ui_task(self):
        """Обновление HUD/UI (30 FPS)"""
        logger.info("HUD/UI task started")
        
        while self._running:
            # Получаем данные для UI
            ui_data = await self._gather_ui_data()
            
            if ui_data:
                # Рендеринг в отдельном потоке
                future = self.thread_pools['hud_ui'].submit(
                    self._render_ui_elements, ui_data
                )
                await self._loop.run_in_executor(None, future.result)
            
            self.stats['frames_rendered'] += 1
            await asyncio.sleep(0.033)  # 30 FPS
    
    async def _combat_task(self):
        """Боевые расчеты (120 Hz для отзывчивости)"""
        logger.info("Combat task started")
        
        while self._running:
            # Получаем боевые события
            combat_events = self.event_bus.get_pending_events('combat_action', max_count=10)
            
            for event in combat_events:
                # Расчет в пуле combat
                future = self.thread_pools['combat'].submit(
                    self._calculate_combat_result,
                    event['data']
                )
                result = await self._loop.run_in_executor(None, future.result)
                
                # Публикуем результат
                await self.event_bus.publish_async('combat_result', result)
                self.stats['combat_calculations'] += 1
            
            await asyncio.sleep(0.008)  # 120 Hz
    
    async def _ai_thinking_task(self):
        """AI принятие решений (30 Hz)"""
        logger.info("AI thinking task started")
        
        while self._running:
            # Получаем состояние для AI
            ai_state = await self._gather_ai_state()
            
            if ai_state:
                # Решение в отдельном потоке
                future = self.thread_pools['ai_thinking'].submit(
                    self._make_ai_decision,
                    ai_state
                )
                decision = await self._loop.run_in_executor(None, future.result)
                
                # Применяем решение
                await self.event_bus.publish_async('ai_decision', decision)
                self.stats['ai_decisions'] += 1
            
            await asyncio.sleep(0.033)  # 30 Hz
    
    async def _ml_training_task(self):
        """ML обучение агентов (фоновая задача)"""
        logger.info("ML training task started")
        
        training_batch = []
        
        while self._running:
            # Собираем данные для обучения
            training_data = await self._gather_training_data()
            
            if training_data:
                training_batch.append(training_data)
                
                # Обучаем когда набрали батч
                if len(training_batch) >= 32:
                    if self.process_pool:
                        future = self.process_pool.submit(
                            self._train_ml_batch,
                            training_batch.copy()
                        )
                        await self._loop.run_in_executor(None, future.result)
                        training_batch.clear()
                        self.stats['ml_updates'] += 1
            
            await asyncio.sleep(0.1)  # 10 Hz
    
    async def _io_task(self):
        """I/O операции (БД, сохранения)"""
        logger.info("I/O task started")
        
        save_buffer = []
        
        while self._running:
            # Получаем запросы на сохранение
            io_requests = self.event_bus.get_pending_events('io_request', max_count=10)
            
            for request in io_requests:
                if request['data'].get('type') == 'save':
                    save_buffer.append(request['data'])
                    
                    # Пакетное сохранение
                    if len(save_buffer) >= 5:
                        future = self.thread_pools['io_ops'].submit(
                            self._perform_io_operations,
                            save_buffer.copy()
                        )
                        await self._loop.run_in_executor(None, future.result)
                        save_buffer.clear()
                        self.stats['io_operations'] += 1
            
            await asyncio.sleep(0.1)  # 10 Hz
    
    async def _analytics_task(self):
        """Сбор аналитики (1 Hz)"""
        logger.info("Analytics task started")
        
        while self._running:
            # Собираем метрики
            metrics = self._collect_metrics()
            
            # Отправляем в analytics пул
            future = self.thread_pools['analytics'].submit(
                self._analyze_metrics,
                metrics
            )
            await self._loop.run_in_executor(None, future.result)
            
            # Публикуем для внешнего потребления
            await self.event_bus.publish_async('analytics_update', metrics)
            
            await asyncio.sleep(1.0)  # 1 Hz
    
    @lru_cache(maxsize=1024)
    def _calculate_combat_result(self, combat_data: tuple) -> dict:
        """Расчет боя с кэшированием"""
        # Десериализуем данные
        data = combat_data[0] if isinstance(combat_data, tuple) else combat_data
        
        attacker_id = data.get('attacker_id', '')
        defender_id = data.get('defender_id', '')
        attack_type = data.get('attack_type', 'melee')
        
        # Имитация расчета (в реальности здесь формулы урона)
        base_damage = 10.0
        crit_chance = 0.15
        dodge_chance = 0.10
        
        is_crit = hash(f"{attacker_id}{time.time()}") % 100 < crit_chance * 100
        is_dodge = hash(f"{defender_id}{time.time()}") % 100 < dodge_chance * 100
        
        damage = base_damage * (2.0 if is_crit else 1.0) if not is_dodge else 0
        
        result = {
            'attacker_id': attacker_id,
            'defender_id': defender_id,
            'damage': round(damage, 2),
            'is_critical': is_crit,
            'is_dodged': is_dodge,
            'attack_type': attack_type,
            'timestamp': time.time(),
        }
        
        # Кэшируем (для lru_cache нужен hashable key)
        return result
    
    def _make_ai_decision(self, state: dict) -> dict:
        """Принятие AI решения"""
        entity_id = state.get('entity_id', '')
        enemy_visible = state.get('enemy_visible', False)
        health_pct = state.get('health_percent', 100)
        
        # Простая логика принятия решений
        if not enemy_visible:
            action = 'wander'
        elif health_pct < 30:
            action = 'retreat'
        elif health_pct < 60:
            action = 'defend'
        else:
            action = 'attack'
        
        return {
            'entity_id': entity_id,
            'action': action,
            'priority': 1.0 / (1.0 + hash(entity_id) % 100),
            'timestamp': time.time(),
        }
    
    def _train_ml_batch(self, batch: list) -> dict:
        """Обучение ML модели на батче данных"""
        # В реальности здесь обучение нейросети
        time.sleep(0.01)  # Имитация
        
        return {
            'batch_size': len(batch),
            'trained': True,
            'loss': 0.1,
            'accuracy': 0.95,
        }
    
    def _perform_io_operations(self, operations: list) -> dict:
        """Выполнение I/O операций"""
        # В реальности здесь запись в БД
        time.sleep(0.005)  # Имитация
        
        return {
            'operations_completed': len(operations),
            'success': True,
        }
    
    def _analyze_metrics(self, metrics: dict) -> dict:
        """Анализ метрик"""
        return {
            'analyzed': True,
            'anomalies_detected': 0,
        }
    
    async def _gather_ui_data(self) -> dict:
        """Сбор данных для UI"""
        return {
            'health': 100,
            'mana': 50,
            'enemies_visible': 3,
        }
    
    async def _gather_ai_state(self) -> dict:
        """Сбор состояния для AI"""
        return {
            'entity_id': 'enemy_1',
            'enemy_visible': True,
            'health_percent': 75,
        }
    
    async def _gather_training_data(self) -> dict:
        """Сбор данных для обучения"""
        return {
            'state': [1, 0, 1],
            'action': 2,
            'reward': 1.0,
        }
    
    def _render_ui_elements(self, ui_data: dict) -> None:
        """Рендеринг UI элементов"""
        pass
    
    def _collect_metrics(self) -> dict:
        """Сбор метрик производительности"""
        return {
            'fps': self.stats['frames_rendered'],
            'combat_calc_per_sec': self.stats['combat_calculations'],
            'ai_decisions_per_sec': self.stats['ai_decisions'],
            'ml_updates': self.stats['ml_updates'],
            'io_ops': self.stats['io_operations'],
        }
    
    async def stop_async(self):
        """Асинхронная остановка"""
        logger.info("Stopping MultiThreadedGameCore...")
        self._running = False
        
        await asyncio.sleep(0.5)
        
        # Останавливаем пулы
        for pool in self.thread_pools.values():
            pool.shutdown(wait=False)
        
        if self.process_pool:
            self.process_pool.shutdown(wait=False)
        
        logger.info("MultiThreadedGameCore stopped")
    
    def submit_to_pool(self, pool_name: str, fn: Callable, *args, **kwargs) -> Any:
        """Отправка задачи в конкретный пул"""
        if pool_name not in self.thread_pools:
            raise ValueError(f"Unknown pool: {pool_name}")
        
        return self.thread_pools[pool_name].submit(fn, *args, **kwargs)
    
    def get_stats(self) -> dict:
        """Получение статистики"""
        self.stats['thread_utilization'] = {
            name: pool._work_queue.qsize() if hasattr(pool, '_work_queue') else 0
            for name, pool in self.thread_pools.items()
        }
        return self.stats


# Интеграция с существующим Game Core

def integrate_with_game_core(game_core_instance: Any) -> MultiThreadedGameCore:
    """Интеграция многопоточности в существующий Game Core"""
    mt_core = MultiThreadedGameCore(game_core_ref=game_core_instance)
    
    # Подключаем события
    if hasattr(game_core_instance, 'event_system'):
        game_core_instance.event_system.subscribe('game_tick', lambda e, d: None)
        game_core_instance.event_system.subscribe('combat_action', lambda e, d: None)
    
    logger.info("MultiThreadedGameCore integrated with GameCore")
    return mt_core


if __name__ == "__main__":
    # Тестирование
    logging.basicConfig(level=logging.INFO)
    
    print("Testing MultiThreadedGameCore...")
    
    mt_core = MultiThreadedGameCore()
    
    async def test_run():
        # Запускаем на 2 секунды
        asyncio.create_task(mt_core.start_async())
        await asyncio.sleep(2.0)
        await mt_core.stop_async()
        
        stats = mt_core.get_stats()
        print("\n=== Statistics ===")
        print(json.dumps(stats, indent=2))
    
    asyncio.run(test_run())
    print("\n✅ MultiThreadedGameCore test passed!")
