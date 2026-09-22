"""
Comprehensive test suite for new data layer modules
Tests SQLAlchemy models, native features, and integration
"""

import pytest
import asyncio
from datetime import datetime
from typing import List

# Import SQLAlchemy models
from data_layer.sqlalchemy_models import (
    Base, ItemModel, SkillModel, EntityModel, 
    LearningEvent, ItemAcquisitionEvent, SkillAcquisitionEvent,
    PerformanceMetric, SessionConfig,
    ItemType, Rarity, SkillType, Element, EventType,
    ItemCreate, SkillCreate, EntityUpdate,
    DatabaseManager, ItemRepository, SkillRepository, EntityRepository
)

# Import native features
from data_layer.native_features import (
    GameEvent, MetricPoint, QueryResult,
    TimeCached, memoize_with_key,
    RingBuffer, EventStream, BatchProcessor,
    timer_context, suppress_and_log,
    chunked, flatten, unique_everseen, running_average,
    detect_anomalies_zscore,
    compose, pipe, partial_apply,
    safe_json_dumps, compact_json_dumps
)


# === Tests for SQLAlchemy Models ===

class TestPydanticModels:
    """Тесты Pydantic моделей валидации"""
    
    def test_item_create_valid(self):
        item = ItemCreate(
            name="Sword of Fire",
            item_type=ItemType.WEAPON,
            rarity=Rarity.EPIC,
            base_stats={"damage": 50, "durability": 100},
            effects=["fire_damage", "life_steal"],
            min_level=15,
            source_types=["boss_drop", "crafting"]
        )
        assert item.name == "Sword of Fire"
        assert item.item_type == ItemType.WEAPON
        assert item.rarity == Rarity.EPIC
        assert item.min_level == 15
    
    def test_item_create_invalid_level(self):
        with pytest.raises(ValueError):
            ItemCreate(
                name="Invalid Sword",
                item_type=ItemType.WEAPON,
                min_level=150  # > 100
            )
    
    def test_skill_create_valid(self):
        skill = SkillCreate(
            name="Fireball",
            skill_type=SkillType.ACTIVE,
            element=Element.FIRE,
            base_power=75.5,
            cooldown=3.0,
            mana_cost=25,
            min_level=10
        )
        assert skill.name == "Fireball"
        assert skill.element == Element.FIRE
        assert skill.base_power == 75.5
    
    def test_entity_update_partial(self):
        update = EntityUpdate(level=5, current_hp=80.0)
        assert update.level == 5
        assert update.current_hp == 80.0
        assert update.experience is None


class TestORMModels:
    """Тесты ORM моделей"""
    
    def test_item_model_creation(self):
        item = ItemModel(
            item_id="item_001",
            name="Health Potion",
            item_type="consumable",
            rarity="common",
            base_stats={"heal_amount": 50},
            effects=["instant_heal"],
            min_level=1,
            source_types=["vendor", "drop"]
        )
        assert item.item_id == "item_001"
        assert item.to_dict()["name"] == "Health Potion"
    
    def test_item_model_from_pydantic(self):
        pydantic_item = ItemCreate(
            name="Magic Staff",
            item_type=ItemType.WEAPON,
            rarity=Rarity.RARE
        )
        orm_item = ItemModel.from_pydantic(pydantic_item, "item_002")
        assert orm_item.item_id == "item_002"
        assert orm_item.name == "Magic Staff"
        assert orm_item.rarity == "rare"
    
    def test_skill_model_conversion(self):
        skill = SkillModel(
            skill_id="skill_001",
            name="Ice Blast",
            skill_type="active",
            element="water",
            base_power=60.0
        )
        d = skill.to_dict()
        assert d["skill_id"] == "skill_001"
        assert "created_at" in d
    
    def test_entity_model_relationships(self):
        entity = EntityModel(
            entity_id="entity_001",
            entity_type="player",
            level=10,
            experience=5000.0,
            max_hp=500.0,
            current_hp=450.0
        )
        assert entity.entity_id == "entity_001"
        assert entity.level == 10


class TestDatabaseManager:
    """Тесты менеджера базы данных"""
    
    @pytest.mark.asyncio
    async def test_async_init(self):
        db_manager = DatabaseManager(
            db_url="sqlite+aiosqlite:///:memory:",
            echo=False
        )
        await db_manager.init_async()
        assert db_manager._async_engine is not None
        assert db_manager._async_session_factory is not None
        await db_manager.close()
    
    def test_sync_init(self):
        db_manager = DatabaseManager(
            db_url="sqlite:///:memory:",
            echo=False
        )
        db_manager.init_sync()
        assert db_manager._sync_engine is not None
        assert db_manager._sync_session_factory is not None


# === Tests for Native Features ===

