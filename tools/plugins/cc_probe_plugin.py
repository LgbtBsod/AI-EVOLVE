"""
CC Testing Plugin for Dev Probe
Позволяет AI агентам и тестировщикам управлять CC эффектами во время сессии.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import sys
sys.path.insert(0, '/workspace')

# Используем базовый класс плагина из ядра
from src.core.base_plugin import BasePlugin
from src.features.cc_system import (
    StatusEffectManager, 
    CharacterCCStats, 
    CCType, 
    BreakState
)

# Алиас для совместимости
BaseDevProbePlugin = BasePlugin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CC_Probe_Plugin")

class CCCommandType(Enum):
    """Типы команд для управления CC"""
    APPLY_STUN = "apply_stun"
    APPLY_KNOCKDOWN = "apply_knockdown"
    APPLY_SLOW = "apply_slow"
    APPLY_MICRO_STUN = "apply_micro_stun"
    DEAL_STAGGER_DMG = "deal_stagger_damage"
    GET_CC_STATUS = "get_cc_status"
    RESET_CC = "reset_cc"
    SIMULATE_BREAK_COMBO = "simulate_break_combo"

@dataclass
class CCTestResult:
    """Результат теста CC системы"""
    target_id: str
    break_triggered: bool
    cc_applied: Optional[CCType]
    stagger_current: float
    stagger_max: float
    break_duration: float
    damage_multiplier: float

class CCProbePlugin(BaseDevProbePlugin):
    """
    Плагин для Dev Probe: управление и тестирование CC механик.
    Позволяет AI агентам подавать команды на применение эффектов.
    """
    
    def __init__(self, probe_instance=None):
        super().__init__(probe_instance)
        self.name = "CCProbePlugin"
        self.version = "1.0.0"
        self.description = "Управление Crowd Control и Break системами"
        
        # Хранилище менеджеров эффектов для разных целей
        self.cc_managers: Dict[str, StatusEffectManager] = {}
        self.test_results: List[CCTestResult] = []
        
        logger.info(f"[{self.name}] Инициализирован")

    def register_entity(self, entity_id: str, stats: CharacterCCStats) -> StatusEffectManager:
        """Регистрирует сущность для управления CC"""
        manager = StatusEffectManager(stats)
        self.cc_managers[entity_id] = manager
        logger.info(f"[{self.name}] Зарегистрирована сущность {entity_id}")
        return manager

    def execute_command(self, command_type: CCCommandType, params: dict) -> dict:
        """
        Выполняет команду управления CC.
        Вызывается AI агентом или тестом.
        """
        logger.info(f"[{self.name}] Команда: {command_type.name}, Params: {params}")
        
        try:
            if command_type == CCCommandType.APPLY_STUN:
                return self._apply_cc(params, CCType.STUN)
                
            elif command_type == CCCommandType.APPLY_KNOCKDOWN:
                return self._apply_cc(params, CCType.KNOCKDOWN)
                
            elif command_type == CCCommandType.APPLY_SLOW:
                return self._apply_cc(params, CCType.SLOW)
                
            elif command_type == CCCommandType.APPLY_MICRO_STUN:
                return self._apply_cc(params, CCType.MICRO_STUN)
                
            elif command_type == CCCommandType.DEAL_STAGGER_DMG:
                return self._deal_stagger_damage(params)
                
            elif command_type == CCCommandType.GET_CC_STATUS:
                return self._get_status(params)
                
            elif command_type == CCCommandType.RESET_CC:
                return self._reset_cc(params)
                
            elif command_type == CCCommandType.SIMULATE_BREAK_COMBO:
                return self._simulate_break_combo(params)
                
            else:
                return {"success": False, "error": f"Неизвестная команда: {command_type}"}
                
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка выполнения команды: {e}")
            return {"success": False, "error": str(e)}

    def _apply_cc(self, params: dict, cc_type: CCType) -> dict:
        """Применяет эффект контроля"""
        target_id = params.get("target_id")
        duration = params.get("duration", 2.0)
        source_id = params.get("source_id", "unknown")
        
        if not target_id or target_id not in self.cc_managers:
            return {"success": False, "error": f"Цель {target_id} не найдена"}
        
        manager = self.cc_managers[target_id]
        manager.apply_cc(cc_type, duration, source_id)
        
        return {
            "success": True,
            "action": "apply_cc",
            "type": cc_type.name,
            "target": target_id,
            "duration": duration
        }

    def _deal_stagger_damage(self, params: dict) -> dict:
        """Наносит урон по стойке"""
        target_id = params.get("target_id")
        damage = params.get("damage", 100.0)
        
        if not target_id or target_id not in self.cc_managers:
            return {"success": False, "error": f"Цель {target_id} не найдена"}
        
        manager = self.cc_managers[target_id]
        was_broken = manager.break_state == BreakState.BROKEN
        
        manager.take_stagger_damage(damage)
        
        is_broken_now = manager.break_state == BreakState.BROKEN
        break_triggered = is_broken_now and not was_broken
        
        result = CCTestResult(
            target_id=target_id,
            break_triggered=break_triggered,
            cc_applied=None,
            stagger_current=manager.stagger.current,
            stagger_max=manager.stagger.max_stagger,
            break_duration=manager.break_timer if is_broken_now else 0.0,
            damage_multiplier=1.15 if is_broken_now else 1.0
        )
        self.test_results.append(result)
        
        return {
            "success": True,
            "action": "stagger_damage",
            "target": target_id,
            "damage_dealt": damage,
            "stagger_current": manager.stagger.current,
            "stagger_max": manager.stagger.max_stagger,
            "break_triggered": break_triggered,
            "is_broken": is_broken_now,
            "break_duration": manager.break_timer if is_broken_now else 0.0
        }

    def _get_status(self, params: dict) -> dict:
        """Возвращает текущий статус CC цели"""
        target_id = params.get("target_id")
        
        if not target_id or target_id not in self.cc_managers:
            return {"success": False, "error": f"Цель {target_id} не найдена"}
        
        manager = self.cc_managers[target_id]
        status = manager.get_current_status()
        
        return {
            "success": True,
            "target": target_id,
            "status": status.name if status else None,
            "break_state": manager.break_state.name,
            "break_timer": manager.break_timer,
            "stagger_current": manager.stagger.current,
            "stagger_max": manager.stagger.max_stagger,
            "active_effects_count": len(manager.active_effects),
            "is_immobilized": manager.is_cc_immobilized()
        }

    def _reset_cc(self, params: dict) -> dict:
        """Сбрасывает все CC эффекты у цели"""
        target_id = params.get("target_id")
        
        if not target_id or target_id not in self.cc_managers:
            return {"success": False, "error": f"Цель {target_id} не найдена"}
        
        manager = self.cc_managers[target_id]
        manager.break_state = BreakState.NORMAL
        manager.break_timer = 0.0
        manager.stagger.reset()
        manager.active_effects.clear()
        manager.is_interrupted = False
        
        return {
            "success": True,
            "action": "reset_cc",
            "target": target_id
        }

    def _simulate_break_combo(self, params: dict) -> dict:
        """
        Симулирует комбо: дебаф -> накопление стойки -> брейк -> урон.
        Для тестирования полной цепочки.
        """
        target_id = params.get("target_id")
        stagger_hits = params.get("hits", 5)
        hit_damage = params.get("hit_damage", 200.0)
        base_damage = params.get("base_damage", 1000.0)
        
        if not target_id or target_id not in self.cc_managers:
            return {"success": False, "error": f"Цель {target_id} не найдена"}
        
        manager = self.cc_managers[target_id]
        
        # Шаг 1: Накладываем дебаф
        manager.apply_cc(CCType.SLOW, 5.0, "combo_setup")
        
        # Шаг 2: Наносим удары по стойке
        for i in range(stagger_hits):
            if manager.break_state == BreakState.BROKEN:
                break
            manager.take_stagger_damage(hit_damage)
        
        # Шаг 3: Если брейк случился, наносим урон с множителем
        damage_dealt = base_damage
        if manager.break_state == BreakState.BROKEN:
            damage_dealt = manager.take_damage_with_cc_mods(base_damage)
        
        result = CCTestResult(
            target_id=target_id,
            break_triggered=manager.break_state == BreakState.BROKEN,
            cc_applied=CCType.SLOW,
            stagger_current=manager.stagger.current,
            stagger_max=manager.stagger.max_stagger,
            break_duration=manager.break_timer,
            damage_multiplier=damage_dealt / base_damage if base_damage > 0 else 0
        )
        self.test_results.append(result)
        
        return {
            "success": True,
            "action": "break_combo_simulated",
            "target": target_id,
            "break_achieved": manager.break_state == BreakState.BROKEN,
            "break_duration": manager.break_timer,
            "damage_with_bonus": damage_dealt,
            "damage_multiplier": f"{(damage_dealt/base_damage)*100:.1f}%" if base_damage > 0 else "N/A"
        }

    def get_statistics(self) -> dict:
        """Возвращает статистику по всем тестам CC"""
        total_tests = len(self.test_results)
        breaks_triggered = sum(1 for r in self.test_results if r.break_triggered)
        
        return {
            "plugin": self.name,
            "version": self.version,
            "total_entities": len(self.cc_managers),
            "total_tests": total_tests,
            "breaks_triggered": breaks_triggered,
            "break_rate": f"{(breaks_triggered/total_tests*100):.1f}%" if total_tests > 0 else "0%",
            "last_results": [
                {
                    "target": r.target_id,
                    "break": r.break_triggered,
                    "stagger": f"{r.stagger_current}/{r.stagger_max}",
                    "dmg_mult": f"{r.damage_multiplier:.2f}x"
                }
                for r in self.test_results[-5:]  # Последние 5 результатов
            ]
        }

    def cleanup(self):
        """Очистка ресурсов"""
        self.cc_managers.clear()
        self.test_results.clear()
        logger.info(f"[{self.name}] Очищен")


# --- Тест плагина ---
def test_cc_probe_plugin():
    print("\n=== ТЕСТ CC PROBE PLUGIN ===\n")
    
    plugin = CCProbePlugin()
    
    # Регистрируем босса
    boss_stats = CharacterCCStats(
        stagger_max=1000.0,
        stagger_resist=1.0,
        cc_duration_resist=0.8
    )
    plugin.register_entity("boss_1", boss_stats)
    
    # Тест 1: Применение стана
    print("Тест 1: Применение стана")
    result = plugin.execute_command(CCCommandType.APPLY_STUN, {
        "target_id": "boss_1",
        "duration": 3.0,
        "source_id": "player_spell"
    })
    print(f"Результат: {result}\n")
    assert result["success"] == True
    
    # Тест 2: Накопление стойки и брейк
    print("Тест 2: Накопление стойки и БРЕЙК")
    for i in range(5):
        result = plugin.execute_command(CCCommandType.DEAL_STAGGER_DMG, {
            "target_id": "boss_1",
            "damage": 250.0
        })
        print(f"Удар {i+1}: Stagger={result['stagger_current']:.0f}/{result['stagger_max']:.0f}, Break={result['break_triggered']}")
    
    assert result["break_triggered"] == True or result["is_broken"] == True
    print(f">>> БРЕЙК АКТИВИРОВАН!\n")
    
    # Тест 3: Проверка статуса
    print("Тест 3: Проверка статуса")
    status = plugin.execute_command(CCCommandType.GET_CC_STATUS, {
        "target_id": "boss_1"
    })
    print(f"Статус: {status['status']}, Break State: {status['break_state']}")
    assert status["break_state"] == "BROKEN"
    print()
    
    # Тест 4: Симуляция комбо
    print("Тест 4: Сброс и симуляция комбо")
    plugin.execute_command(CCCommandType.RESET_CC, {"target_id": "boss_1"})
    
    combo_result = plugin.execute_command(CCCommandType.SIMULATE_BREAK_COMBO, {
        "target_id": "boss_1",
        "hits": 6,
        "hit_damage": 200.0,
        "base_damage": 5000.0
    })
    print(f"Комбо результат: {combo_result}")
    print()
    
    # Статистика
    print("Статистика плагина:")
    stats = plugin.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    plugin.cleanup()
    print("\n=== ТЕСТ ЗАВЕРШЕН УСПЕШНО ===\n")

if __name__ == "__main__":
    test_cc_probe_plugin()
