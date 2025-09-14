#!/usr/bin/env python3
"""AI-EVOLVE Enhanced Edition - Launcher
Основной файл запуска игры с новой модульной архитектурой на Panda3D"""

import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

# Добавляем корневую директорию в путь
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR / "src"))

def _configure_console_encoding():
    """Конфигурируем кодировку консоли для Windows/PowerShell"""
    try:
        if os.name == 'nt':
            os.system('chcp 65001 > nul')
    except Exception:
        pass

_configure_console_encoding()

def _configure_python_io_encoding():
    """Forces UTF-8 encoding for Python stdio on Windows to avoid Unicode errors."""
    try:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        # Python 3.7+ supports reconfigure on text IO wrappers
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_configure_python_io_encoding()

def load_logging_config():
    """Загрузка конфигурации логирования"""
    try:
        # Пытаемся загрузить из файла конфигурации
        config_path = ROOT_DIR / "config" / "logging_config.json"
        if config_path.exists():
            import json
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                print(f"📋 Загружена конфигурация логирования из {config_path}")
                return config.get("logging", {})
    except Exception as e:
        print(f"⚠️  Ошибка загрузки конфигурации логирования: {e}")
    
    # Возвращаем настройки по умолчанию
    return {
        "level": "INFO",
        "file_level": "DEBUG",
        "console_level": "INFO",
        "max_archive_files": 10,
        "cleanup_on_startup": True,
        "save_last_session": True,
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "date_format": "%Y-%m-%d %H:%M:%S",
        "external_libraries": {
            "panda3d": "WARNING",
            "numpy": "WARNING",
            "PIL": "WARNING",
            "direct": "WARNING",
            "panda3d.core": "WARNING"
        },
        "suppress_warnings": [
            "setVerticalSync не поддерживается",
            "setAntialias не поддерживается",
            "LODManager недоступен",
            "OcclusionCuller недоступен"
        ]
    }

def cleanup_old_logs(log_dir: Path, archive_dir: Path, config: dict):
    """Очистка старых логов при каждом запуске игры"""
    try:
        # Получаем все файлы логов (исключаем папку archive)
        log_files = [f for f in log_dir.glob("*.log") if f.parent == log_dir]
        
        if not log_files:
            print("📁 Папка логов пуста")
            return
        
        # Если есть логи, сохраняем самый последний в архив
        if config.get("save_last_session", True) and log_files:
            # Сортируем по времени модификации (новые сначала)
            log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            latest_log = log_files[0]
            
            # Копируем последний лог в архив
            try:
                import shutil
                archive_name = f"last_session_{time.strftime('%Y%m%d_%H%M%S')}.log"
                archive_path = archive_dir / archive_name
                shutil.copy2(latest_log, archive_path)
                print(f"💾 Последний лог сохранен в архив: {archive_name}")
            except Exception as e:
                print(f"⚠️  Не удалось сохранить лог в архив: {e}")
        
        # Удаляем все старые логи
        for log_file in log_files:
            try:
                log_file.unlink()
                print(f"🗑️  Удален старый лог: {log_file.name}")
            except Exception as e:
                print(f"⚠️  Не удалось удалить лог {log_file.name}: {e}")
        
        print(f"🧹 Очищено {len(log_files)} старых логов")
        
        # Очищаем архив логов (оставляем только последние 10)
        cleanup_log_archive(archive_dir, config)
        
    except Exception as e:
        print(f"⚠️  Ошибка при очистке логов: {e}")

def cleanup_log_archive(archive_dir: Path, config: dict):
    """Очистка архива логов, оставляя только последние 10"""
    try:
        archive_files = list(archive_dir.glob("*.log"))
        if len(archive_files) > config.get("max_archive_files", 10):
            # Сортируем по времени модификации (старые сначала)
            archive_files.sort(key=lambda x: x.stat().st_mtime)
            
            # Удаляем старые файлы
            files_to_remove = archive_files[:-config.get("max_archive_files", 10)]
            for file in files_to_remove:
                try:
                    file.unlink()
                    print(f"🗑️  Удален архивный лог: {file.name}")
                except Exception as e:
                    print(f"⚠️  Не удалось удалить архивный лог {file.name}: {e}")
    except Exception as e:
        print(f"⚠️  Ошибка при очистке архива логов: {e}")

