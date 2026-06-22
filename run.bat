@echo off
REM ============================================================
REM  Mech_AI_agents — Local Server Launcher
REM  Run this from the project root:  e:\Mech_AI_agents\
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo   NBA PEO-Mission Mapping Engine - Local Server
echo ============================================================
echo.

REM ── Step 1: Create / activate virtual environment ────────────
if not exist ".venv\Scripts\activate.bat" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        echo       Make sure Python 3.10+ is installed and on PATH.
        pause
        exit /b 1
    )
    echo       Virtual environment created.
) else (
    echo [1/3] Virtual environment found.
)

call .venv\Scripts\activate.bat

REM ── Step 2: Install / update dependencies ────────────────────
echo [2/3] Installing dependencies from requirements.txt...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed. Check requirements.txt and internet connection.
    pause
    exit /b 1
)
echo       Dependencies ready.

REM ── Step 3: Launch Flask server ──────────────────────────────
echo [3/3] Starting Flask server on http://127.0.0.1:5000 ...
echo.
echo  ^>^>^> Open your browser at:  http://127.0.0.1:5000
echo  ^>^>^> Press Ctrl+C to stop the server.
echo.

set FLASK_APP=app.py
set FLASK_ENV=development
set DEBUG=false

python app.py

pause
