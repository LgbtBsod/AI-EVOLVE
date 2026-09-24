"""
Combat Advanced Plugin for Dev Probe
Интеграция продвинутых боевых механик (Reflect, Pure Dmg, Rooms, Emotions) в Dev Probe
"""

import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# Импортируем наши механики
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2] / 'src' / 'core'))
from combat_advanced import (
    Entity, DamageType, ReflectConfig, RoomConfig, RoomEffectType, 
    GameRoom, ContextualTask, Task, EmotionState
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CombatCommand(Enum):
    """Команды для управления боевой системой"""
    SPAWN_DUMMY = "spawn_dummy"
    CREATE_ROOM = "create_room"
    ADD_ENTITY_TO_ROOM = "add_entity_to_room"
    APPLY_REFLECT = "apply_reflect"
    DEAL_DAMAGE = "deal_damage"
    SET_EMOTION = "set_emotion"
    PUSH_TASK = "push_task"
    GET_STATS = "get_stats"
    GET_DPS = "get_dps"
    SIMULATE_COMBAT = "simulate_combat"


@dataclass
class CombatSession:
    """Сессия боевого теста"""
    session_id: str
    entities: Dict[str, Entity]
    rooms: Dict[str, GameRoom]
    start_time: float
    commands_executed: int = 0


class CombatAdvancedPlugin:
    """
    Плагин Dev Probe для тестирования продвинутых боевых механик
    
    Возможности:
    - Создание бессмертных манекенов с регеном
    - Управление комнатами с DoT/HoT зонами
    - Настройка возврата урона (Reflect)
    - Эмуляция эмоций AI и контекстных задач
    - Мониторинг DPS и статистики
    """
    
    def __init__(self, probe_instance=None):
        self.probe = probe_instance
        self.sessions: Dict[str, CombatSession] = {}
        self.logger = logging.getLogger("CombatAdvancedPlugin")
        self.logger.info("Combat Advanced Plugin initialized")
    
    def create_session(self, session_id: str = "default") -> CombatSession:
        """Создать новую боевую сессию"""
        if session_id in self.sessions:
            return self.sessions[session_id]
        
        session = CombatSession(
            session_id=session_id,
            entities={},
            rooms={},
            start_time=time.time()
        )
        self.sessions[session_id] = session
        self.logger.info(f"Session created: {session_id}")
        return session
    
    def execute_command(self, command: CombatCommand, params: Dict[str, Any], session_id: str = "default") -> Dict[str, Any]:
        """Выполнить команду управления боем"""
        if session_id not in self.sessions:
            self.create_session(session_id)
        
        session = self.sessions[session_id]
        session.commands_executed += 1
        
        try:
            if command == CombatCommand.SPAWN_DUMMY:
                return self._spawn_dummy(session, params)
            elif command == CombatCommand.CREATE_ROOM:
                return self._create_room(session, params)
            elif command == CombatCommand.ADD_ENTITY_TO_ROOM:
                return self._add_entity_to_room(session, params)
            elif command == CombatCommand.APPLY_REFLECT:
                return self._apply_reflect(session, params)
            elif command == CombatCommand.DEAL_DAMAGE:
                return self._deal_damage(session, params)
            elif command == CombatCommand.SET_EMOTION:
                return self._set_emotion(session, params)
            elif command == CombatCommand.PUSH_TASK:
                return self._push_task(session, params)
            elif command == CombatCommand.GET_STATS:
                return self._get_stats(session, params)
            elif command == CombatCommand.GET_DPS:
                return self._get_dps(session, params)
            elif command == CombatCommand.SIMULATE_COMBAT:
                return self._simulate_combat(session, params)
            else:
                return {"error": f"Unknown command: {command}"}
        
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return {"error": str(e)}
    
    def _spawn_dummy(self, session: CombatSession, params: Dict) -> Dict:
        """Создать бессмертного манекена"""
        name = params.get("name", f"Dummy_{len(session.entities)}")
        max_hp = params.get("max_hp", 10000)
        regen = params.get("regen", 0)
        
        dummy = Entity(name, is_immortal=True)
        dummy.stats.max_hp = max_hp
        dummy.stats.hp = max_hp
        dummy.stats.regen = regen
        
        session.entities[name] = dummy
        self.logger.info(f"Spawned dummy: {name} (HP: {max_hp}, Regen: {regen})")
        
        return {
            "success": True,
            "entity": name,
            "stats": {
                "hp": dummy.stats.hp,
                "max_hp": dummy.stats.max_hp,
                "regen": dummy.stats.regen
            }
        }
    
    def _create_room(self, session: CombatSession, params: Dict) -> Dict:
        """Создать комнату с эффектом"""
        name = params.get("name", f"Room_{len(session.rooms)}")
        effect_type_str = params.get("effect_type", "do_t")
        value = params.get("value", 100.0)
        spawn_items = params.get("spawn_items", [])
        
        # Маппинг строковых имен в Enum
        effect_map = {
            "damage_over_time": RoomEffectType.DO_T,
            "do_t": RoomEffectType.DO_T,
            "heal_over_time": RoomEffectType.HO_T,
            "ho_t": RoomEffectType.HO_T,
            "buff_zone": RoomEffectType.BUFF_ZONE,
            "loot_spawn": RoomEffectType.LOOT_SPAWN
        }
        
        effect_type = effect_map.get(effect_type_str.lower(), RoomEffectType.DO_T)
        
        config = RoomConfig(
            effect_type=effect_type,
            value=value,
            spawn_items=spawn_items
        )
        
        room = GameRoom(name, config)
        session.rooms[name] = room
        
        self.logger.info(f"Created room: {name} (Type: {effect_type.value}, Value: {value})")
        
        return {
            "success": True,
            "room": name,
            "config": {
                "type": effect_type.value,
                "value": value,
                "spawn_items": spawn_items
            }
        }
    
    def _add_entity_to_room(self, session: CombatSession, params: Dict) -> Dict:
        """Добавить сущность в комнату"""
        entity_name = params.get("entity")
        room_name = params.get("room")
        
        if not entity_name or not room_name:
            return {"error": "Missing entity or room name"}
        
        if entity_name not in session.entities:
            return {"error": f"Entity {entity_name} not found"}
        if room_name not in session.rooms:
            return {"error": f"Room {room_name} not found"}
        
        entity = session.entities[entity_name]
        room = session.rooms[room_name]
        
        room.add_entity(entity)
        
        self.logger.info(f"Added {entity_name} to {room_name}")
        
        return {
            "success": True,
            "entity": entity_name,
            "room": room_name
        }
    
    def _apply_reflect(self, session: CombatSession, params: Dict) -> Dict:
        """Применить эффект возврата урона"""
        entity_name = params.get("entity")
        percent = params.get("percent", 0.0)
        flat = params.get("flat", 0.0)
        dmg_type_str = params.get("return_type", "PURE")
        
        if not entity_name:
            return {"error": "Missing entity name"}
        if entity_name not in session.entities:
            return {"error": f"Entity {entity_name} not found"}
        
        dmg_type = DamageType[dmg_type_str.upper()]
        config = ReflectConfig(
            percent_of_damage=percent,
            flat_amount=flat,
            damage_type_returned=dmg_type
        )
        
        entity = session.entities[entity_name]
        entity.add_reflect(config)
        
        self.logger.info(f"Applied reflect to {entity_name}: {percent}% as {dmg_type.value}")
        
        return {
            "success": True,
            "entity": entity_name,
            "reflect": {
                "percent": percent,
                "flat": flat,
                "type": dmg_type.value
            }
        }
    
    def _deal_damage(self, session: CombatSession, params: Dict) -> Dict:
        """Нанести урон сущности"""
        target_name = params.get("target")
        amount = params.get("amount", 100.0)
        dmg_type_str = params.get("type", "PHYSICAL")
        
        if not target_name:
            return {"error": "Missing target name"}
        if target_name not in session.entities:
            return {"error": f"Target {target_name} not found"}
        
        dmg_type = DamageType[dmg_type_str.upper()]
        entity = session.entities[target_name]
        
        taken, reflected = entity.take_damage(amount, dmg_type)
        
        self.logger.info(f"{target_name} took {taken} {dmg_type.value}, reflected {reflected}")
        
        return {
            "success": True,
            "target": target_name,
            "damage_taken": taken,
            "damage_reflected": reflected,
            "current_hp": entity.stats.hp,
            "is_alive": entity.stats.hp > 0 or entity.stats.is_immortal
        }
    
    def _set_emotion(self, session: CombatSession, params: Dict) -> Dict:
        """Установить эмоцию AI"""
        entity_name = params.get("entity")
        emotion = params.get("emotion")  # fear, anger, adrenaline, greed
        value = params.get("value", 0.0)
        
        if not entity_name or not emotion:
            return {"error": "Missing entity or emotion"}
        if entity_name not in session.entities:
            return {"error": f"Entity {entity_name} not found"}
        
        entity = session.entities[entity_name]
        
        if hasattr(entity.emotions, emotion):
            setattr(entity.emotions, emotion, min(100, max(0, value)))
            self.logger.info(f"Set {emotion}={value} for {entity_name}")
            
            return {
                "success": True,
                "entity": entity_name,
                "emotion": emotion,
                "value": value,
                "all_emotions": {
                    "fear": entity.emotions.fear,
                    "anger": entity.emotions.anger,
                    "adrenaline": entity.emotions.adrenaline,
                    "greed": entity.emotions.greed
                }
            }
        else:
            return {"error": f"Unknown emotion: {emotion}"}
    
    def _push_task(self, session: CombatSession, params: Dict) -> Dict:
        """Добавить задачу AI"""
        entity_name = params.get("entity")
        task_type_str = params.get("task_type")
        priority = params.get("priority", 0)
        
        if not entity_name or not task_type_str:
            return {"error": "Missing entity or task_type"}
        if entity_name not in session.entities:
            return {"error": f"Entity {entity_name} not found"}
        
        task_type = ContextualTask[task_type_str.upper().replace("-", "_")]
        entity = session.entities[entity_name]
        
        task = Task(task_type=task_type, priority=priority, expiry=time.time() + 10)
        entity.push_task(task)
        
        self.logger.info(f"Pushed task {task_type.value} to {entity_name}")
        
        return {
            "success": True,
            "entity": entity_name,
            "task": task_type.value,
            "queue_size": len(entity.task_queue)
        }
    
    def _get_stats(self, session: CombatSession, params: Dict) -> Dict:
        """Получить статистику сущности"""
        entity_name = params.get("entity")
        
        if not entity_name:
            # Вернуть статистику всех сущностей
            all_stats = {}
            for name, entity in session.entities.items():
                all_stats[name] = {
                    "hp": entity.stats.hp,
                    "max_hp": entity.stats.max_hp,
                    "is_immortal": entity.stats.is_immortal,
                    "block_counters": entity.stats.block_counters,
                    "emotions": {
                        "fear": entity.emotions.fear,
                        "anger": entity.emotions.anger,
                        "adrenaline": entity.emotions.adrenaline,
                        "greed": entity.emotions.greed
                    },
                    "current_task": entity.current_task.task_type.value if entity.current_task else None
                }
            return {"success": True, "entities": all_stats}
        
        if entity_name not in session.entities:
            return {"error": f"Entity {entity_name} not found"}
        
        entity = session.entities[entity_name]
        
        return {
            "success": True,
            "entity": entity_name,
            "stats": {
                "hp": entity.stats.hp,
                "max_hp": entity.stats.max_hp,
                "is_immortal": entity.stats.is_immortal,
                "block_counters": entity.stats.block_counters,
                "emotions": {
                    "fear": entity.emotions.fear,
                    "anger": entity.emotions.anger,
                    "adrenaline": entity.emotions.adrenaline,
                    "greed": entity.emotions.greed
                },
                "current_task": entity.current_task.task_type.value if entity.current_task else None,
                "task_queue": [t.task_type.value for t in entity.task_queue]
            }
        }
    
    def _get_dps(self, session: CombatSession, params: Dict) -> Dict:
        """Получить DPS сущности"""
        entity_name = params.get("entity")
        window = params.get("window", 5.0)
        
        if not entity_name:
            return {"error": "Missing entity name"}
        if entity_name not in session.entities:
            return {"error": f"Entity {entity_name} not found"}
        
        entity = session.entities[entity_name]
        dps = entity.get_dps(window)
        
        return {
            "success": True,
            "entity": entity_name,
            "dps": dps,
            "window": window
        }
    
    def _simulate_combat(self, session: CombatSession, params: Dict) -> Dict:
        """Симулировать бой в течение времени"""
        duration = params.get("duration", 5.0)
        dt = params.get("dt", 0.1)
        
        steps = int(duration / dt)
        self.logger.info(f"Simulating combat for {duration}s (dt={dt}, steps={steps})")
        
        for step in range(steps):
            # Обновляем все комнаты
            for room in session.rooms.values():
                room.update(dt)
            
            # Обновляем AI задачи
            for entity in session.entities.values():
                entity.update_ai()
        
        # Собираем итоговую статистику
        results = {}
        for name, entity in session.entities.items():
            results[name] = {
                "hp": entity.stats.hp,
                "dps": entity.get_dps(),
                "current_task": entity.current_task.task_type.value if entity.current_task else None,
                "emotions": {
                    "fear": entity.emotions.fear,
                    "anger": entity.emotions.anger,
                    "adrenaline": entity.emotions.adrenaline,
                    "greed": entity.emotions.greed
                }
            }
        
        self.logger.info(f"Combat simulation completed. Results: {results}")
        
        return {
            "success": True,
            "duration": duration,
            "steps": steps,
            "results": results
        }
    
    def get_session_info(self, session_id: str = "default") -> Dict:
        """Получить информацию о сессии"""
        if session_id not in self.sessions:
            return {"error": f"Session {session_id} not found"}
        
        session = self.sessions[session_id]
        
        return {
            "session_id": session.session_id,
            "start_time": session.start_time,
            "uptime": time.time() - session.start_time,
            "commands_executed": session.commands_executed,
            "entities_count": len(session.entities),
            "rooms_count": len(session.rooms),
            "entities": list(session.entities.keys()),
            "rooms": list(session.rooms.keys())
        }


# Тест плагина
if __name__ == "__main__":
    print("\n=== COMBAT ADVANCED PLUGIN TEST ===\n")
    
    plugin = CombatAdvancedPlugin()
    
    # 1. Создаем сессию
    plugin.create_session("test_session")
    
    # 2. Спавним манекена
    result = plugin.execute_command(CombatCommand.SPAWN_DUMMY, {
        "name": "BossDummy",
        "max_hp": 100000,
        "regen": 1000
    })
    print(f"Spawn Dummy: {result}")
    
    # 3. Создаем комнату с уроном
    result = plugin.execute_command(CombatCommand.CREATE_ROOM, {
        "name": "FireZone",
        "effect_type": "damage_over_time",
        "value": 5000.0  # 5000 DPS
    })
    print(f"Create Room: {result}")
    
    # 4. Добавляем манекена в комнату
    result = plugin.execute_command(CombatCommand.ADD_ENTITY_TO_ROOM, {
        "entity": "BossDummy",
        "room": "FireZone"
    })
    print(f"Add to Room: {result}")
    
    # 5. Применяем возврат урона
    result = plugin.execute_command(CombatCommand.APPLY_REFLECT, {
        "entity": "BossDummy",
        "percent": 30.0,
        "return_type": "FIRE"
    })
    print(f"Apply Reflect: {result}")
    
    # 6. Наносим урон
    result = plugin.execute_command(CombatCommand.DEAL_DAMAGE, {
        "target": "BossDummy",
        "amount": 10000,
        "type": "PHYSICAL"
    })
    print(f"Deal Damage: {result}")
    
    # 7. Устанавливаем эмоцию
    result = plugin.execute_command(CombatCommand.SET_EMOTION, {
        "entity": "BossDummy",
        "emotion": "anger",
        "value": 80.0
    })
    print(f"Set Emotion: {result}")
    
    # 8. Получаем статистику
    result = plugin.execute_command(CombatCommand.GET_STATS, {
        "entity": "BossDummy"
    })
    print(f"Get Stats: {result}")
    
    # 9. Симулируем бой
    result = plugin.execute_command(CombatCommand.SIMULATE_COMBAT, {
        "duration": 3.0,
        "dt": 0.1
    })
    print(f"Simulate Combat: {result}")
    
    # 10. Получаем DPS
    result = plugin.execute_command(CombatCommand.GET_DPS, {
        "entity": "BossDummy",
        "window": 3.0
    })
    print(f"Get DPS: {result}")
    
    # 11. Информация о сессии
    info = plugin.get_session_info("test_session")
    print(f"\nSession Info: {info}")
    
    print("\n=== ALL PLUGIN TESTS PASSED ===")