def setup_logging():
    """Настройка системы логирования с очисткой старых логов"""
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Создаем папку для архива логов
    archive_dir = ROOT_DIR / "logs" / "archive"
    archive_dir.mkdir(exist_ok=True)
    
    # Загружаем конфигурацию логирования
    logging_config = load_logging_config()
    
    # Очистка старых логов (если включено)
    if logging_config.get("cleanup_on_startup", True):
        cleanup_old_logs(log_dir, archive_dir, logging_config)
    
    # Форматтер для логов
    formatter = logging.Formatter(
        logging_config.get("format", '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
        datefmt=logging_config.get("date_format", '%Y-%m-%d %H:%M:%S')
    )
    
    # Файловый обработчик
    current_log_file = log_dir / f"ai_evolve_{time.strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(
        current_log_file,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, logging_config.get("file_level", "DEBUG")))
    file_handler.setFormatter(formatter)
    
    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, logging_config.get("console_level", "INFO")))
    console_handler.setFormatter(formatter)
    
    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, logging_config.get("level", "DEBUG")))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Настройка уровней для внешних библиотек
    external_libs = logging_config.get("external_libraries", {})
    for lib_name, level in external_libs.items():
        try:
            logging.getLogger(lib_name).setLevel(getattr(logging, level))
        except Exception as e:
            print(f"⚠️  Не удалось установить уровень логирования для {lib_name}: {e}")
    
    # Создаем фильтр для подавления определенных предупреждений
    suppress_warnings = logging_config.get("suppress_warnings", [])
    if suppress_warnings:
        class WarningFilter(logging.Filter):
            def filter(self, record):
                message = record.getMessage()
                return not any(warning in message for warning in suppress_warnings)
        
        warning_filter = WarningFilter()
        file_handler.addFilter(warning_filter)
        console_handler.addFilter(warning_filter)
        print(f"🔇 Настроена фильтрация {len(suppress_warnings)} типов предупреждений")
    
    # Сохраняем путь к текущему лог-файлу для возможного архивирования
    root_logger.current_log_file = current_log_file
    
    print(f"📝 Логирование настроено: {current_log_file.name}")
    print(f"📊 Уровень файла: {logging_config.get('file_level', 'DEBUG')}")
    print(f"📊 Уровень консоли: {logging_config.get('console_level', 'INFO')}")

def check_python_version() -> bool:
    """Проверка версии Python"""
    if sys.version_info < (3, 8):
        print("❌ Ошибка: Требуется Python 3.8 или выше")
        print(f"   Текущая версия: {sys.version}")
        return False
    return True

def check_dependencies():
    """Проверка зависимостей"""
    print("\n📦 ПРОВЕРКА ЗАВИСИМОСТЕЙ")
    print("=" * 50)
    
    # Обязательные пакеты
    required_packages = [
        "panda3d",
        "numpy"
    ]
    
    # Опциональные пакеты
    optional_packages = [
        "PIL",
        "cv2",
        "matplotlib"
    ]
    
    missing_required = []
    missing_optional = []
    
    for package in required_packages:
        try:
            if package == "panda3d":
                # Специальная проверка Panda3D
                import panda3d
                print(f"✅ {package} - установлен (версия: {panda3d.__version__})")
                
                # Проверяем возможность создания окна с разными импортами
                try:
                    print("🔍 Тестирование создания окна Panda3D...")
                    
                    # Пробуем разные способы импорта ShowBase
                    try:
                        from panda3d.core import ShowBase, WindowProperties
                        print("✅ Импорт из panda3d.core успешен")
                    except ImportError:
                        try:
                            from direct.showbase.ShowBase import ShowBase
                            print("✅ Импорт из direct.showbase.ShowBase успешен")
                        except ImportError:
                            try:
                                from direct.showbase import ShowBase
                                print("✅ Импорт из direct.showbase успешен")
                            except ImportError:
                                raise ImportError("Не удалось импортировать ShowBase ни одним способом")
                    
                    # Тестируем создание окна
                    test_base = ShowBase()
                    test_base.destroy()
                    print("✅ Panda3D окно создается успешно")
                    
                except Exception as window_e:
                    print(f"⚠️  Panda3D окно не создается: {window_e}")
                    # Не прерываем запуск, так как Panda3D может работать в headless режиме
                    
            else:
                __import__(package)
                print(f"✅ {package} - установлен")
        except ImportError as e:
            missing_required.append(package)
            print(f"❌ {package} - отсутствует: {e}")
        except Exception as e:
            missing_required.append(package)
            print(f"❌ {package} - ошибка: {e}")
    
    for package in optional_packages:
        try:
            __import__(package)
            print(f"✅ {package} - установлен")
        except ImportError:
            missing_optional.append(package)
            print(f"⚠️  {package} - отсутствует (опционально)")
    
    if missing_required:
        print(f"\n❌ Отсутствуют необходимые пакеты: {', '.join(missing_required)}")
        print("Установите их командой:")
        print(f"pip install {' '.join(missing_required)}")
        return False
    
    if missing_optional:
        print(f"\n⚠️  Отсутствуют опциональные пакеты: {', '.join(missing_optional)}")
        print("Некоторые функции могут работать медленнее")
        print(f"pip install {' '.join(missing_optional)}")
    
    print("\n✅ Все необходимые зависимости установлены")
    return True

