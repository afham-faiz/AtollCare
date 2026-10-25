@echo off
rem Double-click to start the AtollCare demo page. Keep this window open while you use it.
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py --serve
pause
