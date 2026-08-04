"""
AI-EVOLVE Asset Manager
Система загрузки, кэширования и управления ассетами.
Оптимизирована для производительности и соответствия SOLID.
"""

import os
from typing import Dict, Optional, Any
from PIL import Image
from src.core.cache import LRUCache
from src.core.interfaces import ILoadable


class AssetManager(ILoadable):
    """
    Централизованный менеджер ассетов (SSOT для графики).
    Реализует кэширование, ленивую загрузку и пуллинг объектов.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._asset_cache: LRUCache = LRUCache(capacity=100, default_ttl=300)
        self._asset_paths: Dict[str, str] = {}
        self._base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "../../assets"))
        
        # Предзагрузка критических ассетов
        self._critical_assets = [
            'sprites/player.png',
            'ui/health_bar_bg.png',
            'ui/health_bar_fill.png'
        ]
    
    def register_asset(self, name: str, relative_path: str) -> None:
        """Регистрация пути к ассету (не загружает, только маппинг)"""
        full_path = os.path.join(self._base_dir, relative_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Asset not found: {full_path}")
        
        self._asset_paths[name] = full_path
    
    def load_asset(self, name: str) -> Optional[Image.Image]:
        """
        Загрузка ассета с кэшированием.
        Если ассет в кэше - возвращается из кэша.
        Если нет - загружается с диска и помещается в кэш.
        """
        # Проверка кэша
        cached = self._asset_cache.get(name)
        if cached is not None:
            return cached
        
        # Загрузка с диска
        path = self._asset_paths.get(name)
        if not path:
            # Попытка авто-обнаружения
            path = self._auto_discover_asset(name)
        
        if not path or not os.path.exists(path):
            return None
        
        try:
            img = Image.open(path).convert('RGBA')
            self._asset_cache.set(name, img)
            return img
        except Exception as e:
            print(f"❌ Error loading asset {name}: {e}")
            return None
    
    def _auto_discover_asset(self, name: str) -> Optional[str]:
        """Автоматический поиск ассета по имени"""
        # Если имя содержит путь (например 'sprites/player.png')
        if '/' in name or '\\' in name:
            path = os.path.join(self._base_dir, name)
            if os.path.exists(path):
                return path
            return None
        
        # Поиск во всех подкаталогах для простого имени
        for subdir in ['sprites', 'tiles', 'ui', 'effects']:
            path = os.path.join(self._base_dir, subdir, f"{name}.png")
            if os.path.exists(path):
                return path
        return None
    
    def preload_critical(self) -> int:
        """Предзагрузка критических ассетов"""
        count = 0
        for asset in self._critical_assets:
            name = asset.replace('/', '_').replace('.png', '')
            self.register_asset(name, asset)
            if self.load_asset(name):
                count += 1
        return count
    
    def preload_category(self, category: str) -> int:
        """Предзагрузка категории ассетов"""
        category_dir = os.path.join(self._base_dir, category)
        if not os.path.exists(category_dir):
            return 0
        
        count = 0
        for filename in os.listdir(category_dir):
            if filename.endswith('.png'):
                name = f"{category}_{filename[:-4]}"
                path = os.path.join(category, filename)
                self.register_asset(name, path)
                if self.load_asset(name):
                    count += 1
        return count
    
    def get_sprite(self, entity_type: str, variant: str = 'basic') -> Optional[Image.Image]:
        """Получение спрайта сущности"""
        if variant == 'basic':
            name = f"sprites/{entity_type}"
        else:
            name = f"sprites/{entity_type}_{variant}"
        
        # Попытка загрузки с расширением .png
        return self.load_asset(f"{name}.png")
    
    def get_tile(self, tile_type: str) -> Optional[Image.Image]:
        """Получение текстуры тайла"""
        return self.load_asset(f"tiles/{tile_type}.png")
    
    def get_ui_element(self, element_name: str) -> Optional[Image.Image]:
        """Получение UI элемента"""
        return self.load_asset(f"ui/{element_name}.png")
    
    def get_effect(self, effect_name: str) -> Optional[Image.Image]:
        """Получение эффекта"""
        return self.load_asset(f"effects/{effect_name}.png")
    
    def clear_cache(self) -> None:
        """Очистка кэша (освобождение памяти)"""
        self._asset_cache.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Статистика кэша"""
        return {
            'capacity': self._asset_cache.capacity,
            'current_size': len(self._asset_cache),
            'hits': self._asset_cache.hits,
            'misses': self._asset_cache.misses,
            'hit_rate': self._asset_cache.hit_rate
        }
    
    def unload_unused(self) -> int:
        """Выгрузка неиспользуемых ассетов (LRU eviction)"""
        # LRUCache автоматически вытесняет старые при превышении capacity
        # Здесь можно добавить принудительную выгрузку по TTL
        return self._asset_cache.cleanup()
    
    async def load_async(self, name: str) -> Optional[Image.Image]:
        """Асинхронная загрузка ассета"""
        import asyncio
        await asyncio.sleep(0)  # Yield control
        return self.load_asset(name)
    
    async def preload_all_async(self) -> Dict[str, int]:
        """Асинхронная предзагрузка всех ассетов"""
        import asyncio
        
        results = {'sprites': 0, 'tiles': 0, 'ui': 0, 'effects': 0}
        
        for category in results.keys():
            results[category] = self.preload_category(category)
            await asyncio.sleep(0)
        
        return results
    
    # ILoadable interface implementation
    def save_state(self) -> Dict[str, Any]:
        """Сохранение состояния менеджера (пути, статистика)"""
        return {
            'registered_assets': self._asset_paths.copy(),
            'cache_stats': self.get_cache_stats()
        }
    
    def load_state(self, state: Dict[str, Any]) -> None:
        """Загрузка состояния менеджера"""
        if 'registered_assets' in state:
            self._asset_paths.update(state['registered_assets'])


# Singleton instance getter
def get_asset_manager() -> AssetManager:
    """Получение экземпляра AssetManager (Singleton)"""
    return AssetManager()
