#!/usr/bin/env python3
"""Константы игры - централизованное управление всеми константами"""

import logging
from typing import Dict, List, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)

# = ОСНОВНЫЕ ТИПЫ И ПЕРЕЧИСЛЕНИЯ

class DamageType(Enum):
    """Типы урона"""
    PHYSICAL = "physical"
    MAGICAL = "magical"
    FIRE = "fire"
    ICE = "ice"
    LIGHTNING = "lightning"
    POISON = "poison"
    PSYCHIC = "psychic"
    TRUE = "true"
    NECROMANCY = "necromancy"
    DARK = "dark"
    LIGHT = "light"
    AIR = "air"
    EARTH = "earth"
    WATER = "water"
    ENERGY = "energy"
    CHAOS = "chaos"
    ORDER = "order"
    LIFE = "life"
    DEATH = "death"
    TIME = "time"
    SPACE = "space"
    MIND = "mind"
    BODY = "body"
    SOUL = "soul"
    SPIRIT = "spirit"


class ToughnessType(Enum):
    """Типы стойкости (стихии)"""
    PHYSICAL = "physical"
    FIRE = "fire"
    ICE = "ice"
    LIGHTNING = "lightning"
    WIND = "wind"
    QUANTUM = "quantum"
    IMAGINARY = "imaginary"
    UNIVERSAL = "universal"  # Пробивает любую стойкость
    ENERGY = "energy"
    CHAOS = "chaos"
    ORDER = "order"
    LIFE = "life"
    DEATH = "death"
    TIME = "time"
    SPACE = "space"
    MIND = "mind"
    BODY = "body"
    SOUL = "soul"
    SPIRIT = "spirit"
    

class StanceState(Enum):
    """Состояния стойкости"""
    NORMAL = "normal"           # Обычное состояние
    WEAKENED = "weakened"       # Ослабленная стойкость
    BROKEN = "broken"           # Пробитая стойкость
    RECOVERING = "recovering"   # Восстановление стойкости

class EmotionType(Enum):
    """Типы эмоций"""
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    TRUST = "trust"
    ANTICIPATION = "anticipation"
    NEUTRAL = "neutral"

class EmotionIntensity(Enum):
    """Интенсивность эмоций"""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"

class AIState(Enum):
    """Состояния ИИ"""
    IDLE = "idle"
    PATROLLING = "patrolling"
    CHASING = "chasing"
    ATTACKING = "attacking"
    FLEEING = "fleeing"
    SEARCHING = "searching"
    INTERACTING = "interacting"
    THINKING = "thinking"
    LEARNING = "learning"

class AIBehavior(Enum):
    """Поведения ИИ"""
    AGGRESSIVE = "aggressive"
    DEFENSIVE = "defensive"
    CAUTIOUS = "cautious"
    CURIOUS = "curious"
    SOCIAL = "social"
    SOLITARY = "solitary"
    ADAPTIVE = "adaptive"
    PREDICTABLE = "predictable"

class GeneType(Enum):
    """Типы генов"""
    STRENGTH = "strength"
    AGILITY = "agility"
    INTELLIGENCE = "intelligence"
    VITALITY = "vitality"
    LUCK = "luck"
    RESISTANCE = "resistance"
    ADAPTATION = "adaptation"
    MUTATION = "mutation"
    # Категории, используемые системой эволюции
    PHYSICAL = "physical"
    MENTAL = "mental"
    SOCIAL = "social"
    COMBAT = "combat"
    MAGIC = "magic"

class EvolutionType(Enum):
    """Типы эволюции"""
    NATURAL = "natural"
    FORCED = "forced"
    MUTATION = "mutation"
    ADAPTIVE = "adaptive"

# = ДОПОЛНИТЕЛЬНЫЕ ТИПЫ (ЦЕНТРАЛИЗОВАННЫЕ)

class TradeType(Enum):
    """Типы торговли (централизованные)"""
    BUY = "buy"
    SELL = "sell"
    EXCHANGE = "exchange"
    AUCTION = "auction"
    BARTER = "barter"
    GIFT = "gift"
    QUEST_REWARD = "quest_reward"
    LOOT = "loot"

class TradeStatus(Enum):
    """Статусы торговли (централизованные)"""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"

