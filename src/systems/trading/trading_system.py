from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from src.core.architecture import BaseComponent, ComponentType, Priority, LifecycleState
from src.core.constants import TradeType, TradeStatus, TradeCategory
from src.core.state_manager import StateManager, StateType
from typing import *
from typing import Dict, List, Optional, Callable, Any, Union, Tuple
import logging
import os
import random
import sys
import time

#!/usr/bin/env python3
"""Система торговли - управление торговлей между сущностями"""

logger = logging.getLogger(__name__)

# = ДОПОЛНИТЕЛЬНЫЕ ТИПЫ (НЕ ЦЕНТРАЛИЗОВАННЫЕ)

class CurrencyType(Enum):
    """Типы валют"""
    GOLD = "gold"
    SILVER = "silver"
    COPPER = "copper"
    CREDITS = "credits"
    REPUTATION = "reputation"

# = СТРУКТУРЫ ДАННЫХ

@dataclass
class TradeOffer:
    """Торговое предложение"""
    offer_id: str
    seller_id: str
    item_id: str
    item_count: int
    price: float
    currency: CurrencyType
    trade_type: TradeType
    category: TradeCategory
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    status: TradeStatus = TradeStatus.PENDING
    description: str = ""
    quality: float = 1.0
    requirements: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TradeItem:
    """Торговый предмет"""
    item_id: str
    name: str
    description: str
    category: TradeCategory
    base_price: float
    rarity: str = "common"
    weight: float = 0.0
    stackable: bool = True
    max_stack: int = 100
    tradeable: bool = True

@dataclass
class TradeHistory:
    """История торговли"""
    transaction_id: str
    buyer_id: str
    seller_id: str
    item_id: str
    item_count: int
    price: float
    currency: CurrencyType
    timestamp: float = field(default_factory=time.time)
    location: str = ""
    success: bool = True

@dataclass
class MarketData:
    """Рыночные данные"""
    item_id: str
    current_price: float
    average_price: float
    min_price: float
    max_price: float
    supply: int = 0
    demand: int = 0
    last_update: float = field(default_factory=time.time)
    price_history: List[float] = field(default_factory=list)

@dataclass
class TradeContract:
    """Торговый контракт"""
    contract_id: str
    parties: List[str] = field(default_factory=list)
    items: Dict[str, int] = field(default_factory=dict)
    total_value: float = 0.0
    currency: CurrencyType = CurrencyType.GOLD
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    status: TradeStatus = TradeStatus.PENDING
    terms: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TradeSession:
    """Торговая сессия"""
    session_id: str
    participants: List[str] = field(default_factory=list)
    offers: List[TradeOffer] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    location: str = ""
    status: TradeStatus = TradeStatus.PENDING

# = СИСТЕМА ТОРГОВЛИ