def create_directories():
    """Создание необходимых директорий"""
    directories = [
        "logs",
        "saves",
        "config",
        "assets/audio",
        "assets/graphics",
        "assets/data",
        "assets/maps",
        "assets/models",
        "assets/textures",
        "assets/shaders"
    ]
    
    for directory in directories:
        dir_path = ROOT_DIR / directory
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 Создана директория: {directory}")

def initialize_game():
    """Инициализация улучшенной игры с правильным рендерингом"""
    try:
        print("\n🔧 ДЕТАЛЬНАЯ ИНИЦИАЛИЗАЦИЯ УЛУЧШЕННОЙ ИГРЫ")
        print("=" * 50)
        
        # Импортируем улучшенные компоненты
        print("📦 Импорт улучшенных компонентов...")
        try:
            from src.main import EnhancedGame
            print("✅ EnhancedGame импортирован")
        except Exception as e:
            print(f"❌ Ошибка импорта EnhancedGame: {e}")
            raise
        
        print("\n🏗️  Создание улучшенной игры...")
        
        # Создаем улучшенную игру
        try:
            enhanced_game = EnhancedGame()
            print("✅ EnhancedGame создана")
        except Exception as e:
            print(f"❌ Ошибка создания EnhancedGame: {e}")
            raise
        
        print("\n🚀 Инициализация улучшенной игры...")
        try:
            # Игра уже инициализирована в конструкторе
            print("✅ Улучшенная игра инициализирована")
        except Exception as e:
            print(f"❌ Ошибка инициализации улучшенной игры: {e}")
            raise
        
        print("\n📊 Проверка состояния улучшенной игры...")
        try:
            # Проверяем основные компоненты
            if hasattr(enhanced_game, 'showbase'):
                print("✅ ShowBase инициализирован")
            else:
                print("❌ ShowBase не найден")
                
            if hasattr(enhanced_game, 'render_system'):
                print("✅ Система рендеринга инициализирована")
            else:
                print("❌ Система рендеринга не найдена")
                
            if hasattr(enhanced_game, 'state_manager'):
                print("✅ Менеджер состояний инициализирован")
            else:
                print("❌ Менеджер состояний не найден")
                
        except Exception as e:
            print(f"⚠️  Не удалось проверить состояние улучшенной игры: {e}")
        
        return enhanced_game
        
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ: {e}")
        print("🔍 Детали ошибки:")
        traceback.print_exc()
        return None

def cleanup_on_exit():
    """Очистка ресурсов при выходе из игры"""
    try:
        print("\n🧹 Очистка ресурсов...")
        
        # Получаем текущий лог-файл
        root_logger = logging.getLogger()
        if hasattr(root_logger, 'current_log_file') and root_logger.current_log_file:
            current_log = root_logger.current_log_file
            
            # Если лог-файл существует и не пустой, копируем его в архив
            if current_log.exists() and current_log.stat().st_size > 0:
                try:
                    import shutil
                    archive_dir = ROOT_DIR / "logs" / "archive"
                    archive_dir.mkdir(exist_ok=True)
                    archive_name = f"session_end_{time.strftime('%Y%m%d_%H%M%S')}.log"
                    archive_path = archive_dir / archive_name
                    shutil.copy2(current_log, archive_path)
                    print(f"💾 Финальный лог сохранен в архив: {archive_name}")
                except Exception as e:
                    print(f"⚠️  Не удалось сохранить финальный лог: {e}")
        
        print("✅ Очистка завершена")
        
    except Exception as e:
        print(f"⚠️  Ошибка при очистке: {e}")