class TestDataClasses:
    """Тесты data classes"""
    
    def test_game_event_immutable(self):
        event = GameEvent(
            event_type="level_up",
            entity_id="player_1",
            data={"old_level": 5, "new_level": 6}
        )
        # Frozen dataclass нельзя изменить напрямую
        with pytest.raises(Exception):  # AttributeError или FrozenInstanceError
            event.event_type = "skill_up"
    
    def test_game_event_with_data(self):
        event = GameEvent(
            event_type="combat",
            entity_id="player_1"
        )
        new_event = event.with_data(damage=50, target="enemy_1")
        assert new_event.data["damage"] == 50
        assert new_event.data["target"] == "enemy_1"
        # Оригинал не изменен
        assert event.data == {}
    
    def test_query_result_pagination(self):
        result = QueryResult(
            items=[1, 2, 3, 4, 5],
            total_count=47,
            page=1,
            page_size=10
        )
        assert result.total_pages == 5
        assert result.has_more is True
        assert result.next_page() == 2
        
        last_page = QueryResult(
            items=[41, 42, 43, 44, 45, 46, 47],
            total_count=47,
            page=5,
            page_size=10
        )
        assert last_page.has_more is False


class TestCaching:
    """Тесты кэширования"""
    
    def test_time_cached(self):
        call_count = 0
        
        @TimeCached(ttl_seconds=1)
        def expensive_operation(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        # Первый вызов - кэш miss
        result1 = expensive_operation(5)
        assert result1 == 10
        assert call_count == 1
        
        # Второй вызов - кэш hit
        result2 = expensive_operation(5)
        assert result2 == 10
        assert call_count == 1  # Не увеличился
        
        # После истечения TTL - кэш miss
        import time
        time.sleep(1.1)
        result3 = expensive_operation(5)
        assert result3 == 10
        assert call_count == 2


class TestRingBuffer:
    """Тесты циклического буфера"""
    
    def test_ring_buffer_capacity(self):
        buffer = RingBuffer[int](capacity=5)
        for i in range(10):
            buffer.append(i)
        
        assert len(buffer.get_all()) == 5
        assert buffer.get_all() == [5, 6, 7, 8, 9]
    
    def test_ring_buffer_average(self):
        buffer = RingBuffer(capacity=3)
        buffer.extend([10, 20, 30])
        assert buffer.average() == 20.0
        
        buffer.append(40)  # Вытесняет 10
        assert buffer.average() == 30.0  # (20+30+40)/3
    
    def test_ring_buffer_get_last(self):
        buffer = RingBuffer(capacity=10)
        buffer.extend(range(10))
        last_3 = buffer.get_last(3)
        assert last_3 == [7, 8, 9]


class TestEventStream:
    """Тесты потока событий"""
    
    def test_event_stream_aggregation(self):
        stream = EventStream()
        stream.add(GameEvent("level_up", "e1"))
        stream.add(GameEvent("level_up", "e2"))
        stream.add(GameEvent("skill_learned", "e1"))
        stream.add(GameEvent("combat", "e1"))
        
        agg = stream.aggregate_by_type()
        assert agg["level_up"] == 2
        assert agg["skill_learned"] == 1
        assert agg["combat"] == 1
    
    def test_event_stream_filter_by_type(self):
        stream = EventStream()
        stream.add(GameEvent("level_up", "e1"))
        stream.add(GameEvent("skill_learned", "e1"))
        stream.add(GameEvent("level_up", "e2"))
        
        level_events = list(stream.filter_by_type("level_up"))
        assert len(level_events) == 2
    
    def test_event_stream_filter_by_entity(self):
        stream = EventStream()
        stream.add(GameEvent("level_up", "player_1"))
        stream.add(GameEvent("combat", "enemy_1"))
        stream.add(GameEvent("skill_learned", "player_1"))
        
        player_events = list(stream.filter_by_entity("player_1"))
        assert len(player_events) == 2


class TestBatchProcessor:
    """Тесты пакетной обработки"""
    
    def test_batch_processor_auto_flush(self):
        processed_batches = []
        
        def process(batch):
            processed_batches.append(batch.copy())
            return len(batch)
        
        processor = BatchProcessor(batch_size=3, process_func=process)
        
        for i in range(5):
            processor.add(i)
        
        # Должен был сработать авто-флеш при 3 элементах
        assert len(processed_batches) == 1
        assert processed_batches[0] == [0, 1, 2]
        assert processor.pending_count == 2  # Осталось 2 элемента
    
    def test_batch_processor_manual_flush(self):
        processor = BatchProcessor(batch_size=100)
        processor.extend([1, 2, 3])
        assert processor.pending_count == 3
        
        processor.flush()
        assert processor.pending_count == 0


class TestUtilities:
    """Тесты утилит"""
    
    def test_chunked(self):
        data = list(range(10))
        chunks = list(chunked(data, 3))
        assert chunks == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]
    
    def test_flatten(self):
        nested = [[1, 2], [3, 4, 5], [6]]
        flat = list(flatten(nested))
        assert flat == [1, 2, 3, 4, 5, 6]
    
    def test_unique_everseen(self):
        data = [1, 2, 2, 3, 1, 4, 3]
        unique = list(unique_everseen(data))
        assert unique == [1, 2, 3, 4]
    
    def test_running_average(self):
        values = [10, 20, 30, 40, 50]
        averages = list(running_average(values, window_size=3))
        assert len(averages) == 5
        assert averages[0] == 10.0  # [10]
        assert averages[1] == 15.0  # [10, 20]
        assert averages[2] == 20.0  # [10, 20, 30]
        assert averages[3] == 30.0  # [20, 30, 40]
        assert averages[4] == 40.0  # [30, 40, 50]
    
    def test_detect_anomalies_zscore(self):
        values = [10, 12, 11, 13, 100, 12, 11]
        anomalies = detect_anomalies_zscore(values, threshold=2.0)
        assert len(anomalies) >= 1
        # 100 должно быть обнаружено как аномалия
        anomaly_indices = [a[0] for a in anomalies]
        assert 4 in anomaly_indices
    
    def test_compose_functions(self):
        add_one = lambda x: x + 1
        multiply_two = lambda x: x * 2
        square = lambda x: x ** 2
        
        # compose применяется справа налево: square(multiply_two(add_one(x)))
        composed = compose(square, multiply_two, add_one)
        result = composed(3)  # (3+1)*2 = 8, 8^2 = 64
        assert result == 64
    
    def test_pipe_functions(self):
        add_one = lambda x: x + 1
        multiply_two = lambda x: x * 2
        
        # pipe применяется слева направо: multiply_two(add_one(x))
        piped = pipe(add_one, multiply_two)
        result = piped(3)  # (3+1)*2 = 8
        assert result == 8
    
    def test_json_utils(self):
        obj = {"date": datetime(2024, 1, 15), "set": {1, 2, 3}}
        
        safe_json = safe_json_dumps(obj)
        assert "2024-01-15" in safe_json
        assert "[1, 2, 3]" in safe_json or "[2, 1, 3]" in safe_json  # set -> list
        
        compact = compact_json_dumps({"a": 1, "b": 2})
        assert compact == '{"a":1,"b":2}'  # Без пробелов