class TradingSystem(BaseComponent):
    """Система торговли"""
    
    def __init__(self):
        super().__init__(
            component_id="TradingSystem",
            component_type=ComponentType.SYSTEM,
            priority=Priority.NORMAL
        )
        
        # Торговые данные
        self.active_offers: Dict[str, TradeOffer] = {}
        self.completed_trades: List[TradeHistory] = []
        self.trade_sessions: Dict[str, TradeSession] = {}
        self.market_data: Dict[str, MarketData] = {}
        self.active_contracts: Dict[str, TradeContract] = {}
        self.completed_contracts: List[TradeContract] = []
        
        # Торговые предметы
        self.trade_items: Dict[str, TradeItem] = {}
        
        # Статистика
        self.stats = {
            "total_transactions": 0,
            "total_value": 0.0,
            "active_offers": 0,
            "completed_contracts": 0,
            "market_updates": 0
        }
        
        # Callbacks
        self.trade_callbacks: Dict[str, Callable] = {}
        self.completion_callbacks: List[Callable] = []
        self.market_callbacks: List[Callable] = []
        
        # Настройки
        self.settings = {
            "max_active_offers": 1000,
            "transaction_fee": 0.05,  # 5%
            "tax_rate": 0.02,  # 2%
            "reputation_impact": 0.1,
            "price_volatility": 0.1,
            "market_update_interval": 3600.0,  # 1 час
            "offer_expiry_time": 86400.0  # 24 часа
        }

    def _on_initialize(self) -> bool:
        """Инициализация системы торговли"""
        try:
            self._logger.info("Инициализация системы торговли")
            
            # Загрузка торговых предметов
            self._load_trade_items()
            
            # Инициализация рыночных данных
            self._initialize_market_data()
            
            # Регистрация callbacks
            self._register_callbacks()
            
            self._logger.info("Система торговли инициализирована")
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка инициализации системы торговли: {e}")
            return False

    def _load_trade_items(self):
        """Загрузка торговых предметов"""
        try:
            # Базовые предметы
            self._add_trade_item(TradeItem(
                item_id="iron_sword",
                name="Железный меч",
                description="Надежный железный меч",
                category=TradeCategory.WEAPONS,
                base_price=100.0,
                rarity="common",
                weight=2.0
            ))
            
            self._add_trade_item(TradeItem(
                item_id="leather_armor",
                name="Кожаная броня",
                description="Легкая кожаная броня",
                category=TradeCategory.ARMOR,
                base_price=80.0,
                rarity="common",
                weight=3.0
            ))
            
            self._add_trade_item(TradeItem(
                item_id="health_potion",
                name="Зелье здоровья",
                description="Восстанавливает здоровье",
                category=TradeCategory.CONSUMABLES,
                base_price=25.0,
                rarity="common",
                weight=0.5,
                stackable=True,
                max_stack=50
            ))
            
            self._add_trade_item(TradeItem(
                item_id="iron_ingot",
                name="Железный слиток",
                description="Качественный железный слиток",
                category=TradeCategory.MATERIALS,
                base_price=15.0,
                rarity="common",
                weight=1.0,
                stackable=True,
                max_stack=100
            ))
            
            self._logger.info(f"Загружено {len(self.trade_items)} торговых предметов")
            
        except Exception as e:
            self._logger.error(f"Ошибка загрузки торговых предметов: {e}")

    def _initialize_market_data(self):
        """Инициализация рыночных данных"""
        try:
            for item_id, item in self.trade_items.items():
                market_data = MarketData(
                    item_id=item_id,
                    current_price=item.base_price,
                    average_price=item.base_price,
                    min_price=item.base_price * 0.8,
                    max_price=item.base_price * 1.2,
                    supply=random.randint(10, 100),
                    demand=random.randint(5, 50)
                )
                self.market_data[item_id] = market_data
            
            self._logger.info(f"Инициализированы рыночные данные для {len(self.market_data)} предметов")
            
        except Exception as e:
            self._logger.error(f"Ошибка инициализации рыночных данных: {e}")

    def _register_callbacks(self):
        """Регистрация callbacks"""
        try:
            # Callback для завершения торговли
            self.completion_callbacks.append(self._on_trade_completed)
            
            # Callback для обновления рынка
            self.market_callbacks.append(self._on_market_updated)
            
        except Exception as e:
            self._logger.error(f"Ошибка регистрации callbacks: {e}")

    def create_offer(self, seller_id: str, item_id: str, item_count: int, 
                    price: float, currency: CurrencyType = CurrencyType.GOLD,
                    trade_type: TradeType = TradeType.SELL) -> Optional[str]:
        """Создание торгового предложения"""
        try:
            # Проверка лимита предложений
            if len(self.active_offers) >= self.settings["max_active_offers"]:
                self._logger.warning("Достигнут лимит активных предложений")
                return None
            
            # Проверка существования предмета
            if item_id not in self.trade_items:
                self._logger.warning(f"Предмет {item_id} не найден в торговой системе")
                return None
            
            trade_item = self.trade_items[item_id]
            
            # Проверка возможности торговли
            if not trade_item.tradeable:
                self._logger.warning(f"Предмет {item_id} не подлежит торговле")
                return None
            
            # Проверка количества
            if item_count <= 0 or item_count > trade_item.max_stack:
                self._logger.warning(f"Недопустимое количество предметов: {item_count}")
                return None
            
            # Проверка цены
            if price <= 0:
                self._logger.warning("Цена должна быть положительной")
                return None
            
            # Создание предложения
            offer_id = f"offer_{seller_id}_{int(time.time())}"
            offer = TradeOffer(
                offer_id=offer_id,
                seller_id=seller_id,
                item_id=item_id,
                item_count=item_count,
                price=price,
                currency=currency,
                trade_type=trade_type,
                category=trade_item.category,
                expires_at=time.time() + self.settings["offer_expiry_time"],
                description=trade_item.description,
                quality=1.0
            )
            
            self.active_offers[offer_id] = offer
            
            # Обновление рыночных данных
            self._update_market_data(item_id, price, item_count, "supply")
            
            # Уведомление о создании предложения
            self._notify_offer_created(offer)
            
            self._logger.info(f"Создано предложение {offer_id} для предмета {item_id}")
            return offer_id
            
        except Exception as e:
            self._logger.error(f"Ошибка создания предложения: {e}")
            return None

    def accept_offer(self, buyer_id: str, offer_id: str) -> bool:
        """Принятие торгового предложения"""
        try:
            if offer_id not in self.active_offers:
                self._logger.warning(f"Предложение {offer_id} не найдено")
                return False
            
            offer = self.active_offers[offer_id]
            
            # Проверка срока действия
            if offer.expires_at and time.time() > offer.expires_at:
                self._logger.warning(f"Предложение {offer_id} истекло")
                offer.status = TradeStatus.EXPIRED
                return False
            
            # Проверка статуса
            if offer.status != TradeStatus.PENDING:
                self._logger.warning(f"Предложение {offer_id} недоступно")
                return False
            
            # Проверка средств покупателя
            if not self._check_buyer_funds(buyer_id, offer.price, offer.currency):
                self._logger.warning(f"Недостаточно средств у покупателя {buyer_id}")
                return False
            
            # Проверка наличия предметов у продавца
            if not self._check_seller_items(offer.seller_id, offer.item_id, offer.item_count):
                self._logger.warning(f"Недостаточно предметов у продавца {offer.seller_id}")
                return False
            
            # Выполнение сделки
            success = self._execute_trade(buyer_id, offer)
            
            if success:
                # Создание записи в истории
                transaction = TradeHistory(
                    transaction_id=f"trade_{int(time.time())}",
                    buyer_id=buyer_id,
                    seller_id=offer.seller_id,
                    item_id=offer.item_id,
                    item_count=offer.item_count,
                    price=offer.price,
                    currency=offer.currency,
                    timestamp=time.time(),
                    success=True
                )
                
                self.completed_trades.append(transaction)
                
                # Обновление статистики
                self.stats["total_transactions"] += 1
                self.stats["total_value"] += offer.price
                
                # Удаление предложения
                del self.active_offers[offer_id]
                
                # Обновление рыночных данных
                self._update_market_data(offer.item_id, offer.price, offer.item_count, "demand")
                
                # Уведомление о завершении сделки
                self._notify_trade_completed(transaction)
                
                self._logger.info(f"Сделка {transaction.transaction_id} завершена успешно")
                return True
            
            return False
            
        except Exception as e:
            self._logger.error(f"Ошибка принятия предложения: {e}")
            return False

    def _execute_trade(self, buyer_id: str, offer: TradeOffer) -> bool:
        """Выполнение торговой сделки"""
        try:
            # Расчет комиссии
            transaction_fee = offer.price * self.settings["transaction_fee"]
            tax_amount = offer.price * self.settings["tax_rate"]
            seller_receives = offer.price - transaction_fee - tax_amount
            
            # Списание средств у покупателя
            if not self._deduct_funds(buyer_id, offer.price, offer.currency):
                return False
            
            # Зачисление средств продавцу
            if not self._add_funds(offer.seller_id, seller_receives, offer.currency):
                # Возврат средств покупателю при ошибке
                self._add_funds(buyer_id, offer.price, offer.currency)
                return False
            
            # Передача предметов
            if not self._transfer_items(offer.seller_id, buyer_id, offer.item_id, offer.item_count):
                # Возврат средств при ошибке
                self._add_funds(buyer_id, offer.price, offer.currency)
                self._deduct_funds(offer.seller_id, seller_receives, offer.currency)
                return False
            
            # Обновление репутации
            self._update_reputation(buyer_id, offer.seller_id, offer.price)
            
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка выполнения сделки: {e}")
            return False

    def _check_buyer_funds(self, buyer_id: str, amount: float, currency: CurrencyType) -> bool:
        """Проверка средств покупателя"""
        try:
            # Здесь должна быть проверка баланса игрока
            # balance = self._get_player_balance(buyer_id, currency)
            # return balance >= amount
            return True  # Временно всегда True
            
        except Exception as e:
            self._logger.error(f"Ошибка проверки средств покупателя: {e}")
            return False

    def _check_seller_items(self, seller_id: str, item_id: str, count: int) -> bool:
        """Проверка наличия предметов у продавца"""
        try:
            # Здесь должна быть проверка инвентаря продавца
            # inventory = self._get_player_inventory(seller_id)
            # return inventory.get(item_id, 0) >= count
            return True  # Временно всегда True
            
        except Exception as e:
            self._logger.error(f"Ошибка проверки предметов продавца: {e}")
            return False

    def _deduct_funds(self, entity_id: str, amount: float, currency: CurrencyType) -> bool:
        """Списание средств"""
        try:
            # Здесь должно быть списание средств
            # self._update_player_balance(entity_id, currency, -amount)
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка списания средств: {e}")
            return False

    def _add_funds(self, entity_id: str, amount: float, currency: CurrencyType) -> bool:
        """Зачисление средств"""
        try:
            # Здесь должно быть зачисление средств
            # self._update_player_balance(entity_id, currency, amount)
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка зачисления средств: {e}")
            return False

    def _transfer_items(self, from_id: str, to_id: str, item_id: str, count: int) -> bool:
        """Передача предметов"""
        try:
            # Здесь должна быть передача предметов между инвентарями
            # self._remove_from_inventory(from_id, item_id, count)
            # self._add_to_inventory(to_id, item_id, count)
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка передачи предметов: {e}")
            return False

    def _update_reputation(self, buyer_id: str, seller_id: str, amount: float):
        """Обновление репутации"""
        try:
            reputation_change = amount * self.settings["reputation_impact"]
            # self._update_player_reputation(buyer_id, seller_id, reputation_change)
            
        except Exception as e:
            self._logger.error(f"Ошибка обновления репутации: {e}")

    def _update_market_data(self, item_id: str, price: float, quantity: int, type_: str):
        """Обновление рыночных данных"""
        try:
            if item_id not in self.market_data:
                return
            
            market_data = self.market_data[item_id]
            
            # Обновление цены
            market_data.current_price = price
            market_data.price_history.append(price)
            
            # Ограничение истории цен
            if len(market_data.price_history) > 100:
                market_data.price_history = market_data.price_history[-100:]
            
            # Обновление статистики
            if market_data.price_history:
                market_data.average_price = sum(market_data.price_history) / len(market_data.price_history)
                market_data.min_price = min(market_data.price_history)
                market_data.max_price = max(market_data.price_history)
            
            # Обновление спроса/предложения
            if type_ == "supply":
                market_data.supply += quantity
            elif type_ == "demand":
                market_data.demand += quantity
            
            market_data.last_update = time.time()
            
            # Уведомление об обновлении рынка
            self._notify_market_updated(item_id, market_data)
            
        except Exception as e:
            self._logger.error(f"Ошибка обновления рыночных данных: {e}")

    def get_market_data(self, item_id: str) -> Optional[MarketData]:
        """Получение рыночных данных"""
        return self.market_data.get(item_id)

    def get_active_offers(self, category: Optional[TradeCategory] = None, 
                         max_price: Optional[float] = None) -> List[TradeOffer]:
        """Получение активных предложений"""
        try:
            offers = []
            current_time = time.time()
            
            for offer in self.active_offers.values():
                # Проверка срока действия
                if offer.expires_at and current_time > offer.expires_at:
                    offer.status = TradeStatus.EXPIRED
                    continue
                
                # Фильтрация по категории
                if category and offer.category != category:
                    continue
                
                # Фильтрация по цене
                if max_price and offer.price > max_price:
                    continue
                
                offers.append(offer)
            
            return offers
            
        except Exception as e:
            self._logger.error(f"Ошибка получения активных предложений: {e}")
            return []

    def cancel_offer(self, offer_id: str, seller_id: str) -> bool:
        """Отмена торгового предложения"""
        try:
            if offer_id not in self.active_offers:
                return False
            
            offer = self.active_offers[offer_id]
            
            # Проверка владельца
            if offer.seller_id != seller_id:
                self._logger.warning(f"Попытка отмены чужого предложения {offer_id}")
                return False
            
            # Отмена предложения
            offer.status = TradeStatus.CANCELLED
            del self.active_offers[offer_id]
            
            self._logger.info(f"Предложение {offer_id} отменено")
            return True
            
        except Exception as e:
            self._logger.error(f"Ошибка отмены предложения: {e}")
            return False

    def _add_trade_item(self, item: TradeItem):
        """Добавление торгового предмета"""
        self.trade_items[item.item_id] = item

    def _notify_offer_created(self, offer: TradeOffer):
        """Уведомление о создании предложения"""
        try:
            for callback in self.trade_callbacks.get("offer_created", []):
                callback(offer)
        except Exception as e:
            self._logger.error(f"Ошибка уведомления о создании предложения: {e}")

    def _notify_trade_completed(self, transaction: TradeHistory):
        """Уведомление о завершении сделки"""
        try:
            for callback in self.completion_callbacks:
                callback(transaction)
        except Exception as e:
            self._logger.error(f"Ошибка уведомления о завершении сделки: {e}")

    def _notify_market_updated(self, item_id: str, market_data: MarketData):
        """Уведомление об обновлении рынка"""
        try:
            for callback in self.market_callbacks:
                callback(item_id, market_data)
        except Exception as e:
            self._logger.error(f"Ошибка уведомления об обновлении рынка: {e}")

    def _on_trade_completed(self, transaction: TradeHistory):
        """Callback при завершении сделки"""
        self._logger.debug(f"Сделка завершена: {transaction.item_id} x{transaction.item_count} за {transaction.price}")

    def _on_market_updated(self, item_id: str, market_data: MarketData):
        """Callback при обновлении рынка"""
        self._logger.debug(f"Рынок обновлен: {item_id} - цена: {market_data.current_price}")

    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики системы"""
        return {
            "total_items": len(self.trade_items),
            "active_offers": len(self.active_offers),
            "completed_trades": len(self.completed_trades),
            "market_items": len(self.market_data),
            "stats": self.stats.copy()
        }

    def update(self, delta_time: float):
        """Обновление системы торговли"""
        try:
            # Очистка истекших предложений
            current_time = time.time()
            expired_offers = []
            
            for offer_id, offer in self.active_offers.items():
                if offer.expires_at and current_time > offer.expires_at:
                    offer.status = TradeStatus.EXPIRED
                    expired_offers.append(offer_id)
            
            for offer_id in expired_offers:
                del self.active_offers[offer_id]
            
            # Обновление рыночных данных
            self.stats["market_updates"] += 1
            
        except Exception as e:
            self._logger.error(f"Ошибка обновления системы торговли: {e}")
