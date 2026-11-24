@echo off
setlocal
title Learning International Schools - Athar
cd /d "%~dp0"

rem ---- 1. uv runs the app. Install it the first time only.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo Installing uv, the tool that runs the app. This happens only once...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >nul 2>nul
if errorlevel 1 (
  echo.
  echo uv could not be installed. Check the internet connection and try again.
  pause
  exit /b 1
)

rem ---- 2. The app's packages. The first time this downloads them; after that it takes a second.
echo Preparing the app...
uv sync --quiet
if errorlevel 1 (
  echo.
  echo The app's packages could not be installed. Check the internet connection and try again.
  pause
  exit /b 1
)

rem ---- 3. Open the browser as soon as the app answers (the first start builds the demo school).
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 300;$i++){try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8765/api/session | Out-Null; Start-Process 'http://127.0.0.1:8765'; break}catch{Start-Sleep -Seconds 1}}"

echo.
echo Starting the app. Keep this window open while you use it. Close it to stop the app.
echo.
uv run athar demo
if errorlevel 1 pause
