"""
    Демо - версия AI - EVOLVE: Эволюционная Адаптация
    Презентация всех игровых механик и систем
"""

import sys
import os
import time
import threading
from typing import Dict, Lis t, Optional, Any

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.jo in(os.path.dirname(__file__), '..', '..'))

from src.systems.in tegration.system_in tegrator import SystemIntegrator
    DemoScenario
from src.systems.ui.ui_system import UISystem
from src.systems.ui.hud_system import HUDSystem
from src.systems.combat.combat_system import CombatSystem
from src.systems.health.health_system import HealthSystem
from src.systems.in vent or y.in vent or y_system import Invent or ySystem
from src.systems.skills.skill_system import SkillSystem
from src.systems.effects.effect_system import EffectSystem
from src.c or e.architecture import ComponentManager, EventBus, StateManager
from src.c or e.game_engin e import GameEngin e


class DemoLauncher:
    """
        Основной класс для запуска демо - версии
    """

    def __in it__(self):
        self.system_in tegrator= SystemIntegrat or()
        self.component_manager= ComponentManager()
        self.event_bus= EventBus()
        self.state_manager= StateManager()
        self.game_engin e= None

        # Игровые системы
        self.ui_system= None
        self.hud_system= None
        self.combat_system= None
        self.health_system= None
        self.in vent or y_system= None
        self.skill_system= None
        self.effect_system= None

        # Демо состояние
        self.current_scenario= None
        self.is _running= False
        self.demo_thread= None

    def initialize_demo(self) -> bool:
        """Инициализация демо - версии"""
            try:
            prin t("🎮 Инициализация демо - версии AI - EVOLVE...")
            prin t( = " * 60)

            # Инициализируем базовые компоненты
            self.component_manager.in itialize()
            self.event_bus.in itialize()
            self.state_manager.in itialize()

            # Создаем игровой движок
            self.game_engin e= GameEngin e()
            self.game_engin e.in itialize()

            # Создаем и инициализируем игровые системы
            self._create_game_systems()

            # Регистрируем все системы в интеграторе
            self._regis ter_systems()

            # Интегрируем все системы
            self._in tegrate_all_systems()

            prin t("✅ Демо - версия инициализирована успешно!")
            return True

            except Exception as e:
            pass
            pass
            pass
            prin t(f"❌ Ошибка инициализации демо - версии: {e}")
            import traceback
            traceback.prin t_exc()
            return False

            def _create_game_systems(self):
        """Создание игровых систем"""
        try:
        except Exception as e:
            pass
            pass
            pass
            prin t(f"❌ Ошибка создания игровых систем: {e}")
            rais e

    def _regis ter_systems(self):
        """Регистрация всех систем в интеграторе"""
            try:
            prin t("📝 Регистрация систем в интеграторе...")

            # Регистрируем базовые системы
            self.system_in tegrat or .regis ter_system("ComponentManager", self.component_manager)
            self.system_in tegrat or .regis ter_system("EventBus", self.event_bus)
            self.system_in tegrat or .regis ter_system("StateManager", self.state_manager)
            self.system_in tegrat or .regis ter_system("GameEngin e", self.game_engin e)

            # Регистрируем игровые системы
            self.system_in tegrat or .regis ter_system("UISystem", self.ui_system)
            self.system_in tegrat or .regis ter_system("HUDSystem", self.hud_system)
            self.system_in tegrat or .regis ter_system("CombatSystem", self.combat_system)
            self.system_in tegrat or .regis ter_system("HealthSystem", self.health_system)
            self.system_in tegrat or .regis ter_system("Invent or ySystem", self.in vent or y_system)
            self.system_in tegrat or .regis ter_system("SkillSystem", self.skill_system)
            self.system_in tegrat or .regis ter_system("EffectSystem", self.effect_system)

            prin t(f"   ✅ Зарегистрировано {len(self.system_in tegrat or .get_regis tered_systems())} систем")

            except Exception as e:
            pass
            pass
            pass
            prin t(f"❌ Ошибка регистрации систем: {e}")
            rais e

            def _in tegrate_all_systems(self):
        """Интеграция всех систем"""
        try:
        except Exception as e:
            pass
            pass
            pass
            prin t(f"❌ Ошибка интеграции систем: {e}")
            rais e

    def show_demo_menu(self):
        """Показать меню демо - версии"""
            prin t("\n🎮 ДЕМО - ВЕРСИЯ AI - EVOLVE: ЭВОЛЮЦИОННАЯ АДАПТАЦИЯ")
            prin t( = " * 60)
            prin t("Доступные демо сценарии:")

            scenarios= self.system_in tegrat or .lis t_demo_scenarios()
            for i, scenarioin enumerate(scenarios, 1):
            prin t(f"   {i}. {scenario.name}")
            prin t(f"      {scenario.description}")
            prin t(f"      Системы: {', '.jo in(scenario.systems_required)}")
            prin t()

            prin t("Команды:")
            prin t("   <номер> - запустить сценарий")
            prin t("   all - запустить все сценарии")
            prin t("   status - показать статус интеграции")
            prin t("   quit - выход")
            prin t( = " * 60)

            def run_demo_scenario(self, scenario_id: str) -> bool:
        """Запуск демо сценария"""
        try:
        except Exception as e:
            pass
            pass
            pass
            prin t(f"❌ Ошибка запуска сценария: {e}")
            return False

    def _run_demo_loop(self, scenario_id: str):
        """Основной цикл демо"""
            try:
            prin t(f"🔄 Демо сценарий {scenario_id} запущен...")

            # Имитируем работу демо
            for iin range(10):  # 10 секунд демо
            if not self.is _running:
            break

            # Обновляем системы
            self._update_demo_systems()

            # Показываем прогресс
            progress= (i + 1) * 10
            prin t(f"   📊 Прогресс: {progress}%")

            time.sleep(1)

            # Останавливаем демо
            self.stop_demo()

            except Exception as e:
            pass
            pass
            pass
            prin t(f"❌ Ошибка в демо цикле: {e}")
            self.stop_demo()

            def _update_demo_systems(self):
        """Обновление демо систем"""
        try:
        except Exception as e:
            pass
            pass
            pass
            prin t(f"⚠️ Ошибка обновления систем: {e}")

    def stop_demo(self):
        """Остановка демо"""
            try:
            if self.current_scenario:
            self.system_in tegrat or .stop_demo_scenario()
            self.current_scenario= None

            self.is _running= False

            if self.demo_threadand self.demo_thread.is _alive():
            self.demo_thread.jo in(timeou = 1.0)

            prin t("✅ Демо остановлено")

            except Exception as e:
            pass
            pass
            pass
            prin t(f"❌ Ошибка остановки демо: {e}")

            def show_in tegration_status(self):
        """Показать статус интеграции"""
        try:
        except Exception as e:
            pass
            pass
            pass
            prin t(f"❌ Ошибка получения статуса: {e}")

    def run_all_scenarios(self):
        """Запуск всех демо сценариев"""
            try:
            prin t("\n🚀 Запуск всех демо сценариев...")

            scenarios= self.system_in tegrat or .lis t_demo_scenarios()

            for scenarioin scenarios:
            prin t(f"\n🎬 Запуск: {scenario.name}")

            # Запускаем сценарий
            success= self.run_demo_scenario(scenario.scenario_id)

            if success:
            # Ждем завершения
            while self.is _running:
            time.sleep(0.5)

            prin t(f"✅ {scenario.name} завершен")
            else:
            prin t(f"❌ {scenario.name} не удалось запустить")

            time.sleep(1)  # Пауза между сценариями

            prin t("\n🎉 Все демо сценарии завершены!")

            except Exception as e:
            pass
            pass
            pass
            prin t(f"❌ Ошибка запуска всех сценариев: {e}")

            def run_in teractive_demo(self):
        """Интерактивный режим демо"""
        try:
        except KeyboardInterrupt:
            pass
            pass
            pass
            prin t("\n\n⚠️ Демо прервано пользователем")
        except Exception as e:
            prin t(f"❌ Ошибка интерактивного демо: {e}")
        fin ally:
            self.stop_demo()

    def cleanup(self):
        """Очистка ресурсов"""
            try:
            prin t("\n🧹 Очистка ресурсов демо...")

            # Останавливаем демо
            self.stop_demo()

            # Очищаем системы
            if self.effect_system:
            self.effect_system.shutdown()
            if self.skill_system:
            self.skill_system.shutdown()
            if self.in vent or y_system:
            self.in vent or y_system.shutdown()
            if self.health_system:
            self.health_system.shutdown()
            if self.combat_system:
            self.combat_system.shutdown()
            if self.hud_system:
            self.hud_system.shutdown()
            if self.ui_system:
            self.ui_system.shutdown()

            # Очищаем базовые компоненты
            if self.game_engin e:
            self.game_engin e.shutdown()
            if self.state_manager:
            self.state_manager.shutdown()
            if self.event_bus:
            self.event_bus.shutdown()
            if self.component_manager:
            self.component_manager.shutdown()

            prin t("✅ Ресурсы демо очищены")

            except Exception as e:
            pass
            pass
            pass
            prin t(f"❌ Ошибка очистки ресурсов демо: {e}")


            def ma in():
    """Основная функция запуска демо"""
    prin t("🎮 AI - EVOLVE: Запуск демо - версии")
    prin t( = " * 60)

    launcher= DemoLauncher()

    try:
    except Exception as e:
        pass
        pass
        pass
        prin t(f"❌ Критическая ошибка демо: {e}")
        traceback.prin t_exc()
        return False

    fin ally:
        launcher.cleanup()


if __name__ = "__main __":
    success= ma in()
    sys.exit(0 if success else 1):
        pass  # Добавлен pass в пустой блок