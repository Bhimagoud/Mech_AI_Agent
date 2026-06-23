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
    echo [1/4] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        echo       Make sure Python 3.10+ is installed and on PATH.
        pause
        exit /b 1
    )
    echo       Virtual environment created.
) else (
    echo [1/4] Virtual environment found.
)

call .venv\Scripts\activate.bat

REM ── Step 2: Install / update dependencies ────────────────────
echo [2/4] Installing dependencies from requirements.txt...
pip install -q -r requirements.txt
if exist "mcp\requirements.txt" (
    pip install -q -r mcp\requirements.txt
)
if errorlevel 1 (
    echo ERROR: pip install failed. Check requirements.txt and internet connection.
    pause
    exit /b 1
)
echo       Dependencies ready.

REM ── Step 3: Launch MCP Server ──────────────────────────────
echo [3/4] Starting MCP Server in a separate window...
REM We use fastmcp to run the MCP server with SSE transport on port 8080 to avoid conflicts.
start "Mech AI Agents MCP Server" cmd /c "call .venv\Scripts\activate.bat && fastmcp run mcp/server.py --transport sse --port 8080"

REM ── Step 4: Launch Web server ──────────────────────────────
echo [4/4] Starting Flask web server on http://127.0.0.1:5000 ...
echo.
echo  ^>^>^> Automatically opening your browser...
echo  ^>^>^> Press Ctrl+C in this window to stop the web server.
echo.

set FLASK_APP=app.py
set FLASK_ENV=development
set DEBUG=false

REM Open the default browser to the Flask frontend
start http://127.0.0.1:5000

python app.py

pause
