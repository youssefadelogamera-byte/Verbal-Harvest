@echo off
title Athar
cd /d "%~dp0"
if not exist "runtime\python\python.exe" (
  echo This folder is not complete. Extract the whole zip first, then run this file from the extracted folder.
  pause
  exit /b 1
)
"runtime\python\python.exe" -E -s -u "app\launch.py"
if errorlevel 1 pause