class TestContextManagers:
    """Тесты контекстных менеджеров"""
    
    def test_timer_context(self):
        import time
        with timer_context("test"):
            time.sleep(0.1)
        # Таймер должен отработать без ошибок
    
    def test_suppress_and_log(self):
        with suppress_and_log(ValueError, "Test error"):
            raise ValueError("This should be suppressed")
        # Исключение подавлено, код продолжается
    
    def test_suppress_and_log_no_exception(self):
        with suppress_and_log(ValueError, "No error"):
            pass  # Никакого исключения


# === Integration Tests ===

class TestIntegration:
    """Интеграционные тесты"""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Полный рабочий цикл: создание БД, добавление данных, запросы"""
        # Инициализация БД
        db_manager = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
        await db_manager.init_async()
        
        # Получение сессии
        async for session in db_manager.get_async_session():
            # Создание предмета через Pydantic
            item_data = ItemCreate(
                name="Dragon Slayer",
                item_type=ItemType.WEAPON,
                rarity=Rarity.LEGENDARY,
                base_stats={"damage": 150, "crit_chance": 0.25},
                effects=["dragon_bane", "fire_resist"],
                min_level=50,
                source_types=["raid_boss"]
            )
            
            # Создание ORM модели
            item = ItemModel.from_pydantic(item_data, "item_legendary_001")
            session.add(item)
            
            # Создание сущности
            entity = EntityModel(
                entity_id="player_001",
                entity_type="player",
                level=55,
                experience=125000.0,
                max_hp=1000.0,
                current_hp=950.0
            )
            session.add(entity)
            
            # Событие получения предмета
            acquisition = ItemAcquisitionEvent(
                entity_id="player_001",
                item_id="item_legendary_001",
                count=1,
                source="raid_completion"
            )
            session.add(acquisition)
            
            await session.commit()
            
            # Проверка через репозиторий
            repo = ItemRepository(session)
            retrieved = await repo.get(ItemModel, "item_legendary_001")
            
            assert retrieved is not None
            assert retrieved.name == "Dragon Slayer"
            assert retrieved.rarity == "legendary"
        
        await db_manager.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
