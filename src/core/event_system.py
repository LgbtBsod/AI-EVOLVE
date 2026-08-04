#!/usr/bin/env python3
"""Система событий - централизованное управление событиями игры

Refactored: 
- Убрано O(n²) поведение в _event_processing_loop (max + remove заменены на heapq)
- Добавлены type hints (Python 3.10+)
- time.time() заменен на time.perf_counter() для точности
- dataclass добавлен slots=True для оптимизации памяти
- Убраны дублирующиеся методы (emit/emit_event, on/subscribe)
"""

from __future__ import annotations

import logging
import threading
import time
import heapq
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# ТИПЫ СОБЫТИЙ
# ============================================================================

class EventType(Enum):
    """Типы событий"""
    SYSTEM = "system"
    GAME = "game"
    UI = "ui"
    AUDIO = "audio"
    NETWORK = "network"
    DEBUG = "debug"


class EventPriority(Enum):
    """Приоритеты событий (обратный порядок для heapq)"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EventState(Enum):
    """Состояния событий"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============================================================================
# СТРУКТУРЫ ДАННЫХ
# ============================================================================

@dataclass(slots=True)
class Event:
    """Событие (оптимизировано с __slots__)"""
    event_id: str
    event_type: str
    event_data: Dict[str, Any]
    source: str
    timestamp: float = field(default_factory=time.perf_counter)
    priority: EventPriority = EventPriority.NORMAL
    state: EventState = EventState.PENDING
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    
    def __lt__(self, other: 'Event') -> bool:
        """Сравнение для heapq (больший приоритет = меньшее значение)"""
        return self.priority.value > other.priority.value


@dataclass(slots=True)
class EventHandler:
    """Обработчик события (оптимизировано с __slots__)"""
    handler_id: str
    handler_func: Callable[[Event], None]
    event_types: List[str]
    priority: EventPriority = EventPriority.NORMAL
    is_active: bool = True
    last_called: float = 0.0
    call_count: int = 0
    error_count: int = 0


@dataclass(slots=True)
class EventSubscription:
    """Подписка на событие (оптимизировано с __slots__)"""
    subscriber_id: str
    event_type: str
    handler: Callable[[Event], None]
    priority: EventPriority = EventPriority.NORMAL
    is_active: bool = True
    created_at: float = field(default_factory=time.perf_counter)


@dataclass
class EventStats:
    """Статистика системы событий"""
    events_processed: int = 0
    events_failed: int = 0
    handlers_registered: int = 0
    subscriptions_active: int = 0


# ============================================================================
# СИСТЕМА СОБЫТИЙ
# ============================================================================