class TradeCategory(Enum):
    """Категории торговли (централизованные)"""
    WEAPONS = "weapons"
    ARMOR = "armor"
    CONSUMABLES = "consumables"
    MATERIALS = "materials"
    ARTIFACTS = "artifacts"
    CURRENCY = "currency"
    SERVICES = "services"
    INFORMATION = "information"

class WeatherType(Enum):
    """Типы погоды (централизованные)"""
    CLEAR = "clear"
    CLOUDY = "cloudy"
    RAIN = "rain"
    STORM = "storm"
    SNOW = "snow"
    BLIZZARD = "blizzard"
    FOG = "fog"
    SANDSTORM = "sandstorm"
    TOXIC_RAIN = "toxic_rain"
    RADIATION_STORM = "radiation_storm"
    HAIL = "hail"
    WINDY = "windy"
    DROUGHT = "drought"
    EXTREME = "extreme"

class MemoryType(Enum):
    """Типы памяти (централизованные)"""
    COMBAT = "combat"
    EXPLORATION = "exploration"
    DIALOGUE = "dialogue"
    QUEST = "quest"
    DEATH = "death"
    ACHIEVEMENT = "achievement"
    LEARNING = "learning"
    EVOLUTION = "evolution"
    SOCIAL = "social"
    EMOTIONAL = "emotional"
    # Расширенные типы памяти, используемые в системах
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    GENETIC = "genetic"

class DialogueType(Enum):
    """Типы диалогов (централизованные)"""
    CONVERSATION = "conversation"
    TRADE = "trade"
    QUEST = "quest"
    INFORMATION = "information"
    COMBAT_TAUNT = "combat_taunt"
    GREETING = "greeting"
    FAREWELL = "farewell"
    EMOTIONAL = "emotional"

class QuestType(Enum):
    """Типы квестов (централизованные)"""
    MAIN = "main"
    SIDE = "side"
    DAILY = "daily"
    WEEKLY = "weekly"
    EXPLORATION = "exploration"
    COMBAT = "combat"
    COLLECTION = "collection"
    DELIVERY = "delivery"
    ESCORT = "escort"
    SURVIVAL = "survival"

class QuestStatus(Enum):
    """Статусы квестов (централизованные)"""
    AVAILABLE = "available"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"
    LOCKED = "locked"

class CraftingType(Enum):
    """Типы крафтинга (централизованные)"""
    WEAPON_CRAFTING = "weapon_crafting"
    ARMOR_CRAFTING = "armor_crafting"
    CONSUMABLE_CRAFTING = "consumable_crafting"
    TOOL_CRAFTING = "tool_crafting"
    BUILDING_CRAFTING = "building_crafting"
    ENCHANTING = "enchanting"
    ALCHEMY = "alchemy"
    ENGINEERING = "engineering"
    # Короткие типы, используемые станциями в CraftingSystem
    WEAPON = "weapon"
    ARMOR = "armor"
    CONSUMABLE = "consumable"

class BuildingType(Enum):
    """Типы зданий (централизованные)"""
    HOUSE = "house"
    SHOP = "shop"
    TAVERN = "tavern"
    TEMPLE = "temple"
    GUILD = "guild"
    WAREHOUSE = "warehouse"
    WORKSHOP = "workshop"
    TOWER = "tower"
    FORTRESS = "fortress"
    RUINS = "ruins"

class StructureType(Enum):
    """Типы структур (централизованные)"""
    BUILDING = "building"
    BRIDGE = "bridge"
    WALL = "wall"
    GATE = "gate"
    MONUMENT = "monument"
    PORTAL = "portal"
    DUNGEON_ENTRANCE = "dungeon_entrance"
    RESOURCE_NODE = "resource_node"
    LANDMARK = "landmark"
    RUINS = "ruins"

class EffectType(Enum):
    """Типы эффектов (централизованные)"""
    BUFF = "buff"
    DEBUFF = "debuff"
    ENVIRONMENTAL = "environmental"
    MAGICAL = "magical"
    VISUAL = "visual"
    SOUND = "sound"
    PASSIVE = "passive"
    ACTIVE = "active"

class EffectCategory(Enum):
    """Категории эффектов (централизованные)"""
    STAT_MODIFIER = "stat_modifier"
    DAMAGE_OVER_TIME = "damage_over_time"
    HEAL_OVER_TIME = "heal_over_time"
    MOVEMENT = "movement"
    COMBAT = "combat"
    UTILITY = "utility"
    EMOTIONAL = "emotional"
    GENETIC = "genetic"
    REVERSIVE = "reversive"

