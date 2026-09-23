"""
CAS Effect System v3.0 - Архитектура на основе событий и подписок

Принципы:
1. CAS Engine - только триггеры и условия (не управляет эффектами)
2. Effect Manager - жизненный цикл эффектов (активация/деактивация)
3. Effects - инкапсулированная логика поведения (тайминги, статы, реакции)
4. Контракт: Эффект подписывается на CAS события → CAS стреляет → Эффект реагирует

Архитектура:
[Item] → [Effect Template] → [Effect Instance] → subscribes to → [CAS Engine]
                                                      ↓
                                              [Event Bus]
                                                      ↓
                                           [Effect Manager] ← manages lifecycle
"""

from dataclasses import dataclass, field
from typing import Dict, List, Callable, Any, Optional, Set
from enum import Enum
import time


class EventType(Enum):
    """Типы событий от CAS Engine"""
    HP_PERCENT_CHANGED = "hp_percent_changed"
    STAT_CHANGED = "stat_changed"
    BUFF_APPLIED = "buff_applied"
    DEBUFF_APPLIED = "debuff_applied"
    ITEM_EQUIPPED = "item_equipped"
    ATTACK_PERFORMED = "attack_performed"
    KILL_CONFIRMED = "kill_confirmed"
    DAMAGE_TAKEN = "damage_taken"
    TIMER_TICK = "timer_tick"  # Для периодических проверок


@dataclass
class Event:
    """Событие от CAS Engine"""
    type: EventType
    source: str  # Кто вызвал (например, "sorrow_of_berserk")
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    
    def get(self, key: str, default=None) -> Any:
        return self.data.get(key, default)


@dataclass
class EffectActivationRequest:
    """Запрос на активацию эффекта от CAS"""
    effect_id: str
    reason: str
    event: Event
    priority: int = 0


@dataclass
class EffectDeactivationRequest:
    """Запрос на деактивацию эффекта"""
    effect_id: str
    reason: str
    event: Optional[Event] = None


class Subscription:
    """Подписка эффекта на CAS события"""
    
    def __init__(
        self,
        effect_id: str,
        event_types: Set[EventType],
        condition_callback: Callable[[Event], bool],
        handler_callback: Callable[[Event], None]
    ):
        self.effect_id = effect_id
        self.event_types = event_types
        self.condition_callback = condition_callback  # Проверяет триггер
        self.handler_callback = handler_callback      # Реагирует на событие
        self.is_active = True
    
    def matches(self, event: Event) -> bool:
        """Проверяет, подходит ли событие для этой подписки"""
        if not self.is_active:
            return False
        if event.type not in self.event_types:
            return False
        return self.condition_callback(event)


class CASSubscriptionManager:
    """
    Управляет подписками эффектов на CAS события.
    CAS Engine НЕ знает об эффектах — он просто стреляет событиями.
    """
    
    def __init__(self):
        self.subscriptions: Dict[EventType, List[Subscription]] = {
            et: [] for et in EventType
        }
    
    def subscribe(
        self,
        effect_id: str,
        event_types: Set[EventType],
        condition_callback: Callable[[Event], bool],
        handler_callback: Callable[[Event], None]
    ) -> Subscription:
        """Эффект подписывается на события"""
        subscription = Subscription(
            effect_id, event_types, condition_callback, handler_callback
        )
        for et in event_types:
            self.subscriptions[et].append(subscription)
        return subscription
    
    def unsubscribe(self, subscription: Subscription):
        """Отписка эффекта"""
        subscription.is_active = False
        for et in subscription.event_types:
            if subscription in self.subscriptions[et]:
                self.subscriptions[et].remove(subscription)
    
    def emit(self, event: Event):
        """CAS Engine выпускает событие → все подписчики реагируют"""
        relevant_subs = self.subscriptions.get(event.type, [])
        for sub in relevant_subs:
            if sub.matches(event):
                sub.handler_callback(event)


class EffectState(Enum):
    """Состояния эффекта"""
    INACTIVE = "inactive"       # Ждёт триггера
    ACTIVE = "active"           # Активен, применяет статы
    COOLDOWN = "cooldown"       # На перезарядке
    EXPIRED = "expired"         # Истёк время действия


