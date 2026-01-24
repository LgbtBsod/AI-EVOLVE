#!/usr/bin/env python3
"""Система рендеринга - интеграция с Panda3D
Управление камерами, освещением, материалами и оптимизацией рендеринга"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import *
from typing import Dict, List, Optional, Any, Tuple, Callable
import logging
import math
import time
import threading

# Пробуем разные способы импорта Panda3D
try:
    from panda3d.core import *
    from panda3d.core import NodePath, LODManager, OcclusionCuller, Material, Light, DirectLabel, AmbientLight, DirectionalLight, CardMaker, Texture
except ImportError:
    try:
        from direct.showbase.ShowBase import ShowBase
    except ImportError:
        try:
            from direct.showbase import ShowBase
        except ImportError:
            raise ImportError("Не удалось импортировать Panda3D ни одним способом")

try:
    from direct.task import Task
except ImportError:
    Task = None

from src.core.architecture import BaseComponent, ComponentType, Priority, LifecycleState

logger = logging.getLogger(__name__)

# = ТИПЫ РЕНДЕРИНГА

class CameraType(Enum):
    """Типы камер"""
    FIRST_PERSON = "first_person"
    THIRD_PERSON = "third_person"
    ORBITAL = "orbital"
    ISOMETRIC = "isometric"
    TOP_DOWN = "top_down"
    FREE = "free"

class RenderQuality(Enum):
    """Качество рендеринга"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    ULTRA = "ultra"

class LightingType(Enum):
    """Типы освещения"""
    AMBIENT = "ambient"
    DIRECTIONAL = "directional"
    POINT = "point"
    SPOT = "spot"
    AREA = "area"

# = СТРУКТУРЫ ДАННЫХ

@dataclass
class CameraSettings:
    """Настройки камеры"""
    camera_type: CameraType
    position: Tuple[float, float, float] = (0, 0, 0)
    target: Tuple[float, float, float] = (0, 0, 0)
    fov: float = 60.0
    near_plane: float = 0.1
    far_plane: float = 1000.0
    sensitivity: float = 1.0
    zoom_speed: float = 1.0
    orbit_radius: float = 10.0
    orbit_speed: float = 1.0

@dataclass
class LightingSettings:
    """Настройки освещения"""
    lighting_type: LightingType
    position: Tuple[float, float, float] = (0, 0, 0)
    direction: Tuple[float, float, float] = (0, -1, 0)
    color: Tuple[float, float, float] = (1, 1, 1)
    intensity: float = 1.0
    range: float = 100.0
    angle: float = 45.0
    cast_shadows: bool = True

@dataclass
class MaterialSettings:
    """Настройки материала"""
    material_id: str
    diffuse_color: Tuple[float, float, float] = (0.8, 0.8, 0.8)
    specular_color: Tuple[float, float, float] = (1, 1, 1)
    ambient_color: Tuple[float, float, float] = (0.2, 0.2, 0.2)
    shininess: float = 32.0
    transparency: float = 1.0
    texture_path: Optional[str] = None
    normal_map_path: Optional[str] = None
    shader_path: Optional[str] = None

@dataclass
class RenderSettings:
    """Настройки рендеринга"""
    quality: RenderQuality = RenderQuality.MEDIUM
    resolution: Tuple[int, int] = (1280, 720)
    fullscreen: bool = False
    vsync: bool = True
    antialiasing: bool = True
    shadows: bool = True
    reflections: bool = False
    post_processing: bool = True
    max_fps: int = 60

