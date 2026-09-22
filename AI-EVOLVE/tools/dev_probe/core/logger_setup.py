"""Logger Setup - настройка логирования для Dev Probe."""
import logging
from pathlib import Path
from typing import Optional


def setup_logging(
    output_dir: Path,
    level: int = logging.INFO,
    log_to_file: bool = True,
    log_to_console: bool = True,
) -> logging.Logger:
    """Настроить логирование для Dev Probe.
    
    Args:
        output_dir: Директория для сохранения логов
        level: Уровень логирования
        log_to_file: Писать логи в файл
        log_to_console: Выводить логи в консоль
        
    Returns:
        Настроенный logger
    """
    logger = logging.getLogger("dev_probe")
    logger.setLevel(level)
    
    # Очистить существующие обработчики
    logger.handlers.clear()
    
    # Форматтер
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    
    # Консольный обработчик
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # Файловый обработчик
    if log_to_file:
        log_file = output_dir / "dev_probe.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "dev_probe") -> logging.Logger:
    """Получить logger по имени.
    
    Args:
        name: Имя logger
        
    Returns:
        Logger с указанным именем
    """
    return logging.getLogger(name)
