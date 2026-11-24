@echo off
cd /d "%~dp0"
"runtime\python\python.exe" -E -s -u "app\launch.py" --stop
timeout /t 3 >nul
