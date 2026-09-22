#!/usr/bin/env python3
"""
Генератор процедурных текстур для AI-EVOLVE.
Создает текстуры без внешних зависимостей (используя PIL или numpy).
Если PIL нет, создает простые заглушки или использует numpy.
"""

import os
import sys
import random
from pathlib import Path

def create_placeholder_texture(path: str, size: tuple = (256, 256), color: tuple = (128, 128, 128)):
    """Создает простую текстуру-заглушку используя только стандартную библиотеку (PPM формат -> конвертация)"""
    try:
        from PIL import Image, ImageDraw
        img = Image.new('RGB', size, color)
        draw = ImageDraw.Draw(img)
        
        # Добавляем шум/детали
        for _ in range(100):
            x = random.randint(0, size[0]-1)
            y = random.randint(0, size[1]-1)
            c = tuple(max(0, min(255, color[i] + random.randint(-30, 30))) for i in range(3))
            draw.point((x, y), fill=c)
        
        img.save(path)
        print(f"✓ Создана текстура: {path}")
        return True
    except ImportError:
        # Если нет PIL, создаем простой PPM и конвертируем или оставляем как заглушку
        print(f"⚠ PIL не найден, создаю заглушку для {path}")
        # Создадим бинарный файл-заглушку
        with open(path.replace('.png', '.placeholder'), 'w') as f:
            f.write(f"PLACEHOLDER_TEXTURE:{size[0]}x{size[1]}:{color}")
        return False

def generate_all_textures():
    import random
    
    base_dir = Path(__file__).parent
    textures_dir = base_dir / "textures"
    textures_dir.mkdir(exist_ok=True)
    
    textures = [
        ("grass.png", (512, 512), (34, 139, 34)),       # Зеленая трава
        ("stone.png", (512, 512), (128, 128, 128)),     # Серый камень
        ("dirt.png", (512, 512), (101, 67, 33)),        # Коричневая земля
        ("water.png", (512, 512), (65, 105, 225)),      # Синяя вода
        ("sand.png", (512, 512), (237, 201, 175)),      # Песок
        ("snow.png", (512, 512), (255, 250, 250)),      # Снег
        ("lava.png", (512, 512), (207, 16, 32)),        # Лава
        ("metal.png", (256, 256), (192, 192, 192)),     # Металл
        ("wood.png", (256, 256), (139, 90, 43)),        # Дерево
        ("brick.png", (256, 256), (178, 34, 34)),       # Кирпич
        # Текстуры персонажей
        ("player_skin.png", (256, 256), (255, 218, 185)), # Кожа игрока
        ("enemy_skin.png", (256, 256), (139, 0, 0)),      # Кожа врага
        ("boss_skin.png", (512, 512), (75, 0, 130)),      # Кожа босса
        # UI текстуры
        ("ui_bg.png", (128, 128), (40, 40, 40)),
        ("ui_button.png", (64, 32), (70, 130, 180)),
        ("ui_health_bar.png", (100, 10), (220, 20, 60)),
        ("ui_mana_bar.png", (100, 10), (0, 100, 255)),
    ]
    
    created = 0
    for name, size, color in textures:
        path = str(textures_dir / name)
        if create_placeholder_texture(path, size, color):
            created += 1
    
    print(f"\n✅ Создано {created} текстур из {len(textures)}")
    if created < len(textures):
        print("💡 Установите Pillow для полноценных текстур: pip install Pillow")
    
    # Создадим README
    readme = textures_dir / "README.md"
    with open(readme, 'w') as f:
        f.write("# Текстуры AI-EVOLVE\n\n")
        f.write("Текстуры сгенерированы процедурно. Для улучшения качества:\n")
        f.write("1. Установите Pillow: `pip install Pillow`\n")
        f.write("2. Запустите генератор заново\n")
        f.write("3. Или замените на свои ассеты в этой папке\n")
    print(f"📄 Создан README: {readme}")

if __name__ == "__main__":
    generate_all_textures()
