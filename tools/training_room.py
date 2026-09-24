#!/usr/bin/env python3
"""
Training Room & Mannequin System v2.0
======================================
Специализированная среда для тестирования предметов, навыков и эффектов.

Возможности:
- Манекены с настраиваемыми характеристиками (HP, defense, resistances)
- Бессмертные герои-враги (как в Доте) - атакуют, используют скиллы, не умирают
- Система баффов/дебаффов через Effect Module (снижение HP, хил, урон от %HP)
- Скрипты автоматического тестирования DPS/эффективности
- Сравнение "до/после" экипировки
- Генерация отчётов с рекомендациями
- Интеграция с CAS Engine для сложных эффектов
- Экспорт данных для анализа агентом (снижение токенов)
- Веб-интерфейс для настройки тестов
- Интеграция с Dev Probe для автозапуска при изменениях кода

Архитектура:
- Lua: Конфигурация манекенов, героев, тест-сценариев, баффов/дебаффов
- Rust: Быстрые вычисления урона, массовые симуляции (опционально)
- Python: Оркестрация тестов, отчёты, визуализация, веб-интерфейс
"""

import time
import json
import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from pathlib import Path

# Импорт систем проекта
import sys
_ROOT = Path(__file__).resolve().parent.parent  # раньше: захардкоженный '/workspace' чужой песочницы
sys.path.insert(0, str(_ROOT / 'src'))
sys.path.insert(0, str(_ROOT))

from features.advanced_items import (
    ItemDefinition, EffectEngine, ResourcePool, StatusManager,
    TriggerCondition, StatType, create_banes_scar_necklace,
    create_sorrow_of_berserk
)
from core.cas_engine import (
    CASManager, DamageCalculator, EffectTemplate, Condition, Action,
    StatType as CASStatType, DamageType, ConditionOperator,
    DamageProfile, DefenseProfile
)

# WARNING по умолчанию: INFO-лог на каждый удар (~120 строк за демо) - чистые
# токены для агента; подробный лог - `--verbose`
_LOG_LEVEL = logging.INFO if "--verbose" in sys.argv else logging.WARNING
logging.basicConfig(level=_LOG_LEVEL, format='%(asctime)s [%(levelname)s] %(message)s')
logging.getLogger().setLevel(_LOG_LEVEL)  # basicConfig - no-op, если импорты выше уже настроили logging
logger = logging.getLogger("TrainingRoom")


class MannequinType(Enum):
    """Типы манекенов для разных тестов"""
    DUMMY = "dummy"  # Статичный, без сопротивлений
    TANK = "tank"  # Высокая защита, низкий HP
    GLASS_CANNON = "glass_cannon"  # Низкая защита, высокий HP
    BALANCED = "balanced"  # Средние характеристики
    BOSS = "boss"  # Высокие все характеристики + special abilities
    CUSTOM = "custom"  # Пользовательская конфигурация


@dataclass
class BuffDebuffConfig:
    """Конфигурация баффа/дебаффа через Effect Module"""
    name: str
    effect_type: str  # "buff" или "debuff"
    stat_modifier: Dict[StatType, float] = field(default_factory=dict)
    hp_percent_change: float = 0.0  # Изменение % HP (для тестов от %HP)
    heal_per_tick: float = 0.0  # Хил за тик
    damage_per_tick: float = 0.0  # Урон за тик
    duration: float = 10.0  # Длительность в секундах
    tick_interval: float = 1.0  # Интервал тиков
    trigger_condition: Optional[str] = None  # Условие активации
    
    @classmethod
    def from_lua_config(cls, lua_data: dict) -> 'BuffDebuffConfig':
        """Создание конфигурации из Lua данных"""
        return cls(
            name=lua_data.get('name', 'Unknown'),
            effect_type=lua_data.get('effect_type', 'buff'),
            stat_modifier={StatType(k): v for k, v in lua_data.get('stat_modifier', {}).items()},
            hp_percent_change=lua_data.get('hp_percent_change', 0.0),
            heal_per_tick=lua_data.get('heal_per_tick', 0.0),
            damage_per_tick=lua_data.get('damage_per_tick', 0.0),
            duration=lua_data.get('duration', 10.0),
            tick_interval=lua_data.get('tick_interval', 1.0),
            trigger_condition=lua_data.get('trigger_condition')
        )


