@echo off
title Auravox - AI Voice Enhancement
cd /d "%~dp0"

echo ============================================
echo   Auravox - AI Voice Enhancement (local)
echo ============================================
echo.

rem ---- locate Python (prefer 3.11) ----
where py >nul 2>nul
if %errorlevel%==0 (
    py -3.11 -3 >nul 2>nul && set "PYCMD=py -3.11"
)
if not defined PYCMD set "PYCMD=python"

rem ---- FFmpeg check (optional but recommended) ----
where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo [info] FFmpeg not found on PATH - the bundled fallback will be used.
    echo        For best results install it:  winget install Gyan.FFmpeg
    echo.
)

rem ---- virtual environment ----
if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creating virtual environment...
    %PYCMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [error] Could not create .venv. Is Python 3.11 installed?
        pause
        exit /b 1
    )
)

rem ---- dependencies ----
if not exist ".venv\deps.ok" (
    echo [setup] Installing dependencies (first run only, ~200 MB download)...
    .venv\Scripts\python.exe -m pip install --upgrade pip >nul
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [error] Dependency installation failed. See docs\TROUBLESHOOTING.md
        pause
        exit /b 1
    )
    echo ok> .venv\deps.ok
)

rem ---- launch ----
echo.
echo [run] Starting Auravox on http://localhost:8000
echo       Press Ctrl+C to stop.
echo.
start "" http://localhost:8000
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port %PORT% %*
if %errorlevel% neq 0 (
    echo.
    echo [error] The server stopped unexpectedly. See docs\TROUBLESHOOTING.md
    pause
)
