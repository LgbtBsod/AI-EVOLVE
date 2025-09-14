#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import math
from typing import Dict, List, Optional, Tuple
# Пробуем импортировать компоненты Panda3D с обработкой ошибок
try:
    from panda3d.core import LODNode, CullBinManager
    LOD_AVAILABLE = True
except ImportError:
    LOD_AVAILABLE = False
    LODNode = None
    CullBinManager = None

try:
    from panda3d.core import OcclusionCuller
    OCCLUSION_AVAILABLE = True
except ImportError:
    OCCLUSION_AVAILABLE = False
    OcclusionCuller = None

class PerformanceOptimizer:
    """Система оптимизации производительности рендеринга"""
    
    def __init__(self, game):
        self.game = game
        self.lod_manager = None
        self.occlusion_culler = None
        self.performance_stats = {
            'fps': 0,
            'frame_time': 0,
            'draw_calls': 0,
            'triangles': 0,
            'vertices': 0
        }
        self.optimization_level = "medium"  # low, medium, high, ultra
        self.adaptive_quality = True
        self.target_fps = 60
        self.min_fps = 30
        
    def initialize(self):
        """Инициализация системы оптимизации"""
        try:
            # Инициализируем LOD менеджер
            self._setup_lod_system()
            
            # Настраиваем окклюзию
            self._setup_occlusion_culling()
            
            # Настраиваем бины рендеринга
            self._setup_render_bins()
            
            # Запускаем мониторинг производительности
            self._start_performance_monitoring()
            
            print("✅ Система оптимизации инициализирована")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка инициализации системы оптимизации: {e}")
            return False
            
    def _setup_lod_system(self):
        """Настройка системы LOD (Level of Detail)"""
        if LOD_AVAILABLE:
            try:
                from panda3d.core import LODManager
                self.lod_manager = LODManager()
                print("✅ LOD система настроена")
            except Exception as e:
                print(f"⚠️  LOD система недоступна: {e}")
        else:
            print("⚠️  LOD система недоступна в данной версии Panda3D")
            
    def _setup_occlusion_culling(self):
        """Настройка окклюзионного отсечения"""
        if OCCLUSION_AVAILABLE:
            try:
                self.occlusion_culler = OcclusionCuller()
                print("✅ Окклюзионное отсечение настроено")
            except Exception as e:
                print(f"⚠️  Окклюзионное отсечение недоступно: {e}")
        else:
            print("⚠️  Окклюзионное отсечение недоступно в данной версии Panda3D")
            
    def _setup_render_bins(self):
        """Настройка бинов рендеринга для оптимизации"""
        if CullBinManager:
            try:
                # Настраиваем порядок рендеринга
                cull_bin_manager = CullBinManager.getGlobalPtr()
                
                # Бин для непрозрачных объектов
                cull_bin_manager.addBin("opaque", CullBinManager.BTStateSorted, 0)
                
                # Бин для прозрачных объектов
                cull_bin_manager.addBin("transparent", CullBinManager.BTStateSorted, 10)
                
                # Бин для UI элементов
                cull_bin_manager.addBin("ui", CullBinManager.BTStateSorted, 20)
                
                print("✅ Бины рендеринга настроены")
            except Exception as e:
                print(f"⚠️  Ошибка настройки бинов рендеринга: {e}")
        else:
            print("⚠️  Бины рендеринга недоступны в данной версии Panda3D")
            
    def _start_performance_monitoring(self):
        """Запуск мониторинга производительности"""
        def monitor_performance(task):
            # Получаем статистику производительности
            if hasattr(self.game, 'showbase'):
                self.performance_stats['fps'] = self.game.showbase.getAverageFrameRate()
                
            # Адаптивная оптимизация
            if self.adaptive_quality:
                self._adaptive_optimization()
                
            return Task.cont
            
        self.game.showbase.taskMgr.add(monitor_performance, "performance_monitor")
        
    def _adaptive_optimization(self):
        """Адаптивная оптимизация на основе FPS"""
        current_fps = self.performance_stats['fps']
        
        if current_fps < self.min_fps:
            # Снижаем качество
            self._reduce_quality()
        elif current_fps > self.target_fps + 10:
            # Повышаем качество
            self._increase_quality()
            
    def _reduce_quality(self):
        """Снижение качества рендеринга"""
        if self.optimization_level == "ultra":
            self.optimization_level = "high"
            self._apply_optimization_settings()
        elif self.optimization_level == "high":
            self.optimization_level = "medium"
            self._apply_optimization_settings()
        elif self.optimization_level == "medium":
            self.optimization_level = "low"
            self._apply_optimization_settings()
            
    def _increase_quality(self):
        """Повышение качества рендеринга"""
        if self.optimization_level == "low":
            self.optimization_level = "medium"
            self._apply_optimization_settings()
        elif self.optimization_level == "medium":
            self.optimization_level = "high"
            self._apply_optimization_settings()
        elif self.optimization_level == "high":
            self.optimization_level = "ultra"
            self._apply_optimization_settings()
            
    def _apply_optimization_settings(self):
        """Применение настроек оптимизации"""
        if not hasattr(self.game, 'render_system'):
            return
            
        render_system = self.game.render_system
        
        if self.optimization_level == "low":
            # Низкое качество
            self._set_low_quality(render_system)
        elif self.optimization_level == "medium":
            # Среднее качество
            self._set_medium_quality(render_system)
        elif self.optimization_level == "high":
            # Высокое качество
            self._set_high_quality(render_system)
        elif self.optimization_level == "ultra":
            # Ультра качество
            self._set_ultra_quality(render_system)
            
    def _set_low_quality(self, render_system):
        """Настройка низкого качества"""
        try:
            # Отключаем сглаживание
            if hasattr(render_system.showbase.win, 'setAntialias'):
                render_system.showbase.win.setAntialias(False)
                
            # Отключаем шейдеры
            render_system.render.setShaderAuto(False)
            
            # Уменьшаем дальность видимости
            if hasattr(render_system.cam, 'setFar'):
                render_system.cam.setFar(100)
                
        except Exception as e:
            print(f"⚠️  Ошибка настройки низкого качества: {e}")
            
    def _set_medium_quality(self, render_system):
        """Настройка среднего качества"""
        try:
            # Включаем базовое сглаживание
            if hasattr(render_system.showbase.win, 'setAntialias'):
                render_system.showbase.win.setAntialias(True)
                
            # Включаем базовые шейдеры
            render_system.render.setShaderAuto(True)
            
            # Средняя дальность видимости
            if hasattr(render_system.cam, 'setFar'):
                render_system.cam.setFar(500)
                
        except Exception as e:
            print(f"⚠️  Ошибка настройки среднего качества: {e}")
            
    def _set_high_quality(self, render_system):
        """Настройка высокого качества"""
        try:
            # Включаем сглаживание
            if hasattr(render_system.showbase.win, 'setAntialias'):
                render_system.showbase.win.setAntialias(True)
                
            # Включаем шейдеры
            render_system.render.setShaderAuto(True)
            render_system.render.setTwoSidedLighting(True)
            
            # Высокая дальность видимости
            if hasattr(render_system.cam, 'setFar'):
                render_system.cam.setFar(1000)
                
        except Exception as e:
            print(f"⚠️  Ошибка настройки высокого качества: {e}")
            
    def _set_ultra_quality(self, render_system):
        """Настройка ультра качества"""
        try:
            # Максимальное сглаживание
            if hasattr(render_system.showbase.win, 'setAntialias'):
                render_system.showbase.win.setAntialias(True)
                
            # Все шейдеры
            render_system.render.setShaderAuto(True)
            render_system.render.setTwoSidedLighting(True)
            render_system.render.setDepthTest(True)
            render_system.render.setDepthWrite(True)
            
            # Максимальная дальность видимости
            if hasattr(render_system.cam, 'setFar'):
                render_system.cam.setFar(2000)
                
        except Exception as e:
            print(f"⚠️  Ошибка настройки ультра качества: {e}")
            
    def create_lod_object(self, name, high_detail, medium_detail, low_detail, 
                         high_distance=50, medium_distance=100):
        """Создание объекта с LOD"""
        if not LOD_AVAILABLE or not self.lod_manager:
            return high_detail
            
        try:
            # Создаем LOD узел
            lod_node = LODNode(name)
            lod_np = self.game.render.attachNewNode(lod_node)
            
            # Добавляем уровни детализации
            high_np = lod_np.attachNewNode(high_detail)
            medium_np = lod_np.attachNewNode(medium_detail)
            low_np = lod_np.attachNewNode(low_detail)
            
            # Настраиваем расстояния переключения
            lod_node.addSwitch(high_distance, 0)
            lod_node.addSwitch(medium_distance, 1)
            lod_node.addSwitch(float('inf'), 2)
            
            return lod_np
            
        except Exception as e:
            print(f"❌ Ошибка создания LOD объекта: {e}")
            return high_detail
            
    def optimize_scene(self, scene_objects):
        """Оптимизация сцены"""
        try:
            # Группируем объекты по типу
            object_groups = self._group_objects(scene_objects)
            
            # Применяем оптимизации к каждой группе
            for group_type, objects in object_groups.items():
                self._optimize_object_group(group_type, objects)
                
            print(f"✅ Сцена оптимизирована: {len(scene_objects)} объектов")
            
        except Exception as e:
            print(f"❌ Ошибка оптимизации сцены: {e}")
            
    def _group_objects(self, objects):
        """Группировка объектов по типу"""
        groups = {
            'static': [],
            'dynamic': [],
            'transparent': [],
            'ui': []
        }
        
        for obj in objects:
            if hasattr(obj, 'is_static') and obj.is_static:
                groups['static'].append(obj)
            elif hasattr(obj, 'is_transparent') and obj.is_transparent:
                groups['transparent'].append(obj)
            elif hasattr(obj, 'is_ui') and obj.is_ui:
                groups['ui'].append(obj)
            else:
                groups['dynamic'].append(obj)
                
        return groups
        
    def _optimize_object_group(self, group_type, objects):
        """Оптимизация группы объектов"""
        if group_type == 'static':
            # Статические объекты можно объединить в один узел
            self._batch_static_objects(objects)
        elif group_type == 'transparent':
            # Прозрачные объекты сортируем по расстоянию
            self._sort_transparent_objects(objects)
        elif group_type == 'dynamic':
            # Динамические объекты оптимизируем по LOD
            self._apply_lod_to_dynamic_objects(objects)
            
    def _batch_static_objects(self, objects):
        """Объединение статических объектов"""
        # В реальной игре здесь была бы батчинг геометрии
        pass
        
    def _sort_transparent_objects(self, objects):
        """Сортировка прозрачных объектов по расстоянию"""
        # Сортируем по расстоянию до камеры
        if hasattr(self.game, 'cam'):
            camera_pos = self.game.cam.getPos()
            objects.sort(key=lambda obj: obj.getPos().distance(camera_pos))
            
    def _apply_lod_to_dynamic_objects(self, objects):
        """Применение LOD к динамическим объектам"""
        for obj in objects:
            if hasattr(obj, 'create_lod_versions'):
                obj.create_lod_versions()
                
    def set_optimization_level(self, level):
        """Установка уровня оптимизации"""
        if level in ["low", "medium", "high", "ultra"]:
            self.optimization_level = level
            self._apply_optimization_settings()
            return True
        return False
        
    def enable_adaptive_quality(self, enabled):
        """Включение/отключение адаптивного качества"""
        self.adaptive_quality = enabled
        
    def get_performance_stats(self):
        """Получение статистики производительности"""
        return self.performance_stats.copy()
        
    def get_optimization_recommendations(self):
        """Получение рекомендаций по оптимизации"""
        recommendations = []
        
        if self.performance_stats['fps'] < 30:
            recommendations.append("Снизьте качество графики")
            recommendations.append("Уменьшите дальность видимости")
            recommendations.append("Отключите пост-обработку")
            
        if self.performance_stats['fps'] > 60:
            recommendations.append("Можно повысить качество графики")
            recommendations.append("Можно увеличить дальность видимости")
            
        return recommendations
        
    def destroy(self):
        """Уничтожение системы оптимизации"""
        # Останавливаем мониторинг
        self.game.showbase.taskMgr.remove("performance_monitor")
        
        # Очищаем данные
        self.performance_stats.clear()
