"""
Advanced Combat Mechanics: Damage Return, Pure Damage, Rooms, Emotions & Contextual AI
Реализация:
1. Возврат урона (Reflect): %, Flat, Base, Elemental, Pure
2. Чистый урон (True Damage): игнорирует броню/резисты, блокируется только IFrames/Immunity
3. Разовая блокировка (Block Counters): "Неуязвимость на N атак"
4. Бессмертный манекен (Immortal Dummy) с регеном
5. Комнаты/Зоны (Rooms): AoE эффекты (DoT/HoT), спавн лута
6. Система Эмоций AI: Страх, Гнев, Адреналин, Жадность
7. Контекстные задачи: Бежать, Атаковать, Подобрать, Использовать
"""

import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Tuple
from enum import Enum, auto
from collections import deque
import random
import math

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- 1. Типы Урона и Защиты ---

class DamageType(Enum):
    PHYSICAL = "physical"
    FIRE = "fire"
    ICE = "ice"
    LIGHTNING = "lightning"
    HOLY = "holy"
    DARK = "dark"
    PURE = "pure"  # Игнорирует все защиты, кроме полной неуязвимости


class MitigationType(Enum):
    ARMOR = "armor"  # Режет физический урон
    RESIST = "resist"  # Режет стихийный урон
    BLOCK_COUNTER = "block_counter"  # Разовая блокировка (на N атак)
    IFrames = "iframes"  # Полная неуязвимость по времени
    PURE_IMMUNITY = "pure_immunity"  # Специфическая защита от чистого урона


# --- 2. Механика Возврата Урона (Reflect) ---

@dataclass
class ReflectConfig:
    """Конфигурация возврата урона"""
    percent_of_damage: float = 0.0  # % от полученного урона
    flat_amount: float = 0.0        # Флэт значение
    reflect_base_only: bool = False # Только базовый урон (до снижений)
    reflect_elemental: bool = False # Только стихийный
    damage_type_returned: DamageType = DamageType.PURE  # Каким уроном возвращаем (часто Pure)


@dataclass
class ReflectEffect:
    """Активный эффект возврата"""
    config: ReflectConfig
    duration: float = 0.0  # 0 = навсегда или до срабатывания
    start_time: float = field(default_factory=time.time)
    charges: int = -1  # -1 = бесконечно, иначе кол-во срабатываний

    def is_active(self) -> bool:
        if self.charges == 0:
            return False
        if self.duration > 0 and (time.time() - self.start_time) > self.duration:
            return False
        return True

    def consume_charge(self):
        if self.charges > 0:
            self.charges -= 1


# --- 3. Сущности (Entity, Dummy, Player) ---

@dataclass
class Stats:
    armor: float = 0.0
    resist: float = 0.0  # Универсальный резист для простоты или dict по стихиям
    pure_immunity: float = 0.0  # Шанс или % снижения чистого урона
    block_counters: int = 0  # Кол-во剩余的 блокировок атак
    hp: float = 1000.0
    max_hp: float = 1000.0
    regen: float = 0.0  # HP/sec
    is_immortal: bool = False  # Для манекена
    
    # Сопротивления по стихиям (упрощенно: единый резист, но можно расширить)
    elemental_resist: Dict[DamageType, float] = field(default_factory=lambda: {
        DamageType.FIRE: 0.0, DamageType.ICE: 0.0, 
        DamageType.LIGHTNING: 0.0, DamageType.HOLY: 0.0, DamageType.DARK: 0.0
    })


@dataclass
class EmotionState:
    """Состояние эмоций AI"""
    fear: float = 0.0      # 0-100: Высокий страх -> бегство
    anger: float = 0.0     # 0-100: Высокий гнев -> агрессия, меньше защиты
    adrenaline: float = 0.0# 0-100: Скорость реакции, крит шанс
    greed: float = 0.0     # 0-100: Приоритет лута над боем

    def update(self, event: str, value: float):
        """Обновление эмоций по событию"""
        if event == "take_damage":
            self.fear = min(100, self.fear + value * 0.5)
            self.anger = min(100, self.anger + value * 1.2)
        elif event == "deal_damage":
            self.anger = min(100, self.anger + value * 0.8)
            self.adrenaline = min(100, self.adrenaline + value * 0.5)
        elif event == "low_hp":
            self.fear = min(100, self.fear + value * 2.0)
        elif event == "kill":
            self.adrenaline = min(100, self.adrenaline + 20.0)
            self.greed = min(100, self.greed + 10.0)
        
        # Затухание
        self.fear = max(0, self.fear - 0.1)
        self.anger = max(0, self.anger - 0.1)
        self.adrenaline = max(0, self.adrenaline - 0.2)
        self.greed = max(0, self.greed - 0.1)