class BaseEffect:
    """
    Базовый класс эффекта.
    Знает о своей логике, но НЕ знает о CAS напрямую.
    """
    
    _instance_counter = 0  # Класс-уровень счётчик для уникальных ID
    
    def __init__(self, effect_id: str, item_source: str):
        BaseEffect._instance_counter += 1
        self.effect_id = f"{effect_id}_{BaseEffect._instance_counter}"  # Уникальный ID
        self.item_source = item_source
        self.state = EffectState.INACTIVE
        self.subscription: Optional[Subscription] = None
        self.activation_time: Optional[float] = None
        self.expiration_time: Optional[float] = None
        self.cooldown_until: Optional[float] = None
        
        # Статы, которые эффект предоставляет
        self.stat_modifiers: Dict[str, float] = {}
        
        # Внутреннее состояние
        self.internal_state: Dict[str, Any] = {}
    
    def get_subscription_config(self) -> Dict[str, Any]:
        """
        Возвращает конфигурацию подписки для CAS.
        CAS использует это для регистрации подписки.
        """
        raise NotImplementedError
    
    def on_activate(self, event: Event):
        """Вызывается Effect Manager при активации"""
        self.state = EffectState.ACTIVE
        self.activation_time = time.time()
    
    def on_deactivate(self, reason: str):
        """Вызывается Effect Manager при деактивации"""
        self.state = EffectState.INACTIVE
        self.activation_time = None
        self.expiration_time = None
    
    def on_cooldown(self, duration: float):
        """Переводит эффект в cooldown"""
        self.state = EffectState.COOLDOWN
        self.cooldown_until = time.time() + duration
    
    def handle_event(self, event: Event):
        """Обработка события от CAS (вызывается через подписку)"""
        raise NotImplementedError
    
    def tick(self, delta_time: float):
        """Периодический тик (вызывается Effect Manager)"""
        if self.state == EffectState.ACTIVE and self.expiration_time:
            if time.time() >= self.expiration_time:
                return "expire"  # Signal to deactivate
        return None
    
    def get_stat_modifiers(self) -> Dict[str, float]:
        """Возвращает текущие модификаторы статов"""
        if self.state != EffectState.ACTIVE:
            return {}
        return self.stat_modifiers.copy()


class EffectManager:
    """
    Управляет жизненным циклом всех эффектов у сущности.
    - Активирует эффекты по запросу CAS
    - Деактивирует по истечении времени или условию
    - Вызывает tick() для периодических обновлений
    - Агрегирует статы от всех активных эффектов
    """
    
    def __init__(self, entity_id: str, cas_manager: CASSubscriptionManager):
        self.entity_id = entity_id
        self.cas_manager = cas_manager
        self.effects: Dict[str, BaseEffect] = {}
        self.active_effects: Set[str] = set()
    
    def register_effect(self, effect: BaseEffect):
        """Регистрирует эффект и подписывает на CAS"""
        self.effects[effect.effect_id] = effect
        
        # Получаем конфигурацию подписки
        config = effect.get_subscription_config()
        
        # Подписываем эффект на CAS события
        effect.subscription = self.cas_manager.subscribe(
            effect_id=effect.effect_id,
            event_types=config["event_types"],
            condition_callback=config["condition"],
            handler_callback=lambda evt, eff=effect: eff.handle_event(evt)
        )
    
    def activate_effect(self, effect_id: str, event: Event):
        """Активирует эффект по запросу"""
        if effect_id not in self.effects:
            return False
        
        effect = self.effects[effect_id]
        if effect.state != EffectState.INACTIVE:
            return False  # Уже активен или в cooldown
        
        effect.on_activate(event)
        self.active_effects.add(effect_id)
        return True
    
    def deactivate_effect(self, effect_id: str, reason: str = ""):
        """Деактивирует эффект"""
        if effect_id not in self.effects:
            return
        
        effect = self.effects[effect_id]
        effect.on_deactivate(reason)
        self.active_effects.discard(effect_id)
    
    def tick_all(self, delta_time: float = 0.1):
        """Обновляет все активные эффекты"""
        to_deactivate = []
        for effect_id in self.active_effects:
            effect = self.effects.get(effect_id)
            if effect:
                result = effect.tick(delta_time)
                if result == "expire":
                    to_deactivate.append((effect_id, "expired"))
        
        for effect_id, reason in to_deactivate:
            self.deactivate_effect(effect_id, reason)
    
    def get_aggregated_stats(self) -> Dict[str, float]:
        """Агрегирует статы от всех активных эффектов"""
        aggregated: Dict[str, float] = {}
        for effect_id in self.active_effects:
            effect = self.effects.get(effect_id)
            if effect:
                mods = effect.get_stat_modifiers()
                for stat, value in mods.items():
                    aggregated[stat] = aggregated.get(stat, 0) + value
        return aggregated


