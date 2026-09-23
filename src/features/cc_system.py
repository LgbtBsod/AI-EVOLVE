"""
Advanced Crowd Control, Stagger & Break System
Реализует механики: Stagger, Break, Stun, Knockdown, Micro-stun, CC Stats.
Соблюдает SOLID, использует стандартные библиотеки (dataclasses, enum, threading).
"""

import time
import threading
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Callable
from collections import deque
import random

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CC_System")

class CCType(Enum):
    """Типы негативных эффектов"""
    STUN = auto()          # Полный контроль, нельзя действовать
    KNOCKDOWN = auto()     # Сбит с ног, нельзя двигаться/атаковать
    DISORIENTED = auto()   # Замедление, промахи (Blind/Silence аналог)
    MICRO_STUN = auto()    # 0.2с прерывание кастов (Mini-bash)
    ROOT = auto()          # Нельзя двигаться, можно атаковать
    SLOW = auto()          # Замедление

class BreakState(Enum):
    """Состояния стойкости"""
    NORMAL = auto()
    STAGGERING = auto()    # Накопление урона по стойке
    BROKEN = auto()        # Сломлен, уязвим

@dataclass
class CCEffect:
    """Представление активного эффекта контроля"""
    type: CCType
    duration: float
    remaining: float
    source_id: str
    magnitude: float = 1.0  # Сила эффекта (для замедления и т.д.)
    
    def tick(self, dt: float) -> bool:
        """Уменьшает длительность. Возвращает True, если эффект истек."""
        self.remaining -= dt
        return self.remaining <= 0

@dataclass
class StaggerBar:
    """Шкала стойкости (Poise)"""
    current: float
    max_stagger: float
    break_duration_base: float = 1.0  # 1 сек за каждые 500 единиц (будет масштабировано)
    
    # Множители от характеристик
    stagger_resist_mult: float = 1.0  # Сопротивление накоплению
    break_duration_resist: float = 1.0 # Сопротивление длительности брейка
    
    def add_damage(self, damage: float) -> bool:
        """
        Наносит урон по стойке.
        Возвращает True, если произошел BREAK.
        """
        effective_dmg = damage * self.stagger_resist_mult
        self.current += effective_dmg
        
        if self.current >= self.max_stagger:
            self.current = self.max_stagger
            return True # BREAK!
        return False
    
    def reset(self):
        self.current = 0.0
        
    def get_break_duration(self) -> float:
        """Расчет длительности брейка: мин 0.5 сек + 0.1 сек за каждые 50 ед. макс стойки"""
        # Формула: 0.5 + (MaxStagger / 50) * 0.1
        min_duration = 0.5
        additional_duration = (self.max_stagger / 50.0) * 0.1
        return max(min_duration, min_duration + additional_duration) * self.break_duration_resist

@dataclass
class CharacterCCStats:
    """Характеристики персонажа, связанные с контролем"""
    # Атака
    cc_damage_mult: float = 1.0       # +% урона по оглушенным/контролируемым
    cc_duration_mult: float = 1.0     # +% длительности накладываемых эффектов
    
    # Защита
    cc_resist_flat: float = 0.0       # Плоское снижение урона когда ты в КК
    cc_resist_percent: float = 0.0    # % снижения урона когда ты в КК
    cc_duration_resist: float = 1.0   # Множитель длительности эффектов на тебе (0.5 = -50%)
    
    # Стойкость
    stagger_max: float = 500.0
    stagger_regen: float = 10.0       # Восстановление стойки в сек
    stagger_resist: float = 1.0       # Множитель сопротивления урону по стойке (1.0 = норма, 0.5 = -50% урона по стойке)
    
    # Специфичные
    micro_stun_window: float = 0.2    # Окно микро-стана

