"""
Combat Stats Component
Реализует ICombatStats интерфейс.
Отвечает только за хранение и расчет боевых характеристик.
"""
from src.core.interfaces import ICombatStats
from src.core.architecture import BaseComponent
from src.core.cache import LRUCache


class CombatStatsComponent(BaseComponent, ICombatStats):
    """
    Компонент боевых характеристик.
    Принцип единственной ответственности (SRP).
    Использует кэширование для тяжелых вычислений.
    """
    
    def __init__(
        self, 
        name: str = "CombatStats",
        base_damage: float = 10.0,
        base_defense: float = 0.0,
        base_speed: float = 1.0
    ):
        from src.core.architecture import ComponentType, Priority
        super().__init__(
            component_id=f"combat_stats_{name}",
            component_type=ComponentType.COMPONENT,
            priority=Priority.NORMAL
        )
        
        # Базовые характеристики
        self._base_damage = base_damage
        self._base_defense = base_defense
        self._base_speed = base_speed
        
        # Модификаторы (баффы/дебаффы)
        self._damage_mods: list = []
        self._defense_mods: list = []
        self._speed_mods: list = []
        
        # Кэш для тяжелых вычислений
        self._calc_cache = LRUCache(max_size=32, default_ttl=1.0)
    
    def _on_update(self, delta_time: float) -> None:
        """Обновление компонента - обновляет баффы."""
        self.update_buffs()
    
    @property
    def damage(self) -> float:
        """Итоговый урон с учетом всех модификаторов."""
        return self._calculate_stat("damage")
    
    @property
    def defense(self) -> float:
        """Итоговая защита с учетом всех модификаторов."""
        return self._calculate_stat("defense")
    
    @property
    def speed(self) -> float:
        """Итоговая скорость с учетом всех модификаторов."""
        return self._calculate_stat("speed")
    
    @property
    def base_damage(self) -> float:
        """Базовый урон без модификаторов."""
        return self._base_damage
    
    @property
    def base_defense(self) -> float:
        """Базовая защита без модификаторов."""
        return self._base_defense
    
    @property
    def base_speed(self) -> float:
        """Базовая скорость без модификаторов."""
        return self._base_speed
    
    def _calculate_stat(self, stat_name: str) -> float:
        """
        Расчет характеристики с кэшированием.
        """
        # Проверка кэша
        cached = self._calc_cache.get(stat_name)
        if cached is not None:
            return cached
        
        # Получение базового значения
        if stat_name == "damage":
            base = self._base_damage
            mods = self._damage_mods
        elif stat_name == "defense":
            base = self._base_defense
            mods = self._defense_mods
        elif stat_name == "speed":
            base = self._base_speed
            mods = self._speed_mods
        else:
            raise ValueError(f"Unknown stat: {stat_name}")
        
        # Применение модификаторов
        result = base
        for mod in mods:
            if mod.get("type") == "percent":
                result *= (1 + mod.get("value", 0) / 100.0)
            elif mod.get("type") == "flat":
                result += mod.get("value", 0)
        
        result = max(0.0, result)
        
        # Кэширование
        self._calc_cache.set(stat_name, result)
        
        return result
    
    def add_buff(self, stat: str, buff_type: str, value: float, duration: float = None) -> None:
        """
        Добавить бафф/дебафф к характеристике.
        
        Args:
            stat: Название характеристики (damage, defense, speed)
            buff_type: Тип модификатора (percent, flat)
            value: Значение модификатора
            duration: Длительность в секундах (None = постоянно)
        """
        mod = {
            "type": buff_type,
            "value": value,
            "duration": duration,
            "created_at": self._get_time() if duration else None
        }
        
        if stat == "damage":
            self._damage_mods.append(mod)
        elif stat == "defense":
            self._defense_mods.append(mod)
        elif stat == "speed":
            self._speed_mods.append(mod)
        
        # Очистка кэша
        self._calc_cache.delete(stat)
    
    def remove_buff(self, stat: str, value: float) -> bool:
        """Удалить конкретный модификатор."""
        mods_list = None
        if stat == "damage":
            mods_list = self._damage_mods
        elif stat == "defense":
            mods_list = self._defense_mods
        elif stat == "speed":
            mods_list = self._speed_mods
        
        if mods_list:
            for i, mod in enumerate(mods_list):
                if abs(mod.get("value", 0) - value) < 0.001:
                    mods_list.pop(i)
                    self._calc_cache.delete(stat)
                    return True
        
        return False
    
    def clear_buffs(self, stat: str = None) -> None:
        """Очистить все баффы."""
        if stat is None or stat == "damage":
            self._damage_mods.clear()
        if stat is None or stat == "defense":
            self._defense_mods.clear()
        if stat is None or stat == "speed":
            self._speed_mods.clear()
        
        self._calc_cache.clear()
    
    def _get_time(self) -> float:
        """Получение текущего времени."""
        import time
        return time.time()
    
    def update_buffs(self) -> None:
        """Обновление баффов (удаление истекших)."""
        now = self._get_time()
        
        for stat, mods_list in [
            ("damage", self._damage_mods),
            ("defense", self._defense_mods),
            ("speed", self._speed_mods)
        ]:
            expired = [
                m for m in mods_list 
                if m.get("duration") and now - m.get("created_at", 0) > m["duration"]
            ]
            
            for exp in expired:
                mods_list.remove(exp)
            
            if expired:
                self._calc_cache.delete(stat)
    
    def get_metrics(self) -> dict:
        """Метрики компонента."""
        base_metrics = super().get_metrics()
        base_metrics.update({
            "damage": self.damage,
            "defense": self.defense,
            "speed": self.speed,
            "damage_buffs_count": len(self._damage_mods),
            "defense_buffs_count": len(self._defense_mods),
            "speed_buffs_count": len(self._speed_mods),
            "cache_stats": self._calc_cache.stats
        })
        return base_metrics