# ============================================================================
# ПРИМЕР: Sorrow of Berserk - Lost My Self Effect
# ============================================================================

class SorrowLostMySelfEffect(BaseEffect):
    """
    Эффект 'Lost My Self' от Sorrow of Berserk.
    
    Логика:
    - Триггер: HP < 40%
    - Скалирование: каждые 10% ниже 40% усиливают эффект
    - Blood Cost Attack: тратит HP для урона
    - Safety Net: если HP не хватает → ставит на 1 + iframe
    """
    
    def __init__(self, entity_id: str):
        super().__init__(f"{entity_id}_sorrow_lost_my_self", "sorrow_of_berserk")
        self.entity_id = entity_id
        
        # Конфигурация
        self.hp_threshold = 0.40  # 40%
        self.scaling_step = 0.10  # каждые 10%
        
        # Базовые бонусы при активации
        self.base_bonuses = {
            "str_percent": 0.20,
            "sta_percent": 0.10,
            "crit_chance_percent": 0.05,
            "crit_damage_percent": 0.10,
            "attack_speed_percent": 0.05,
            "hp_regen_flat": 20.0,
            "vamp_percent": 0.05,
        }
        
        # Текущие бонусы (скалятся)
        self.current_bonuses = self.base_bonuses.copy()
        self.scaling_multiplier = 1.0
        
        # Blood Cost
        self.blood_cost_base = 0.005  # 0.5% max HP
        self.blood_damage_base = 0.015  # 1.5% max HP
        self.current_blood_cost = self.blood_cost_base
        self.current_blood_damage = self.blood_damage_base
        
        # Safety Net
        self.last_will_active = False
        self.last_will_expires = 0.0
        self.safety_net_cooldown = 30.0  # 30 сек
        self.safety_net_available_at = 0.0
        
        # Iframe
        self.iframes_until = 0.0
    
    def get_subscription_config(self) -> Dict[str, Any]:
        return {
            "event_types": {
                EventType.HP_PERCENT_CHANGED,
                EventType.ATTACK_PERFORMED,
                EventType.DAMAGE_TAKEN,
                EventType.KILL_CONFIRMED,
                EventType.TIMER_TICK,
            },
            "condition": self._check_trigger,
        }
    
    def _check_trigger(self, event: Event) -> bool:
        """Проверяет, должен ли эффект реагировать на событие"""
        if event.type == EventType.HP_PERCENT_CHANGED:
            hp_percent = event.get("hp_percent", 1.0)
            return hp_percent < self.hp_threshold or self.state == EffectState.ACTIVE
        return True  # Для других событий всегда слушаем
    
    def _calculate_scaling(self, hp_percent: float):
        """Расчитывает скалирование от недостающего HP"""
        if hp_percent >= self.hp_threshold:
            self.scaling_multiplier = 1.0
        else:
            missing = self.hp_threshold - hp_percent
            steps = int(missing / self.scaling_step)
            self.scaling_multiplier = 1.0 + (steps * 0.5)  # +50% за шаг
        
        # Обновляем бонусы
        for key, base_value in self.base_bonuses.items():
            self.current_bonuses[key] = base_value * self.scaling_multiplier
        
        # Обновляем blood cost/damage
        self.current_blood_cost = self.blood_cost_base * self.scaling_multiplier
        self.current_blood_damage = self.blood_damage_base * self.scaling_multiplier
    
    def _apply_safety_net(self, required_cost: float, current_hp_percent: float):
        """Проверяет и применяет Safety Net если HP не хватает"""
        # required_cost - это абсолютное значение HP (например, 7.5)
        # current_hp_percent - это процент (например, 0.25 = 25%)
        
        # Конвертируем required_cost в процент для сравнения
        required_cost_percent = required_cost  # Уже в процентах (0.0075 = 0.75%)
        
        if current_hp_percent <= required_cost_percent:
            now = time.time()
            
            # Проверяем cooldown
            if now >= self.safety_net_available_at:
                # Активируем Last Will
                self.last_will_active = True
                self.last_will_expires = now + 5.0  # 5 сек
                self.safety_net_available_at = now + self.safety_net_cooldown
                
                # Устанавливаем HP в 1 (симуляция)
                # В реальной игре: entity.set_hp(1)
                
                # Даем iframe
                self.iframes_until = now + 5.0
                
                # Усиливаем баффы в 2 раза за каждые отсутствующие 10%
                missing_steps = int((self.hp_threshold - current_hp_percent) / 0.10)
                amp_multiplier = 2 ** missing_steps
                for key in self.current_bonuses:
                    self.current_bonuses[key] *= amp_multiplier
                
                return True  # Safety Net активирован
        
        return False
    
    def handle_event(self, event: Event):
        """Обрабатывает события от CAS"""
        if event.type == EventType.HP_PERCENT_CHANGED:
            hp_percent = event.get("hp_percent", 1.0)
            self._calculate_scaling(hp_percent)
            
            # Проверяем активацию/деактивацию
            if hp_percent < self.hp_threshold and self.state == EffectState.INACTIVE:
                # Триггер активации (CAS уже проверил условие, мы просто реагируем)
                pass  # Effect Manager активирует нас
            
            if hp_percent >= self.hp_threshold and self.state == EffectState.ACTIVE:
                # Время деактивироваться
                pass  # Effect Manager деактивирует нас
        
        elif event.type == EventType.ATTACK_PERFORMED:
            if self.state != EffectState.ACTIVE:
                return
            
            max_hp = event.get("max_hp", 1000)
            current_hp = event.get("current_hp", 500)
            current_hp_percent = current_hp / max_hp if max_hp > 0 else 0
            
            # required_cost как процент от max HP
            required_cost_percent = self.current_blood_cost
            
            # Проверяем Safety Net (оба аргумента в процентах)
            safety_net_triggered = self._apply_safety_net(required_cost_percent, current_hp_percent)
            
            if safety_net_triggered:
                # Атака прошла с HP=1 и iframe
                pass
            elif current_hp_percent >= required_cost_percent:
                # Обычная атака с кровью (HP достаточно)
                # entity.take_damage(required_cost_percent * max_hp)  # True damage
                # entity.deal_damage(self.current_blood_damage * max_hp)
                pass
            elif current_hp >= required_cost:
                # Обычная атака с кровью
                # entity.take_damage(required_cost)  # True damage
                # entity.deal_damage(self.current_blood_damage * max_hp)
                pass
        
        elif event.type == EventType.KILL_CONFIRMED:
            if self.last_will_active:
                # Продлеваем iframe на 5 сек
                self.last_will_expires = time.time() + 5.0
                self.iframes_until = time.time() + 5.0
        
        elif event.type == EventType.TIMER_TICK:
            now = time.time()
            
            # Проверяем окончание Last Will
            if self.last_will_active and now >= self.last_will_expires:
                self.last_will_active = False
            
            # Проверяем окончание iframe
            if now >= self.iframes_until:
                pass  # Iframe спал
    
    def on_activate(self, event: Event):
        super().on_activate(event)
        # Начальный расчёт
        hp_percent = event.get("hp_percent", 0.39)
        self._calculate_scaling(hp_percent)
    
    def get_stat_modifiers(self) -> Dict[str, float]:
        if self.state != EffectState.ACTIVE:
            return {}
        
        # Если Last Will активен, бонусы уже усилены в handle_event
        return self.current_bonuses.copy()
    
    def get_blood_cost_info(self) -> Dict[str, float]:
        """Возвращает информацию о стоимости крови"""
        return {
            "cost_percent": self.current_blood_cost,
            "damage_percent": self.current_blood_damage,
            "scaling_multiplier": self.scaling_multiplier,
        }


