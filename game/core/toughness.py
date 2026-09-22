"""
Компонент стойкости (Toughness).
Реализует механику как в HSR/BNS:
- Полоска стойкости у врагов
- При полном истощении - состояние BREAK (оглушение + повышенный урон)
- Постепенное восстановление
"""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import time


class ToughnessState(Enum):
    """Состояния стойкости"""
    NORMAL = "normal"           # Обычное состояние
    WEAKENED = "weakened"       # Стойкость ниже 50% (опционально)
    BROKEN = "broken"           # Стойкость на 0, враг оглушен
    RECOVERING = "recovering"   # Восстановление после BREAK


@dataclass
class ToughnessConfig:
    """Конфигурация системы стойкости для сущности"""
    max_toughness: float = 100.0
    recovery_rate: float = 10.0        # Единиц в секунду
    recovery_delay: float = 3.0        # Задержка перед началом восстановления после удара
    break_duration: float = 5.0        # Длительность состояния BREAK
    weakened_threshold: float = 0.5    # Порог для состояния WEAKENED (50%)
    
    # Множители
    damage_reduction_normal: float = 0.0    # Снижение урона в нормальном состоянии (0%)
    damage_reduction_weakened: float = 0.0  # Снижение урона в ослабленном (0%)
    damage_taken_multiplier_broken: float = 0.25  # +25% получаемого урона в состоянии BREAK


@dataclass
class ToughnessComponent:
    """
    Компонент стойкости сущности.
    Управляет текущей стойкостью, состояниями и восстановлением.
    """
    config: ToughnessConfig = field(default_factory=ToughnessConfig)
    
    current_toughness: float = 100.0
    state: ToughnessState = ToughnessState.NORMAL
    
    # Таймеры
    last_damage_time: float = field(default_factory=time.time)
    break_start_time: Optional[float] = None
    recovery_start_time: Optional[float] = None
    
    # Статистика
    total_toughness_damage_dealt: float = 0.0
    times_broken: int = 0
    
    def __post_init__(self):
        self.current_toughness = self.config.max_toughness
        self.recovery_start_time = time.time()

    @property
    def toughness_percent(self) -> float:
        """Текущий процент стойкости (0.0 - 1.0)"""
        if self.config.max_toughness <= 0:
            return 1.0
        return max(0.0, min(1.0, self.current_toughness / self.config.max_toughness))

    @property
    def is_broken(self) -> bool:
        return self.state == ToughnessState.BROKEN

    @property
    def is_weakened(self) -> bool:
        return self.state == ToughnessState.WEAKENED

    def take_toughness_damage(self, amount: float, modifier: float = 1.0) -> bool:
        """
        Получает урон по стойкости.
        
        Args:
            amount: Базовый урон по стойкости
            modifier: Модификатор от эффектов (баффы атакующего, дебаффы цели)
        
        Returns:
            True если произошел BREAK (переход в сломанное состояние)
        """
        if self.state == ToughnessState.BROKEN:
            return False  # Нельзя нанести урон по стойкости когда уже сломлен
        
        effective_damage = amount * modifier
        old_state = self.state
        
        self.current_toughness = max(0.0, self.current_toughness - effective_damage)
        self.last_damage_time = time.time()
        self.recovery_start_time = None  # Сбрасываем начало восстановления
        self.total_toughness_damage_dealt += effective_damage
        
        # Проверяем переход в WEAKENED
        if self.toughness_percent < self.config.weakened_threshold:
            self.state = ToughnessState.WEAKENED
        
        # Проверяем BREAK
        broke = False
        if self.current_toughness <= 0.0 and self.state != ToughnessState.BROKEN:
            self.state = ToughnessState.BROKEN
            self.break_start_time = time.time()
            self.current_toughness = 0.0
            self.times_broken += 1
            broke = True
        
        return broke

    def update(self, dt: float) -> bool:
        """
        Обновляет состояние стойкости.
        
        Args:
            dt: Время в секундах с последнего обновления
        
        Returns:
            True если состояние изменилось (например, вышел из BREAK)
        """
        old_state = self.state
        current_time = time.time()
        
        if self.state == ToughnessState.BROKEN:
            # Проверяем окончание длительности BREAK
            if self.break_start_time is not None:
                elapsed = current_time - self.break_start_time
                if elapsed >= self.config.break_duration:
                    # Выход из BREAK
                    self.state = ToughnessState.RECOVERING
                    self.current_toughness = self.config.max_toughness * 0.3  # Восстанавливаем 30% сразу
                    self.recovery_start_time = current_time
        elif self.state in [ToughnessState.WEAKENED, ToughnessState.NORMAL]:
            # Проверяем начало восстановления (после задержки)
            time_since_damage = current_time - self.last_damage_time
            
            if time_since_damage >= self.config.recovery_delay:
                # Восстанавливаем стойкость на основе прошедшего времени
                # Используем time_since_damage минус задержка
                recovery_time = time_since_damage - self.config.recovery_delay
                recovered = recovery_time * self.config.recovery_rate
                
                self.current_toughness = min(
                    self.config.max_toughness,
                    self.current_toughness + recovered
                )
                
                # Если восстановились до максимума или выше порога weakened
                if self.current_toughness >= self.config.max_toughness:
                    self.current_toughness = self.config.max_toughness
                    self.state = ToughnessState.NORMAL
                elif self.toughness_percent >= self.config.weakened_threshold:
                    self.state = ToughnessState.NORMAL
        
        return old_state != self.state

    def get_damage_reduction(self) -> float:
        """Возвращает множитель снижения входящего урона на основе состояния"""
        if self.state == ToughnessState.BROKEN:
            return -self.config.damage_taken_multiplier_broken  # Отрицательный = увеличение урона
        elif self.state == ToughnessState.WEAKENED:
            return self.config.damage_reduction_weakened
        else:
            return self.config.damage_reduction_normal

    def to_dict(self) -> dict:
        """Сериализация для UI/сети"""
        return {
            "current": self.current_toughness,
            "max": self.config.max_toughness,
            "percent": self.toughness_percent,
            "state": self.state.value,
            "recovery_remaining": self.get_recovery_remaining(),
            "break_remaining": self.get_break_remaining()
        }

    def get_recovery_remaining(self) -> float:
        """Оставшееся время до начала восстановления"""
        if self.state == ToughnessState.BROKEN:
            return 0.0
        elapsed = time.time() - self.last_damage_time
        return max(0.0, self.config.recovery_delay - elapsed)

    def get_break_remaining(self) -> float:
        """Оставшееся время в состоянии BREAK"""
        if self.state != ToughnessState.BROKEN or self.break_start_time is None:
            return 0.0
        elapsed = time.time() - self.break_start_time
        return max(0.0, self.config.break_duration - elapsed)

    def reset(self):
        """Сброс к начальному состоянию"""
        self.current_toughness = self.config.max_toughness
        self.state = ToughnessState.NORMAL
        self.break_start_time = None
        self.recovery_start_time = None
        self.last_damage_time = time.time()