@dataclass
class ImmortalHeroConfig:
    """Конфигурация бессмертного героя-врага (как в Доте)"""
    name: str
    level: int = 1
    base_hp: float = 1000.0
    base_damage: float = 50.0
    attack_speed: float = 1.0  # Атак в секунду
    skills: List[str] = field(default_factory=list)  # Названия навыков
    equipment: List[ItemDefinition] = field(default_factory=list)
    behavior: str = "aggressive"  # "aggressive", "passive", "random"
    is_immortal: bool = True  # Не умирает, только респаунится
    
    @classmethod
    def from_lua_config(cls, lua_data: dict) -> 'ImmortalHeroConfig':
        """Создание конфигурации из Lua данных"""
        return cls(
            name=lua_data.get('name', 'Hero'),
            level=lua_data.get('level', 1),
            base_hp=lua_data.get('base_hp', 1000.0),
            base_damage=lua_data.get('base_damage', 50.0),
            attack_speed=lua_data.get('attack_speed', 1.0),
            skills=lua_data.get('skills', []),
            equipment=[],  # Загружается отдельно
            behavior=lua_data.get('behavior', 'aggressive'),
            is_immortal=lua_data.get('is_immortal', True)
        )


@dataclass
class MannequinConfig:
    """Конфигурация манекена"""
    name: str
    mannequin_type: MannequinType
    max_hp: float = 10000.0
    defense: float = 0.0
    resistances: Dict[DamageType, float] = field(default_factory=dict)
    dodge_chance: float = 0.0
    crit_resistance: float = 0.0
    special_abilities: List[str] = field(default_factory=list)
    equipment: List[ItemDefinition] = field(default_factory=list)  # Шмотки на манекене
    
    @classmethod
    def from_lua_config(cls, lua_data: dict) -> 'MannequinConfig':
        """Создание конфигурации из Lua данных"""
        return cls(
            name=lua_data.get('name', 'Unknown'),
            mannequin_type=MannequinType(lua_data.get('type', 'dummy')),
            max_hp=lua_data.get('max_hp', 10000.0),
            defense=lua_data.get('defense', 0.0),
            resistances={DamageType(k): v for k, v in lua_data.get('resistances', {}).items()},
            dodge_chance=lua_data.get('dodge_chance', 0.0),
            crit_resistance=lua_data.get('crit_resistance', 0.0),
            special_abilities=lua_data.get('special_abilities', []),
            equipment=[]  # Загружается отдельно
        )


@dataclass
class TestScenario:
    """Сценарий тестирования"""
    name: str
    description: str
    duration_seconds: float = 30.0
    attacks_per_second: float = 1.0
    enable_crits: bool = True
    enable_specials: bool = True
    log_every_hit: bool = False  # Если False, агрегировать данные
    compare_items: List[str] = field(default_factory=list)  # Какие предметы сравнивать
    

@dataclass
class TestResult:
    """Результаты теста"""
    scenario_name: str
    total_damage: float
    dps: float
    total_hits: int
    crit_count: int
    crit_rate: float
    average_hit: float
    damage_breakdown: Dict[str, float] = field(default_factory=dict)
    timeline: List[Tuple[float, float]] = field(default_factory=list)  # (time, cumulative_dmg)
    recommendations: List[str] = field(default_factory=list)
    

