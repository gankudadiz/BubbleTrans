@echo off
set PYTHONPATH=%PYTHONPATH%;%~dp0src
python setup_check.py
if %errorlevel% neq 0 (
    echo Environment check failed.
    pause
    exit /b
)
python src/main.py
pause
