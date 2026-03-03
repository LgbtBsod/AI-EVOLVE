@echo off
chcp 65001 >nul
echo 🎮 AI-EVOLVE Enhanced Edition
echo ================================
echo.

REM Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден!
    echo Установите Python 3.8+ с https://python.org
    pause
    exit /b 1
)

REM Устанавливаем зависимости из requirements.txt
if exist requirements.txt (
    echo 📦 Установка зависимостей из requirements.txt...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ❌ Ошибка установки зависимостей из requirements.txt
        pause
        exit /b 1
    )
)

echo ✅ Все готово! Запускаем игру...
echo.
python launcher.py

if errorlevel 1 (
    echo.
    echo ❌ Игра завершилась с ошибкой
    pause
)