class ContextualTask(Enum):
    """Контекстные задачи для AI"""
    ATTACK_TARGET = "attack_target"
    FLEE_TO_POINT = "flee_to_point"
    PICKUP_ITEM = "pickup_item"
    MOVE_TO_ZONE = "move_to_zone"
    USE_SKILL = "use_skill"
    WAIT = "wait"
    BUY_ITEM = "buy_item"


@dataclass
class Task:
    task_type: ContextualTask
    target: Any = None  # Entity, Item, Vector
    priority: int = 0
    expiry: float = 0.0

    def is_valid(self) -> bool:
        return time.time() < self.expiry if self.expiry > 0 else True


class Entity:
    def __init__(self, name: str, is_immortal: bool = False):
        self.name = name
        self.stats = Stats(is_immortal=is_immortal)
        self.reflects: List[ReflectEffect] = []
        self.emotions = EmotionState()
        self.task_queue: deque = deque()
        self.current_task: Optional[Task] = None
        self.logger = logging.getLogger(f"Entity:{name}")
        
        # Для тестов DPS
        self.damage_taken_log: List[Tuple[float, float]] = [] # (time, amount)
        self.damage_dealt_log: List[Tuple[float, float]] = []

    def add_reflect(self, config: ReflectConfig, duration: float = 0, charges: int = -1):
        effect = ReflectEffect(config, duration, time.time(), charges)
        self.reflects.append(effect)
        self.logger.info(f"Added reflect: {config}")

    def take_damage(self, amount: float, dtype: DamageType, is_base: bool = True) -> Tuple[float, float]:
        """
        Возвращает (final_damage, reflected_damage)
        """
        original_amount = amount
        final_damage = amount
        reflected_damage = 0.0

        # 1. Проверка Block Counters (Разовая блокировка)
        if self.stats.block_counters > 0:
            self.stats.block_counters -= 1
            self.logger.info(f"Block counter used! Remaining: {self.stats.block_counters}")
            return 0.0, 0.0  # Полная блокировка

        # 2. Расчет митигации
        mitigation = 0.0
        if dtype == DamageType.PHYSICAL:
            # Формула брони: Armor / (Armor + K)
            k = 1000 # Константа
            mitigation = self.stats.armor / (self.stats.armor + k)
        elif dtype in [DamageType.FIRE, DamageType.ICE, DamageType.LIGHTNING, DamageType.HOLY, DamageType.DARK]:
            mitigation = self.stats.elemental_resist.get(dtype, self.stats.resist) / 100.0
        elif dtype == DamageType.PURE:
            # Чистый урон игнорирует броню/резисты, но может быть снижен специфической иммункой
            mitigation = self.stats.pure_immunity / 100.0
        
        final_damage = amount * (1.0 - max(0, mitigation))
        
        # 3. Применение урона
        if not self.stats.is_immortal:
            self.stats.hp = max(0, self.stats.hp - final_damage)
        
        # Логирование для DPS
        now = time.time()
        self.damage_taken_log.append((now, final_damage))
        # Очистка старых записей (за последние 5 сек)
        self.damage_taken_log = [(t, d) for t, d in self.damage_taken_log if now - t < 5.0]

        self.logger.info(f"{self.name} took {final_damage:.2f} {dtype.value} dmg (Mitigated: {mitigation*100:.1f}%)")

        # 4. Обработка Возврата Урона (Reflect)
        for ref in self.reflects:
            if ref.is_active():
                ref_dmg = 0.0
                # Логика что возвращаем
                if ref.config.reflect_base_only:
                    ref_dmg = original_amount * (ref.config.percent_of_damage / 100.0) + ref.config.flat_amount
                elif ref.config.reflect_elemental and dtype != DamageType.PHYSICAL:
                    ref_dmg = final_damage * (ref.config.percent_of_damage / 100.0) + ref.config.flat_amount
                else:
                    # Возврат от любого полученного урона
                    ref_dmg = final_damage * (ref.config.percent_of_damage / 100.0) + ref.config.flat_amount
                
                if ref_dmg > 0:
                    reflected_damage += ref_dmg
                    ref.consume_charge()
                    self.logger.info(f"Reflecting {ref_dmg:.2f} as {ref.config.damage_type_returned.value}")
        
        # Обновление эмоций
        self.emotions.update("take_damage", final_damage / self.stats.max_hp * 100)
        if self.stats.hp < self.stats.max_hp * 0.3:
            self.emotions.update("low_hp", 50)

        return final_damage, reflected_damage

    def regenerate(self, dt: float):
        if self.stats.regen > 0 and not self.stats.is_immortal:
            heal = self.stats.regen * dt
            self.stats.hp = min(self.stats.max_hp, self.stats.hp + heal)
        elif self.stats.is_immortal:
            # Манекен всегда полон если есть реген
            if self.stats.regen > 0:
                self.stats.hp = self.stats.max_hp

    def get_dps(self, window: float = 5.0) -> float:
        now = time.time()
        recent = [d for t, d in self.damage_taken_log if now - t < window]
        if not recent: return 0.0
        return sum(recent) / window

    def push_task(self, task: Task):
        self.task_queue.append(task)
        self.logger.info(f"Task added: {task.task_type.value}")

    def update_ai(self):
        """Логика выбора задачи на основе эмоций и очереди"""
        # Приоритет: Текущая задача -> Эмоции -> Очередь
        
        # 1. Проверка текущей задачи
        if self.current_task and self.current_task.is_valid():
            # Эмоции могут прервать задачу
            if self.emotions.fear > 80 and self.current_task.task_type == ContextualTask.ATTACK_TARGET:
                self.current_task = None # Прерываем атаку из-за страха
            else:
                return self.current_task
        
        self.current_task = None

        # 2. Генерация задач от эмоций
        if self.emotions.fear > 70:
            task = Task(ContextualTask.FLEE_TO_POINT, target=(0,0), priority=10, expiry=time.time()+5)
            self.current_task = task
            return task
        
        if self.emotions.greed > 60:
            # Ищем лут (упрощенно)
            task = Task(ContextualTask.PICKUP_ITEM, priority=5, expiry=time.time()+3)
            self.current_task = task
            return task

        # 3. Выполнение очереди
        if self.task_queue:
            next_task = self.task_queue.popleft()
            if next_task.is_valid():
                self.current_task = next_task
                return next_task
        
        return None


