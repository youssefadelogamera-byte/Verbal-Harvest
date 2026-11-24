@echo off
title Athar: download the model
cd /d "%~dp0"
"runtime\python\python.exe" -E -s -u "app\download_model.py"
pause
