@echo off
rem Double-click to start the AtollCare demo page AND the phone link (Cloudflare tunnel).
rem Keep this window open and the laptop awake and online while the phone is in use.
cd /d "%~dp0"
where cloudflared >nul 2>nul
if errorlevel 1 (
    echo cloudflared is not installed. Install it once with:
    echo     winget install Cloudflare.cloudflared
    echo then close this window and double-click this file again.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" run.py --tunnel
pause
