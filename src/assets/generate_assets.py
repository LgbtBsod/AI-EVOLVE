"""
AI-EVOLVE Asset Generator
Генерация процедурных графических ассетов для игры.
Создает спрайты, текстуры и UI элементы программно.
"""

import os
import math
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import numpy as np

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "../../assets")

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def generate_player_sprite(size=64, color=(0, 100, 255), glow=True):
    """Генерация спрайта игрока (футуристический солдат)"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    cx, cy = size // 2, size // 2
    
    # Свечение
    if glow:
        glow_img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_img)
        glow_draw.ellipse([cx-20, cy-20, cx+20, cy+20], fill=(*color, 50))
        glow_img = glow_img.filter(ImageFilter.GaussianBlur(8))
        img = Image.alpha_composite(img, glow_img)
    
    # Тело
    draw.ellipse([cx-15, cy-15, cx+15, cy+15], fill=color)
    
    # Шлем/Визор
    draw.ellipse([cx-10, cy-12, cx+10, cy-2], fill=(200, 230, 255))
    
    # Детали брони
    draw.line([cx-15, cy, cx+15, cy], fill=(0, 50, 150), width=2)
    draw.line([cx, cy-15, cx, cy+15], fill=(0, 50, 150), width=2)
    
    return img

def generate_enemy_sprite(size=64, variant='basic'):
    """Генерация спрайтов врагов разных типов"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    
    colors = {
        'basic': (200, 50, 50),
        'elite': (150, 50, 200),
        'boss': (50, 200, 100),
        'scout': (255, 150, 50)
    }
    
    base_color = colors.get(variant, (200, 50, 50))
    
    # Форма зависит от типа
    if variant == 'scout':
        # Треугольник для разведчика
        points = [(cx, cy-20), (cx-15, cy+15), (cx+15, cy+15)]
        draw.polygon(points, fill=base_color)
    elif variant == 'boss':
        # Большой круг с шипами
        draw.ellipse([cx-25, cy-25, cx+25, cy+25], fill=base_color)
        for i in range(8):
            angle = i * (360 / 8)
            rad = math.radians(angle)
            x1, y1 = cx + int(25 * math.cos(rad)), cy + int(25 * math.sin(rad))
            x2, y2 = cx + int(32 * math.cos(rad)), cy + int(32 * math.sin(rad))
            draw.line([x1, y1, x2, y2], fill=base_color, width=3)
    else:
        # Стандартный враг
        draw.rectangle([cx-18, cy-18, cx+18, cy+18], fill=base_color)
        draw.ellipse([cx-10, cy-10, cx+10, cy+10], fill=(255, 200, 200))
    
    # Глаза
    draw.ellipse([cx-8, cy-5, cx-3, cy], fill=(255, 255, 0))
    draw.ellipse([cx+3, cy-5, cx+8, cy], fill=(255, 255, 0))
    
    return img

def generate_tile_texture(size=128, type='ground'):
    """Генерация текстур тайлов окружения"""
    img = Image.new('RGB', (size, size), (20, 20, 25))
    draw = ImageDraw.Draw(img)
    
    noise = np.random.randint(0, 20, (size, size, 3), dtype=np.uint8)
    noise_img = Image.fromarray(noise, 'RGB')
    img = Image.blend(img, noise_img, 0.3)
    
    if type == 'grass':
        # Зеленые вкрапления
        for _ in range(100):
            x, y = np.random.randint(0, size), np.random.randint(0, size)
            shade = np.random.randint(50, 150)
            draw.point((x, y), fill=(20, shade, 20))
    
    elif type == 'metal':
        # Линии металла
        for i in range(0, size, 16):
            draw.line([(0, i), (size, i)], fill=(60, 60, 70), width=1)
            draw.line([(i, 0), (i, size)], fill=(60, 60, 70), width=1)
    
    elif type == 'water':
        # Волны
        for y in range(0, size, 8):
            offset = math.sin(y / 10) * 5
            draw.line([(0, y+offset), (size, y+offset)], fill=(50, 100, 200), width=2)
    
    return img

