# 🎮 AI-EVOLVE Assets

## Структура ассетов

```
assets/
├── textures/          # Текстуры (PNG)
│   ├── grass.png      # Трава (512x512)
│   ├── stone.png      # Камень (512x512)
│   ├── water.png      # Вода (512x512)
│   ├── player_skin.png # Кожа игрока (256x256)
│   └── ... (17 текстур)
│
├── models/            # 3D модели (OBJ)
│   ├── player_*.obj   # Части тела игрока
│   ├── enemy_*.obj    # Части тела врага
│   ├── boss_*.obj     # Части тела босса
│   ├── arena_*.obj    # Объекты арены
│   └── ... (19 моделей)
│
├── maps/              # Карты (JSON)
│   └── arena_map.json # Процедурная карта 100x100
│
└── audio/             # Аудио (заглушки для FMOD/Wwise)
```

## Генерация ассетов

### Текстуры
```bash
python assets/textures/generate_textures.py
```
Создает 17 процедурных текстур с использованием Pillow.

### Модели
```bash
python assets/models/generate_models.py
```
Создает 19 .obj моделей:
- **Персонажи**: голова, тело, руки, ноги
- **Враги**: голова, тело, щит
- **Боссы**: голова, тело, оружие
- **Окружение**: камни, деревья, ящики, бочки
- **Арена**: пол, стены, колонны

### Карты
```bash
python assets/maps/generate_map.py
```
Создает процедурную карту:
- Размер: 100x100 тайлов
- Биомы: вода, песок, трава, лес, камень, снег
- Спавны: 30 врагов, 1 босс, 15 лута, 1 игрок
- Точки интереса: костры, святилища, пещеры, руины, арены

## Интеграция с движком

### Panda3D
```python
from panda3d.core import load_model, Texture

# Загрузка модели
model = loader.load_model("assets/models/player_head.obj")
model.reparent_to(render)

# Загрузка текстуры
texture = loader.load_texture("assets/textures/grass.png")
model.set_texture(texture)
```

### Карта
```python
import json

with open("assets/maps/arena_map.json") as f:
    map_data = json.load(f)

terrain = map_data["terrain"]
spawns = map_data["spawns"]
pois = map_data["points_of_interest"]
```

## Замена на кастомные ассеты

1. **Текстуры**: Замените PNG файлы в `assets/textures/`
2. **Модели**: Экспортируйте из Blender/Maya в `.obj` или `.gltf`
3. **Карты**: Создайте в Tiled и экспортируйте в JSON

## Требования

- **Pillow** для генерации текстур: `pip install Pillow`
- **Blender** (опционально) для редактирования моделей
- **Tiled** (опционально) для редактирования карт

## Статистика

| Тип | Количество | Общий размер |
|-----|------------|--------------|
| Текстуры | 17 | ~50 KB |
| Модели | 19 | ~80 KB |
| Карты | 1 | ~160 KB |
| **Всего** | **37** | **~290 KB** |

## Лицензия

Все ассеты сгенерированы процедурно и доступны для использования в проекте AI-EVOLVE.