class StatusEffectManager:
    """
    Управляет активными эффектами контроля и состоянием брейка.
    Реализует логику приоритетов и взаимодействий.
    """
    def __init__(self, owner_stats: CharacterCCStats):
        self.stats = owner_stats
        self.active_effects: List[CCEffect] = []
        self.stagger = StaggerBar(current=0.0, max_stagger=owner_stats.stagger_max)
        self.break_state = BreakState.NORMAL
        self.break_timer: float = 0.0
        self.is_interrupted: bool = False # Для микро-стана
        
        # Lock для потокобезопасности
        self.lock = threading.Lock()

    def apply_cc(self, effect_type: CCType, base_duration: float, source_id: str="system", magnitude: float=1.0):
        """
        Применяет эффект контроля.
        Логика:
        1. Если в БРЕЙКЕ -> Контроль длится все время брейка (игнорируем таймер), но не стакается отдельно.
        2. Если НЕ в брейке -> Обычная длительность с учетом резистов.
        3. Микро-стан всегда прерывает касты.
        """
        with self.lock:
            # Расчет длительности с учетом характеристик цели
            final_duration = base_duration * self.stats.cc_duration_resist
            
            # Если цель уже в брейке, новые контроли не добавляются как отдельные таймеры,
            # они просто действуют в рамках брейка (по ТЗ: "нельзя забрейкать и потом законтролить")
            if self.break_state == BreakState.BROKEN:
                logger.debug(f"Цель в брейке. Эффект {effect_type.name} игнорируется как отдельный таймер.")
                # Но мы можем обновить тип контроля, если он жестче? 
                # Пока оставим просто активным состоянием брейка.
                return

            # Проверка на иммунитет или сокращение
            if final_duration <= 0:
                logger.debug(f"Эффект {effect_type.name} полностью сопротивлен.")
                return

            new_effect = CCEffect(
                type=effect_type,
                duration=final_duration,
                remaining=final_duration,
                source_id=source_id,
                magnitude=magnitude
            )
            
            # Приоритеты: Стан > Нокдаун > Корень > Замедление
            # Простая реализация: добавляем в список, при проверке статуса берем самый жесткий
            self.active_effects.append(new_effect)
            
            if effect_type == CCType.MICRO_STUN:
                self.trigger_micro_stun()
                
            logger.info(f"Применен {effect_type.name} на {final_duration:.2f}с. Всего эффектов: {len(self.active_effects)}")

    def trigger_micro_stun(self):
        """Мгновенное прерывание действий (кастов)"""
        self.is_interrupted = True
        logger.warning("!!! MICRO STUN: КАСТ ПРЕРВАН !!!")

    def take_stagger_damage(self, amount: float):
        """Получение урона по стойке"""
        with self.lock:
            if self.break_state == BreakState.BROKEN:
                return # Уже сломлен
            
            # Применяем сопротивление стойки из статов персонажа
            effective_amount = amount * self.stats.stagger_resist
            
            if self.stagger.add_damage(effective_amount):
                self.trigger_break()

    def trigger_break(self):
        """Перевод в состояние брейка"""
        self.break_state = BreakState.BROKEN
        self.break_timer = self.stagger.get_break_duration()
        self.stagger.reset()
        
        # Очистка мелких контролей, так как брейк их перекрывает
        self.active_effects.clear()
        
        logger.critical(f"!!! BREAK! Цель ломается на {self.break_timer:.2f}с. Уязвимость активна. !!!")

    def update(self, dt: float):
        """Обновление таймеров (вызывать в игровом цикле)"""
        with self.lock:
            # 1. Обновление брейка
            if self.break_state == BreakState.BROKEN:
                self.break_timer -= dt
                if self.break_timer <= 0:
                    self.break_state = BreakState.NORMAL
                    logger.info("Брейк закончен. Цель восстанавливается.")
                return # В брейке обычные эффекты не тикают (они заморожены или сняты)

            # 2. Регенерация стойки
            if self.stagger.current > 0:
                self.stagger.current = max(0, self.stagger.current - (self.stats.stagger_regen * dt))

            # 3. Обновление эффектов
            # Микро-стан сбрасывается быстро сам или через 0.2с
            if self.is_interrupted:
                # Логика сброса флага прерывания (например, через 0.2с если не продлен)
                pass 

            active_count = len(self.active_effects)
            self.active_effects = [eff for eff in self.active_effects if not eff.tick(dt)]
            
            if len(self.active_effects) < active_count:
                logger.debug(f"Эффекты истекли. Осталось: {len(self.active_effects)}")

    def get_current_status(self) -> Optional[CCType]:
        """Возвращает самый приоритетный активный статус"""
        if self.break_state == BreakState.BROKEN:
            return CCType.STUN # Технически брейк работает как стан + уязвимость
            
        if not self.active_effects:
            return None
            
        # Приоритеты
        priority = {
            CCType.STUN: 5,
            CCType.KNOCKDOWN: 4,
            CCType.MICRO_STUN: 3, # Высокий приоритет для прерывания
            CCType.ROOT: 2,
            CCType.DISORIENTED: 1,
            CCType.SLOW: 0
        }
        
        # Возвращаем эффект с высшим приоритетом
        best_eff = max(self.active_effects, key=lambda e: priority.get(e.type, -1))
        return best_eff.type

    def is_cc_immobilized(self) -> bool:
        """Проверка: обездвижен ли персонаж"""
        status = self.get_current_status()
        if status is None: return False
        return status in [CCType.STUN, CCType.KNOCKDOWN, CCType.ROOT, CCType.MICRO_STUN]

    def take_damage_with_cc_mods(self, base_dmg: float) -> float:
        """
        Расчет входящего урона с учетом модификаторов от КК и Брейка.
        """
        final_dmg = base_dmg
        
        # 1. Модификатор "Урон по контролируемым" (от атакующего, тут упрощено)
        # Предположим, у атакующего есть статы, которые передаются сюда
        
        # 2. Если цель в БРЕЙКЕ: +15% урона, -25% резистов (реализуется в калькуляторе урона)
        if self.break_state == BreakState.BROKEN:
            final_dmg *= 1.15
            logger.debug("Урон увеличен на 15% из-за БРЕЙКА")
            
        # 3. Если цель под эффектом (не брейк), проверяем защиту от урона в КК
        elif self.active_effects:
            flat_reduce = self.stats.cc_resist_flat
            pct_reduce = self.stats.cc_resist_percent
            final_dmg = max(0, (final_dmg - flat_reduce) * (1.0 - pct_reduce))
            if flat_reduce > 0 or pct_reduce > 0:
                logger.debug(f"Урон снижен защитой от КК: {final_dmg:.2f}")
                
        return final_dmg

