"""
L7 - Игрок-тренер (Renderer Layer)

Panda3D рендеринг и UI:
- Изометрическая камера
- Панели управления (спавн, директивы, эмоции)
- Редактор сцены
- Визуализация обучения
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class ToolMode(Enum):
    """Режимы редактора"""
    SPAWN_ENEMY = "spawn_enemy"
    SPAWN_TRAP = "spawn_trap"
    SPAWN_LOOT = "spawn_loot"
    TERRAIN_EDIT = "terrain_edit"
    DIRECTIVE_PLACE = "directive_place"
    CAMERA_FREE = "camera_free"


@dataclass
class SpawnConfig:
    """Конфигурация спавна объекта"""
    object_type: str
    position: tuple  # (x, y, z)
    rotation: float = 0.0
    scale: float = 1.0
    properties: Dict = None


@dataclass
class PlayerDirective:
    """Директива от игрока-тренера"""
    directive_type: str  # attack, defend, explore, retreat
    target_position: Optional[tuple]
    priority: int  # 1-5
    duration_seconds: float
    emotion_modifier: Optional[str] = None


class IsometricCamera:
    """
    Изометрическая камера для Panda3D
    
    Функции:
    - Изометрический вид (2:1 или 1:1)
    - Плавное перемещение
    - Zoom in/out
    - Вращение вокруг фокуса
    """
    
    def __init__(self, camera_node, aspect_ratio: float = 16/9):
        """
        Args:
            camera_node: Panda3D Camera node
            aspect_ratio: Соотношение сторон экрана
        """
        self.camera = camera_node
        self.aspect_ratio = aspect_ratio
        
        # Изометрические углы
        self.pitch = 35.264  # arctan(1/sqrt(2))
        self.heading = 45.0
        
        # Параметры zoom
        self.min_distance = 10.0
        self.max_distance = 100.0
        self.current_distance = 30.0
        
        # Фокус камеры
        self.focus_point = (0, 0, 0)
        
    def set_isometric_view(self):
        """Установить классический изометрический вид"""
        self.camera.set_p(self.pitch)
        self.camera.set_h(self.heading)
        self._update_position()
        
    def _update_position(self):
        """Обновить позицию камеры на основе фокуса и дистанции"""
        import math
        
        # Конвертация сферических координат в декартовы
        x = self.focus_point[0] + self.current_distance * math.cos(math.radians(self.pitch)) * math.cos(math.radians(self.heading))
        y = self.focus_point[1] + self.current_distance * math.cos(math.radians(self.pitch)) * math.sin(math.radians(self.heading))
        z = self.focus_point[2] + self.current_distance * math.sin(math.radians(self.pitch))
        
        self.camera.set_pos(x, y, z)
        self.camera.look_at(*self.focus_point)
        
    def zoom(self, delta: float):
        """
        Zoom камеры
        
        Args:
            delta: Изменение дистанции (>0 zoom out, <0 zoom in)
        """
        self.current_distance = max(
            self.min_distance,
            min(self.max_distance, self.current_distance + delta)
        )
        self._update_position()
        
    def pan(self, dx: float, dy: float):
        """
        Панорамирование камеры
        
        Args:
            dx: Смещение по X
            dy: Смещение по Y
        """
        self.focus_point = (
            self.focus_point[0] + dx,
            self.focus_point[1] + dy,
            self.focus_point[2]
        )
        self._update_position()
        
    def rotate_around_focus(self, angle_delta: float):
        """
        Вращение вокруг фокуса
        
        Args:
            angle_delta: Изменение угла (градусы)
        """
        self.heading = (self.heading + angle_delta) % 360
        self._update_position()


class SceneEditor:
    """
    Редактор сцены для размещения объектов
    
    Функции:
    - Спавн врагов, ловушек, сундуков
    - Редактирование ландшафта
    - Размещение директив
    - Предпросмотр перед размещением
    """
    
    def __init__(self, render_node):
        """
        Args:
            render_node: Panda3D render node
        """
        self.render = render_node
        self.current_tool = ToolMode.CAMERA_FREE
        self.preview_node = None
        self.spawn_history: List[SpawnConfig] = []
        
        # Палитра объектов
        self.available_enemies = []
        self.available_traps = []
        self.available_loot = []
        
    def set_tool(self, tool: ToolMode):
        """Выбрать инструмент редактора"""
        self.current_tool = tool
        print(f"Tool selected: {tool.value}")
        
    def spawn_object(self, config: SpawnConfig):
        """
        Заспавнить объект на сцене
        
        Args:
            config: Конфигурация спавна
        """
        # Загрузка модели
        model_path = self._get_model_path(config.object_type)
        model = self.render.attach_new_node(model_path)
        
        # Применение трансформации
        model.set_pos(*config.position)
        model.set_h(config.rotation)
        model.set_scale(config.scale)
        
        # Сохранение в историю
        self.spawn_history.append(config)
        
        print(f"Spawned {config.object_type} at {config.position}")
        return model
        
    def _get_model_path(self, object_type: str) -> str:
        """Получить путь к модели объекта"""
        # Здесь должна быть логика маппинга типов к путям
        return f"models/{object_type}.egg"
        
    def show_preview(self, position: tuple):
        """Показать превью объекта перед размещением"""
        if self.preview_node:
            self.preview_node.remove_node()
            
        # Создание полупрозрачного превью
        self.preview_node = self.render.attach_new_node("preview")
        self.preview_node.set_pos(*position)
        self.preview_node.set_transparency(True)
        self.preview_node.set_color_alpha(0.5)
        
    def hide_preview(self):
        """Скрыть превью"""
        if self.preview_node:
            self.preview_node.remove_node()
            self.preview_node = None
            
    def undo_last_spawn(self):
        """Отменить последний спавн"""
        if not self.spawn_history:
            return
            
        last_config = self.spawn_history.pop()
        # Удаление объекта (требуется ссылка на созданный узел)
        print(f"Undid spawn of {last_config.object_type}")


class TrainerUI:
    """
    UI панель игрока-тренера
    
    Компоненты:
    - Список активных агентов
    - Статистика обучения
    - Панель спавна
    - Эмоциональные модификаторы
    - Директивы
    """
    
    def __init__(self, base_gui):
        """
        Args:
            base_gui: Panda3D DirectGUI base
        """
        self.gui = base_gui
        self.panels = {}
        
        self._create_panels()
        
    def _create_panels(self):
        """Создать UI панели"""
        # TODO: Реализовать создание панелей через DirectGUI
        print("Creating trainer UI panels...")
        
        # Панель статистики агента
        self.panels['agent_stats'] = self._create_agent_stats_panel()
        
        # Панель спавна
        self.panels['spawn'] = self._create_spawn_panel()
        
        # Панель эмоций
        self.panels['emotions'] = self._create_emotion_panel()
        
        # Панель директив
        self.panels['directives'] = self._create_directive_panel()
        
    def _create_agent_stats_panel(self):
        """Панель статистики агента"""
        return {
            'visible': True,
            'position': (10, 10),
            'size': (300, 200)
        }
        
    def _create_spawn_panel(self):
        """Панель спавна объектов"""
        return {
            'visible': False,
            'position': (10, 220),
            'size': (200, 300),
            'categories': ['enemies', 'traps', 'loot', 'terrain']
        }
        
    def _create_emotion_panel(self):
        """Панель эмоциональных модификаторов"""
        emotions = ['happy', 'frustrated', 'excited', 'calm', 'stressed']
        return {
            'visible': False,
            'position': (320, 10),
            'size': (150, 200),
            'emotions': emotions
        }
        
    def _create_directive_panel(self):
        """Панель директив"""
        directives = ['attack', 'defend', 'explore', 'retreat', 'patrol']
        return {
            'visible': False,
            'position': (320, 220),
            'size': (150, 250),
            'directives': directives
        }
        
    def update_agent_stats(self, stats: Dict):
        """
        Обновить статистику агента
        
        Args:
            stats: Dictionary с метриками (win_rate, reward, и т.д.)
        """
        # TODO: Обновление UI элементов
        print(f"Updating agent stats: {stats}")
        
    def toggle_panel(self, panel_name: str):
        """Показать/скрыть панель"""
        if panel_name in self.panels:
            self.panels[panel_name]['visible'] = not self.panels[panel_name]['visible']
            print(f"Panel {panel_name}: {'shown' if self.panels[panel_name]['visible'] else 'hidden'}")


class AutoBalancer:
    """
    Автоматический балансировщик сложности
    
    Анализирует производительность агента и предлагает изменения:
    - Количество врагов
    - Типы ловушек
    - Частоту powerups
    - Модификаторы эмоций
    """
    
    def __init__(self):
        self.history = []
        
    def analyze_and_suggest(self, metrics: Dict) -> List[str]:
        """
        Проанализировать метрики и предложить изменения
        
        Args:
            metrics: Метрики текущей сессии
            
        Returns:
            Список рекомендаций
        """
        suggestions = []
        
        win_rate = metrics.get('win_rate', 0.5)
        
        if win_rate > 0.8:
            suggestions.append("Increase enemy count by 1-2")
            suggestions.append("Add elite enemies to composition")
        elif win_rate < 0.3:
            suggestions.append("Reduce enemy aggression")
            suggestions.append("Add more powerup spawns")
            
        if metrics.get('avg_battle_duration', 0) < 10:
            suggestions.append("Fights too short - add tanky enemies")
        elif metrics.get('avg_battle_duration', 0) > 60:
            suggestions.append("Fights dragging - reduce enemy HP")
            
        return suggestions


def create_training_session(
    session_id: str,
    agent_checkpoint: str,
    environment_config: Dict
) -> Dict:
    """
    Создать новую тренировочную сессию
    
    Args:
        session_id: Уникальный ID сессии
        agent_checkpoint: Путь к чекпоинту агента
        environment_config: Конфигурация среды
        
    Returns:
        Dictionary с компонентами сессии
    """
    print(f"Creating training session: {session_id}")
    
    # Здесь будет инициализация Panda3D, загрузка агента, и т.д.
    
    return {
        'session_id': session_id,
        'status': 'initialized',
        'components': {
            'camera': None,
            'editor': None,
            'ui': None,
            'balancer': AutoBalancer()
        }
    }
