#!/usr/bin/env python3
"""
Пример плагина - Combat Plugin
Демонстрирует как создавать фичи в виде плагинов
"""

import logging
from typing import Any

from src.core.base_plugin import BasePlugin
from src.core.architecture import LifecycleState
from src.core.rng_manager import get_default_rng
from src.systems.combat.combat_system import CombatSystem

logger = logging.getLogger(__name__)


class CombatPlugin(BasePlugin):
    """
    Плагин боевой системы
    
    Фичи:
    - Расчет урона
    - Критические удары
    - Уклонения и блоки
    - Эффекты попаданий
    """
    
    def __init__(self, effects_plugin: Any = None):
        """
        Args:
            effects_plugin: EffectsPlugin - его EffectSystem передаётся в
                CombatSystem (баффы в статах, on_hit_effect при попадании)
        """
        super().__init__(
            plugin_id="combat_plugin",
            plugin_name="Combat System",
            version="1.0.0",
            dependencies=["effects"] if effects_plugin is not None else [],
        )
        self._effects_plugin = effects_plugin
        # Настоящая боевая система, которую вызывают сущности через
        # game.combat_system.execute_attack(...). Создаётся в initialize().
        self.combat_system: CombatSystem | None = None

        # Конфигурация боя
        self.combat_config = {
            'crit_chance_base': 0.05,
            'crit_damage_multiplier': 2.0,
            'dodge_chance_base': 0.1,
            'block_chance_base': 0.15,
            'damage_variance': 0.2,  # ±20% вариация урона
        }
        
        # Статистика боя
        self.combat_stats = {
            'attacks_made': 0,
            'hits_landed': 0,
            'crits_landed': 0,
            'attacks_dodged': 0,
            'attacks_blocked': 0,
            'total_damage_dealt': 0.0,
        }
    
    def initialize(self) -> bool:
        """Инициализация боевого плагина"""
        try:
            logger.info("Инициализация CombatPlugin...")
            
            # Загружаем конфиг из БД если есть
            saved_config = self.load_state()
            if saved_config:
                self.combat_config.update(saved_config.get('config', {}))

            # get_default_rng() - общий генератор: dev_probe --seed подменяет
            # его до создания игры, поэтому криты/уклоны воспроизводимы
            effect_system = getattr(self._effects_plugin, "effect_system", None)
            self.combat_system = CombatSystem(rng=get_default_rng(), effect_system=effect_system)

            self.system_state = LifecycleState.READY
            logger.info("CombatPlugin успешно инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации CombatPlugin: {e}", exc_info=True)
            return False
    
    def start(self) -> bool:
        """Запуск боевого плагина"""
        try:
            logger.info("Запуск CombatPlugin...")
            
            self.system_state = LifecycleState.RUNNING
            logger.info("CombatPlugin успешно запущен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска CombatPlugin: {e}", exc_info=True)
            return False
    
    def update_logic(self, delta_time: float) -> None:
        """Логика обновления боя (no-op для этой фичи)"""
        pass
    
    def calculate_damage(
        self,
        attacker_stats: dict[str, Any],
        defender_stats: dict[str, Any],
        base_damage: float,
    ) -> dict[str, Any]:
        """
        Расчет урона с учетом всех факторов
        
        Args:
            attacker_stats: Статы атакующего (strength, crit_chance, etc)
            defender_stats: Статы защищающегося (armor, dodge_chance, etc)
            base_damage: Базовый урон оружия
        
        Returns:
            dict: Результаты расчета урона
        """
        import random
        
        result = {
            'base_damage': base_damage,
            'final_damage': 0.0,
            'is_crit': False,
            'is_dodged': False,
            'is_blocked': False,
            'damage_variance': 0.0,
        }
        
        # Проверка на уклонение
        dodge_chance = defender_stats.get('dodge_chance', self.combat_config['dodge_chance_base'])
        if random.random() < dodge_chance:
            result['is_dodged'] = True
            result['final_damage'] = 0.0
            self.combat_stats['attacks_dodged'] += 1
            return result
        
        # Проверка на блок
        block_chance = defender_stats.get('block_chance', self.combat_config['block_chance_base'])
        if random.random() < block_chance:
            result['is_blocked'] = True
            base_damage *= 0.5  # Блок снижает урон на 50%
        
        # Вариация урона
        variance = random.uniform(-self.combat_config['damage_variance'], self.combat_config['damage_variance'])
        damage_with_variance = base_damage * (1 + variance)
        result['damage_variance'] = variance
        
        # Проверка на крит
        crit_chance = attacker_stats.get('crit_chance', self.combat_config['crit_chance_base'])
        if random.random() < crit_chance:
            result['is_crit'] = True
            damage_with_variance *= self.combat_config['crit_damage_multiplier']
            self.combat_stats['crits_landed'] += 1
        
        # Применяем броню
        armor = defender_stats.get('armor', 0)
        final_damage = max(0, damage_with_variance - armor)
        
        result['final_damage'] = final_damage
        self.combat_stats['total_damage_dealt'] += final_damage
        
        return result
    
    def register_kill(self, killer_id: str, victim_id: str, damage: float) -> None:
        """Регистрация убийства"""
        logger.debug(f"Kill: {killer_id} -> {victim_id} ({damage} dmg)")
    
    def get_combat_stats(self) -> dict[str, Any]:
        """Получение статистики боя"""
        return {
            **self.combat_stats,
            'hit_rate': (
                self.combat_stats['hits_landed'] / self.combat_stats['attacks_made']
                if self.combat_stats['attacks_made'] > 0 else 0.0
            ),
            'crit_rate': (
                self.combat_stats['crits_landed'] / self.combat_stats['attacks_made']
                if self.combat_stats['attacks_made'] > 0 else 0.0
            ),
        }
    
    def get_plugin_info(self) -> dict[str, Any]:
        """Информация о плагине"""
        base_info = super().get_plugin_info()
        base_info['combat_config'] = self.combat_config
        base_info['combat_stats'] = self.get_combat_stats()
        return base_info


__all__ = ['CombatPlugin']
