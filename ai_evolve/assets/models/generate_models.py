#!/usr/bin/env python3
"""
Генератор процедурных 3D моделей для AI-EVOLVE.
Создает простые .obj модели для персонажей, врагов и окружения.
"""

import os
from pathlib import Path
import math

def create_sphere_obj(path: str, radius: float = 1.0, segments: int = 16):
    """Создает сферу в формате OBJ"""
    vertices = []
    faces = []
    
    # Генерация вершин
    for i in range(segments + 1):
        lat = math.pi * (-0.5 + float(i) / segments)
        y = radius * math.sin(lat)
        r = radius * math.cos(lat)
        
        for j in range(segments + 1):
            lon = 2 * math.pi * float(j) / segments
            x = r * math.cos(lon)
            z = r * math.sin(lon)
            vertices.append((x, y, z))
    
    # Генерация граней
    for i in range(segments):
        for j in range(segments):
            v1 = i * (segments + 1) + j
            v2 = v1 + 1
            v3 = (i + 1) * (segments + 1) + j
            v4 = v3 + 1
            
            if i > 0:
                faces.append((v1, v3, v2))
            if i < segments - 1:
                faces.append((v2, v3, v4))
    
    # Запись в файл
    with open(path, 'w') as f:
        f.write(f"# AI-EVOLVE Model: {os.path.basename(path)}\n")
        f.write(f"# Vertices: {len(vertices)}, Faces: {len(faces)}\n\n")
        
        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        
        f.write("\n")
        
        for face in faces:
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
    
    print(f"✓ Создана модель: {path} ({len(vertices)} вершин, {len(faces)} граней)")

def create_cylinder_obj(path: str, radius: float = 1.0, height: float = 2.0, segments: int = 16):
    """Создает цилиндр в формате OBJ"""
    vertices = []
    faces = []
    
    # Верх и низ
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        x = radius * math.cos(angle)
        z = radius * math.sin(angle)
        vertices.append((x, -height/2, z))  # Низ
        vertices.append((x, height/2, z))   # Верх
    
    # Центр верха и низа
    vertices.append((0, -height/2, 0))  # Центр низа
    vertices.append((0, height/2, 0))   # Центр верха
    center_bottom = len(vertices) - 2
    center_top = len(vertices) - 1
    
    # Боковые грани
    for i in range(segments):
        next_i = (i + 1) % segments
        v1 = i * 2
        v2 = v1 + 1
        v3 = next_i * 2 + 1
        v4 = next_i * 2
        faces.append((v1, v2, v3))
        faces.append((v1, v3, v4))
    
    # Грани дна
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.append((center_bottom, i * 2, next_i * 2))
    
    # Грани верха
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.append((center_top, next_i * 2 + 1, i * 2 + 1))
    
    with open(path, 'w') as f:
        f.write(f"# AI-EVOLVE Model: {os.path.basename(path)}\n")
        f.write(f"# Vertices: {len(vertices)}, Faces: {len(faces)}\n\n")
        
        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        
        f.write("\n")
        
        for face in faces:
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
    
    print(f"✓ Создана модель: {path} ({len(vertices)} вершин, {len(faces)} граней)")

def create_box_obj(path: str, width: float = 1.0, height: float = 1.0, depth: float = 1.0):
    """Создает куб/бокс в формате OBJ"""
    w, h, d = width/2, height/2, depth/2
    
    vertices = [
        (-w, -h, -d), (w, -h, -d), (w, h, -d), (-w, h, -d),  # Задняя грань
        (-w, -h, d), (w, -h, d), (w, h, d), (-w, h, d)       # Передняя грань
    ]
    
    faces = [
        (0, 1, 2), (0, 2, 3),  # Зад
        (4, 6, 5), (4, 7, 6),  # Перед
        (0, 4, 5), (0, 5, 1),  # Низ
        (2, 6, 7), (2, 7, 3),  # Верх
        (0, 3, 7), (0, 7, 4),  # Лево
        (1, 5, 6), (1, 6, 2)   # Право
    ]
    
    with open(path, 'w') as f:
        f.write(f"# AI-EVOLVE Model: {os.path.basename(path)}\n")
        f.write(f"# Vertices: {len(vertices)}, Faces: {len(faces)}\n\n")
        
        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        
        f.write("\n")
        
        for face in faces:
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
    
    print(f"✓ Создана модель: {path} ({len(vertices)} вершин, {len(faces)} граней)")