class EntityType(Enum):
    """Типы сущностей"""
    PLAYER = "player"
    NPC = "npc"
    ENEMY = "enemy"
    BOSS = "boss"
    ITEM = "item"
    WEAPON = "weapon"
    ARMOR = "armor"
    CONSUMABLE = "consumable"
    STRUCTURE = "structure"
    VEHICLE = "vehicle"
    ANIMAL = "animal"
    PLANT = "plant"
    PROJECTILE = "projectile"
    EFFECT = "effect"
    TRIGGER = "trigger"

class EntityState(Enum):
    """Состояния сущностей"""
    ALIVE = "alive"
    DEAD = "dead"
    UNCONSCIOUS = "unconscious"
    STUNNED = "stunned"
    FROZEN = "frozen"
    BURNING = "burning"
    POISONED = "poisoned"
    HEALING = "healing"
    INVISIBLE = "invisible"
    INVULNERABLE = "invulnerable"

class UIElementType(Enum):
    """Типы элементов UI"""
    BUTTON = "button"
    LABEL = "label"
    PANEL = "panel"
    MENU = "menu"
    DIALOG = "dialog"
    HUD = "hud"
    INVENTORY = "inventory"
    SKILL_TREE = "skill_tree"
    MAP = "map"
    CHAT = "chat"

class UIState(Enum):
    """Состояния UI"""
    HIDDEN = "hidden"
    VISIBLE = "visible"
    ACTIVE = "active"
    DISABLED = "disabled"
    LOADING = "loading"
    ERROR = "error"

class SceneType(Enum):
    """Типы сцен"""
    MAIN_MENU = "main_menu"
    GAME_WORLD = "game_world"
    COMBAT = "combat"
    DIALOGUE = "dialogue"
    INVENTORY = "inventory"
    SKILL_TREE = "skill_tree"
    MAP = "map"
    SETTINGS = "settings"
    LOADING = "loading"
    CREDITS = "credits"

class SceneState(Enum):
    """Состояния сцен"""
    UNLOADED = "unloaded"
    LOADING = "loading"
    ACTIVE = "active"
    PAUSED = "paused"
    TRANSITIONING = "transitioning"
    UNLOADING = "unloading"

# = КОНСТАНТЫ СТОЙКОСТИ И ПРОБИТИЯ

TOUGHNESS_CONSTANTS = {
    # Базовые значения стойкости для разных типов врагов
    "base_toughness": {
        "player": 100,
        "npc": 50,
        "enemy": 800,
        "boss": 2000,
        "elite": 1500
    },
    
    # Множители восстановления стойкости
    "recovery_multipliers": {
        "normal": 1.0,
        "weakened": 0.5,
        "broken": 0.0,
        "recovering": 2.0
    },
    
    # Время восстановления стойкости (в секундах)
    "recovery_times": {
        "normal": 0.0,
        "weakened": 5.0,
        "broken": 10.0,
        "recovering": 3.0
    },
    
    # Множители урона при пробитии стойкости
    "break_damage_multipliers": {
        "normal": 1.0,
        "weakened": 1.5,
        "broken": 2.0,
        "recovering": 1.2
    },
    
    # Длительность стана при пробитии (в секундах)
    "break_stun_duration": {
        "normal": 0.0,
        "weakened": 1.0,
        "broken": 3.0,
        "recovering": 0.5
    },
    
    # Эффективность пробития для разных стихий
    "elemental_effectiveness": {
        "physical": {
            "physical": 1.0,
            "fire": 0.5,
            "ice": 0.5,
            "lightning": 0.5,
            "wind": 0.5,
            "quantum": 0.3,
            "imaginary": 0.3,
            "universal": 1.0
        },
        "fire": {
            "physical": 0.5,
            "fire": 1.0,
            "ice": 2.0,
            "lightning": 0.5,
            "wind": 0.5,
            "quantum": 0.3,
            "imaginary": 0.3,
            "universal": 1.0
        },
        "ice": {
            "physical": 0.5,
            "fire": 0.5,
            "ice": 1.0,
            "lightning": 0.5,
            "wind": 2.0,
            "quantum": 0.3,
            "imaginary": 0.3,
            "universal": 1.0
        },
        "lightning": {
            "physical": 0.5,
            "fire": 0.5,
            "ice": 0.5,
            "lightning": 1.0,
            "wind": 0.5,
            "quantum": 2.0,
            "imaginary": 0.3,
            "universal": 1.0
        },
        "wind": {
            "physical": 0.5,
            "fire": 0.5,
            "ice": 0.5,
            "lightning": 0.5,
            "wind": 1.0,
            "quantum": 0.3,
            "imaginary": 2.0,
            "universal": 1.0
        },
        "quantum": {
            "physical": 0.3,
            "fire": 0.3,
            "ice": 0.3,
            "lightning": 0.3,
            "wind": 0.3,
            "quantum": 1.0,
            "imaginary": 0.5,
            "universal": 1.0
        },
        "imaginary": {
            "physical": 0.3,
            "fire": 0.3,
            "ice": 0.3,
            "lightning": 0.3,
            "wind": 0.3,
            "quantum": 0.5,
            "imaginary": 1.0,
            "universal": 1.0
        },
        "universal": {
            "physical": 1.0,
            "fire": 1.0,
            "ice": 1.0,
            "lightning": 1.0,
            "wind": 1.0,
            "quantum": 1.0,
            "imaginary": 1.0,
            "universal": 1.0
        }
    }
}

