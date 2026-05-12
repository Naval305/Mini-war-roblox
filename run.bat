@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is not installed. Install it with:
    echo pip install uv
    pause
    exit /b 1
)

if not exist ".env" (
    echo Missing .env file.
    echo Copy .env.example to .env and add your Gemini and Discord values.
    pause
    exit /b 1
)

uv sync
uv run python main.py

pause
