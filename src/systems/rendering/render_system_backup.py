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
    from panda3d.core import NodePath, LODManager, OcclusionCuller, Material, Light, DirectLabel , AmbientLight, DirectionalLight, CardMaker, Texture
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
        
        # Добавляем состояние игры для предотвращения множественных сцен
        self.game_state = "menu"  # "menu", "game", "paused"
        self.game_scene_created = False
        self.pause_menu_created = False
        
        # Добавляем защиту от множественных кликов
        self.last_click_time = 0
        self.click_cooldown = 0.05  
        
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
            
            # Создаем базовую сцену для демонстрации
            self._create_demo_scene()
            
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
            
            # Настройка стабилизации рендеринга для устранения мерцания
            try:
                if hasattr(self.showbase, 'setBackgroundColor'):
                    self.showbase.setBackgroundColor(0.1, 0.1, 0.1)  # Темный фон
                
                # Устанавливаем стабильный FPS
                if hasattr(self.showbase, 'setFrameRateMeter'):
                    self.showbase.setFrameRateMeter(True)
                
                # Настройка сглаживания для устранения мерцания
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
    
    def _create_demo_scene(self):
        """Создание демонстрационной сцены"""
        try:
            # Создаем простой куб для демонстрации
            cube_geom = self._create_simple_cube()
            if cube_geom:
                # Оборачиваем GeomNode в NodePath для доступа к методам позиционирования
                cube = self.render.attachNewNode(cube_geom)
                cube.setPos(0, 0, 0)
                cube.setScale(1)
                
                # Применяем материал
                if 'default' in self.material_cache:
                    cube.setMaterial(self.material_cache['default'])
            
            # Добавляем текст
            from panda3d.core import TextNode
            text = TextNode("title")
            text.setText("AI-EVOLVE Enhanced Edition")
            text.setAlign(TextNode.ACenter)
            try:
                # Пробуем использовать setTextColor для новых версий Panda3D
                if hasattr(text, 'setTextColor'):
                    text.setTextColor(1, 1, 1, 1)
                elif hasattr(text, 'setColor'):
                    text.setColor(1, 1, 1, 1)
                else:
                    logger.debug("setColor не поддерживается для TextNode в данной версии Panda3D")
            except Exception as e:
                logger.warning(f"Не удалось установить цвет текста: {e}")
            
            text_np = self.render.attachNewNode(text)
            text_np.setPos(0, 0, 3)
            text_np.setScale(0.5)
            
            logger.info("Демонстрационная сцена создана")
            
        except Exception as e:
            logger.error(f"Ошибка создания демонстрационной сцены: {e}")
    
    def _create_simple_cube(self):
        """Создание простого куба"""
        try:
            from panda3d.core import GeomVertexFormat, GeomVertexData, GeomVertexWriter
            from panda3d.core import GeomTriangles, Geom, GeomNode
            
            # Создаем геометрию куба
            format = GeomVertexFormat.getV3n3c4()
            vdata = GeomVertexData("cube", format, Geom.UHStatic)
            
            # Вершины куба
            vertex = GeomVertexWriter(vdata, "vertex")
            normal = GeomVertexWriter(vdata, "normal")
            color = GeomVertexWriter(vdata, "color")
            
            # 8 вершин куба
            vertex.addData3(-1, -1, -1)
            vertex.addData3(1, -1, -1)
            vertex.addData3(1, 1, -1)
            vertex.addData3(-1, 1, -1)
            vertex.addData3(-1, -1, 1)
            vertex.addData3(1, -1, 1)
            vertex.addData3(1, 1, 1)
            vertex.addData3(-1, 1, 1)
            
            # Нормали и цвета
            for i in range(8):
                normal.addData3(0, 0, 1)
                color.addData4(0.8, 0.8, 0.8, 1)
            
            # Индексы для граней
            tris = GeomTriangles(Geom.UHStatic)
            
            # Нижняя грань
            tris.addVertices(0, 1, 2)
            tris.addVertices(0, 2, 3)
            # Верхняя грань
            tris.addVertices(4, 7, 6)
            tris.addVertices(4, 6, 5)
            # Передняя грань
            tris.addVertices(0, 4, 5)
            tris.addVertices(0, 5, 1)
            # Задняя грань
            tris.addVertices(2, 6, 7)
            tris.addVertices(2, 7, 3)
            # Левая грань
            tris.addVertices(0, 3, 7)
            tris.addVertices(0, 7, 4)
            # Правая грань
            tris.addVertices(1, 5, 6)
            tris.addVertices(1, 6, 2)
            
            tris.closePrimitive()
            
            # Создаем геометрию
            geom = Geom(vdata)
            geom.addPrimitive(tris)
            
            # Создаем узел
            node = GeomNode("cube")
            node.addGeom(geom)
            
            return node
            
        except Exception as e:
            logger.error(f"Ошибка создания куба: {e}")
            return None
    
    def _create_default_cameras(self) -> bool:
        """Создание базовых камер"""
        try:
            # Основная камера
            main_camera = CameraSettings(
                camera_type=CameraType.THIRD_PERSON,
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
            from panda3d.core import AmbientLight, DirectionalLight
            
            # Окружающее освещение
            ambient_light = AmbientLight("ambient_light")
            ambient_light.setColor((0.3, 0.3, 0.3, 1))
            ambient_np = self.render.attachNewNode(ambient_light)
            self.render.setLight(ambient_np)
            self.lights["ambient"] = ambient_light
            
            # Направленное освещение (солнце)
            directional_light = DirectionalLight("directional_light")
            directional_light.setColor((0.8, 0.8, 0.7, 1))
            directional_np = self.render.attachNewNode(directional_light)
            directional_np.setHpr(45, -45, 0)
            self.render.setLight(directional_np)
            self.lights["directional"] = directional_light
            
            # Настройки освещения
            self.lighting_settings["ambient"] = LightingSettings(
                lighting_type=LightingType.AMBIENT,
                color=(0.3, 0.3, 0.3),
                intensity=0.3
            )
            
            self.lighting_settings["directional"] = LightingSettings(
                lighting_type=LightingType.DIRECTIONAL,
                direction=(1, -1, 0),
                color=(0.8, 0.8, 0.7),
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
                    # Вращение куба
                    cube = self.render.find("cube")
                    if cube and not cube.isEmpty():
                        cube.setH(cube.getH() + 1)
                    
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
    
    def show_start_menu(self, ui_manager=None):
        """Отображение стартового меню"""
        try:
            logger.info("=" * 50)
            logger.info("🎮 СОЗДАНИЕ СТАРТОВОГО МЕНЮ")
            logger.info("=" * 50)
            
            if ui_manager:
                logger.info("🔍 Попытка создания стартового меню через UIManager...")
                # Создаем стартовое меню через UIManager
                start_menu = ui_manager.create_start_menu()
                if start_menu:
                    logger.info("✅ Стартовое меню отображено через UIManager")
                    return True
                else:
                    logger.warning("⚠️  Не удалось создать стартовое меню через UIManager")
                    return False
            else:
                logger.info("🔍 UIManager не предоставлен, создаем простое меню...")
                # Создаем простое стартовое меню напрямую
                result = self._create_simple_start_menu()
                if result:
                    logger.info("✅ Простое стартовое меню создано успешно")
                    return True
                else:
                    logger.warning("⚠️  Не удалось создать простое стартовое меню")
                    return False
                
        except Exception as e:
            logger.error("=" * 50)
            logger.error("❌ ОШИБКА СОЗДАНИЯ СТАРТОВОГО МЕНЮ")
            logger.error("=" * 50)
            logger.error(f"Ошибка отображения стартового меню: {e}")
            import traceback
            logger.error(f"Детали ошибки: {traceback.format_exc()}")
            return False
    
    def _on_start_game(self):
        """Обработчик нажатия кнопки START GAME"""
        try:
            # Проверяем задержку между кликами
            import time
            current_time = time.time()
            if current_time - self.last_click_time < self.click_cooldown:
                logger.debug("⚠️  Слишком быстрый клик, игнорируем")
                return
            
            # Проверяем состояние игры - предотвращаем множественные сцены
            if self.game_state == "game":
                logger.info("⚠️  Игра уже запущена, игнорируем повторное нажатие")
                return
                
            logger.info("🎮 Кнопка START GAME нажата!")
            
            # Обновляем время последнего клика
            self.last_click_time = current_time
            
            # Изменяем состояние игры
            self.game_state = "game"
            
            # Скрываем стартовое меню
            if hasattr(self, 'start_menu_elements'):
                hidden_count = 0
                for element in self.start_menu_elements.values():
                    if hasattr(element, 'hide'):
                        element.hide()
                        hidden_count += 1
                if hidden_count > 0:
                    logger.info(f"✅ Скрыто {hidden_count} элементов стартового меню")
            
            # Здесь можно добавить логику запуска игры
            logger.info("🚀 Запуск игрового процесса...")
            
            # Создаем простую игровую сцену только если она еще не создана
            if not self.game_scene_created:
                try:
                    self._create_game_scene()
                    self.game_scene_created = True
                    logger.info("✅ Игровая сцена успешно создана")
                except Exception as scene_error:
                    logger.error(f"❌ Ошибка создания игровой сцены: {scene_error}")
                    # Сбрасываем состояние при ошибке
                    self.game_state = "menu"
                    self.game_scene_created = False
                    logger.info("🔄 Состояние игры сброшено в 'menu' из-за ошибки создания сцены")
            else:
                logger.info("✅ Игровая сцена уже существует")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при нажатии START GAME: {e}")
            # Сбрасываем состояние при любой ошибке
            self.game_state = "menu"
            self.game_scene_created = False
            logger.info("🔄 Состояние игры сброшено в 'menu' из-за общей ошибки")
    
    def _on_settings(self):
        """Обработчик нажатия кнопки SETTINGS"""
        try:
            # Проверяем задержку между кликами
            import time
            current_time = time.time()
            if current_time - self.last_click_time < self.click_cooldown:
                logger.debug("⚠️  Слишком быстрый клик, игнорируем")
                return
            
            logger.info("⚙️  Кнопка SETTINGS нажата!")
            
            # Обновляем время последнего клика
            self.last_click_time = current_time
            
            # Если игра запущена, показываем меню паузы
            if self.game_state == "game":
                self._show_pause_menu()
            else:
                # Иначе показываем настройки (НЕ игровую сцену!)
                logger.info("🔧 Открытие настроек...")
                self._show_settings_menu()
                
        except Exception as e:
            logger.error(f"❌ Ошибка при нажатии SETTINGS: {e}")
    
    def _show_pause_menu(self):
        """Показать меню паузы"""
        try:
            if self.pause_menu_created:
                logger.info("⚠️  Меню паузы уже отображается")
                return
                
            logger.info("⏸️  Отображение меню паузы...")
            
            # Скрываем игровую сцену при показе меню паузы
            self._ensure_game_scene_hidden()
            
            if hasattr(self, 'showbase') and hasattr(self.showbase, 'render2d'):
                from direct.gui.DirectFrame import DirectFrame
                from direct.gui.DirectButton import DirectButton
                from direct.gui.DirectLabel import DirectLabel
                
                # Создаем фон меню паузы
                pause_frame = DirectFrame(
                    parent=self.showbase.render2d,
                    frameColor=(0, 0, 0, 0.8),
                    frameSize=(-0.5, 0.5, -0.6, 0.6),
                    pos=(0, 0, 0)
                )
                
                # Заголовок
                pause_title = DirectLabel(
                    parent=pause_frame,
                    text="ПАУЗА",
                    scale=0.06,
                    pos=(0, 0, 0.4),
                    text_fg=(1, 1, 1, 1),
                    text_shadow=(0, 0, 0, 1)
                )
                
                # Кнопка продолжить
                resume_button = DirectButton(
                    parent=pause_frame,
                    text="Продолжить",
                    scale=0.04,
                    pos=(0, 0, 0.2),
                    command=self._resume_game,
                    frameColor=(0.2, 0.6, 0.2, 1),
                    text_fg=(1, 1, 1, 1)
                )
                
                # Кнопка настройки
                settings_button = DirectButton(
                    parent=pause_frame,
                    text="Настройки",
                    scale=0.04,
                    pos=(0, 0, 0),
                    command=self._show_settings_menu,
                    frameColor=(0.2, 0.2, 0.6, 1),
                    text_fg=(1, 1, 1, 1)
                )
                
                # Кнопка выйти в меню
                menu_button = DirectButton(
                    parent=pause_frame,
                    text="В главное меню",
                    scale=0.04,
                    pos=(0, 0, -0.2),
                    command=self._return_to_main_menu,
                    frameColor=(0.6, 0.2, 0.2, 1),
                    text_fg=(1, 1, 1, 1)
                )
                
                # Сохраняем элементы меню паузы
                self.pause_menu_elements = {
                    'frame': pause_frame,
                    'title': pause_title,
                    'resume': resume_button,
                    'settings': settings_button,
                    'menu': menu_button
                }
                
                self.pause_menu_created = True
                logger.info("✅ Меню паузы создано")
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания меню паузы: {e}")
    
    def _show_settings_menu(self):
        """Показать меню настроек"""
        try:
            logger.info("🔧 Открытие настроек...")
            
            if hasattr(self, 'showbase') and hasattr(self.showbase, 'render2d'):
                from direct.gui.DirectFrame import DirectFrame
                from direct.gui.DirectButton import DirectButton
                from direct.gui.DirectLabel import DirectLabel
                
                # Создаем фон меню настроек
                settings_frame = DirectFrame(
                    parent=self.showbase.render2d,
                    frameColor=(0, 0, 0, 0.9),
                    frameSize=(-0.6, 0.6, -0.7, 0.7),
                    pos=(0, 0, 0)
                )
                
                # Заголовок настроек
                settings_title = DirectLabel(
                    parent=settings_frame,
                    text="НАСТРОЙКИ",
                    scale=0.06,
                    pos=(0, 0, 0.5),
                    text_fg=(1, 1, 0, 1),  # Яркий желтый
                    text_shadow=(0, 0, 0, 1)
                )
                
                # Кнопка качества графики
                graphics_button = DirectButton(
                    parent=settings_frame,
                    text="Качество графики: СРЕДНЕЕ",
                    scale=0.04,
                    pos=(0, 0, 0.3),
                    command=self._toggle_graphics_quality,
                    frameColor=(0.3, 0.3, 0.6, 1),
                    text_fg=(1, 1, 1, 1)
                )
                
                # Кнопка звука
                sound_button = DirectButton(
                    parent=settings_frame,
                    text="Звук: ВКЛ",
                    scale=0.04,
                    pos=(0, 0, 0.1),
                    command=self._toggle_sound,
                    frameColor=(0.3, 0.6, 0.3, 1),
                    text_fg=(1, 1, 1, 1)
                )
                
                # Кнопка управления
                controls_button = DirectButton(
                    parent=settings_frame,
                    text="Управление",
                    scale=0.04,
                    pos=(0, 0, -0.1),
                    command=self._show_controls_info,
                    frameColor=(0.6, 0.3, 0.3, 1),
                    text_fg=(1, 1, 1, 1)
                )
                
                # Кнопка возврата
                back_button = DirectButton(
                    parent=settings_frame,
                    text="НАЗАД",
                    scale=0.04,
                    pos=(0, 0, -0.3),
                    command=self._close_settings_menu,
                    frameColor=(0.6, 0.2, 0.2, 1),
                    text_fg=(1, 1, 1, 1)
                )
                
                # Сохраняем элементы меню настроек
                self.settings_menu_elements = {
                    'frame': settings_frame,
                    'title': settings_title,
                    'graphics': graphics_button,
                    'sound': sound_button,
                    'controls': controls_button,
                    'back': back_button
                }
                
                logger.info("✅ Меню настроек создано")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при показе настроек: {e}")
    
    def _resume_game(self):
        """Продолжить игру"""
        try:
            logger.info("▶️  Продолжение игры...")
            
            # Скрываем меню паузы
            if hasattr(self, 'pause_menu_elements'):
                for element in self.pause_menu_elements.values():
                    if hasattr(element, 'hide'):
                        element.hide()
                self.pause_menu_created = False
                logger.info("✅ Меню паузы скрыто")
            
            # Показываем игровую сцену при продолжении игры
            self._ensure_game_scene_visible()
            
        except Exception as e:
            logger.error(f"❌ Ошибка при продолжении игры: {e}")
    
    def _return_to_main_menu(self):
        """Вернуться в главное меню"""
        try:
            logger.info("🏠 Возврат в главное меню...")
            
            # Скрываем меню паузы
            if hasattr(self, 'pause_menu_elements'):
                for element in self.pause_menu_elements.values():
                    if hasattr(element, 'destroy'):
                        element.destroy()
                self.pause_menu_created = False
            
            # Скрываем игровую сцену
            if hasattr(self, 'game_scene_elements'):
                for element in self.game_scene_elements.values():
                    if hasattr(element, 'destroy'):
                        element.destroy()
                self.game_scene_created = False
            
            # Очищаем задачи анимации
            if hasattr(self, 'game_animation_tasks'):
                for task_name in self.game_animation_tasks:
                    if hasattr(self, 'showbase') and hasattr(self.showbase, 'taskMgr'):
                        self.showbase.taskMgr.remove(task_name)
                logger.info("✅ Задачи анимации очищены")
            
            # Очищаем управление камерой
            self._cleanup_camera_controls()
            
            # Показываем стартовое меню
            if hasattr(self, 'start_menu_elements'):
                for element in self.start_menu_elements.values():
                    if hasattr(element, 'show'):
                        element.show()
            
            # Возвращаемся в состояние меню
            self.game_state = "menu"
            self.game_scene_created = False
            logger.info("✅ Возврат в главное меню выполнен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при возврате в главное меню: {e}")
    
    def _setup_keyboard_controls(self):
        """Настройка клавиатурного управления"""
        try:
            logger.info("⌨️  Настройка клавиатурного управления...")
            
            if hasattr(self, 'showbase') and hasattr(self.showbase, 'accept'):
                # Клавиша ESC для паузы/меню
                self.showbase.accept('escape', self._handle_escape_key)
                logger.info("✅ Клавиша ESC настроена для паузы")
                
        except Exception as e:
            logger.error(f"❌ Ошибка настройки клавиатуры: {e}")
    
    def _handle_escape_key(self):
        """Обработка нажатия клавиши ESC"""
        try:
            if self.game_state == "game":
                if not self.pause_menu_created:
                    logger.info("⏸️  ESC нажата - показываем меню паузы")
                    self._show_pause_menu()
                else:
                    logger.info("▶️  ESC нажата - скрываем меню паузы")
                    self._resume_game()
            elif self.game_state == "menu":
                logger.info("⚠️  ESC нажата в главном меню - игнорируем")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки клавиши ESC: {e}")
    
    def _ensure_game_scene_hidden(self):
        """Убедиться, что игровая сцена скрыта в меню"""
        try:
            if hasattr(self, 'game_scene_elements') and self.game_scene_elements:
                for element in self.game_scene_elements.values():
                    try:
                        if hasattr(element, 'hide') and element and not element.isEmpty():
                            element.hide()
                        elif hasattr(element, 'stash') and element and not element.isEmpty():
                            element.stash()
                    except Exception as element_error:
                        logger.debug(f"Не удалось скрыть элемент: {element_error}")
                logger.info("✅ Игровая сцена скрыта")
        except Exception as e:
            logger.error(f"❌ Ошибка скрытия игровой сцены: {e}")
    
    def _ensure_game_scene_visible(self):
        """Убедиться, что игровая сцена видима в игре"""
        try:
            if hasattr(self, 'game_scene_elements') and self.game_scene_elements:
                for element in self.game_scene_elements.values():
                    try:
                        if hasattr(element, 'show') and element and not element.isEmpty():
                            element.show()
                        elif hasattr(element, 'unstash') and element and not element.isEmpty():
                            element.unstash()
                    except Exception as element_error:
                        logger.debug(f"Не удалось показать элемент: {element_error}")
                logger.info("✅ Игровая сцена показана")
        except Exception as e:
            logger.error(f"❌ Ошибка показа игровой сцены: {e}")
    
    def _setup_camera_controls(self):
        """Настройка простого управления камерой"""
        try:
            logger.info("📷 Настройка управления камерой...")
            
            if hasattr(self, 'showbase') and hasattr(self.showbase, 'accept'):
                # Клавиши WASD для перемещения камеры
                self.showbase.accept('w', self._move_camera_forward)
                self.showbase.accept('s', self._move_camera_backward)
                self.showbase.accept('a', self._move_camera_left)
                self.showbase.accept('d', self._move_camera_right)
                self.showbase.accept('q', self._move_camera_up)
                self.showbase.accept('e', self._move_camera_down)
                
                # Клавиши стрелок для поворота камеры
                self.showbase.accept('arrow_up', self._rotate_camera_up)
                self.showbase.accept('arrow_down', self._rotate_camera_down)
                self.showbase.accept('arrow_left', self._rotate_camera_left)
                self.showbase.accept('arrow_right', self._rotate_camera_right)
                
                logger.info("✅ Управление камерой настроено (WASD + стрелки)")
                
        except Exception as e:
            logger.error(f"❌ Ошибка настройки управления камерой: {e}")
    
    def _move_camera_forward(self):
        """Движение камеры вперед"""
        if hasattr(self, 'showbase') and hasattr(self.showbase, 'camera'):
            self.showbase.camera.setY(self.showbase.camera, -0.5)
    
    def _move_camera_backward(self):
        """Движение камеры назад"""
        if hasattr(self, 'showbase') and hasattr(self.showbase, 'camera'):
            self.showbase.camera.setY(self.showbase.camera, 0.5)
    
    def _move_camera_left(self):
        """Движение камеры влево"""
        if hasattr(self, 'showbase') and hasattr(self.showbase, 'camera'):
            self.showbase.camera.setX(self.showbase.camera, -0.5)
    
    def _move_camera_right(self):
        """Движение камеры вправо"""
        if hasattr(self, 'showbase') and hasattr(self.showbase, 'camera'):
            self.showbase.camera.setX(self.showbase.camera, 0.5)
    
    def _move_camera_up(self):
        """Движение камеры вверх"""
        if hasattr(self, 'showbase') and hasattr(self.showbase, 'camera'):
            self.showbase.camera.setZ(self.showbase.camera, 0.5)
    
    def _move_camera_down(self):
        """Движение камеры вниз"""
        if hasattr(self, 'showbase') and hasattr(self.showbase, 'camera'):
            self.showbase.camera.setZ(self.showbase.camera, -0.5)
    
    def _rotate_camera_up(self):
        """Поворот камеры вверх"""
        if hasattr(self, 'showbase') and hasattr(self.showbase, 'camera'):
            self.showbase.camera.setP(self.showbase.camera.getP() - 5)
    
    def _rotate_camera_down(self):
        """Поворот камеры вниз"""
        if hasattr(self, 'showbase') and hasattr(self.showbase, 'camera'):
            self.showbase.camera.setP(self.showbase.camera.getP() + 5)
    
    def _rotate_camera_left(self):
        """Поворот камеры влево"""
        if hasattr(self, 'showbase') and hasattr(self.showbase, 'camera'):
            self.showbase.camera.setH(self.showbase.camera.getH() - 5)
    
    def _rotate_camera_right(self):
        """Поворот камеры вправо"""
        if hasattr(self, 'showbase') and hasattr(self.showbase, 'camera'):
            self.showbase.camera.setH(self.showbase.camera.getH() + 5)
    
    def _cleanup_camera_controls(self):
        """Очистка управления камерой"""
        try:
            logger.info("📷 Очистка управления камерой...")
            
            if hasattr(self, 'showbase') and hasattr(self.showbase, 'ignore'):
                # Отключаем все клавиши управления камерой
                camera_keys = ['w', 's', 'a', 'd', 'q', 'e', 
                              'arrow_up', 'arrow_down', 'arrow_left', 'arrow_right']
                
                for key in camera_keys:
                    self.showbase.ignore(key)
                
                logger.info("✅ Управление камерой очищено")
                
        except Exception as e:
            logger.error(f"❌ Ошибка очистки управления камерой: {e}")
    
    def _toggle_graphics_quality(self):
        """Переключение качества графики"""
        try:
            current_quality = self.render_settings.quality
            if current_quality == RenderQuality.LOW:
                self.set_render_quality(RenderQuality.MEDIUM)
            elif current_quality == RenderQuality.MEDIUM:
                self.set_render_quality(RenderQuality.HIGH)
            elif current_quality == RenderQuality.HIGH:
                self.set_render_quality(RenderQuality.ULTRA)
            else:
                self.set_render_quality(RenderQuality.LOW)
            
            # Обновляем текст кнопки
            if hasattr(self, 'settings_menu_elements') and 'graphics' in self.settings_menu_elements:
                button = self.settings_menu_elements['graphics']
                button['text'] = f"Качество графики: {self.render_settings.quality.value.upper()}"
                
        except Exception as e:
            logger.error(f"❌ Ошибка переключения качества графики: {e}")
    
    def _toggle_sound(self):
        """Переключение звука"""
        try:
            if not hasattr(self, 'sound_enabled'):
                self.sound_enabled = True
            
            self.sound_enabled = not self.sound_enabled
            
            # Обновляем текст кнопки
            if hasattr(self, 'settings_menu_elements') and 'sound' in self.settings_menu_elements:
                button = self.settings_menu_elements['sound']
                button['text'] = f"Звук: {'ВКЛ' if self.sound_enabled else 'ВЫКЛ'}"
                
            logger.info(f"🔊 Звук {'включен' if self.sound_enabled else 'выключен'}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка переключения звука: {e}")
    
    def _show_controls_info(self):
        """Показать информацию об управлении"""
        try:
            if hasattr(self, 'showbase') and hasattr(self.showbase, 'render2d'):
                from direct.gui.DirectLabel import DirectLabel
                
                controls_info = DirectLabel(
                    parent=self.showbase.render2d,
                    text="Управление:\nWASD - движение камеры\nСтрелки - поворот камеры\nESC - пауза/меню\nМышь - выбор в меню",
                    scale=0.03,
                    pos=(0, 0, 0),
                    text_fg=(1, 1, 0, 1),  # Яркий желтый
                    text_shadow=(0, 0, 0, 1)
                )
                
                # Убираем через 5 секунд
                from direct.task import Task
                def remove_controls_info(task):
                    controls_info.destroy()
                    return Task.done
                
                self.showbase.taskMgr.doMethodLater(5.0, remove_controls_info, "remove_controls_info")
                
        except Exception as e:
            logger.error(f"❌ Ошибка показа информации об управлении: {e}")
    
    def _close_settings_menu(self):
        """Закрыть меню настроек"""
        try:
            if hasattr(self, 'settings_menu_elements'):
                for element in self.settings_menu_elements.values():
                    if hasattr(element, 'destroy'):
                        element.destroy()
                logger.info("✅ Меню настроек закрыто")
                
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия меню настроек: {e}")
    
    def _on_quit_game(self):
        """Обработчик нажатия кнопки QUIT GAME"""
        try:
            # Проверяем задержку между кликами
            import time
            current_time = time.time()
            if current_time - self.last_click_time < self.click_cooldown:
                logger.debug("⚠️  Слишком быстрый клик, игнорируем")
                return
            
            logger.info("🚪 Кнопка QUIT GAME нажата!")
            
            # Обновляем время последнего клика
            self.last_click_time = current_time
            
            # Завершаем игру
            logger.info("🛑 Завершение игры...")
            
            if hasattr(self, 'showbase'):
                self.showbase.userExit()
            
        except Exception as e:
            logger.error(f"❌ Ошибка при нажатии QUIT GAME: {e}")
    
    def _create_game_scene(self):
        """Создание игровой сцены после нажатия START GAME"""
        try:
            logger.info("🎨 Создание игровой сцены...")
            
            if hasattr(self, 'showbase'):
                # Скрываем стартовое меню
                if hasattr(self, 'start_menu_elements'):
                    hidden_count = 0
                    for element in self.start_menu_elements.values():
                        if hasattr(element, 'hide'):
                            element.hide()
                            hidden_count += 1
                    if hidden_count > 0:
                        logger.info(f"✅ Скрыто {hidden_count} элементов стартового меню")
                
                # Создаем простую 3D сцену
                from panda3d.core import GeomNode, NodePath, TextNode, PandaNode
                
                # Очищаем предыдущую сцену если она существует
                if hasattr(self, 'game_scene_elements') and self.game_scene_elements:
                    for element in self.game_scene_elements.values():
                        if hasattr(element, 'destroy'):
                            element.destroy()
                        elif hasattr(element, 'removeNode'):
                            element.removeNode()
                    logger.info("✅ Предыдущая игровая сцена очищена")
                
                # Очищаем предыдущие задачи анимации
                if hasattr(self, 'game_animation_tasks'):
                    for task_name in self.game_animation_tasks:
                        if hasattr(self, 'showbase') and hasattr(self.showbase, 'taskMgr'):
                            self.showbase.taskMgr.remove(task_name)
                    logger.info("✅ Предыдущие задачи анимации очищены")
                
                # Очищаем предыдущее управление камерой
                self._cleanup_camera_controls()
                
                # Создаем тестовый куб для персонажа
                test_node = GeomNode("player_cube")
                test_np = self.showbase.render.attachNewNode(test_node)
                test_np.setPos(0, 5, 0)
                
                # Добавляем простую анимацию вращения
                from direct.task import Task
                def rotate_cube(task):
                    test_np.setH(test_np.getH() + 1)
                    return Task.cont
                
                self.showbase.taskMgr.add(rotate_cube, "rotate_cube")
                logger.info("✅ Персонаж (куб) создан с анимацией")
                
                # Создаем простую землю
                from panda3d.core import CardMaker
                ground_maker = CardMaker("ground")
                ground_maker.setFrame(-10, 10, -10, 10)
                ground_np = self.showbase.render.attachNewNode(ground_maker.generate())
                ground_np.setP(-90)  # Поворачиваем горизонтально
                ground_np.setZ(-2)   # Размещаем ниже куба
                ground_np.setColor(0.3, 0.5, 0.3, 1)  # Зеленый цвет
                logger.info("✅ Земля создана")
                
                # Сохраняем элементы игровой сцены для возможного удаления
                self.game_scene_elements = {
                    'player_cube': test_np,
                    'ground': ground_np
                }
                
                # Сохраняем задачи анимации для очистки
                self.game_animation_tasks = ['rotate_cube']
                
                # Создаем HUD/UI элементы
                logger.info("🎮 Создание HUD/UI...")
                
                # Загружаем шрифт для HUD
                hud_font = None
                try:
                    from panda3d.core import DynamicTextFont
                    font_path = "assets/fonts/dotf1.ttf"
                    
                    # Проверяем существование файла шрифта
                    if Path(font_path).exists():
                        hud_font = DynamicTextFont(font_path)
                        logger.info("✅ Шрифт для HUD загружен")
                    else:
                        logger.warning(f"⚠️  Файл шрифта не найден: {font_path}")
                        
                except ImportError:
                    logger.warning("⚠️  DynamicTextFont недоступен в данной версии Panda3D")
                except Exception as e:
                    logger.warning(f"⚠️  Не удалось загрузить шрифт для HUD: {e}")
                
                # Создаем панель HUD
                from direct.gui.DirectFrame import DirectFrame
                hud_panel = DirectFrame(
                    parent=self.showbase.render2d,
                    frameColor=(0.1, 0.1, 0.1, 0.7),
                    frameSize=(-0.4, 0.4, -0.1, 0.1),
                    pos=(0, 0, -0.8)
                )
                logger.info("✅ Панель HUD создана")
                
                # Создаем элементы HUD
                from direct.gui.DirectLabel import DirectLabel
                
                # Здоровье
                health_label = DirectLabel(
                    parent=hud_panel,
                    text="HP: 100/100",
                    scale=0.03,
                    pos=(-0.3, 0, 0),
                    text_fg=(1, 0.2, 0.2, 1),  # Яркий красный цвет для здоровья
                    text_shadow=(0, 0, 0, 1)
                )
                # Применяем шрифт через правильный метод
                if hud_font:
                    try:
                        health_label.configure(font=hud_font)
                    except Exception as font_e:
                        logger.debug(f"Не удалось применить шрифт к health_label: {font_e}")
                logger.info("✅ Индикатор здоровья создан")
                
                # Мана
                mana_label = DirectLabel(
                    parent=hud_panel,
                    text="MP: 50/50",
                    scale=0.03,
                    pos=(-0.1, 0, 0),
                    text_fg=(0.2, 0.2, 1, 1),  # Яркий синий цвет для маны
                    text_shadow=(0, 0, 0, 1)
                )
                # Применяем шрифт через правильный метод
                if hud_font:
                    try:
                        mana_label.configure(font=hud_font)
                    except Exception as font_e:
                        logger.debug(f"Не удалось применить шрифт к mana_label: {font_e}")
                logger.info("✅ Индикатор маны создан")
                
                # Уровень
                level_label = DirectLabel(
                    parent=hud_panel,
                    text="LVL: 1",
                    scale=0.03,
                    pos=(0.1, 0, 0),
                    text_fg=(1, 1, 0.2, 1),  # Яркий желтый цвет для уровня
                    text_shadow=(0, 0, 0, 1)
                )
                # Применяем шрифт через правильный метод
                if hud_font:
                    try:
                        level_label.configure(font=hud_font)
                    except Exception as font_e:
                        logger.debug(f"Не удалось применить шрифт к level_label: {font_e}")
                logger.info("✅ Индикатор уровня создан")
                
                # Опыт
                exp_label = DirectLabel(
                    parent=hud_panel,
                    text="EXP: 0/100",
                    scale=0.03,
                    pos=(0.3, 0, 0),
                    text_fg=(0.2, 1, 0.2, 1),  # Яркий зеленый цвет для опыта
                    text_shadow=(0, 0, 0, 1)
                )
                # Применяем шрифт через правильный метод
                if hud_font:
                    try:
                        exp_label.configure(font=hud_font)
                    except Exception as font_e:
                        logger.debug(f"Не удалось применить шрифт к exp_label: {font_e}")
                logger.info("✅ Индикатор опыта создан")
                
                # Сообщение о начале игры
                game_start_label = DirectLabel(
                    parent=self.showbase.render2d,
                    text="ИГРА ЗАПУЩЕНА! Добро пожаловать в AI EVOLVE!",
                    scale=0.04,
                    pos=(0, 0, 0.3),
                    text_fg=(0, 1, 0.5, 1),  # Яркий зеленый с оттенком
                    text_shadow=(0, 0, 0, 1)
                )
                # Применяем шрифт через правильный метод
                if hud_font:
                    try:
                        game_start_label.configure(font=hud_font)
                    except Exception as font_e:
                        logger.debug(f"Не удалось применить шрифт к game_start_label: {font_e}")
                logger.info("✅ Сообщение о начале игры создано")
                
                # Инструкции по управлению
                controls_label = DirectLabel(
                    parent=self.showbase.render2d,
                    text="Управление: WASD - движение, стрелки - поворот, ESC - пауза",
                    scale=0.025,
                    pos=(0, 0, 0.2),
                    text_fg=(1, 1, 0.8, 1),  # Яркий белый с оттенком желтого
                    text_shadow=(0, 0, 0, 1)
                )
                # Применяем шрифт через правильный метод
                if hud_font:
                    try:
                        controls_label.configure(font=hud_font)
                    except Exception as font_e:
                        logger.debug(f"Не удалось применить шрифт к controls_label: {font_e}")
                logger.info("✅ Инструкции по управлению созданы")
                
                # Добавляем HUD элементы в хранилище
                self.game_scene_elements.update({
                    'hud_panel': hud_panel,
                    'health_label': health_label,
                    'mana_label': mana_label,
                    'level_label': level_label,
                    'exp_label': exp_label,
                    'game_start_label': game_start_label,
                    'controls_label': controls_label
                })
                
                # Убираем сообщение через 5 секунд
                from direct.task import Task
                def remove_game_start_label(task):
                    game_start_label.destroy()
                    return Task.done
                
                self.showbase.taskMgr.doMethodLater(5.0, remove_game_start_label, "remove_game_start")
                
                # Сохраняем ссылки на HUD элементы
                self.hud_elements = {
                    'panel': hud_panel,
                    'health': health_label,
                    'mana': mana_label,
                    'level': level_label,
                    'exp': exp_label
                }
                
                logger.info("✅ Игровая сцена создана успешно")
                
                # Убеждаемся, что игровая сцена видима
                self._ensure_game_scene_visible()
                
                # Добавляем простые элементы управления камерой
                self._setup_camera_controls()
                
            else:
                logger.error("❌ ShowBase недоступен")
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания игровой сцены: {e}")
            import traceback
            logger.error(f"Детали ошибки: {traceback.format_exc()}")
            
            # Сбрасываем состояние игры при ошибке
            self.game_state = "menu"
            self.game_scene_created = False
            logger.info("🔄 Состояние игры сброшено в 'menu' из-за ошибки")
    
    def _create_simple_start_menu(self):
        """Создание простого стартового меню"""
        try:
            logger.info("=" * 50)
            logger.info("🎮 СОЗДАНИЕ ПРОСТОГО СТАРТОВОГО МЕНЮ")
            logger.info("=" * 50)
            
            # Проверяем кодировку для корректного отображения символов
            import sys
            if sys.platform == "win32":
                try:
                    import locale
                    locale.setlocale(locale.LC_ALL, 'Russian_Russia.1251')
                    logger.info("✅ Кодировка для Windows установлена")
                except Exception as locale_e:
                    logger.debug(f"Не удалось установить кодировку: {locale_e}")
            
            logger.info("Начинаем создание простого стартового меню...")
            
            # Импортируем необходимые компоненты
            try:
                from direct.gui.DirectFrame import DirectFrame
                from direct.gui.DirectButton import DirectButton
                from direct.gui.DirectLabel import DirectLabel
                from direct.task import Task
                logger.info("✅ Импорт DirectGUI компонентов успешен")
            except ImportError as e:
                logger.error(f"❌ Ошибка импорта DirectGUI: {e}")
                return False
            
            if not hasattr(self, 'showbase') or not hasattr(self.showbase, 'render2d'):
                logger.error("❌ showbase.render2d недоступен")
                return False
            
            logger.info("✅ showbase.render2d доступен")
            
            # Создаем основную панель меню
            try:
                menu_frame = DirectFrame(
                    frameColor=(0.2, 0.2, 0.2, 0.8),
                    frameSize=(-0.3, 0.3, -0.4, 0.4),
                    pos=(0, 0, 0)
                )
                logger.info("✅ Панель меню создана")
            except Exception as e:
                logger.error(f"❌ Ошибка создания панели меню: {e}")
                return False
            
            # Привязываем к render2d
            try:
                menu_frame.reparentTo(self.showbase.render2d)
                logger.info("✅ Панель меню привязана к render2d")
            except Exception as e:
                logger.error(f"❌ Ошибка привязки панели к render2d: {e}")
                return False
            
                            # Создаем заголовок
                try:
                    title_label = DirectLabel(
                        parent=menu_frame,
                        text="AI EVOLVE",
                        scale=0.05,
                        pos=(0, 0, 0.25),
                        text_fg=(0, 1, 1, 1),  # Яркий голубой
                        text_shadow=(0, 0, 0, 1)
                    )
                    logger.info("✅ Заголовок создан")
                except Exception as e:
                    logger.error(f"❌ Ошибка создания заголовка: {e}")
                    return False
            
            # СОЗДАЕМ МЕНЮ С АЛЬТЕРНАТИВНОЙ ОБРАБОТКОЙ СОБЫТИЙ
            logger.info("🔧 Создание меню с альтернативной обработкой событий...")
            
            try:
                # Создаем простые кнопки без обработчиков
                start_button = DirectButton(
                    parent=menu_frame,
                    text="START GAME",
                    scale=0.04,
                    pos=(0, 0, 0.1),
                    frameColor=(0.2, 0.8, 0.2, 1),  # Яркий зеленый
                    text_fg=(0, 0, 0, 1),  # Черный текст для контраста
                    relief=1
                )
                logger.info("✅ Кнопка START GAME создана")
                
                settings_button = DirectButton(
                    parent=menu_frame,
                    text="SETTINGS",
                    scale=0.04,
                    pos=(0, 0, 0),
                    frameColor=(0.2, 0.2, 0.8, 1),  # Яркий синий
                    text_fg=(1, 1, 1, 1),  # Белый текст
                    relief=1
                )
                logger.info("✅ Кнопка SETTINGS создана")
                
                quit_button = DirectButton(
                    parent=menu_frame,
                    text="QUIT GAME",
                    scale=0.04,
                    pos=(0, 0, -0.1),
                    frameColor=(0.8, 0.2, 0.2, 1),  # Яркий красный
                    text_fg=(1, 1, 1, 1),  # Белый текст
                    relief=1
                )
                logger.info("✅ Кнопка QUIT GAME создана")
                
                # Сохраняем ссылки на элементы меню
                self.start_menu_elements = {
                    'frame': menu_frame,
                    'title': 'title_label',
                    'start_button': start_button,
                    'settings_button': settings_button,
                    'quit_button': quit_button
                }
                
                # ДОБАВЛЯЕМ АЛЬТЕРНАТИВНУЮ ОБРАБОТКУ СОБЫТИЙ
                logger.info("🔧 Добавление альтернативной обработки событий...")
                
                # Создаем задачу для проверки кликов по кнопкам
                def check_button_clicks(task):
                    try:
                        if hasattr(self, 'showbase') and hasattr(self.showbase, 'mouseWatcherNode'):
                            mouse_watcher = self.showbase.mouseWatcherNode
                            if mouse_watcher and mouse_watcher.hasMouse():
                                # Получаем позицию мыши
                                if hasattr(mouse_watcher, 'getMouse'):
                                    mouse_pos = mouse_watcher.getMouse()
                                    
                                    # Проверяем клик по START GAME кнопке
                                    if hasattr(start_button, 'getBounds'):
                                        bounds = start_button.getBounds()
                                        if bounds and mouse_pos[0] >= bounds[0] and mouse_pos[0] <= bounds[1] and mouse_pos[1] >= bounds[2] and mouse_pos[1] <= bounds[3]:
                                            if hasattr(mouse_watcher, 'is_button_down') and mouse_watcher.is_button_down('mouse1'):
                                                # Проверяем состояние игры перед обработкой клика
                                                if self.game_state != "game":
                                                    logger.info("🎯 START GAME кнопка нажата через альтернативную обработку!")
                                                    print("🎯 START GAME кнопка работает!")
                                                    try:
                                                        self._on_start_game()
                                                    except Exception as click_error:
                                                        logger.error(f"❌ Ошибка обработки клика START GAME: {click_error}")
                                                else:
                                                    logger.debug("⚠️  Игра уже запущена, игнорируем клик по START GAME")
                                                return Task.cont
                                    
                                    # Проверяем клик по SETTINGS кнопке
                                    if hasattr(settings_button, 'getBounds'):
                                        bounds = settings_button.getBounds()
                                        if bounds and mouse_pos[0] >= bounds[0] and mouse_pos[0] <= bounds[1] and mouse_pos[1] >= bounds[2] and mouse_pos[1] <= bounds[3]:
                                            if hasattr(mouse_watcher, 'is_button_down') and mouse_watcher.is_button_down('mouse1'):
                                                logger.info("🎯 SETTINGS кнопка нажата через альтернативную обработку!")
                                                print("🎯 SETTINGS кнопка работает!")
                                                self._on_settings()
                                                return Task.cont
                                    
                                    # Проверяем клик по QUIT GAME кнопке
                                    if hasattr(quit_button, 'getBounds'):
                                        bounds = quit_button.getBounds()
                                        if bounds and mouse_pos[0] >= bounds[0] and mouse_pos[0] <= bounds[1] and mouse_pos[1] >= bounds[2] and mouse_pos[1] <= bounds[3]:
                                            if hasattr(mouse_watcher, 'is_button_down') and mouse_watcher.is_button_down('mouse1'):
                                                logger.info("🎯 QUIT GAME кнопка нажата через альтернативную обработку!")
                                                print("🎯 QUIT GAME кнопка работает!")
                                                self._on_quit_game()
                                                return Task.cont
                    except Exception as e:
                        logger.warning(f"⚠️  Ошибка в альтернативной обработке событий: {e}")
                    
                    return Task.cont
                
                # Добавляем задачу проверки кликов
                self.showbase.taskMgr.add(check_button_clicks, "button_click_checker")
                logger.info("✅ Задача проверки кликов добавлена")
                
                # Добавляем обработку клавиши ESC для паузы
                self._setup_keyboard_controls()
                
            except Exception as e:
                logger.error(f"❌ Ошибка создания кнопок: {e}")
                return False
            
            # Дополнительная проверка - убеждаемся что меню видимо
            logger.info("🔍 Проверка видимости меню...")
            try:
                if hasattr(menu_frame, 'isVisible'):
                    is_visible = menu_frame.isVisible()
                    logger.info(f"   📊 Меню видимо: {is_visible}")
                else:
                    logger.info("   ⚠️  Метод isVisible недоступен")
                
                if hasattr(menu_frame, 'getPos'):
                    pos = menu_frame.getPos()
                    logger.info(f"   📍 Позиция меню: {pos}")
                else:
                    logger.info("   ⚠️  Метод getPos недоступен")
                
                if hasattr(menu_frame, 'getScale'):
                    scale = menu_frame.getScale()
                    logger.info(f"   📐 Масштаб меню: {scale}")
                else:
                    logger.info("   ⚠️  Метод getScale недоступен")
                    
            except Exception as e:
                logger.warning(f"   ⚠️  Не удалось проверить свойства меню: {e}")
            
            # Проверяем, что mouseWatcherNode доступен
            logger.info("🔍 Проверка mouseWatcherNode...")
            if hasattr(self.showbase, 'mouseWatcherNode'):
                mouse_watcher = self.showbase.mouseWatcherNode
                if mouse_watcher:
                    logger.info("   ✅ mouseWatcherNode доступен")
                    if hasattr(mouse_watcher, 'hasMouse'):
                        has_mouse = mouse_watcher.hasMouse()
                        logger.info(f"   📊 Мышь в окне: {has_mouse}")
                else:
                    logger.warning("   ⚠️  mouseWatcherNode не инициализирован")
            else:
                logger.warning("   ⚠️  mouseWatcherNode не найден")
            
            logger.info("✅ Простое стартовое меню создано успешно")
            return True
            
        except Exception as e:
            logger.error("=" * 50)
            logger.error("❌ ОШИБКА СОЗДАНИЯ СТАРТОВОГО МЕНЮ")
            logger.error("=" * 50)
            logger.error(f"Ошибка создания стартового меню: {e}")
            import traceback
            logger.error(f"Детали ошибки: {traceback.format_exc()}")
            return False
    
    def run(self):
        """Запуск главного цикла Panda3D"""
        try:
            logger.info("=" * 60)
            logger.info("🚀 ЗАПУСК ГЛАВНОГО ЦИКЛА PANDA3D")
            logger.info("=" * 60)
            
            if hasattr(self, 'showbase'):
                logger.info("✅ ShowBase найден")
                
                # Показываем стартовое меню
                logger.info("🎮 Отображение стартового меню...")
                menu_result = self.show_start_menu()
                if menu_result:
                    logger.info("✅ Стартовое меню успешно отображено")
                else:
                    logger.warning("⚠️  Не удалось отобразить стартовое меню")
                
                # Проверяем состояние окна перед запуском
                logger.info("🔍 Проверка состояния окна перед запуском...")
                if hasattr(self.showbase, 'win'):
                    win = self.showbase.win
                    logger.info(f"Окно найдено: {type(win).__name__}")
                    if hasattr(win, 'isValid'):
                        try:
                            is_valid = win.isValid()
                            logger.info(f"Окно валидно: {is_valid}")
                        except Exception as e:
                            logger.warning(f"Не удалось проверить валидность окна: {e}")
                else:
                    logger.warning("Окно не найдено в ShowBase")
                
                # Дополнительная проверка - убеждаемся, что окно видимо
                logger.info("🔍 Проверка видимости окна...")
                if hasattr(self.showbase, 'win'):
                    win = self.showbase.win
                    if hasattr(win, 'getXSize') and hasattr(win, 'getYSize'):
                        try:
                            width = win.getXSize()
                            height = win.getYSize()
                            logger.info(f"Размеры окна: {width}x{height}")
                        except Exception as e:
                            logger.warning(f"Не удалось получить размеры окна: {e}")
                    
                    # Проверяем, что окно не минимизировано
                    if hasattr(win, 'getState'):
                        try:
                            state = win.getState()
                            logger.info(f"Состояние окна: {state}")
                        except Exception as e:
                            logger.warning(f"Не удалось получить состояние окна: {e}")
                
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
                logger.error(f"Камера {camera_id} не найдена")
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
            
            # Очистка данных
            self.cameras.clear()
            self.camera_settings.clear()
            self.lights.clear()
            self.lighting_settings.clear()
            self.materials.clear()
            self.material_cache.clear()
            
            logger.info("Система рендеринга очищена")
            
        except Exception as e:
            logger.error(f"Ошибка очистки системы рендеринга: {e}")