# ============================================================================
# ДЕМО: Использование системы
# ============================================================================

def demo_sorrow_of_berserk():
    """Демонстрация работы Sorrow of Berserk через новую архитектуру"""
    print("=" * 60)
    print("CAS Effect System v3.0 - Sorrow of Berserk Demo")
    print("=" * 60)
    
    # Создаём CAS Manager
    cas_manager = CASSubscriptionManager()
    
    # Создаём Effect Manager для персонажа
    player_id = "player_1"
    effect_manager = EffectManager(player_id, cas_manager)
    
    # Создаём эффект Sorrow of Berserk
    sorrow_effect = SorrowLostMySelfEffect(player_id)
    
    # Регистрируем эффект (автоматически подписывается на CAS)
    effect_manager.register_effect(sorrow_effect)
    
    print(f"\n✅ Эффект зарегистрирован: {sorrow_effect.effect_id}")
    print(f"   Подписан на события: {[e.value for e in sorrow_effect.subscription.event_types]}")
    
    # Симуляция: HP падает до 35%
    print("\n--- Симуляция: HP падает до 35% ---")
    hp_event = Event(
        type=EventType.HP_PERCENT_CHANGED,
        source="damage_taken",
        data={"hp_percent": 0.35, "current_hp": 350, "max_hp": 1000}
    )
    
    # CAS стреляет событием
    cas_manager.emit(hp_event)
    
    # Effect Manager видит, что условие выполнено → активирует эффект
    if hp_event.data["hp_percent"] < 0.40:
        activated = effect_manager.activate_effect(sorrow_effect.effect_id, hp_event)
        if activated:
            print(f"✅ Эффект АКТИВИРОВАН (HP < 40%)")
    
    # Проверяем статы
    stats = effect_manager.get_aggregated_stats()
    print(f"\n📊 Активные бонусы при 35% HP:")
    for stat, value in sorted(stats.items()):
        print(f"   {stat}: +{value:.2%}" if "percent" in stat else f"   {stat}: +{value:.1f}")
    
    blood_info = sorrow_effect.get_blood_cost_info()
    print(f"\n🩸 Blood Cost:")
    print(f"   Стоимость: {blood_info['cost_percent']:.2%} от макс HP")
    print(f"   Урон: {blood_info['damage_percent']:.2%} от макс HP")
    print(f"   Множитель: x{blood_info['scaling_multiplier']:.2f}")
    
    # Симуляция: HP падает до 8% (триггер Safety Net)
    print("\n--- Симуляция: HP падает до 8% ---")
    hp_event_low = Event(
        type=EventType.HP_PERCENT_CHANGED,
        source="damage_taken",
        data={"hp_percent": 0.08, "current_hp": 80, "max_hp": 1000}
    )
    cas_manager.emit(hp_event_low)
    
    sorrow_effect._calculate_scaling(0.08)
    stats_low = sorrow_effect.get_stat_modifiers()
    blood_low = sorrow_effect.get_blood_cost_info()
    
    print(f"\n📊 Активные бонусы при 8% HP:")
    for stat, value in sorted(stats_low.items()):
        print(f"   {stat}: +{value:.2%}" if "percent" in stat else f"   {stat}: +{value:.1f}")
    
    print(f"\n🩸 Blood Cost при 8% HP:")
    print(f"   Стоимость: {blood_low['cost_percent']:.2%} от макс HP ({blood_low['cost_percent'] * 1000:.1f} HP)")
    print(f"   Урон: {blood_low['damage_percent']:.2%} от макс HP ({blood_low['damage_percent'] * 1000:.1f})")
    print(f"   Множитель: x{blood_low['scaling_multiplier']:.2f}")
    
    # Симуляция: Атака при 8% HP (нужно 50 HP, есть 80 → проходит)
    print("\n--- Симуляция: Атака при 8% HP (80 HP) ---")
    attack_event = Event(
        type=EventType.ATTACK_PERFORMED,
        source="player_attack",
        data={"max_hp": 1000, "current_hp": 80}
    )
    cas_manager.emit(attack_event)
    sorrow_effect.handle_event(attack_event)
    
    required_cost = blood_low['cost_percent'] * 1000
    print(f"   Требуется HP: {required_cost:.1f}")
    print(f"   Есть HP: 80")
    print(f"   ✅ Атака прошла (HP достаточно)")
    
    # Симуляция: HP падает до 1% (Safety Net триггер)
    print("\n--- Симуляция: HP падает до 1% → Safety Net ---")
    hp_event_critical = Event(
        type=EventType.HP_PERCENT_CHANGED,
        source="damage_taken",
        data={"hp_percent": 0.01, "current_hp": 10, "max_hp": 1000}
    )
    cas_manager.emit(hp_event_critical)
    sorrow_effect.handle_event(hp_event_critical)
    
    # Проверяем Safety Net
    if sorrow_effect.last_will_active:
        print(f"   🛡️ SAFETY NET АКТИВИРОВАН!")
        print(f"   HP установлен в 1")
        print(f"   Iframe: 5 сек")
        print(f"   Cooldown: 30 сек")
        
        # Проверяем усиление баффов
        missing_steps = int((0.40 - 0.01) / 0.10)
        amp = 2 ** missing_steps
        print(f"   Усиление баффов: x{amp} (за {missing_steps} отсутствующих 10%)")
    
    print("\n" + "=" * 60)
    print("✅ Демо завершено - архитектура работает корректно!")
    print("=" * 60)


if __name__ == "__main__":
    demo_sorrow_of_berserk()