# = БАЗОВЫЕ КОНСТАНТЫ

BASE_STATS = {
    "health": 100,
    "mana": 50,
    "stamina": 100,
    "attack": 10,
    "defense": 5,
    "speed": 1.0,
    "range": 1.0,
    "strength": 10,
    "agility": 10,
    "intelligence": 10,
    "vitality": 10,
    "wisdom": 10,
    "charisma": 10,
    "luck": 10,
    "endurance": 10,
    "toughness": 100,  # Добавлена стойкость
    "toughness_recovery": 10.0  # Восстановление стойкости в секунду
}

PROBABILITY_CONSTANTS = {
    "base_luck": 0.05,
    "base_critical_chance": 0.05,
    "base_dodge_chance": 0.05,
    "base_block_chance": 0.05,
    "base_break_chance": 0.1  # Шанс пробития стойкости
}

TIME_CONSTANTS = {
    "game_tick": 0.016,  # 60 FPS
    "update_interval": 0.1,
    "save_interval": 300.0,  # 5 минут
    "auto_save_interval": 600.0,  # 10 минут
    "session_timeout": 3600.0,  # 1 час
    "content_generation_timeout": 30.0,
    "toughness_recovery_interval": 1.0  # Интервал восстановления стойкости
}

# = ЦВЕТА ЭМОЦИЙ

EMOTION_COLORS = {
    EmotionType.JOY: (255, 255, 0),      # Желтый
    EmotionType.SADNESS: (0, 0, 255),    # Синий
    EmotionType.ANGER: (255, 0, 0),      # Красный
    EmotionType.FEAR: (128, 0, 128),     # Фиолетовый
    EmotionType.SURPRISE: (255, 165, 0), # Оранжевый
    EmotionType.DISGUST: (0, 128, 0),    # Зеленый
    EmotionType.TRUST: (0, 255, 255),    # Голубой
    EmotionType.ANTICIPATION: (255, 192, 203), # Розовый
    EmotionType.NEUTRAL: (128, 128, 128) # Серый
}

# = НАСТРОЙКИ СИСТЕМ

AI_SETTINGS = {
    "learning_rate": 0.1,
    "memory_capacity": 1000,
    "decision_threshold": 0.5,
    "adaptation_speed": 0.05,
    "personality_stability": 0.8
}

UI_SETTINGS = {
    "screen_width": 1920,
    "screen_height": 1080,
    "ui_scale": 1.0,
    "theme": "default",
    "language": "en",
    "show_fps": True,
    "show_debug_info": False
}

ENTITY_SETTINGS = {
    "max_entities_per_scene": 1000,
    "entity_update_interval": 0.1,
    "collision_detection": True,
    "physics_enabled": True,
    "ai_enabled": True
}

SCENE_SETTINGS = {
    "auto_save_on_scene_change": True,
    "preload_adjacent_scenes": True,
    "scene_transition_effects": True,
    "scene_loading_timeout": 30.0,
    "max_scene_stack_size": 10
}

