@echo off
setlocal
cd /d "%~dp0"

set VENV_PY=.venv\Scripts\python.exe

if not exist "%VENV_PY%" (
    echo [AI-EVOLVE] Creating virtual environment with Python 3.13...
    echo [AI-EVOLVE] ^(Panda3D has no wheels for Python 3.14/3.15 yet, so 3.13 is required^)
    py -3.13 -m venv .venv
    if errorlevel 1 (
        echo.
        echo [AI-EVOLVE] ERROR: Python 3.13 was not found via the "py" launcher.
        echo Install it first, e.g.:
        echo     winget install --id Python.Python.3.13 -e
        echo.
        pause
        exit /b 1
    )
)

echo [AI-EVOLVE] Checking/installing dependencies...
"%VENV_PY%" -m pip install --quiet --upgrade pip
"%VENV_PY%" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [AI-EVOLVE] ERROR: failed to install dependencies.
    pause
    exit /b 1
)

set DEV_FLAG=--dev
if /I "%~1"=="full" set DEV_FLAG=

echo [AI-EVOLVE] Launching game...
if defined DEV_FLAG (
    echo [AI-EVOLVE] Dev map ^(small, fast to test^). Run "run_game.bat full" for the real-size map.
)
echo.
"%VENV_PY%" main.py %DEV_FLAG%

echo.
echo [AI-EVOLVE] Game closed.
pause
