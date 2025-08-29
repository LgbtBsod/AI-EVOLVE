#!/usr/bin/env python3
"""
Запуск всех тестов для проекта "Эволюционная Адаптация: Генетический Резонанс"
"""

import unittest
import sys
import io
import os
import time

# Добавляем пути к проекту и исходникам
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..')
SRC_ROOT = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SRC_ROOT)

def run_all_tests():
    """Запуск всех тестов"""
    print("🧪 Запуск тестов для проекта 'Эволюционная Адаптация: Генетический Резонанс'")
    print("=" * 80)
    
    # Создаем тестовый набор
    test_suite = unittest.TestSuite()
    
    # Добавляем базовые тесты архитектуры
    try:
        from tests.test_basic_architecture import TestBasicArchitecture
        test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestBasicArchitecture))
        print("✅ Базовые тесты архитектуры добавлены")
    except ImportError as e:
        print(f"❌ Ошибка импорта базовых тестов архитектуры: {e}")
    
    # Добавляем тесты для EvolutionSystem
    try:
        from tests.test_evolution_system import TestEvolutionSystem
        test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestEvolutionSystem))
        print("✅ EvolutionSystem тесты добавлены")
    except ImportError as e:
        print(f"❌ Ошибка импорта EvolutionSystem тестов: {e}")
    
    # Добавляем тесты для EmotionSystem
    try:
        from tests.test_emotion_system import TestEmotionSystem
        test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestEmotionSystem))
        print("✅ EmotionSystem тесты добавлены")
    except ImportError as e:
        print(f"❌ Ошибка импорта EmotionSystem тестов: {e}")
    
    # Добавляем тесты для CombatSystem
    try:
        from tests.test_combat_system import TestCombatSystem
        test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCombatSystem))
        print("✅ CombatSystem тесты добавлены")
    except ImportError as e:
        print(f"❌ Ошибка импорта CombatSystem тестов: {e}")
    
    # Добавляем тесты для других систем (когда они будут созданы)
    # Тесты унификации сцен: событие/состояние при смене сцены
    try:
        from tests.test_scene_manager_events import TestSceneManagerEvents
        test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestSceneManagerEvents))
        print("✅ SceneManager events/state тесты добавлены")
    except ImportError as e:
        print(f"⚠️  Ошибка импорта SceneManager events/state тестов: {e}")

    # Легкий тест интеграции AI: создание базовой AI и регистрация сущности
    # SystemFactory/Manager ordering
    try:
        from tests.test_system_factory_ordering import TestSystemFactoryOrdering
        test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestSystemFactoryOrdering))
        print("✅ SystemFactory ordering тесты добавлены")
    except ImportError as e:
        print(f"⚠️  Ошибка импорта SystemFactory ordering тестов: {e}")

    # Performance metrics toggle
    try:
        from tests.test_performance_metrics_toggle import TestPerformanceMetricsToggle
        test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestPerformanceMetricsToggle))
        print("✅ Performance metrics toggle тесты добавлены")
    except ImportError as e:
        print(f"⚠️  Ошибка импорта performance metrics toggle тестов: {e}")

    # Plugin lifecycle
    try:
        from tests.test_plugin_lifecycle import TestPluginLifecycle
        test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestPluginLifecycle))
        print("✅ Plugin lifecycle тесты добавлены")
    except ImportError as e:
        print(f"⚠️  Ошибка импорта plugin lifecycle тестов: {e}")

    # Repository perf
    try:
        from tests.test_repository_perf import TestRepositoryPerf
        test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestRepositoryPerf))
        print("✅ Repository perf тесты добавлены")
    except ImportError as e:
        print(f"⚠️  Ошибка импорта repository perf тестов: {e}")
    try:
        from tests.test_ai_integration_minimal import TestAIIntegrationMinimal
        test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestAIIntegrationMinimal))
        print("✅ Минимальные AI интеграционные тесты добавлены")
    except ImportError as e:
        print(f"⚠️  Ошибка импорта AI интеграционных тестов: {e}")
    # Легкий интеграционный тест: совместимость on/emit alias в EventSystem
    try:
        from src.core.event_system import EventSystem, EventPriority
        class IntegrationEventAlias(unittest.TestCase):
            def runTest(self):
                es = EventSystem()
                es.initialize()
                hit = {"n": 0}
                def h(ev):
                    hit["n"] += 1
                self.assertTrue(es.on("_alias_test", h, EventPriority.NORMAL))
                self.assertTrue(es.emit_event("_alias_test", {"ok": True}, "test", EventPriority.NORMAL))
                es.process_events()
                self.assertEqual(hit["n"], 1)
        test_suite.addTest(IntegrationEventAlias())
        print("✅ Интеграционный тест: event on/emit alias добавлен")
    except Exception as e:
        print(f"⚠️  Интеграционный тест event alias пропущен: {e}")
    
    print(f"\n📊 Всего тестовых случаев: {test_suite.countTestCases()}")
    print("=" * 80)
    
    # Запускаем тесты
    start_time = time.time()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    end_time = time.time()
    
    # Выводим результаты
    print("=" * 80)
    print("📋 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    print(f"⏱️  Время выполнения: {end_time - start_time:.2f} секунд")
    print(f"✅ Успешных тестов: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"❌ Проваленных тестов: {len(result.failures)}")
    print(f"⚠️  Тестов с ошибками: {len(result.errors)}")
    print(f"📊 Всего тестов: {result.testsRun}")
    
    if result.failures:
        print("\n❌ ПРОВАЛЕННЫЕ ТЕСТЫ:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback.split('AssertionError:')[-1].strip()}")
    
    if result.errors:
        print("\n⚠️  ТЕСТЫ С ОШИБКАМИ:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback.split('Exception:')[-1].strip()}")
    
    # Определяем общий результат
    if result.wasSuccessful():
        print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        return True
    else:
        print("\n💥 НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ!")
        return False

def run_specific_test(test_name):
    """Запуск конкретного теста"""
    print(f"🧪 Запуск теста: {test_name}")
    print("=" * 80)
    
    # Создаем тестовый набор для конкретного теста
    test_suite = unittest.TestSuite()
    
    if test_name.lower() == "evolution":
        try:
            from tests.test_evolution_system import TestEvolutionSystem
            test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestEvolutionSystem))
            print("✅ EvolutionSystem тесты добавлены")
        except ImportError as e:
            print(f"❌ Ошибка импорта EvolutionSystem тестов: {e}")
            return False
    
    elif test_name.lower() == "emotion":
        try:
            from tests.test_emotion_system import TestEmotionSystem
            test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestEmotionSystem))
            print("✅ EmotionSystem тесты добавлены")
        except ImportError as e:
            print(f"❌ Ошибка импорта EmotionSystem тестов: {e}")
            return False
    
    elif test_name.lower() == "combat":
        try:
            from tests.test_combat_system import TestCombatSystem
            test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCombatSystem))
            print("✅ CombatSystem тесты добавлены")
        except ImportError as e:
            print(f"❌ Ошибка импорта CombatSystem тестов: {e}")
            return False
    
    elif test_name.lower() == "basic":
        try:
            from tests.test_basic_architecture import TestBasicArchitecture
            test_suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestBasicArchitecture))
            print("✅ Базовые тесты архитектуры добавлены")
        except ImportError as e:
            print(f"❌ Ошибка импорта базовых тестов архитектуры: {e}")
            return False
    
    else:
        print(f"❌ Неизвестный тест: {test_name}")
        print("Доступные тесты: basic, evolution, emotion, combat")
        return False
    
    print(f"\n📊 Тестовых случаев: {test_suite.countTestCases()}")
    print("=" * 80)
    
    # Запускаем тесты
    start_time = time.time()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    end_time = time.time()
    
    # Выводим результаты
    print("=" * 80)
    print("📋 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    print(f"⏱️  Время выполнения: {end_time - start_time:.2f} секунд")
    print(f"✅ Успешных тестов: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"❌ Проваленных тестов: {len(result.failures)}")
    print(f"⚠️  Тестов с ошибками: {len(result.errors)}")
    print(f"📊 Всего тестов: {result.testsRun}")
    
    return result.wasSuccessful()

def main():
    # Ensure UTF-8 output on Windows consoles
    try:
        if sys.stdout.encoding.lower() != 'utf-8':
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='ignore')
    except Exception:
        pass
    """Основная функция"""
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        success = run_specific_test(test_name)
    else:
        success = run_all_tests()
    
    # Возвращаем код выхода
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