# = МЕНЕДЖЕР КОНСТАНТ

class ConstantsManager:
    """Централизованный менеджер констант"""
    
    def __init__(self):
        self._constants = {
            'base_stats': BASE_STATS,
            'probability_constants': PROBABILITY_CONSTANTS,
            'time_constants': TIME_CONSTANTS,
            'toughness_constants': TOUGHNESS_CONSTANTS,
            'emotion_colors': EMOTION_COLORS,
            'ai_settings': AI_SETTINGS,
            'ui_settings': UI_SETTINGS,
            'entity_settings': ENTITY_SETTINGS,
            'scene_settings': SCENE_SETTINGS
        }
    
    def get_base_stats(self) -> Dict[str, Any]:
        """Получение базовых характеристик"""
        return self._constants['base_stats'].copy()
    
    def get_probability_constants(self) -> Dict[str, Any]:
        """Получение констант вероятности"""
        return self._constants['probability_constants'].copy()
    
    def get_time_constants(self) -> Dict[str, Any]:
        """Получение временных констант"""
        return self._constants['time_constants'].copy()
    
    def get_toughness_constants(self) -> Dict[str, Any]:
        """Получение констант стойкости"""
        return self._constants['toughness_constants'].copy()
    
    def get_emotion_colors(self) -> Dict[EmotionType, tuple]:
        """Получение цветов эмоций"""
        return self._constants['emotion_colors'].copy()
    
    def get_ai_settings(self) -> Dict[str, Any]:
        """Получение настроек ИИ"""
        return self._constants['ai_settings'].copy()
    
    def get_ui_settings(self) -> Dict[str, Any]:
        """Получение настроек UI"""
        return self._constants['ui_settings'].copy()
    
    def get_entity_settings(self) -> Dict[str, Any]:
        """Получение настроек сущностей"""
        return self._constants['entity_settings'].copy()
    
    def get_scene_settings(self) -> Dict[str, Any]:
        """Получение настроек сцен"""
        return self._constants['scene_settings'].copy()
    
    def get_toughness_effectiveness(self, attack_type: ToughnessType, defense_type: ToughnessType) -> float:
        """Получение эффективности пробития стойкости"""
        effectiveness = self._constants['toughness_constants']['elemental_effectiveness']
        if attack_type.value in effectiveness and defense_type.value in effectiveness[attack_type.value]:
            return effectiveness[attack_type.value][defense_type.value]
        return 1.0
    
    def get_break_damage_multiplier(self, stance_state: StanceState) -> float:
        """Получение множителя урона при пробитии"""
        multipliers = self._constants['toughness_constants']['break_damage_multipliers']
        return multipliers.get(stance_state.value, 1.0)
    
    def get_break_stun_duration(self, stance_state: StanceState) -> float:
        """Получение длительности стана при пробитии"""
        durations = self._constants['toughness_constants']['break_stun_duration']
        return durations.get(stance_state.value, 0.0)
    
    def get_toughness_recovery_time(self, stance_state: StanceState) -> float:
        """Получение времени восстановления стойкости"""
        recovery_times = self._constants['toughness_constants']['recovery_times']
        return recovery_times.get(stance_state.value, 0.0)
    
    def get_toughness_recovery_multiplier(self, stance_state: StanceState) -> float:
        """Получение множителя восстановления стойкости"""
        multipliers = self._constants['toughness_constants']['recovery_multipliers']
        return multipliers.get(stance_state.value, 1.0)
    
    def reset_stats(self):
        """Сброс статистики"""
        self.system_stats = {
            'total_constants': len(self._constants),
            'total_enums': len(self._enums),
            'total_settings': len(self._settings),
            'access_count': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'update_time': 0.0
        }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Получение информации о системе"""
        return {
            'name': self.component_id,
            'state': self.state.value,
            'priority': self.priority.value,
            'total_constants': self.system_stats['total_constants'],
            'total_enums': self.system_stats['total_enums'],
            'total_settings': self.system_stats['total_settings'],
            'access_count': self.system_stats['access_count'],
            'cache_hits': self.system_stats['cache_hits'],
            'cache_misses': self.system_stats['cache_misses'],
            'update_time': self.system_stats['update_time']
        }

# Глобальный экземпляр менеджера констант
constants_manager = ConstantsManager()
