@echo off
title Установка зависимостей AI-EVOLVE
echo 📦 Установка зависимостей...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %ERRORLEVEL% EQU 0 (
    echo ✅ Зависимости установлены успешно!
    echo Теперь можно запустить start_game.bat
) else (
    echo ❌ Ошибка установки зависимостей
    echo Проверьте подключение к интернету
)
pause
