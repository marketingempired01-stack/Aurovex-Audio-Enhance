@echo off
title Auravox - dev mode (auto-reload)
cd /d "%~dp0"
if "%PORT%"=="" set "PORT=8000"
echo [dev] Starting Auravox with auto-reload on http://localhost:%PORT%
call "%~dp0start.bat" --reload
