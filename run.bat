@echo off
cd /d "%~dp0"

REM Auto-create venv if not exists
if not exist .venv\Scripts\python.exe (
    echo [BubbleTrans] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo Failed to create venv. Please install Python 3.10+
        pause
        exit /b
    )
    echo [BubbleTrans] Virtual environment created.
)

REM Use venv Python
set VENV_PYTHON=%~dp0.venv\Scripts\python.exe
set PYTHONPATH=%~dp0src

REM Check & install dependencies
"%VENV_PYTHON%" setup_check.py
if %errorlevel% neq 0 (
    echo Environment check failed.
    pause
    exit /b
)

REM Launch
"%VENV_PYTHON%" src/main.py
pause