class EventSystem:
    """
    Система событий с оптимизированной очередью приоритетов.
    
    Изменения:
    - heapq вместо list + max() + remove() для O(log n) операций
    - Deque для истории вместо List
    - Type hints для всех методов
    """
    
    def __init__(self, max_history_size: int = 1000) -> None:
        self._event_handlers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._event_queue: List[Event] = []  # heapq priority queue
        self._subscriptions: Dict[str, List[EventSubscription]] = defaultdict(list)
        self._event_history: Deque[Event] = deque(maxlen=max_history_size)
        self._is_running = False
        self._processing_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        self._stats = EventStats()
        
        logger.info("EventSystem инициализирована")
    
    def initialize(self) -> bool:
        """Инициализация системы событий"""
        try:
            self._is_running = True
            self._processing_thread = threading.Thread(
                target=self._event_processing_loop, 
                daemon=True,
                name="EventProcessingThread"
            )
            self._processing_thread.start()
            logger.info("EventSystem успешно инициализирована")
            return True
        except Exception as e:
            logger.exception("Ошибка инициализации EventSystem: %s", e)
            return False
    
    def shutdown(self) -> bool:
        """Завершение работы системы событий"""
        try:
            self._is_running = False
            if self._processing_thread and self._processing_thread.is_alive():
                self._processing_thread.join(timeout=5.0)
            logger.info("EventSystem успешно завершена")
            return True
        except Exception as e:
            logger.exception("Ошибка завершения EventSystem: %s", e)
            return False
    
    def emit(
        self, 
        event_type: str, 
        event_data: Dict[str, Any], 
        source: str = "system",
        priority: EventPriority = EventPriority.NORMAL
    ) -> bool:
        """Отправка события в очередь (O(log n))"""
        try:
            event = Event(
                event_id=f"{event_type}_{int(time.perf_counter() * 1000)}",
                event_type=event_type,
                event_data=event_data,
                source=source,
                priority=priority
            )
            
            with self._lock:
                heapq.heappush(self._event_queue, event)
                self._event_history.append(event)
            
            logger.debug("Событие %s добавлено в очередь от %s", event_type, source)
            return True
            
        except Exception as e:
            logger.exception("Ошибка отправки события %s: %s", event_type, e)
            return False
    
    def on(
        self, 
        event_type: str, 
        handler: Callable[[Event], None], 
        subscriber_id: str = "unknown",
        priority: EventPriority = EventPriority.NORMAL
    ) -> bool:
        """Подписка на событие"""
        try:
            subscription = EventSubscription(
                subscriber_id=subscriber_id,
                event_type=event_type,
                handler=handler,
                priority=priority
            )
            
            with self._lock:
                self._subscriptions[event_type].append(subscription)
                self._stats.subscriptions_active += 1
            
            logger.debug("Подписка на %s от %s", event_type, subscriber_id)
            return True
            
        except Exception as e:
            logger.exception("Ошибка подписки на %s: %s", event_type, e)
            return False
    
    def off(self, event_type: str, subscriber_id: str) -> bool:
        """Отписка от события"""
        try:
            with self._lock:
                if event_type in self._subscriptions:
                    self._subscriptions[event_type] = [
                        sub for sub in self._subscriptions[event_type]
                        if sub.subscriber_id != subscriber_id
                    ]
                    self._stats.subscriptions_active = sum(
                        1 for subs in self._subscriptions.values()
                        for sub in subs if sub.is_active
                    )
            
            logger.debug("Отписка от %s для %s", event_type, subscriber_id)
            return True
            
        except Exception as e:
            logger.exception("Ошибка отписки от %s: %s", event_type, e)
            return False
    
    def subscribe(
        self, 
        event_type: str, 
        handler: Callable[[Event], None], 
        subscriber_id: str = "unknown",
        priority: EventPriority = EventPriority.NORMAL
    ) -> bool:
        """Alias для on()"""
        return self.on(event_type, handler, subscriber_id, priority)
    
    def unsubscribe(self, event_type: str, subscriber_id: str) -> bool:
        """Alias для off()"""
        return self.off(event_type, subscriber_id)
    
    def _event_processing_loop(self) -> None:
        """Основной цикл обработки событий (O(log n) вместо O(n²))"""
        while self._is_running:
            try:
                event: Optional[Event] = None
                
                with self._lock:
                    if self._event_queue:
                        # heapq.heappop() - O(log n) вместо O(n) для max() + remove()
                        event = heapq.heappop(self._event_queue)
                
                if event:
                    if self._process_single_event(event):
                        self._stats.events_processed += 1
                    else:
                        self._stats.events_failed += 1
                else:
                    time.sleep(0.001)
                    
            except Exception as e:
                logger.exception("Ошибка в цикле обработки событий: %s", e)
                time.sleep(0.1)
    
    def _process_single_event(self, event: Event) -> bool:
        """Обработка одного события"""
        try:
            event.state = EventState.PROCESSING
            
            subscriptions = self._subscriptions.get(event.event_type, [])
            
            if not subscriptions:
                event.state = EventState.COMPLETED
                return True
            
            # Сортируем по приоритету (высокий приоритет первым)
            sorted_subs = sorted(
                (s for s in subscriptions if s.is_active),
                key=lambda s: s.priority.value,
                reverse=True
            )
            
            success_count = 0
            for subscription in sorted_subs:
                try:
                    subscription.handler(event)
                    subscription.last_called = time.perf_counter()
                    subscription.call_count += 1
                    success_count += 1
                    
                except Exception as e:
                    subscription.error_count += 1
                    logger.exception(
                        "Ошибка в обработчике %s для %s: %s",
                        subscription.subscriber_id, 
                        event.event_type, 
                        e
                    )
            
            event.state = EventState.COMPLETED if success_count > 0 else EventState.FAILED
            return success_count > 0
                
        except Exception as e:
            event.state = EventState.FAILED
            event.error_message = str(e)
            logger.exception("Ошибка обработки события %s: %s", event.event_type, e)
            return False
    
    def process_events(self, max_events: int = 100) -> int:
        """Обработка событий в текущем потоке (для тестов)"""
        processed = 0
        while self._event_queue and processed < max_events:
            event = None
            with self._lock:
                if self._event_queue:
                    event = heapq.heappop(self._event_queue)
            
            if event and self._process_single_event(event):
                processed += 1
        
        return processed
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики системы"""
        with self._lock:
            return {
                'events_processed': self._stats.events_processed,
                'events_failed': self._stats.events_failed,
                'handlers_registered': self._stats.handlers_registered,
                'subscriptions_active': self._stats.subscriptions_active,
                'queue_size': len(self._event_queue),
                'history_size': len(self._event_history),
                'is_running': self._is_running
            }
    
    def clear_history(self) -> None:
        """Очистка истории событий"""
        with self._lock:
            self._event_history.clear()
            logger.info("История событий очищена")
    
    def get_event_history(
        self, 
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Event]:
        """Получение истории событий"""
        with self._lock:
            if event_type:
                filtered_events = [
                    e for e in self._event_history 
                    if e.event_type == event_type
                ]
            else:
                filtered_events = list(self._event_history)
            
            return filtered_events[-limit:]