class Mannequin:
    """Манекен для тестирования"""
    
    def __init__(self, config: MannequinConfig):
        self.config = config
        self.current_hp = config.max_hp
        self.damage_taken: Dict[str, float] = {}  # source -> damage
        self.hit_log: List[Dict] = []
        self.active_effects: List[Any] = []  # Активные эффекты от шмоток
        self.buffs_debuffs: List[BuffDebuffConfig] = []  # Активные баффы/дебаффы
        
    def reset(self):
        """Сброс манекена"""
        self.current_hp = self.config.max_hp
        self.damage_taken = {}
        self.hit_log = []
        self.active_effects = []
        self.buffs_debuffs = []
        
    def apply_equipment_effects(self):
        """Применение эффектов от экипировки на манекене"""
        if not self.config.equipment:
            return
            
        for item in self.config.equipment:
            for stat, val in item.stats.items():
                # Применение статов к манекену (defense, HP и т.д.)
                if stat == StatType.DEFENSE:
                    self.config.defense += val
                elif stat == StatType.MAX_HP:
                    self.config.max_hp += val
                    self.current_hp = self.config.max_hp  # Update current HP too
                # PHYSICAL_RESISTANCE и MAGICAL_RESISTANCE не существуют в StatType
                # Используем defense и HP для симуляции mitigation
                    
    def apply_buff_debuff(self, buff_debuff: BuffDebuffConfig):
        """Применение баффа/дебаффа через Effect Module"""
        self.buffs_debuffs.append(buff_debuff)
        
        # Применение мгновенных эффектов
        if buff_debuff.hp_percent_change != 0:
            hp_change = self.config.max_hp * (buff_debuff.hp_percent_change / 100.0)
            self.current_hp += hp_change
            logger.info(f"Applied {buff_debuff.name}: HP changed by {hp_change:.1f}")
            
        # Применение стат модификаторов
        for stat, val in buff_debuff.stat_modifier.items():
            if stat == StatType.DEFENSE:
                self.config.defense += val
            elif stat == StatType.MAX_HP:
                self.config.max_hp += val
                self.current_hp += val
                
    def process_buff_debuff_ticks(self, current_time: float, tick_interval: float = 1.0):
        """Обработка тиков баффов/дебаффов (хил, урон за тик)"""
        for buff in self.buffs_debuffs:
            if current_time % buff.tick_interval < tick_interval:
                # Хил за тик
                if buff.heal_per_tick > 0:
                    self.current_hp = min(self.config.max_hp, self.current_hp + buff.heal_per_tick)
                # Урон за тик
                if buff.damage_per_tick > 0:
                    self.take_damage(
                        damage=buff.damage_per_tick,
                        damage_type=DamageType.TRUE,  # True damage ignores resistance
                        source=f"buff_{buff.name}",
                        is_crit=False,
                        timestamp=current_time
                    )
                    
    def take_damage(self, damage: float, damage_type: DamageType, 
                    source: str = "unknown", is_crit: bool = False, timestamp: float = 0.0):
        """Получение урона с учётом сопротивлений и экипировки"""
        # Применение сопротивлений от шмоток
        resistance = self.config.resistances.get(damage_type, 0.0)
        final_damage = damage * (1.0 - resistance / 100.0)
        
        # Применение защиты (плоское снижение)
        final_damage = max(1.0, final_damage - self.config.defense)
        
        # Логирование
        if source not in self.damage_taken:
            self.damage_taken[source] = 0.0
        self.damage_taken[source] += final_damage
        
        self.hit_log.append({
            'timestamp': timestamp,
            'base_damage': damage,
            'final_damage': final_damage,
            'damage_type': damage_type.value,
            'source': source,
            'is_crit': is_crit,
            'resistance_applied': resistance
        })
        
        self.current_hp -= final_damage
        
    def is_alive(self) -> bool:
        return self.current_hp > 0
        
    def get_stats_summary(self) -> Dict[str, Any]:
        """Краткая статистика для отчёта (снижение токенов)"""
        if not self.hit_log:
            return {'hits': 0, 'total_damage': 0}
            
        total_damage = sum(h['final_damage'] for h in self.hit_log)
        crit_count = sum(1 for h in self.hit_log if h['is_crit'])
        
        # Агрегированные данные вместо полного лога
        return {
            'hits': len(self.hit_log),
            'total_damage': round(total_damage, 2),
            'crit_count': crit_count,
            'crit_rate': round(crit_count / len(self.hit_log) * 100, 2) if self.hit_log else 0,
            'avg_damage': round(total_damage / len(self.hit_log), 2) if self.hit_log else 0,
            'damage_by_source': {k: round(v, 2) for k, v in self.damage_taken.items()},
            'equipment_active': len(self.config.equipment) > 0,
            'buffs_active': len(self.buffs_debuffs) > 0
        }


