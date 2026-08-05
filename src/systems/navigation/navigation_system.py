#!/usr/bin/env python3
"""
Система навигации и поиска пути для персонажей
Использует упрощенный A* алгоритм с поддержкой динамических препятствий
"""

import heapq
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Node:
    """Узел графа для поиска пути"""
    x: float
    y: float
    g_cost: float = 0.0  # Стоимость от старта
    h_cost: float = 0.0  # Эвристическая стоимость до цели
    parent: Optional['Node'] = None
    
    @property
    def f_cost(self) -> float:
        return self.g_cost + self.h_cost
    
    def __lt__(self, other):
        return self.f_cost < other.f_cost


@dataclass
class PathResult:
    """Результат поиска пути"""
    success: bool
    path: list[tuple[float, float]] = field(default_factory=list)
    distance: float = 0.0
    error_message: str = ""


class NavigationSystem:
    """
    Система навигации с поиском пути и избеганием препятствий
    """
    
    def __init__(self, world_size: float = 5000.0, grid_resolution: float = 2.0):
        self.world_size = world_size
        self.grid_resolution = grid_resolution
        
        # Препятствия (статические и динамические)
        self.static_obstacles: list[dict] = []  # {x, y, radius}
        self.dynamic_obstacles: list[dict] = []  # {x, y, radius, entity_id}
        
        # Кэш путей для оптимизации
        self.path_cache: dict[str, PathResult] = {}
        self.cache_max_size = 100
        
        # Цели для исследования
        self.exploration_targets: list[tuple[float, float]] = []
        
    def add_static_obstacle(self, x: float, y: float, radius: float):
        """Добавить статическое препятствие"""
        self.static_obstacles.append({'x': x, 'y': y, 'radius': radius})
        
    def add_dynamic_obstacle(self, x: float, y: float, radius: float, entity_id: str):
        """Добавить динамическое препятствие"""
        self.dynamic_obstacles.append({
            'x': x, 'y': y, 'radius': radius, 'entity_id': entity_id
        })
        
    def remove_dynamic_obstacle(self, entity_id: str):
        """Удалить динамическое препятствие по ID сущности"""
        self.dynamic_obstacles = [
            obs for obs in self.dynamic_obstacles 
            if obs['entity_id'] != entity_id
        ]
        
    def find_path(self, start: tuple[float, float], end: tuple[float, float], 
                  avoidance_radius: float = 1.0) -> PathResult:
        """
        Найти путь от start до end с обходом препятствий
        Использует упрощенный A* на графе видимости
        """
        # Проверка кэша
        cache_key = f"{start}_{end}"
        if cache_key in self.path_cache:
            return self.path_cache[cache_key]
        
        # Прямая видимость - проверяем есть ли прямая линия без препятствий
        if self._has_line_of_sight(start, end, avoidance_radius):
            result = PathResult(
                success=True,
                path=[start, end],
                distance=self._calculate_distance(start, end)
            )
            self._cache_result(cache_key, result)
            return result
        
        # Поиск пути через промежуточные точки
        path = self._find_path_astar(start, end, avoidance_radius)
        
        if path and len(path) >= 2:
            distance = sum(
                self._calculate_distance(path[i], path[i+1]) 
                for i in range(len(path)-1)
            )
            result = PathResult(success=True, path=path, distance=distance)
        else:
            result = PathResult(
                success=False,
                error_message="Путь не найден"
            )
        
        self._cache_result(cache_key, result)
        return result
    
    def _find_path_astar(self, start: tuple[float, float], end: tuple[float, float],
                         avoidance_radius: float) -> list[tuple[float, float]]:
        """Упрощенный A* поиск пути"""
        # Создаем узлы для ключевых точек
        nodes = self._create_waypoint_graph(start, end, avoidance_radius)
        
        if not nodes:
            return []
        
        start_node = nodes.get('start')
        end_node = nodes.get('end')
        
        if not start_node or not end_node:
            return []
        
        # A* алгоритм
        open_set = [start_node]
        closed_set: set[tuple[float, float]] = set()
        
        while open_set:
            current = heapq.heappop(open_set)
            
            if (current.x, current.y) == (end_node.x, end_node.y):
                # Восстанавливаем путь
                path = []
                node = current
                while node:
                    path.append((node.x, node.y))
                    node = node.parent
                return list(reversed(path))
            
            closed_set.add((current.x, current.y))
            
            # Проверяем соседей
            for neighbor in self._get_neighbors(current, nodes, avoidance_radius):
                if (neighbor.x, neighbor.y) in closed_set:
                    continue
                
                tentative_g = current.g_cost + self._calculate_distance(
                    (current.x, current.y), (neighbor.x, neighbor.y)
                )
                
                if neighbor.parent is None or tentative_g < neighbor.g_cost:
                    neighbor.parent = current
                    neighbor.g_cost = tentative_g
                    neighbor.h_cost = self._calculate_distance(
                        (neighbor.x, neighbor.y), (end_node.x, end_node.y)
                    )
                    
                    if neighbor not in open_set:
                        heapq.heappush(open_set, neighbor)
        
        return []
    
    def _create_waypoint_graph(self, start: tuple[float, float], end: tuple[float, float],
                                avoidance_radius: float) -> dict[str, Node]:
        """Создать граф промежуточных точек для поиска пути"""
        nodes = {}
        
        # Добавляем старт и конец
        nodes['start'] = Node(x=start[0], y=start[1])
        nodes['end'] = Node(x=end[0], y=end[1])
        nodes['end'].h_cost = 0
        
        # Добавляем точки вокруг препятствий как потенциальные waypoints
        waypoint_id = 0
        all_obstacles = self.static_obstacles + self.dynamic_obstacles
        
        for obstacle in all_obstacles:
            obs_x, obs_y = obstacle['x'], obstacle['y']
            obs_radius = obstacle['radius'] + avoidance_radius
            
            # Создаем 8 точек вокруг препятствия
            for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
                rad = math.radians(angle)
                wx = obs_x + obs_radius * 1.5 * math.cos(rad)
                wy = obs_y + obs_radius * 1.5 * math.sin(rad)
                
                # Проверяем что точка в пределах мира
                if self._is_in_world_bounds(wx, wy):
                    node = Node(x=wx, y=wy)
                    node.h_cost = self._calculate_distance((wx, wy), end)
                    nodes[f'waypoint_{waypoint_id}'] = node
                    waypoint_id += 1
        
        return nodes
    
    def _get_neighbors(self, node: Node, nodes: dict[str, Node], 
                       avoidance_radius: float) -> list[Node]:
        """Получить доступных соседей узла"""
        neighbors = []
        
        for key, other_node in nodes.items():
            if key == 'start' or key == 'end' or key.startswith('waypoint_'):
                if (other_node.x, other_node.y) == (node.x, node.y):
                    continue
                
                # Проверяем прямую видимость между узлами
                if self._has_line_of_sight(
                    (node.x, node.y), (other_node.x, other_node.y), avoidance_radius
                ):
                    neighbors.append(other_node)
        
        return neighbors
    
    def _has_line_of_sight(self, start: tuple[float, float], end: tuple[float, float],
                           avoidance_radius: float) -> bool:
        """Проверить есть ли прямая видимость между точками"""
        # Дискретизируем линию и проверяем каждое звено
        distance = self._calculate_distance(start, end)
        if distance < 0.1:
            return True
        
        steps = int(distance / (avoidance_radius * 0.5))
        steps = max(steps, 2)
        
        dx = (end[0] - start[0]) / steps
        dy = (end[1] - start[1]) / steps
        
        for i in range(steps + 1):
            x = start[0] + dx * i
            y = start[1] + dy * i
            
            # Проверяем столкновения с препятствиями
            if self._check_collision(x, y, avoidance_radius):
                return False
        
        return True
    
    def _check_collision(self, x: float, y: float, radius: float) -> bool:
        """Проверить столкновение с препятствиями"""
        all_obstacles = self.static_obstacles + self.dynamic_obstacles
        
        for obstacle in all_obstacles:
            obs_x, obs_y = obstacle['x'], obstacle['y']
            obs_radius = obstacle['radius']
            
            distance = self._calculate_distance((x, y), (obs_x, obs_y))
            if distance < (obs_radius + radius):
                return True  # Столкновение!
        
        return False  # Нет столкновений
    
    def _is_in_world_bounds(self, x: float, y: float) -> bool:
        """Проверить находится ли точка в пределах мира"""
        half_size = self.world_size / 2
        return -half_size <= x <= half_size and -half_size <= y <= half_size
    
    def _calculate_distance(self, point1: tuple[float, float], 
                            point2: tuple[float, float]) -> float:
        """Вычислить расстояние между двумя точками"""
        dx = point2[0] - point1[0]
        dy = point2[1] - point1[1]
        return math.sqrt(dx * dx + dy * dy)
    
    def _cache_result(self, key: str, result: PathResult):
        """Кэшировать результат поиска пути"""
        if len(self.path_cache) >= self.cache_max_size:
            # Удаляем самый старый элемент
            oldest_key = next(iter(self.path_cache))
            del self.path_cache[oldest_key]
        
        self.path_cache[key] = result
    
    def get_exploration_target(self, current_pos: tuple[float, float], 
                               known_targets: list[tuple[float, float]]) -> tuple[float, float] | None:
        """
        Получить цель для исследования
        Возвращает ближайшую неизвестную точку или случайную точку для исследования
        """
        if known_targets:
            # Ищем ближайшую цель
            min_dist = float('inf')
            nearest_target = None
            
            for target in known_targets:
                dist = self._calculate_distance(current_pos, target)
                if dist < min_dist:
                    min_dist = dist
                    nearest_target = target
            
            return nearest_target
        
        # Если нет известных целей, выбираем случайную точку для исследования
        import random
        margin = self.world_size * 0.4
        return (
            random.uniform(-margin, margin),
            random.uniform(-margin, margin)
        )
    
    def clear_cache(self):
        """Очистить кэш путей"""
        self.path_cache.clear()
    
    def update_dynamic_obstacles(self, entities: list[dict]):
        """Обновить позиции динамических препятствий"""
        self.dynamic_obstacles.clear()
        for entity in entities:
            self.add_dynamic_obstacle(
                entity['x'], entity['y'], 
                entity.get('radius', 1.0), 
                entity['id']
            )