def generate_ui_elements():
    """Генерация UI элементов"""
    assets = {}
    
    # Health bar background
    hb_bg = Image.new('RGBA', (200, 20), (50, 50, 50, 200))
    draw = ImageDraw.Draw(hb_bg)
    draw.rounded_rectangle([0, 0, 200, 20], radius=5, outline=(100, 100, 100), width=2)
    assets['health_bar_bg'] = hb_bg
    
    # Health bar fill (gradient simulation)
    hb_fill = Image.new('RGBA', (200, 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(hb_fill)
    draw.rounded_rectangle([2, 2, 198, 18], radius=3, fill=(0, 200, 50))
    assets['health_bar_fill'] = hb_fill
    
    # Mana/Energy bar
    mb_fill = Image.new('RGBA', (200, 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(mb_fill)
    draw.rounded_rectangle([2, 2, 198, 18], radius=3, fill=(50, 100, 255))
    assets['energy_bar_fill'] = mb_fill
    
    # Button
    btn = Image.new('RGBA', (150, 50), (0, 0, 0, 0))
    draw = ImageDraw.Draw(btn)
    draw.rounded_rectangle([0, 0, 150, 50], radius=10, fill=(70, 70, 80, 200))
    draw.rounded_rectangle([0, 0, 150, 50], radius=10, outline=(150, 150, 160), width=2)
    assets['button'] = btn
    
    return assets

def generate_projectile_effect(color=(255, 200, 50), size=32):
    """Генерация эффекта снаряда"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Ядро
    draw.ellipse([size//2-6, size//2-6, size//2+6, size//2+6], fill=color)
    
    # Хвост
    for i in range(1, 10):
        alpha = 255 - (i * 25)
        s = size//2 - (i * 2)
        draw.ellipse([s, s, size-s, size-s], fill=(*color, alpha))
    
    img = img.filter(ImageFilter.GaussianBlur(1))
    return img

def generate_all_assets():
    """Генерация всех ассетов игры"""
    print("🎨 Генерация графических ассетов AI-EVOLVE...")
    
    ensure_dir(ASSETS_DIR)
    ensure_dir(os.path.join(ASSETS_DIR, "sprites"))
    ensure_dir(os.path.join(ASSETS_DIR, "tiles"))
    ensure_dir(os.path.join(ASSETS_DIR, "ui"))
    ensure_dir(os.path.join(ASSETS_DIR, "effects"))
    
    # Спрайты персонажей
    player = generate_player_sprite()
    player.save(os.path.join(ASSETS_DIR, "sprites", "player.png"))
    print("✅ Спрайт игрока создан")
    
    for variant in ['basic', 'elite', 'boss', 'scout']:
        enemy = generate_enemy_sprite(variant=variant)
        enemy.save(os.path.join(ASSETS_DIR, "sprites", f"enemy_{variant}.png"))
        print(f"✅ Спрайт врага ({variant}) создан")
    
    # Текстуры
    for t_type in ['ground', 'grass', 'metal', 'water']:
        tile = generate_tile_texture(type=t_type)
        tile.save(os.path.join(ASSETS_DIR, "tiles", f"{t_type}.png"))
        print(f"✅ Текстура ({t_type}) создана")
    
    # UI
    ui_assets = generate_ui_elements()
    for name, img in ui_assets.items():
        img.save(os.path.join(ASSETS_DIR, "ui", f"{name}.png"))
        print(f"✅ UI элемент ({name}) создан")
    
    # Эффекты
    projectile = generate_projectile_effect()
    projectile.save(os.path.join(ASSETS_DIR, "effects", "projectile_basic.png"))
    
    explosion = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(explosion)
    draw.ellipse([10, 10, 54, 54], fill=(255, 100, 50, 200))
    draw.ellipse([20, 20, 44, 44], fill=(255, 200, 50, 255))
    explosion = explosion.filter(ImageFilter.GaussianBlur(3))
    explosion.save(os.path.join(ASSETS_DIR, "effects", "explosion.png"))
    print("✅ Эффекты созданы")
    
    print(f"\n📦 Все ассеты сохранены в: {os.path.abspath(ASSETS_DIR)}")
    return True

if __name__ == "__main__":
    generate_all_assets()