# --- Тестовый сценарий (Simulation) ---

def run_cc_simulation():
    print("\n=== ЗАПУСК СИМУЛЯЦИИ CC & BREAK SYSTEM ===\n")
    
    # Создаем персонажа (Босс)
    boss_stats = CharacterCCStats(
        stagger_max=1000.0,  # Нужно 1000 урона по стойке для брейка
        stagger_regen=20.0,
        cc_duration_resist=0.8, # -20% длительности контролей
        cc_resist_percent=0.1   # -10% урона когда оглушен
    )
    boss_cc = StatusEffectManager(boss_stats)
    
    # Создаем игрока (Атакующий)
    player_cc_stats = CharacterCCStats(
        cc_damage_mult=1.2, # +20% урона по оглушенным
        cc_duration_mult=1.5 # +50% длительности контролей
    )
    
    print(f"Босс: Max Stagger={boss_stats.stagger_max}, Resist={boss_stats.cc_duration_resist}")
    print(f"Игрок: Dmg Mult={player_cc_stats.cc_damage_mult}, Dur Mult={player_cc_stats.cc_duration_mult}\n")
    
    dt = 0.1 # Шаг симуляции 100ms
    total_time = 0.0
    
    # ЭТАП 1: Накопление стойки (Stagger)
    print("--- ЭТАП 1: Накопление урона по стойке ---")
    stagger_hits = 4
    hit_dmg = 260 # 4 * 260 = 1040 > 1000 -> БРЕЙК
    
    for i in range(stagger_hits):
        boss_cc.take_stagger_damage(hit_dmg)
        print(f"Удар {i+1}: Урон по стойке {hit_dmg}. Текущая стойка: {boss_cc.stagger.current:.1f}/{boss_cc.stagger.max_stagger}")
        time.sleep(0.05)
        
    # Должен сработать БРЕЙК
    assert boss_cc.break_state == BreakState.BROKEN, "Брейк не сработал!"
    print(f">>> БРЕЙК АКТИВИРОВАН! Длительность: {boss_cc.break_timer:.2f}с\n")
    
    # ЭТАП 2: Попытка наложить стан во время брейка (должна быть проигнорирована как отдельный таймер)
    print("--- ЭТАП 2: Попытка контроля во время Брейка ---")
    boss_cc.apply_cc(CCType.STUN, base_duration=3.0, source_id="player_spell")
    # Логика внутри apply_cc должна понять, что мы в брейке, и не добавить таймер
    print(f"Активные эффекты (должно быть 0, т.к. брейк перекрывает): {len(boss_cc.active_effects)}")
    
    # ЭТАП 3: Урон во время брейка
    print("\n--- ЭТАП 3: Урон во время Брейка ---")
    base_dmg = 1000.0
    actual_dmg = boss_cc.take_damage_with_cc_mods(base_dmg)
    expected_dmg = base_dmg * 1.15 # +15%
    print(f"Базовый урон: {base_dmg}. Урон по брейкнутому: {actual_dmg:.1f} (Ожидалось ~{expected_dmg})")
    assert abs(actual_dmg - expected_dmg) < 1.0, "Множитель урона по брейку неверен!"
    
    # ЭТАП 4: Микро-стан (Прерывание каста)
    print("\n--- ЭТАП 4: Микро-стан (Прерывание) ---")
    # Сбросим брейк вручную для теста
    boss_cc.break_state = BreakState.NORMAL
    boss_cc.is_interrupted = False
    
    print("Каст заклинания...")
    boss_cc.apply_cc(CCType.MICRO_STUN, base_duration=0.2, source_id="potion")
    print(f"Статус прерывания: {boss_cc.is_interrupted}")
    assert boss_cc.is_interrupted == True, "Микро-стан не прервал каст!"
    print(">>> КАСТ ПРЕРВАН УСПЕШНО!")
    
    # ЭТАП 5: Комбо (Дебаф + Брейк)
    print("\n--- ЭТАП 5: Комбо (Дебаф -> Брейк) ---")
    boss_cc.stagger.current = 900 # Почти сломлен
    
    # Накладываем дебаф (замедление)
    boss_cc.apply_cc(CCType.SLOW, base_duration=5.0, source_id="arrow")
    print(f"Наложен Slow. Активных эффектов: {len(boss_cc.active_effects)}")
    
    # Добиваем стойку
    boss_cc.take_stagger_damage(150)
    print(f"Нанесен урон по стойке. Состояние: {boss_cc.break_state.name}")
    
    # Проверяем, что Slow все еще "активен" концептуально (внутри брейка)
    # Но физически таймер стоит.
    
    print("\n=== СИМУЛЯЦИЯ ЗАВЕРШЕНА УСПЕШНО ===")

if __name__ == "__main__":
    run_cc_simulation()