def generate_all_models():
    base_dir = Path(__file__).parent
    models_dir = base_dir / "models"
    models_dir.mkdir(exist_ok=True)
    
    # Персонажи
    create_sphere_obj(str(models_dir / "player_head.obj"), radius=0.3, segments=12)
    create_cylinder_obj(str(models_dir / "player_body.obj"), radius=0.4, height=1.0, segments=12)
    create_cylinder_obj(str(models_dir / "player_arm.obj"), radius=0.1, height=0.8, segments=8)
    create_cylinder_obj(str(models_dir / "player_leg.obj"), radius=0.12, height=1.0, segments=8)
    
    # Враги
    create_sphere_obj(str(models_dir / "enemy_head.obj"), radius=0.35, segments=12)
    create_cylinder_obj(str(models_dir / "enemy_body.obj"), radius=0.5, height=1.2, segments=12)
    create_box_obj(str(models_dir / "enemy_shield.obj"), width=0.6, height=0.8, depth=0.1)
    
    # Боссы
    create_sphere_obj(str(models_dir / "boss_head.obj"), radius=0.8, segments=16)
    create_cylinder_obj(str(models_dir / "boss_body.obj"), radius=1.0, height=2.0, segments=16)
    create_box_obj(str(models_dir / "boss_weapon.obj"), width=0.2, height=1.5, depth=0.2)
    
    # Окружение
    create_box_obj(str(models_dir / "rock_small.obj"), width=0.5, height=0.4, depth=0.5)
    create_box_obj(str(models_dir / "rock_large.obj"), width=1.5, height=1.0, depth=1.5)
    create_cylinder_obj(str(models_dir / "tree_trunk.obj"), radius=0.3, height=3.0, segments=8)
    create_sphere_obj(str(models_dir / "tree_foliage.obj"), radius=1.5, segments=12)
    create_box_obj(str(models_dir / "crate.obj"), width=1.0, height=1.0, depth=1.0)
    create_box_obj(str(models_dir / "barrel.obj"), width=0.8, height=1.2, depth=0.8)
    
    # Арена
    create_box_obj(str(models_dir / "arena_wall.obj"), width=4.0, height=3.0, depth=0.5)
    create_box_obj(str(models_dir / "arena_floor.obj"), width=20.0, height=0.5, depth=20.0)
    create_cylinder_obj(str(models_dir / "arena_pillar.obj"), radius=0.5, height=4.0, segments=12)
    
    print(f"\n✅ Создано {len(list(models_dir.glob('*.obj')))} моделей")
    
    # README
    readme = models_dir / "README.md"
    with open(readme, 'w') as f:
        f.write("# 3D Модели AI-EVOLVE\n\n")
        f.write("Процедурно сгенерированные .obj модели.\n\n")
        f.write("## Структура\n")
        f.write("- **Персонажи**: player_*, enemy_*, boss_*\n")
        f.write("- **Окружение**: rock_*, tree_*, crate, barrel\n")
        f.write("- **Арена**: arena_*\n\n")
        f.write("## Замена на кастомные модели\n")
        f.write("1. Создайте модели в Blender/Maya\n")
        f.write("2. Экспортируйте в .obj или .gltf\n")
        f.write("3. Замените файлы в этой папке\n")
    print(f"📄 Создан README: {readme}")

if __name__ == "__main__":
    generate_all_models()