# --- 4. Room / Zone System ---

class RoomEffectType(Enum):
    DO_T = "damage_over_time"
    HO_T = "heal_over_time"
    BUFF_ZONE = "buff_zone"
    LOOT_SPAWN = "loot_spawn"


@dataclass
class RoomConfig:
    effect_type: RoomEffectType
    value: float  # DPS или HPS
    duration: float = 0.0 # 0 = бесконечно
    spawn_items: List[str] = field(default_factory=list)
    radius: float = 10.0


class GameRoom:
    def __init__(self, name: str, config: RoomConfig):
        self.name = name
        self.config = config
        self.entities: List[Entity] = []
        self.active = True
        self.logger = logging.getLogger(f"Room:{name}")

    def add_entity(self, entity: Entity):
        self.entities.append(entity)
        self.logger.info(f"Entity {entity.name} entered room")
        
        # Спавн лута при входе (если настроено)
        if self.config.effect_type == RoomEffectType.LOOT_SPAWN and self.config.spawn_items:
            for item in self.config.spawn_items:
                entity.push_task(Task(ContextualTask.PICKUP_ITEM, target=item, priority=1))

    def update(self, dt: float):
        if not self.active: return

        for entity in self.entities:
            if self.config.effect_type == RoomEffectType.DO_T:
                dmg = self.config.value * dt
                entity.take_damage(dmg, DamageType.PURE) # Чистый урон от зоны
                self.logger.debug(f"Room {self.name} dealt {dmg} to {entity.name}")
            
            elif self.config.effect_type == RoomEffectType.HO_T:
                if not entity.stats.is_immortal:
                    entity.stats.hp = min(entity.stats.max_hp, entity.stats.hp + self.config.value * dt)
                else:
                    entity.stats.hp = entity.stats.max_hp # Манекен полный
                self.logger.debug(f"Room {self.name} healed {entity.name}")

            # Регенерация сущности
            entity.regenerate(dt)


# --- 5. Test Suite ---

