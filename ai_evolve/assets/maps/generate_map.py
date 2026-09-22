#!/usr/bin/env python3
"""
Генератор карты для AI-EVOLVE.
Создает карту в формате JSON для загрузки движком.
Включает: ландшафт, спавны объектов, точки интереса, зоны.
"""

import json
import random
from pathlib import Path

def generate_terrain(width: int = 100, height: int = 100) -> list:
    """Генерирует простой ландшафт с биомами"""
    terrain = []
    
    for y in range(height):
        row = []
        for x in range(width):
            # Простая генерация на основе расстояния от центра
            cx, cy = width // 2, height // 2
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            
            # Шум
            noise = random.uniform(-0.1, 0.1)
            normalized_dist = dist / (width // 2) + noise
            
            if normalized_dist > 0.9:
                tile = "water"
            elif normalized_dist > 0.8:
                tile = "sand"
            elif normalized_dist > 0.6:
                tile = "grass"
            elif normalized_dist > 0.4:
                tile = random.choice(["grass", "forest"])
            elif normalized_dist > 0.2:
                tile = random.choice(["forest", "stone"])
            else:
                tile = "snow"
            
            row.append(tile)
        terrain.append(row)
    
    return terrain

def generate_spawns(terrain: list, count: int = 20, spawn_type: str = "enemy") -> list:
    """Генерирует точки спавна сущностей"""
    spawns = []
    height = len(terrain)
    width = len(terrain[0]) if terrain else 0
    
    for _ in range(count):
        attempts = 0
        while attempts < 100:
            x = random.randint(5, width - 6)
            y = random.randint(5, height - 6)
            tile = terrain[y][x]
            
            # Проверка подходящей поверхности
            if spawn_type == "enemy" and tile in ["grass", "forest", "stone"]:
                spawns.append({
                    "type": spawn_type,
                    "x": x,
                    "y": y,
                    "variant": random.choice(["basic", "archer", "brute"]),
                    "level": random.randint(1, 5)
                })
                break
            elif spawn_type == "player" and tile in ["grass", "sand"]:
                spawns.append({
                    "type": spawn_type,
                    "x": x,
                    "y": y
                })
                break
            elif spawn_type == "boss" and tile == "stone":
                spawns.append({
                    "type": spawn_type,
                    "x": x,
                    "y": y,
                    "name": random.choice(["Dragon", "Demon King", "Ancient Golem"])
                })
                break
            elif spawn_type == "loot" and tile in ["grass", "forest", "sand"]:
                spawns.append({
                    "type": spawn_type,
                    "x": x,
                    "y": y,
                    "rarity": random.choices(
                        ["common", "rare", "epic", "legendary"],
                        weights=[70, 20, 8, 2]
                    )[0]
                })
                break
            
            attempts += 1
    
    return spawns

def generate_points_of_interest(terrain: list) -> list:
    """Генерирует точки интереса"""
    pois = []
    height = len(terrain)
    width = len(terrain[0]) if terrain else 0
    
    poi_types = [
        {"type": "campfire", "tile": "grass", "radius": 3},
        {"type": "shrine", "tile": "forest", "radius": 2},
        {"type": "cave_entrance", "tile": "stone", "radius": 4},
        {"type": "oasis", "tile": "sand", "radius": 5},
        {"type": "ruins", "tile": "grass", "radius": 6},
        {"type": "arena", "tile": "stone", "radius": 10},
    ]
    
    for poi in poi_types:
        attempts = 0
        while attempts < 200:
            x = random.randint(poi["radius"] + 2, width - poi["radius"] - 2)
            y = random.randint(poi["radius"] + 2, height - poi["radius"] - 2)
            
            # Проверка области
            valid = True
            for dy in range(-poi["radius"], poi["radius"] + 1):
                for dx in range(-poi["radius"], poi["radius"] + 1):
                    if dx*dx + dy*dy <= poi["radius"]*poi["radius"]:
                        if terrain[y+dy][x+dx] != poi["tile"]:
                            valid = False
                            break
                if not valid:
                    break
            
            if valid:
                pois.append({
                    "type": poi["type"],
                    "x": x,
                    "y": y,
                    "radius": poi["radius"]
                })
                break
            
            attempts += 1
    
    return pois

def generate_map_config() -> dict:
    """Создает полную конфигурацию карты"""
    width, height = 100, 100
    
    print("🗺️  Генерация ландшафта...")
    terrain = generate_terrain(width, height)
    
    print("⚔️  Генерация спавнов врагов...")
    enemy_spawns = generate_spawns(terrain, count=30, spawn_type="enemy")
    
    print("👤 Генерация точки старта игрока...")
    player_spawn = generate_spawns(terrain, count=1, spawn_type="player")
    
    print("👹 Генерация босса...")
    boss_spawn = generate_spawns(terrain, count=1, spawn_type="boss")
    
    print("💰 Генерация лута...")
    loot_spawns = generate_spawns(terrain, count=15, spawn_type="loot")
    
    print("🏛️  Генерация точек интереса...")
    pois = generate_points_of_interest(terrain)
    
    # Подсчет биомов
    biome_counts = {}
    for row in terrain:
        for tile in row:
            biome_counts[tile] = biome_counts.get(tile, 0) + 1
    
    map_config = {
        "metadata": {
            "name": "Procedural Arena Map",
            "version": "1.0",
            "width": width,
            "height": height,
            "tile_size": 1.0,
            "generated_by": "ai_evolve_map_generator"
        },
        "biomes": {
            "water": {"color": [65, 105, 225], "walkable": False, "damage": 0},
            "sand": {"color": [237, 201, 175], "walkable": True, "speed_modifier": 0.9},
            "grass": {"color": [34, 139, 34], "walkable": True, "speed_modifier": 1.0},
            "forest": {"color": [0, 100, 0], "walkable": True, "speed_modifier": 0.8, "cover": True},
            "stone": {"color": [128, 128, 128], "walkable": True, "speed_modifier": 1.0},
            "snow": {"color": [255, 250, 250], "walkable": True, "speed_modifier": 0.7}
        },
        "terrain": terrain,
        "spawns": {
            "player": player_spawn,
            "enemies": enemy_spawns,
            "boss": boss_spawn,
            "loot": loot_spawns
        },
        "points_of_interest": pois,
        "stats": {
            "biome_distribution": biome_counts,
            "total_enemies": len(enemy_spawns),
            "total_loot": len(loot_spawns),
            "total_pois": len(pois)
        }
    }
    
    return map_config

def save_map(map_config: dict, output_path: str):
    """Сохраняет карту в JSON файл"""
    with open(output_path, 'w') as f:
        json.dump(map_config, f, indent=2)
    
    print(f"\n✅ Карта сохранена: {output_path}")
    print(f"📊 Статистика:")
    print(f"   Размер: {map_config['metadata']['width']}x{map_config['metadata']['height']}")
    print(f"   Врагов: {map_config['stats']['total_enemies']}")
    print(f"   Лута: {map_config['stats']['total_loot']}")
    print(f"   Точек интереса: {map_config['stats']['total_pois']}")
    print(f"   Биомы: {', '.join(f'{k}={v}' for k, v in map_config['stats']['biome_distribution'].items())}")

def main():
    base_dir = Path(__file__).parent.parent / "maps"
    base_dir.mkdir(exist_ok=True)
    
    print("🎮 AI-EVOLVE Map Generator\n")
    
    map_config = generate_map_config()
    
    output_file = base_dir / "arena_map.json"
    save_map(map_config, str(output_file))
    
    # Создадим README
    readme = base_dir / "README.md"
    with open(readme, 'w') as f:
        f.write("# Карты AI-EVOLVE\n\n")
        f.write("## arena_map.json\n")
        f.write("Процедурно сгенерированная карта арены.\n\n")
        f.write("### Структура:\n")
        f.write("- **terrain**: 2D массив тайлов (biome types)\n")
        f.write("- **spawns**: точки появления сущностей\n")
        f.write("- **points_of_interest**: локации (костры, святилища, пещеры, арены)\n\n")
        f.write("### Биомы:\n")
        f.write("- water (непроходимый)\n")
        f.write("- sand, grass, forest, stone, snow (проходимые с разными модификаторами)\n\n")
        f.write("## Создание своей карты\n")
        f.write("1. Запустите генератор: `python maps/generate_map.py`\n")
        f.write("2. Отредактируйте JSON вручную или в Tiled\n")
        f.write("3. Или создайте карту в Blender/Tiled и экспортируйте в JSON\n")
    
    print(f"📄 Создан README: {readme}")

if __name__ == "__main__":
    main()