class ImmortalHero:
    """Бессмертный герой-враг (как в Доте) - атакует, использует скиллы, не умирает"""
    
    def __init__(self, config: ImmortalHeroConfig):
        self.config = config
        self.level = config.level
        self.current_hp = config.base_hp * (1.0 + 0.1 * (self.level - 1))  # +10% HP за уровень
        self.max_hp = self.current_hp
        self.base_damage = config.base_damage * (1.0 + 0.05 * (self.level - 1))  # +5% урона за уровень
        self.attack_speed = config.attack_speed
        self.skills = config.skills
        self.equipment = config.equipment
        self.behavior = config.behavior
        self.is_immortal = config.is_immortal
        
        self.damage_dealt: Dict[str, float] = {}  # target -> damage
        self.skill_usage_log: List[Dict] = []
        self.attack_log: List[Dict] = []
        self.death_count = 0  # Сколько раз "умирал" (респавн)
        self.equipment_stats = self._calculate_equipment_stats()
        
    def _calculate_equipment_stats(self) -> Dict[str, float]:
        """Расчёт статов от экипировки"""
        stats = {'damage_bonus': 0.0, 'attack_speed_bonus': 0.0, 'crit_chance': 0.0}
        for item in self.equipment:
            for stat, val in item.stats.items():
                if stat == StatType.ATTACK_POWER:
                    stats['damage_bonus'] += val
                elif stat == StatType.ATTACK_SPEED:
                    stats['attack_speed_bonus'] += val
                elif stat == StatType.CRIT_CHANCE:
                    stats['crit_chance'] += val
        return stats
        
    def reset(self):
        """Сброс героя (респавн)"""
        self.current_hp = self.max_hp
        self.damage_dealt = {}
        self.skill_usage_log = []
        self.attack_log = []
        if self.is_immortal and self.death_count > 0:
            logger.info(f"{self.config.name} respawned (death #{self.death_count})")
            
    def take_damage(self, damage: float, damage_type: DamageType, 
                    source: str = "unknown", is_crit: bool = False, timestamp: float = 0.0):
        """Получение урона - если immortal, то не умирает, а респавнится"""
        self.current_hp -= damage
        
        if self.current_hp <= 0:
            if self.is_immortal:
                self.death_count += 1
                logger.debug(f"{self.config.name} 'died' (immortal, will respawn)")
                self.reset()  # Мгновенный респавн
            else:
                self.current_hp = 0
                
    def perform_attack(self, target: Any, timestamp: float = 0.0) -> float:
        """Атака цели - возвращает нанесённый урон"""
        # Расчёт урона с учётом уровня и экипировки
        base_dmg = self.base_damage * (1.0 + self.equipment_stats['damage_bonus'] / 100.0)
        
        # Крит
        is_crit = random.random() * 100 < self.equipment_stats['crit_chance']
        if is_crit:
            base_dmg *= 2.0
            
        # Применение урона к цели
        target.take_damage(
            damage=base_dmg,
            damage_type=DamageType.PHYSICAL,
            source=f"hero_{self.config.name}",
            is_crit=is_crit,
            timestamp=timestamp
        )
        
        # Логирование
        self.attack_log.append({
            'timestamp': timestamp,
            'damage': base_dmg,
            'is_crit': is_crit,
            'target': getattr(target, 'config', {}).name if hasattr(target, 'config') else str(target)
        })
        
        if hasattr(target, 'config'):
            target_name = target.config.name
            if target_name not in self.damage_dealt:
                self.damage_dealt[target_name] = 0.0
            self.damage_dealt[target_name] += base_dmg
            
        return base_dmg
        
    def use_skill(self, skill_name: str, target: Any, timestamp: float = 0.0) -> Dict[str, Any]:
        """Использование навыка (упрощённая модель)"""
        if skill_name not in self.skills:
            return {'success': False, 'error': f'Skill {skill_name} not known'}
            
        # Симуляция урона навыка (в реальности будет интеграция с CAS Engine)
        skill_damage = self.base_damage * 2.5  # Скиллы бьют сильнее автоатак
        
        target.take_damage(
            damage=skill_damage,
            damage_type=DamageType.FIRE,  # Используем существующий тип
            source=f"hero_{self.config.name}_{skill_name}",
            is_crit=False,
            timestamp=timestamp
        )
        
        self.skill_usage_log.append({
            'timestamp': timestamp,
            'skill': skill_name,
            'damage': skill_damage,
            'target': getattr(target, 'config', {}).name if hasattr(target, 'config') else str(target)
        })
        
        return {'success': True, 'damage': skill_damage}
        
    def get_stats_summary(self) -> Dict[str, Any]:
        """Краткая статистика для отчёта"""
        total_damage = sum(self.damage_dealt.values())
        total_attacks = len(self.attack_log)
        total_skills = len(self.skill_usage_log)
        crit_count = sum(1 for a in self.attack_log if a['is_crit'])
        
        return {
            'name': self.config.name,
            'level': self.level,
            'deaths': self.death_count,
            'total_damage_dealt': round(total_damage, 2),
            'total_attacks': total_attacks,
            'total_skills_used': total_skills,
            'crit_rate': round(crit_count / total_attacks * 100, 2) if total_attacks > 0 else 0,
            'avg_attack_damage': round(total_damage / total_attacks, 2) if total_attacks > 0 else 0,
            'damage_by_target': {k: round(v, 2) for k, v in self.damage_dealt.items()}
        }


