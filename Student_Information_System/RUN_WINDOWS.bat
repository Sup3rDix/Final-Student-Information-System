@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py main.py
) else (
    python main.py
)
if errorlevel 1 (
    echo.
    echo Could not start Python. Install Python 3.9+ from python.org.
    echo If needed, enable Add Python to PATH and restart the terminal.
)
pause