class RenderSystem(BaseComponent):
    """Система рендеринга с интеграцией Panda3D"""
    
    def __init__(self, config=None, ui_manager=None):
        """Инициализация системы рендеринга"""
        super().__init__(
            component_id="render_system",
            component_type=ComponentType.SYSTEM,
            priority=Priority.CRITICAL
        )
        
        # Архитектурные компоненты
        self.state_manager = None
        self.attribute_system = None
        
        # Panda3D компоненты
        self.showbase: Optional[ShowBase] = None
        self.render: Optional[NodePath] = None
        self.cam: Optional[NodePath] = None
        
        # Камеры
        self.cameras: Dict[str, NodePath] = {}
        self.active_camera: Optional[str] = None
        self.camera_settings: Dict[str, CameraSettings] = {}
        
        # Освещение
        self.lights: Dict[str, Light] = {}
        self.lighting_settings: Dict[str, LightingSettings] = {}
        
        # Материалы
        self.materials: Dict[str, MaterialSettings] = {}
        self.material_cache: Dict[str, Material] = {}
        
        # Модели и объекты
        self.loaded_models: Dict[str, NodePath] = {}
        self.scene_objects: Dict[str, NodePath] = {}
        self.model_cache: Dict[str, NodePath] = {}
        
        # Настройки рендеринга
        self.render_settings = RenderSettings()
        
        # Оптимизация
        self.lod_manager: Optional[LODManager] = None
        self.occlusion_culler: Optional[OcclusionCuller] = None
        
        # Callbacks
        self.on_camera_change: Optional[Callable] = None
        self.on_quality_change: Optional[Callable] = None
        
        # Статистика системы
        self.system_stats = {
            'update_count': 0,
            'total_update_time': 0.0,
            'last_update_time': 0.0
        }
        
        logger.info("Система рендеринга инициализирована")
    
    def set_architecture_components(self, state_manager, attribute_system=None):
        """Установка архитектурных компонентов"""
        self.state_manager = state_manager
        self.attribute_system = attribute_system
        logger.info("Архитектурные компоненты установлены в RenderSystem")
    
    def initialize(self) -> bool:
        """Инициализация системы рендеринга"""
        try:
            logger.info("Инициализация RenderSystem...")
            
            # Создаем окно Panda3D
            if not self._create_panda3d_window():
                return False
            
            # Создание базовых камер
            if not self._create_default_cameras():
                return False
            
            # Настройка освещения
            if not self._setup_lighting():
                return False
            
            # Загрузка материалов
            if not self._load_materials():
                return False
            
            # Настройка оптимизации
            if not self._setup_optimization():
                return False
            
            self._state = LifecycleState.READY
            logger.info("RenderSystem инициализирован успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации RenderSystem: {e}")
            self._state = LifecycleState.ERROR
            return False
    
    def _create_panda3d_window(self) -> bool:
        """Создание окна Panda3D"""
        try:
            # Импортируем Panda3D
            from panda3d.core import WindowProperties, GraphicsPipe
            from direct.showbase.ShowBase import ShowBase
            
            # Создаем базовое окно
            self.showbase = ShowBase()
            
            # Настраиваем свойства окна
            props = WindowProperties()
            props.setTitle("AI-EVOLVE Enhanced Edition")
            props.setSize(*self.render_settings.resolution)
            props.setFullscreen(self.render_settings.fullscreen)
            props.setCursorHidden(False)
            
            # Применяем свойства
            self.showbase.win.requestProperties(props)
            
            # Настройка вертикальной синхронизации
            if self.render_settings.vsync:
                try:
                    if hasattr(self.showbase.win, 'setVerticalSync'):
                        self.showbase.win.setVerticalSync(True)
                    else:
                        logger.debug("setVerticalSync не поддерживается в данной версии Panda3D")
                except Exception as vsync_e:
                    logger.debug(f"Не удалось установить вертикальную синхронизацию: {vsync_e}")
            
            # Настройка стабилизации рендеринга
            try:
                if hasattr(self.showbase, 'setBackgroundColor'):
                    self.showbase.setBackgroundColor(0.1, 0.1, 0.1)
                
                # Устанавливаем стабильный FPS
                if hasattr(self.showbase, 'setFrameRateMeter'):
                    self.showbase.setFrameRateMeter(True)
                
                # Настройка сглаживания
                if hasattr(self.showbase.win, 'setAntialias'):
                    self.showbase.win.setAntialias(True)
                    
            except Exception as render_e:
                logger.debug(f"Не удалось настроить стабилизацию рендеринга: {render_e}")
            
            # Получаем основные компоненты
            self.render = self.showbase.render
            self.cam = self.showbase.cam
            
            logger.info("Окно Panda3D создано успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания окна Panda3D: {e}")
            return False
    
    def _create_default_cameras(self) -> bool:
        """Создание базовых камер"""
        try:
            # Основная камера
            main_camera = CameraSettings(
                camera_type=CameraType.ISOMETRIC,
                position=(0, -20, 10),
                target=(0, 0, 0),
                fov=60.0
            )
            
            self.camera_settings["main"] = main_camera
            self.cameras["main"] = self.cam
            self.active_camera = "main"
            
            # Орбитальная камера
            orbital_camera = self._create_orbital_camera()
            self.cameras["orbital"] = orbital_camera
            self.camera_settings["orbital"] = CameraSettings(
                camera_type=CameraType.ORBITAL,
                position=(0, -20, 10),
                target=(0, 0, 0),
                orbit_radius=20.0
            )
            
            # Изометрическая камера
            isometric_camera = self._create_isometric_camera()
            self.cameras["isometric"] = isometric_camera
            self.camera_settings["isometric"] = CameraSettings(
                camera_type=CameraType.ISOMETRIC,
                position=(20, -20, 20),
                target=(0, 0, 0),
                fov=45.0
            )
            
            logger.info(f"Создано {len(self.cameras)} камер")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания камер: {e}")
            return False
    
    def _create_orbital_camera(self) -> NodePath:
        """Создание орбитальной камеры"""
        try:
            from panda3d.core import Camera
            
            # Создание камеры
            camera = Camera("orbital_camera")
            camera_np = self.render.attachNewNode(camera)
            
            # Настройка позиции
            camera_np.setPos(0, -20, 10)
            camera_np.lookAt(0, 0, 0)
            
            return camera_np
            
        except Exception as e:
            logger.error(f"Ошибка создания орбитальной камеры: {e}")
            return self.cam
    
    def _create_isometric_camera(self) -> NodePath:
        """Создание изометрической камеры"""
        try:
            from panda3d.core import Camera
            
            # Создание камеры
            camera = Camera("isometric_camera")
            camera_np = self.render.attachNewNode(camera)
            
            # Настройка изометрической позиции
            camera_np.setPos(20, -20, 20)
            camera_np.lookAt(0, 0, 0)
            
            return camera_np
            
        except Exception as e:
            logger.error(f"Ошибка создания изометрической камеры: {e}")
            return self.cam
    
    def _setup_lighting(self) -> bool:
        """Настройка освещения"""
        try:
            from panda3d.core import AmbientLight, DirectionalLight, Vec4
            
            # Окружающее освещение
            ambient_light = AmbientLight('ambient_light')
            ambient_light.setColor(Vec4(0.5, 0.5, 0.5, 1))
            ambient_np = self.render.attachNewNode(ambient_light)
            self.render.setLight(ambient_np)
            self.lights["ambient"] = ambient_light
            
            # Направленное освещение (солнце)
            directional_light = DirectionalLight('directional_light')
            directional_light.setColor(Vec4(0.8, 0.8, 0.8, 1))
            directional_np = self.render.attachNewNode(directional_light)
            directional_np.setHpr(45, -45, 0)
            self.render.setLight(directional_np)
            self.lights["directional"] = directional_light
            
            # Дополнительный направленный свет
            directional_light2 = DirectionalLight('directional_light2')
            directional_light2.setColor(Vec4(0.4, 0.4, 0.4, 1))
            directional_light2_np = self.render.attachNewNode(directional_light2)
            directional_light2_np.setHpr(-45, -30, 0)
            self.render.setLight(directional_light2_np)
            self.lights["directional2"] = directional_light2
            
            # Настройки освещения
            self.lighting_settings["ambient"] = LightingSettings(
                lighting_type=LightingType.AMBIENT,
                color=(0.5, 0.5, 0.5),
                intensity=0.5
            )
            
            self.lighting_settings["directional"] = LightingSettings(
                lighting_type=LightingType.DIRECTIONAL,
                direction=(1, -1, 0),
                color=(0.8, 0.8, 0.8),
                intensity=0.8,
                cast_shadows=True
            )
            
            logger.info(f"Настроено {len(self.lights)} источников света")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка настройки освещения: {e}")
            return False
    
    def _load_materials(self) -> bool:
        """Загрузка материалов"""
        try:
            from panda3d.core import Material, VBase4
            
            # Базовые материалы
            materials = [
                MaterialSettings(
                    material_id="default",
                    diffuse_color=(0.8, 0.8, 0.8),
                    specular_color=(1, 1, 1),
                    shininess=32.0
                ),
                MaterialSettings(
                    material_id="metal",
                    diffuse_color=(0.7, 0.7, 0.8),
                    specular_color=(1, 1, 1),
                    shininess=128.0
                ),
                MaterialSettings(
                    material_id="wood",
                    diffuse_color=(0.6, 0.4, 0.2),
                    specular_color=(0.3, 0.3, 0.3),
                    shininess=16.0
                ),
                MaterialSettings(
                    material_id="stone",
                    diffuse_color=(0.5, 0.5, 0.5),
                    specular_color=(0.2, 0.2, 0.2),
                    shininess=8.0
                )
            ]
            
            for material in materials:
                self.materials[material.material_id] = material
                self._create_material(material)
            
            logger.info(f"Загружено {len(self.materials)} материалов")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки материалов: {e}")
            return False
    
    def _create_material(self, material_settings: MaterialSettings):
        """Создание материала"""
        try:
            from panda3d.core import Material, VBase4
            
            material = Material()
            
            # Настройка цветов
            material.setDiffuse(VBase4(*material_settings.diffuse_color, 1.0))
            material.setSpecular(VBase4(*material_settings.specular_color, 1.0))
            material.setAmbient(VBase4(*material_settings.ambient_color, 1.0))
            material.setShininess(material_settings.shininess)
            
            # Настройка прозрачности
            if material_settings.transparency < 1.0:
                material.setTransparency(Material.MAlpha)
            
            # Загрузка текстур
            if material_settings.texture_path:
                texture = self._load_texture(material_settings.texture_path)
                if texture:
                    material.setTexture(texture)
            
            self.material_cache[material_settings.material_id] = material
            
        except Exception as e:
            logger.error(f"Ошибка создания материала {material_settings.material_id}: {e}")
    
    def _load_texture(self, texture_path: str):
        """Загрузка текстуры"""
        try:
            from panda3d.core import Texture
            texture = Texture(texture_path)
            texture.read(texture_path)
            return texture
        except Exception as e:
            logger.debug(f"Не удалось загрузить текстуру {texture_path}: {e}")
            return None
    
    def _setup_optimization(self) -> bool:
        """Настройка оптимизации рендеринга"""
        try:
            # Импорт оптимизации рендеринга
            self.lod_manager = None
            self.occlusion_culler = None
            
            try:
                from panda3d.core import LODManager
                # Проверяем, что LODManager действительно доступен и работает
                test_lod = LODManager()
                if test_lod is not None:
                    self.lod_manager = test_lod
                    logger.info("LODManager инициализирован для оптимизации")
                else:
                    logger.debug("LODManager недоступен - оптимизация отключена")
            except (ImportError, AttributeError, Exception) as e:
                logger.debug(f"LODManager недоступен в данной версии Panda3D: {e}")
            
            try:
                from panda3d.core import OcclusionCuller
                # Проверяем, что OcclusionCuller доступен
                test_occlusion = OcclusionCuller()
                if test_occlusion is not None:
                    self.occlusion_culler = test_occlusion
                    logger.info("OcclusionCuller инициализирован для оптимизации")
                else:
                    logger.debug("OcclusionCuller недоступен - оптимизация отключена")
            except (ImportError, AttributeError, Exception) as e:
                logger.debug(f"OcclusionCuller недоступен в данной версии Panda3D: {e}")
            
            # Настройка качества рендеринга
            self._apply_quality_settings()
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка настройки оптимизации: {e}")
            return False
    
    def _apply_quality_settings(self):
        """Применение настроек качества"""
        try:
            quality = self.render_settings.quality
            
            if quality == RenderQuality.LOW:
                # Низкое качество
                try:
                    if hasattr(self.showbase.win, 'setAntialias'):
                        self.showbase.win.setAntialias(False)
                    else:
                        logger.debug("setAntialias не поддерживается в данной версии Panda3D")
                except Exception as e:
                    logger.debug(f"Не удалось отключить сглаживание: {e}")
                    
                self.render.setShaderAuto(False)
                
            elif quality == RenderQuality.MEDIUM:
                # Среднее качество
                try:
                    if hasattr(self.showbase.win, 'setAntialias'):
                        self.showbase.win.setAntialias(True)
                    else:
                        logger.debug("setAntialias не поддерживается в данной версии Panda3D")
                except Exception as e:
                    logger.debug(f"Не удалось включить сглаживание: {e}")
                    
                self.render.setShaderAuto(True)
                
            elif quality == RenderQuality.HIGH:
                # Высокое качество
                try:
                    if hasattr(self.showbase.win, 'setAntialias'):
                        self.showbase.win.setAntialias(True)
                    else:
                        logger.debug("setAntialias не поддерживается в данной версии Panda3D")
                except Exception as e:
                    logger.debug(f"Не удалось включить сглаживание: {e}")
                    
                self.render.setShaderAuto(True)
                self.render.setTwoSidedLighting(True)
                
            elif quality == RenderQuality.ULTRA:
                # Ультра качество
                try:
                    if hasattr(self.showbase.win, 'setAntialias'):
                        self.showbase.win.setAntialias(True)
                    else:
                        logger.debug("setAntialias не поддерживается в данной версии Panda3D")
                except Exception as e:
                    logger.debug(f"Не удалось включить сглаживание: {e}")
                    
                self.render.setShaderAuto(True)
                self.render.setTwoSidedLighting(True)
                self.render.setDepthTest(True)
                self.render.setDepthWrite(True)
            
            logger.info(f"Применены настройки качества: {quality.value}")
            
        except Exception as e:
            logger.error(f"Ошибка применения настроек качества: {e}")
    
    def start(self) -> bool:
        """Запуск системы рендеринга"""
        try:
            logger.info("Запуск RenderSystem...")
            
            if self._state != LifecycleState.READY:
                logger.error("RenderSystem не готов к запуску")
                return False
            
            # Запускаем главный цикл Panda3D
            self._start_render_loop()
            
            self._state = LifecycleState.RUNNING
            logger.info("RenderSystem запущен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска RenderSystem: {e}")
            self._state = LifecycleState.ERROR
            return False
    
    def _start_render_loop(self):
        """Запуск цикла рендеринга"""
        try:
            # Добавляем задачу обновления
            from direct.task import Task
            
            def update_task(task):
                try:
                    # Стабилизация FPS для устранения мерцания
                    if hasattr(self, 'showbase') and hasattr(self.showbase, 'setFrameRateMeter'):
                        current_fps = self.showbase.getAverageFrameRate()
                        if current_fps > 0 and current_fps < 30:
                            logger.debug(f"Низкий FPS: {current_fps}")
                            
                except Exception as update_error:
                    logger.debug(f"Ошибка в задаче обновления: {update_error}")
                    
                return Task.cont
            
            self.showbase.taskMgr.add(update_task, "render_update")
            
            logger.info("Цикл рендеринга запущен")
            
        except Exception as e:
            logger.error(f"Ошибка запуска цикла рендеринга: {e}")
    
    def update(self, delta_time: float):
        """Обновление системы рендеринга"""
        if self._state != LifecycleState.RUNNING:
            return
        
        try:
            # Обновляем статистику
            self.system_stats['update_count'] += 1
            self.system_stats['total_update_time'] += delta_time
            self.system_stats['last_update_time'] = time.time()
            
            # Обновляем орбитальные камеры
            for camera_id, settings in self.camera_settings.items():
                if settings.camera_type == CameraType.ORBITAL:
                    # Автоматическое вращение
                    current_time = time.time()
                    angle_x = current_time * settings.orbit_speed * 0.1
                    angle_y = math.pi / 4  # Фиксированный угол
                    self.orbit_camera(camera_id, angle_x, angle_y)
            
            # Обновляем Panda3D
            if hasattr(self, 'showbase'):
                self.showbase.graphicsEngine.renderFrame()
                
        except Exception as e:
            logger.error(f"Ошибка обновления RenderSystem: {e}")
    
    def run(self):
        """Запуск главного цикла Panda3D"""
        try:
            logger.info("=" * 60)
            logger.info("🚀 ЗАПУСК ГЛАВНОГО ЦИКЛА PANDA3D")
            logger.info("=" * 60)
            
            if hasattr(self, 'showbase'):
                logger.info("✅ ShowBase найден")
                
                # Запускаем главный цикл
                logger.info("🚀 ЗАПУСКАЕМ ГЛАВНЫЙ ЦИКЛ...")
                logger.info("⚠️  ВНИМАНИЕ: Окно должно остаться открытым!")
                logger.info("   Для выхода закройте окно игры")
                
                # ВАЖНО: Используем тот же подход что сработал в простом тесте
                self.showbase.run()
                logger.info("✅ showbase.run() завершен")
                
            else:
                logger.error("❌ Panda3D не инициализирован")
                raise Exception("Panda3D не инициализирован")
                
        except Exception as e:
            logger.error("=" * 60)
            logger.error("❌ ОШИБКА ЗАПУСКА ГЛАВНОГО ЦИКЛА")
            logger.error("=" * 60)
            logger.error(f"Ошибка запуска главного цикла: {e}")
            import traceback
            logger.error(f"Детали ошибки: {traceback.format_exc()}")
            raise
    
    def switch_camera(self, camera_id: str) -> bool:
        """Переключение камеры"""
        try:
            if camera_id not in self.cameras:
                # В прототипах RenderSystem может существовать без явной регистрации
                # дополнительных камер (например, только базовая камера ShowBase).
                # В этом случае отсутствие камеры не является критической ошибкой.
                logger.warning(f"Камера {camera_id} не найдена")
                return False
            
            # Переключение активной камеры
            old_camera = self.active_camera
            self.active_camera = camera_id
            
            # Применение настроек камеры
            camera_np = self.cameras[camera_id]
            settings = self.camera_settings.get(camera_id)
            
            if settings:
                camera_np.setPos(*settings.position)
                camera_np.lookAt(*settings.target)
            
            # Вызов callback
            if self.on_camera_change:
                self.on_camera_change(old_camera, camera_id)
            
            logger.info(f"Переключена камера: {old_camera} -> {camera_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка переключения камеры: {e}")
            return False
    
    def set_camera_position(self, camera_id: str, position: Tuple[float, float, float]):
        """Установка позиции камеры"""
        try:
            if camera_id not in self.cameras:
                return False
            
            camera_np = self.cameras[camera_id]
            camera_np.setPos(*position)
            
            # Обновление настроек
            if camera_id in self.camera_settings:
                self.camera_settings[camera_id].position = position
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка установки позиции камеры: {e}")
            return False
    
    def orbit_camera(self, camera_id: str, angle_x: float, angle_y: float):
        """Орбитальное движение камеры"""
        try:
            if camera_id not in self.cameras:
                return False
            
            camera_np = self.cameras[camera_id]
            settings = self.camera_settings.get(camera_id)
            
            if not settings or settings.camera_type != CameraType.ORBITAL:
                return False
            
            # Вычисление новой позиции
            radius = settings.orbit_radius
            x = radius * math.sin(angle_y) * math.cos(angle_x)
            y = radius * math.sin(angle_y) * math.sin(angle_x)
            z = radius * math.cos(angle_y)
            
            camera_np.setPos(x, y, z)
            camera_np.lookAt(*settings.target)
            
        except Exception as e:
            logger.error(f"Ошибка орбитального движения камеры: {e}")
    
    def add_light(self, light_id: str, settings: LightingSettings) -> bool:
        """Добавление источника света"""
        try:
            from panda3d.core import AmbientLight, DirectionalLight, PointLight, Spotlight, VBase4
            
            if settings.lighting_type == LightingType.AMBIENT:
                light = AmbientLight(light_id)
            elif settings.lighting_type == LightingType.DIRECTIONAL:
                light = DirectionalLight(light_id)
            elif settings.lighting_type == LightingType.POINT:
                light = PointLight(light_id)
            elif settings.lighting_type == LightingType.SPOT:
                light = Spotlight(light_id)
            else:
                logger.error(f"Неподдерживаемый тип освещения: {settings.lighting_type}")
                return False
            
            # Настройка света
            light.setColor(VBase4(*settings.color, 1.0))
            
            # Размещение света
            light_np = self.render.attachNewNode(light)
            light_np.setPos(*settings.position)
            
            if settings.lighting_type in [LightingType.DIRECTIONAL, LightingType.SPOT]:
                light_np.lookAt(*settings.direction)
            
            # Применение света
            self.render.setLight(light_np)
            
            # Сохранение
            self.lights[light_id] = light
            self.lighting_settings[light_id] = settings
            
            logger.info(f"Добавлен источник света: {light_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка добавления источника света: {e}")
            return False
    
    def apply_material(self, node_path, material_id: str) -> bool:
        """Применение материала к объекту"""
        try:
            if material_id not in self.material_cache:
                logger.error(f"Материал {material_id} не найден")
                return False
            
            material = self.material_cache[material_id]
            node_path.setMaterial(material)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка применения материала: {e}")
            return False
    
    def set_render_quality(self, quality: RenderQuality) -> bool:
        """Установка качества рендеринга"""
        try:
            self.render_settings.quality = quality
            self._apply_quality_settings()
            
            # Вызов callback
            if self.on_quality_change:
                self.on_quality_change(quality)
            
            logger.info(f"Установлено качество рендеринга: {quality.value}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка установки качества рендеринга: {e}")
            return False
    
    def get_camera_info(self, camera_id: str):
        """Получение информации о камере"""
        try:
            if camera_id not in self.cameras:
                return None
            
            camera_np = self.cameras[camera_id]
            settings = self.camera_settings.get(camera_id)
            
            return {
                "camera_id": camera_id,
                "position": camera_np.getPos(),
                "rotation": camera_np.getHpr(),
                "settings": settings.__dict__ if settings else None,
                "is_active": camera_id == self.active_camera
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения информации о камере: {e}")
            return None
    
    def get_render_stats(self) -> Dict[str, Any]:
        """Получение статистики рендеринга"""
        try:
            return {
                "active_camera": self.active_camera,
                "total_cameras": len(self.cameras),
                "total_lights": len(self.lights),
                "total_materials": len(self.materials),
                "render_quality": self.render_settings.quality.value,
                "resolution": self.render_settings.resolution,
                "fps": self.showbase.getAverageFrameRate() if hasattr(self, 'showbase') else 0
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики рендеринга: {e}")
            return {}
    
    def get_system_info(self) -> Dict[str, Any]:
        """Получение информации о системе"""
        return {
            'name': self.component_id,
            'state': self.state.value,
            'priority': self.priority.value,
            'active_camera': self.active_camera,
            'total_cameras': len(self.cameras),
            'total_lights': len(self.lights),
            'total_materials': len(self.materials),
            'render_quality': self.render_settings.quality.value,
            'resolution': self.render_settings.resolution,
            'fps': self.showbase.getAverageFrameRate() if hasattr(self, 'showbase') else 0,
            'update_count': self.system_stats.get('update_count', 0),
            'total_update_time': self.system_stats.get('total_update_time', 0.0),
            'last_update_time': self.system_stats.get('last_update_time', 0.0)
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self.system_stats = {
            'update_count': 0,
            'total_update_time': 0.0,
            'last_update_time': 0.0
        }
    
    def stop(self) -> bool:
        """Остановка системы рендеринга"""
        try:
            logger.info("Остановка RenderSystem...")
            
            self._state = LifecycleState.STOPPED
            logger.info("RenderSystem остановлен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки RenderSystem: {e}")
            return False
    
    def destroy(self) -> bool:
        """Уничтожение системы рендеринга"""
        try:
            logger.info("Уничтожение RenderSystem...")
            
            # Очистка камер
            for camera_np in self.cameras.values():
                if camera_np != self.cam:  # Не удаляем основную камеру
                    camera_np.removeNode()
            
            # Очистка источников света
            for light in self.lights.values():
                light.removeNode()
            
            # Очистка данных
            self.cameras.clear()
            self.camera_settings.clear()
            self.lights.clear()
            self.lighting_settings.clear()
            self.materials.clear()
            self.material_cache.clear()
            
            self._state = LifecycleState.DESTROYED
            logger.info("RenderSystem уничтожен успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка уничтожения RenderSystem: {e}")
            return False
    
    def load_model(self, model_id: str, model_path: str, position: Tuple[float, float, float] = (0, 0, 0)) -> bool:
        """Загрузка 3D модели"""
        try:
            if model_id in self.loaded_models:
                logger.warning(f"Модель {model_id} уже загружена")
                return True
            
            # Загружаем модель
            model = self.showbase.loader.loadModel(model_path)
            if not model:
                logger.error(f"Не удалось загрузить модель {model_path}")
                return False
            
            # Размещаем модель в сцене
            model.reparentTo(self.render)
            model.setPos(*position)
            
            # Сохраняем модель
            self.loaded_models[model_id] = model
            self.scene_objects[model_id] = model
            
            logger.info(f"Модель {model_id} загружена из {model_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки модели {model_id}: {e}")
            return False
    
    def create_primitive_object(self, object_id: str, primitive_type: str, position: Tuple[float, float, float] = (0, 0, 0)) -> bool:
        """Создание примитивного объекта"""
        try:
            if object_id in self.scene_objects:
                logger.warning(f"Объект {object_id} уже существует")
                return True
            
            from panda3d.core import CardMaker, GeomNode
            
            if primitive_type == "cube":
                # Создаем куб
                cm = CardMaker("cube")
                cm.setFrame(-1, 1, -1, 1)
                cube = self.render.attachNewNode(cm.generate())
                cube.setPos(*position)
                
            elif primitive_type == "sphere":
                # Создаем сферу (упрощенная версия)
                cm = CardMaker("sphere")
                cm.setFrame(-1, 1, -1, 1)
                sphere = self.render.attachNewNode(cm.generate())
                sphere.setPos(*position)
                
            else:
                logger.error(f"Неподдерживаемый тип примитива: {primitive_type}")
                return False
            
            # Сохраняем объект
            self.scene_objects[object_id] = cube if primitive_type == "cube" else sphere
            
            logger.info(f"Создан примитивный объект {object_id} типа {primitive_type}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания примитивного объекта {object_id}: {e}")
            return False
    
    def remove_object(self, object_id: str) -> bool:
        """Удаление объекта из сцены"""
        try:
            if object_id not in self.scene_objects:
                logger.warning(f"Объект {object_id} не найден")
                return False
            
            # Удаляем объект
            obj = self.scene_objects[object_id]
            obj.removeNode()
            
            # Очищаем из кэшей
            if object_id in self.loaded_models:
                del self.loaded_models[object_id]
            del self.scene_objects[object_id]
            
            logger.info(f"Объект {object_id} удален из сцены")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка удаления объекта {object_id}: {e}")
            return False
    
    def cleanup(self):
        """Очистка системы рендеринга"""
        try:
            # Очистка камер
            for camera_np in self.cameras.values():
                if camera_np != self.cam:  # Не удаляем основную камеру
                    camera_np.removeNode()
            
            # Очистка источников света
            for light in self.lights.values():
                light.removeNode()
            
            # Очистка объектов сцены
            for obj in self.scene_objects.values():
                obj.removeNode()
            
            # Очистка данных
            self.cameras.clear()
            self.camera_settings.clear()
            self.lights.clear()
            self.lighting_settings.clear()
            self.materials.clear()
            self.material_cache.clear()
            self.loaded_models.clear()
            self.scene_objects.clear()
            self.model_cache.clear()
            
            logger.info("Система рендеринга очищена")
            
        except Exception as e:
            logger.error(f"Ошибка очистки системы рендеринга: {e}")