class TrainingRoom:
    """
    Основная система Training Room
    Управляет манекенами, сценариями тестирования и генерацией отчётов
    """
    
    def __init__(self, output_dir: Optional[str] = None):
        # Отчёты - в git-игнорируемый dev_probe_output/ (раньше каждый запуск
        # дописывал файлы в отслеживаемую training_room_output/ и пачкал репо)
        self.output_dir = Path(output_dir) if output_dir else _ROOT / "dev_probe_output" / "training_room"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.mannequins: Dict[str, Mannequin] = {}
        self.active_scenario: Optional[TestScenario] = None
        self.test_results: List[TestResult] = []
        
        # Инициализация систем
        self.cas_manager = CASManager()
        self.effect_engine: Optional[EffectEngine] = None
        self.damage_calculator = DamageCalculator()
        
        # Загрузка Lua конфигураций
        self.lua_configs = self._load_lua_configs()
        
    def _load_lua_configs(self) -> Dict[str, Any]:
        """lua_content/training_room/*.lua через tools/lua_bridge.py (Lua 5.5).

        Файлы объявляют глобальные таблицы (mannequins, scenarios, item_sets,
        thresholds) - они и возвращаются: {file_stem: {global: value}}.
        Раньше здесь стояла заглушка `configs[stem] = {}` - Lua не читался вовсе,
        а манекены брали захардкоженные значения."""
        configs = {}
        lua_path = _ROOT / 'lua_content' / 'training_room'
        if not lua_path.exists():
            logger.warning(f"Lua config directory not found: {lua_path}")
            return configs
        try:
            import lua_bridge
        except ImportError:
            from tools import lua_bridge
        for lua_file in sorted(lua_path.glob('*.lua')):
            try:
                data = lua_bridge.load(lua_file, globals=("mannequins", "scenarios", "item_sets", "thresholds"))
            except RuntimeError as exc:  # нет ни rust_core, ни lupa
                logger.warning(f"{exc} - mannequins use built-in defaults")
                return configs
            except Exception as exc:
                logger.warning(f"Lua config {lua_file.name} failed: {exc}")
                continue
            configs[lua_file.stem] = data
            logger.info(f"Loaded Lua config: {lua_file.name} ({', '.join(data)})")
        return configs

    def create_mannequin(self, name: str, mannequin_type: MannequinType = MannequinType.DUMMY,
                        custom_config: Optional[MannequinConfig] = None,
                        equipment: Optional[List[ItemDefinition]] = None) -> Mannequin:
        """Создание манекена с опциональной экипировкой"""
        lua_mannequins = self.lua_configs.get("mannequins", {}).get("mannequins", {})
        if custom_config:
            config = custom_config
        elif mannequin_type.value in lua_mannequins:
            try:
                config = MannequinConfig.from_lua_config(lua_mannequins[mannequin_type.value])
                config.name = name
            except (ValueError, KeyError) as exc:
                logger.warning(f"Lua mannequin '{mannequin_type.value}' invalid ({exc}); using defaults")
                config = MannequinConfig(name, mannequin_type)
        else:
            # Конфигурация по типу
            configs = {
                MannequinType.DUMMY: MannequinConfig(name, MannequinType.DUMMY, 
                                                      max_hp=100000.0, defense=0.0),
                MannequinType.TANK: MannequinConfig(name, MannequinType.TANK,
                                                     max_hp=50000.0, defense=500.0),
                MannequinType.GLASS_CANNON: MannequinConfig(name, MannequinType.GLASS_CANNON,
                                                             max_hp=20000.0, defense=0.0),
                MannequinType.BALANCED: MannequinConfig(name, MannequinType.BALANCED,
                                                         max_hp=50000.0, defense=200.0),
                MannequinType.BOSS: MannequinConfig(name, MannequinType.BOSS,
                                                     max_hp=500000.0, defense=1000.0)
            }
            config = configs.get(mannequin_type, configs[MannequinType.DUMMY])
            
        # Применение экипировки
        if equipment:
            config.equipment = equipment
            
        mannequin = Mannequin(config)
        
        # Применение эффектов экипировки
        if equipment:
            mannequin.apply_equipment_effects()
            
        self.mannequins[name] = mannequin
        logger.info(f"Created mannequin '{name}' ({mannequin_type.value}) with {config.max_hp} HP")
        if equipment:
            logger.info(f"  Equipped with {len(equipment)} items")
        return mannequin
        
    def setup_test_scenario(self, scenario: TestScenario):
        """Настройка сценария тестирования"""
        self.active_scenario = scenario
        logger.info(f"Setup scenario: {scenario.name} - {scenario.description}")
        
    def run_dps_test(self, player_items: List[ItemDefinition], 
                    mannequin_name: str = "target_dummy",
                    duration: Optional[float] = None,
                    test_defense: bool = False) -> TestResult:
        """
        Запуск теста DPS
        
        Args:
            player_items: Предметы игрока для тестирования
            mannequin_name: Имя манекена
            duration: Длительность теста (переопределяет сценарий)
            test_defense: Если True, тестируем защиту манекена (не атакуем)
            
        Returns:
            TestResult с результатами
        """
        if mannequin_name not in self.mannequins:
            raise ValueError(f"Mannequin '{mannequin_name}' not found")
            
        mannequin = self.mannequins[mannequin_name]
        mannequin.reset()
        
        # Применение эффектов экипировки манекена
        mannequin.apply_equipment_effects()
        
        scenario = self.active_scenario or TestScenario(name="default", description="Default DPS test")
        duration = duration or scenario.duration_seconds
        attack_interval = 1.0 / scenario.attacks_per_second
        
        # Настройка игрока
        player_pool = ResourcePool(base_max_hp=1000.0)
        status_mgr = StatusManager()
        effect_engine = EffectEngine(player_pool, status_mgr)
        
        # Применение предметов игрока
        for item in player_items:
            for stat, val in item.stats.items():
                if "percent" in stat.value or stat in [StatType.CRIT_CHANCE, StatType.VAMPIRISM]:
                    player_pool.percent_modifiers[stat] += val
                else:
                    player_pool.modifiers[stat] += val
                    
        # Логирование (агрегированное для снижения токенов)
        hit_log = []
        total_damage = 0.0
        crit_count = 0
        current_time = 0.0
        timeline = []
        
        base_damage = 100.0  # Базовый урон атаки
        crit_chance = player_pool.get_stat(StatType.CRIT_CHANCE) / 100.0
        crit_multiplier = 2.0
        
        logger.info(f"Starting DPS test: {duration}s, {scenario.attacks_per_second} attacks/s")
        logger.info(f"Crit chance: {crit_chance*100:.1f}%")
        if test_defense:
            logger.info(f"Testing defense mode - mannequin equipment active")
        
        while current_time < duration and mannequin.is_alive():
            # Определение крита
            is_crit = scenario.enable_crits and (crit_chance > 0 and crit_chance >= 0.5)
            
            # Расчёт урона с эффектами
            context = {'dmg_pct': 1.5}
            bonus_dmg = effect_engine.process_effects(
                player_items, 
                TriggerCondition.ON_ATTACK, 
                context
            )
            
            # Финальный урон
            hit_damage = base_damage + bonus_dmg
            if is_crit:
                hit_damage *= crit_multiplier
                crit_count += 1
                
            # Нанесение урона (или симуляция защиты)
            if not test_defense:
                mannequin.take_damage(
                    damage=hit_damage,
                    damage_type=DamageType.PHYSICAL,
                    source="player_auto_attack",
                    is_crit=is_crit,
                    timestamp=current_time
                )
                total_damage += hit_damage
            else:
                # Тест защиты - просто логируем параметры манекена
                total_damage = 0  # Урона нет, тестируем mitigation
                
            if scenario.log_every_hit and not test_defense:
                hit_log.append({
                    'time': current_time,
                    'damage': hit_damage,
                    'is_crit': is_crit
                })
                
            timeline.append((current_time, total_damage))
            
            current_time += attack_interval
            effect_engine.set_time(current_time)
            
        # Расчёт метрик
        actual_duration = current_time
        dps = total_damage / actual_duration if actual_duration > 0 else 0
        total_hits = len(timeline)
        crit_rate = (crit_count / total_hits * 100) if total_hits > 0 else 0
        avg_hit = total_damage / total_hits if total_hits > 0 else 0
        
        result = TestResult(
            scenario_name=scenario.name,
            total_damage=round(total_damage, 2),
            dps=round(dps, 2),
            total_hits=total_hits,
            crit_count=crit_count,
            crit_rate=round(crit_rate, 2),
            average_hit=round(avg_hit, 2),
            damage_breakdown=mannequin.damage_taken,
            timeline=timeline[-10:],  # Только последние 10 точек для экономии токенов
            recommendations=self._generate_recommendations(result=None, mannequin=mannequin)
        )
        
        self.test_results.append(result)
        logger.info(f"DPS Test complete: {result.dps} DPS, {total_hits} hits, {crit_rate:.1f}% crit")
        
        return result
        
    def compare_items(self, item_sets: Dict[str, List[ItemDefinition]], 
                     mannequin_name: str = "target_dummy",
                     duration: float = 30.0) -> Dict[str, Any]:
        """
        Сравнение нескольких наборов предметов
        
        Args:
            item_sets: {"set_name": [item1, item2, ...], ...}
            mannequin_name: Имя манекена
            duration: Длительность каждого теста
            
        Returns:
            Сравнительный отчёт
        """
        results = {}
        
        for set_name, items in item_sets.items():
            logger.info(f"\nTesting item set: {set_name}")
            scenario = TestScenario(name=f"compare_{set_name}", description=f"Testing {set_name}")
            self.setup_test_scenario(scenario)
            
            result = self.run_dps_test(items, mannequin_name, duration)
            results[set_name] = result
            
        # Генерация сравнительного отчёта
        comparison = self._generate_comparison_report(results)
        return comparison
        
    def _generate_recommendations(self, result: Optional[TestResult], 
                                  mannequin: Optional[Mannequin]) -> List[str]:
        """Генерация рекомендаций на основе результатов"""
        recommendations = []
        
        if result:
            if result.crit_rate < 20.0:
                recommendations.append("Consider increasing crit chance for higher DPS")
            if result.average_hit < 100:
                recommendations.append("Base damage is low - focus on attack power items")
            if result.dps < 500:
                recommendations.append("Overall DPS is low - review item synergies")
                
        if mannequin:
            stats = mannequin.get_stats_summary()
            # Проверяем наличие ключа перед использованием
            if 'crit_rate' in stats and stats['crit_rate'] > 50.0:
                recommendations.append("High crit rate achieved - excellent build synergy")
            if 'equipment_active' in stats and stats['equipment_active']:
                recommendations.append("Mannequin equipment active - defense testing enabled")
                
        return recommendations
        
    def _generate_comparison_report(self, results: Dict[str, TestResult]) -> Dict[str, Any]:
        """Генерация сравнительного отчёта"""
        if not results:
            return {'error': 'No results to compare'}
            
        best_dps_set = max(results.items(), key=lambda x: x[1].dps)
        
        report = {
            'tested_sets': list(results.keys()),
            'best_dps': {
                'set_name': best_dps_set[0],
                'dps': best_dps_set[1].dps
            },
            'comparison_table': [
                {
                    'set_name': name,
                    'dps': r.dps,
                    'total_damage': r.total_damage,
                    'crit_rate': r.crit_rate,
                    'relative_performance': f"{r.dps/best_dps_set[1].dps*100:.1f}%"
                }
                for name, r in results.items()
            ],
            'recommendations': best_dps_set[1].recommendations
        }
        
        return report
        
    def export_report(self, result: TestResult, filename: Optional[str] = None) -> Path:
        """Экспорт отчёта в JSON (для агента)"""
        filename = filename or f"test_result_{int(time.time())}.json"
        filepath = self.output_dir / filename
        
        # Оптимизированный формат для снижения токенов
        report_data = {
            'metadata': {
                'scenario': result.scenario_name,
                'timestamp': time.time(),
                'format_version': '1.0'
            },
            'summary': {
                'dps': result.dps,
                'total_damage': result.total_damage,
                'total_hits': result.total_hits,
                'crit_rate': result.crit_rate,
                'average_hit': result.average_hit
            },
            'breakdown': result.damage_breakdown,
            'timeline_sample': result.timeline,  # Только sample
            'recommendations': result.recommendations
        }
        
        with open(filepath, 'w') as f:
            json.dump(report_data, f, indent=2)
            
        logger.info(f"Report exported to {filepath}")
        return filepath


