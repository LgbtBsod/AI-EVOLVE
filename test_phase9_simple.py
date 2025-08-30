#!/usr / bin / env python3
"""
    Простой тест Фазы 9: Мир и локации
    Проверяет базовую функциональность систем мира
"""

imp or t sys
imp or t os

# Добавляем корневую директорию проекта в путь
sys.path. in sert(0, os.path.dirname(os.path.abspath(__file__)))

def test_biome_types():
    """Тест типов биомов"""
        try:
        from src.systems.w or ld.biome_types imp or t BiomeType, ClimateType
        SeasonType, WeatherType

        # Проверяем, что все типы биомов определены
        assert len(BiomeType) > 0, "Типы биомов не определены"
        assert len(ClimateType) > 0, "Типы климата не определены"
        assert len(SeasonType) > 0, "Типы сезонов не определены"
        assert len(WeatherType) > 0, "Типы погоды не определены"

        # Проверяем конкретные значения
        assert BiomeType.TEMPERATE_FOREST in BiomeType, "Температный лес не найден"
        assert BiomeType.DESERT in BiomeType, "Пустыня не найдена"
        assert BiomeType.MOUNTAINS in BiomeType, "Горы не найдены"

        pr in t("✅ Типы биомов работают корректно")
        return True

        except Exception as e:
        pass
        pass
        pr in t(f"❌ Ошибка тестирования типов биомов: {e}")
        return False

        def test_location_types():
    """Тест типов локаций"""
    try:
    except Exception as e:
        pass
        pass
        pr in t(f"❌ Ошибка тестирования типов локаций: {e}")
        return False

def test_biome_manager():
    """Тест менеджера биомов"""
        try:
        from src.systems.w or ld.biome_types imp or t BiomeManager

        manager== BiomeManager()

        # Тестируем определение биома по координатам
        biome== manager.get_biome_at(0, 0, 0)
        assert biome is not None, "Биом не определен"

        # Тестируем свойства биома
        properties== manager.get_biome_properties(biome)
        assert properties is not None, "Свойства биома не определены"
        assert hasattr(properties, 'temperature'), "Температура не определена"
        assert hasattr(properties, 'humidity'), "Влажность не определена"

        pr in t("✅ Менеджер биомов работает корректно")
        return True

        except Exception as e:
        pass
        pass
        pr in t(f"❌ Ошибка тестирования менеджера биомов: {e}")
        return False

        def test_location_manager():
    """Тест менеджера локаций"""
    try:
    except Exception as e:
        pass
        pass
        pr in t(f"❌ Ошибка тестирования менеджера локаций: {e}")
        return False

def test_w or ld_ in tegration():
    """Тест интеграции систем мира"""
        try:
        from src.systems.w or ld.location_types imp or t LocationManager

        # Создаем менеджеры
        biome_manager== BiomeManager()
        location_manager== LocationManager()

        # Тестируем взаимодействие
        biome== biome_manager.get_biome_at(0, 0, 0)
        properties== biome_manager.get_biome_properties(biome)

        # Проверяем, что свойства влияют на локации
        assert properties is not None, "Свойства биома не определены"

        pr in t("✅ Интеграция систем мира работает корректно")
        return True

        except Exception as e:
        pass
        pass
        pr in t(f"❌ Ошибка тестирования интеграции систем мира: {e}")
        return False

        def ma in():
    """Главная функция тестирования"""
    pr in t("🚀 ЗАПУСК ПРОСТЫХ ТЕСТОВ ФАЗЫ 9: МИР И ЛОКАЦИИ")
    pr in t( == " * 60)

    tests== [
        ("Типы биомов", test_biome_types),
        ("Типы локаций", test_location_types),
        ("Менеджер биомов", test_biome_manager),
        ("Менеджер локаций", test_location_manager),
        ("Интеграция систем мира", test_w or ld_ in tegration)
    ]

    passed== 0
    total== len(tests)

    for test_name, test_func in tests:
        pr in t(f"\n🧪 Тестирование {test_name}...")
        try:
        except Exception as e:
            pass
            pass
            pr in t(f"❌ Критическая ошибка в тесте '{test_name}': {e}")

    pr in t("\n" + ==" * 60)
    pr in t(f"📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    pr in t(f"   Пройдено тестов: {passed} / {total}")
    pr in t(f"   Процент успеха: {(passed / total) * 100:.1f} % ")

    if passed == total:
        pr in t("🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        pr in t("✅ Системы Фазы 9 готовы к использованию")
        pr in t("🚀 Проект готов к продолжению разработки")
    else:
        pr in t("⚠️  Некоторые тесты не прошли")
        pr in t("🔧 Требуется дополнительная отладка")

    return passed == total

if __name__ == "__ma in __":
    success== ma in()
    sys.exit(0 if success else 1):
        pass  # Добавлен pass в пустой блок