def main():
    """Главная функция"""
    print("🎮 AI-EVOLVE Enhanced Edition - Panda3D Version")
    print("=" * 50)
    
    # Настройка логирования
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Проверка версии Python
        if not check_python_version():
            return 1
        
        # Проверка зависимостей
        if not check_dependencies():
            return 1
        
        # Создание директорий
        create_directories()
        
        # Инициализация игры
        game = initialize_game()
        if not game:
            return 1
        
        print("\n🎉 Игра успешно запущена!")
        print("📊 Статистика систем:")
        
        # Проверяем состояние улучшенной игры
        try:
            if hasattr(game, 'showbase'):
                print(f"✅ ShowBase готов")
            if hasattr(game, 'render_system'):
                print(f"✅ Система рендеринга готова")
            if hasattr(game, 'state_manager'):
                print(f"✅ Менеджер состояний готов")
        except Exception as e:
            print(f"⚠️  Ошибка проверки состояния: {e}")
        
        print("\n🎮 Улучшенная игра готова к использованию!")
        print("🚀 ЗАПУСК УЛУЧШЕННОГО ОКНА ИГРЫ")
        print("=" * 50)
        
        # Дополнительная диагностика состояния улучшенной игры
        print("🔍 ДИАГНОСТИКА СОСТОЯНИЯ УЛУЧШЕННОЙ ИГРЫ:")
        try:
            # Проверяем основные компоненты улучшенной игры
            if hasattr(game, 'showbase'):
                print(f"✅ ShowBase: {type(game.showbase).__name__}")
            else:
                print("❌ ShowBase: отсутствует")
                
            if hasattr(game, 'render_system'):
                print(f"✅ Система рендеринга: {type(game.render_system).__name__}")
            else:
                print("❌ Система рендеринга: отсутствует")
                
            if hasattr(game, 'state_manager'):
                print(f"✅ Менеджер состояний: {type(game.state_manager).__name__}")
            else:
                print("❌ Менеджер состояний: отсутствует")
                
            if hasattr(game, 'running'):
                print(f"📊 Состояние игры: {'запущена' if game.running else 'остановлена'}")
            else:
                print("⚠️  Игра не имеет атрибута 'running'")
                
        except Exception as diag_e:
            print(f"⚠️  Ошибка диагностики состояния: {diag_e}")
        
        print("\n🎬 Запуск улучшенного главного цикла игры...")
        
        # Запускаем улучшенную игру
        try:
            print(f"\n🚀 ЗАПУСК УЛУЧШЕННОЙ ИГРЫ:")
            print(f"   =================================================")
            
            # Проверяем, что игра готова к запуску
            if not hasattr(game, 'start'):
                raise Exception("Улучшенная игра не имеет метода 'start'")
            
            print(f"✅ Метод 'start' найден")
            print(f"🚀 Запускаем улучшенную игру...")
            
            # Запускаем игру
            try:
                game.start()
                print(f"✅ Улучшенная игра запущена успешно")
            except Exception as start_error:
                print(f"❌ Ошибка при запуске улучшенной игры: {start_error}")
                raise Exception(f"Ошибка при запуске улучшенной игры: {start_error}")
            
            print(f"\n🎉 УЛУЧШЕННАЯ ИГРА УСПЕШНО ЗАПУЩЕНА!")
            print(f"   🎮 Игра готова к использованию")
            print(f"   🪟 Окно должно быть видимым")
            print(f"   ⏹️  Для выхода закройте окно игры или нажмите Ctrl+C")
            
        except Exception as e:
            logger.error(f"Ошибка запуска улучшенной игры: {e}")
            print(f"\n❌ ОШИБКА ЗАПУСКА УЛУЧШЕННОЙ ИГРЫ: {e}")
            print("🔍 Детали ошибки:")
            traceback.print_exc()
            
            # Дополнительная диагностика
            print("\n🔍 ДОПОЛНИТЕЛЬНАЯ ДИАГНОСТИКА:")
            try:
                if hasattr(game, 'showbase'):
                    print(f"✅ ShowBase: {type(game.showbase).__name__}")
                else:
                    print("❌ ShowBase отсутствует")
                
                if hasattr(game, 'render_system'):
                    print(f"✅ Система рендеринга: {type(game.render_system).__name__}")
                else:
                    print("❌ Система рендеринга отсутствует")
                    
            except Exception as diag_e:
                print(f"⚠️  Ошибка дополнительной диагностики: {diag_e}")
            
            return 1
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Игра остановлена пользователем")
        return 0
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        logger.error(f"Критическая ошибка: {e}")
        traceback.print_exc()
        return 1
    finally:
        # Очистка при любом выходе
        cleanup_on_exit()

if __name__ == "__main__":
    try:
        exit_code = main()
        if exit_code == 0:
            print("\n✅ Игра завершена успешно")
        else:
            print(f"\n❌ Игра завершена с ошибкой (код: {exit_code})")
        sys.exit(exit_code)
    except SystemExit:
        cleanup_on_exit()
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Неожиданная ошибка: {e}")
        cleanup_on_exit()
        sys.exit(1)