def main():
    """Demo запуска Training Room"""
    print("\n" + "="*60)
    print("TRAINING ROOM & MANNEQUIN SYSTEM")
    print("="*60 + "\n")
    
    # Инициализация
    room = TrainingRoom()
    
    # Создание манекенов
    room.create_mannequin("target_dummy", MannequinType.DUMMY)
    room.create_mannequin("tank_bot", MannequinType.TANK)
    room.create_mannequin("boss_test", MannequinType.BOSS)
    
    # Тестовые предметы
    items = [create_banes_scar_necklace()]
    
    # Запуск DPS теста
    scenario = TestScenario(
        name="basic_dps_test",
        description="Basic DPS test with Bane's necklace",
        duration_seconds=10.0,
        attacks_per_second=1.0
    )
    room.setup_test_scenario(scenario)
    
    result = room.run_dps_test(items, "target_dummy")
    
    print(f"\n📊 Results:")
    print(f"   DPS: {result.dps}")
    print(f"   Total Damage: {result.total_damage}")
    print(f"   Hits: {result.total_hits}")
    print(f"   Crit Rate: {result.crit_rate}%")
    
    # Экспорт отчёта
    report_path = room.export_report(result)
    print(f"\n📄 Report saved to: {report_path}")
    
    # Сравнение наборов
    print("\n\n🔄 Comparing item sets...")
    comparison = room.compare_items(
        item_sets={
            'banes_only': [create_banes_scar_necklace()],
            'sorrow_only': [create_sorrow_of_berserk()],
            'both': [create_banes_scar_necklace(), create_sorrow_of_berserk()]
        },
        duration=5.0
    )
    
    print(f"\n🏆 Best DPS Set: {comparison['best_dps']['set_name']} ({comparison['best_dps']['dps']} DPS)")
    print("\nComparison Table:")
    for row in comparison['comparison_table']:
        print(f"   {row['set_name']}: {row['dps']} DPS ({row['relative_performance']})")
    
    print("\n" + "="*60)
    print("TRAINING ROOM TESTS COMPLETE!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
