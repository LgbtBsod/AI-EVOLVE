#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Простой тест улучшенного рендеринга"""

import sys
import os
from pathlib import Path

# Добавляем путь к модулям
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR / "src"))

def test_enhanced_rendering():
    """Тест улучшенного рендеринга"""
    try:
        print("🎮 ТЕСТ УЛУЧШЕННОГО РЕНДЕРИНГА")
        print("=" * 50)
        
        # Импортируем улучшенную игру
        from src.enhanced_main import EnhancedGame
        print("✅ EnhancedGame импортирован")
        
        # Создаем игру
        game = EnhancedGame()
        print("✅ EnhancedGame создана")
        
        # Проверяем компоненты
        if hasattr(game, 'showbase'):
            print("✅ ShowBase готов")
        else:
            print("❌ ShowBase отсутствует")
            
        if hasattr(game, 'render_system'):
            print("✅ Система рендеринга готова")
        else:
            print("❌ Система рендеринга отсутствует")
            
        if hasattr(game, 'state_manager'):
            print("✅ Менеджер состояний готов")
        else:
            print("❌ Менеджер состояний отсутствует")
        
        print("\n🚀 Запуск тестового окна...")
        
        # Запускаем игру
        game.start()
        
        print("✅ Тест завершен успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка теста: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    return True

if __name__ == "__main__":
    success = test_enhanced_rendering()
    if success:
        print("\n🎉 ТЕСТ ПРОЙДЕН УСПЕШНО!")
    else:
        print("\n❌ ТЕСТ НЕ ПРОЙДЕН!")
        sys.exit(1)
