@echo off
REM ============================================================
REM  MCP Server Inspector Launcher
REM ============================================================

cd /d "%~dp0"

echo [1/3] Checking virtual environment...
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo [2/3] Activating virtual environment and ensuring fastmcp is installed...
call .venv\Scripts\activate.bat
pip install -q fastmcp

echo [3/3] Launching FastMCP Inspector...
fastmcp dev server.py

pause