def run_combat_tests():
    print("\n=== START COMBAT MECHANICS TESTS ===\n")
    
    # Тест 1: Бессмертный манекен с регеном
    print("Test 1: Immortal Dummy with Regen")
    dummy = Entity("ImmortalDummy", is_immortal=True)
    dummy.stats.max_hp = 10000
    dummy.stats.hp = 10000
    dummy.stats.regen = 500.0 # 500 HP/sec
    
    room = GameRoom("DamageZone", RoomConfig(RoomEffectType.DO_T, value=1000.0)) # 1000 DPS
    room.add_entity(dummy)
    
    # Симпулируем 2 секунды (dt=0.1, 20 итераций = 2 сек)
    # 1000 DPS * 0.1 sec = 100 урона за тик
    for _ in range(20):
        room.update(0.1)
        time.sleep(0.01)
    
    assert dummy.stats.hp == 10000, "Dummy HP should be full due to immortality+regen"
    dps = dummy.get_dps()
    print(f"Dummy DPS taken: {dps:.2f} (Expected ~1000)")
    # Примечание: DPS считается по последним 5 сек, но мы били только 2 сек (2000 урона всего)
    # 2000 урона / 5 сек окно = 400 DPS в среднем, если окно шире чем тест
    # Если считать по факту теста: 2000 урона / 2 сек = 1000 DPS
    # Исправим проверку на общее кол-во урона или изменим окно
    total_dmg = sum(d for t, d in dummy.damage_taken_log)
    print(f"Total damage taken: {total_dmg} (Expected ~2000)")
    assert 1900 < total_dmg < 2100, f"Total dmg mismatch: {total_dmg}"
    print("✅ Test 1 Passed\n")

    # Тест 2: Возврат урона (Reflect)
    print("Test 2: Reflect Mechanics")
    attacker = Entity("Attacker")
    defender = Entity("DefenderWithReflect")
    
    # Щит возвращает 50% урона чистым уроном
    defender.add_reflect(ReflectConfig(
        percent_of_damage=50.0, 
        damage_type_returned=DamageType.PURE
    ))
    
    dmg, ref = attacker.take_damage(0, DamageType.PHYSICAL) # Attacker takes nothing
    # Defender takes damage from somewhere else to trigger reflect logic manually? 
    # No, let's simulate defender taking hit
    incoming_dmg, reflected_dmg = defender.take_damage(100.0, DamageType.PHYSICAL)
    
    assert incoming_dmg == 100.0, f"Incoming dmg wrong: {incoming_dmg}"
    assert reflected_dmg == 50.0, f"Reflected dmg wrong: {reflected_dmg}"
    print(f"Taken: {incoming_dmg}, Reflected: {reflected_dmg}")
    print("✅ Test 2 Passed\n")

    # Тест 3: Block Counters (Разовая блокировка)
    print("Test 3: Block Counters (IFrames on hits)")
    tank = Entity("TankWithCounter")
    tank.stats.block_counters = 3 # 3 атаки
    
    dmg1, _ = tank.take_damage(1000, DamageType.PHYSICAL)
    assert dmg1 == 0, "First hit should be blocked"
    assert tank.stats.block_counters == 2, "Counter decremented"
    
    dmg2, _ = tank.take_damage(1000, DamageType.PHYSICAL)
    assert dmg2 == 0, "Second hit blocked"
    
    dmg3, _ = tank.take_damage(1000, DamageType.PHYSICAL)
    assert dmg3 == 0, "Third hit blocked"
    
    dmg4, _ = tank.take_damage(1000, DamageType.PHYSICAL)
    assert dmg4 == 1000, "Fourth hit should go through"
    print("✅ Test 3 Passed\n")

    # Тест 4: Эмоции и Контекстные Задачи
    print("Test 4: Emotions & Contextual Tasks")
    ai_bot = Entity("AIBot")
    ai_bot.stats.max_hp = 1000
    ai_bot.stats.hp = 1000
    
    # Получаем урон -> Страх
    ai_bot.take_damage(800, DamageType.FIRE) # 80% HP lost
    ai_bot.emotions.update("low_hp", 50)
    
    task = ai_bot.update_ai()
    assert task is not None, "Task should be generated"
    assert task.task_type == ContextualTask.FLEE_TO_POINT, f"Expected FLEE, got {task.task_type}"
    print(f"AI Task: {task.task_type.value} (Fear: {ai_bot.emotions.fear:.1f})")
    
    # Сброс страха, добавляем жадность
    ai_bot.emotions.fear = 0
    ai_bot.emotions.greed = 70
    ai_bot.current_task = None  # Сбрасываем текущую задачу чтобы AI пересчитал
    task2 = ai_bot.update_ai()
    assert task2.task_type == ContextualTask.PICKUP_ITEM, f"Should pickup item, got {task2.task_type}"
    print("✅ Test 4 Passed\n")

    # Тест 5: Интеграция Комнаты + Лут + Эмоции
    print("Test 5: Integrated Room + Loot + Emotions")
    hero = Entity("Hero")
    loot_room = GameRoom("LootRoom", RoomConfig(
        RoomEffectType.LOOT_SPAWN, 
        value=0, 
        spawn_items=["GoldChest", "RareSword"]
    ))
    loot_room.add_entity(hero)
    
    assert len(hero.task_queue) == 2, "Should have 2 pickup tasks"
    task = hero.update_ai()
    assert task.task_type == ContextualTask.PICKUP_ITEM
    print(f"Hero picked up: {task.target}")
    print("✅ Test 5 Passed\n")

    print("=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_combat_tests()
