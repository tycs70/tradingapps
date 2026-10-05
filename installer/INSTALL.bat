@echo off
setlocal
title EMA Pre-Cross Scanner - Windows installation
cd /d "%~dp0"
echo Installing EMA Pre-Cross Scanner 1.0.1 for this Windows user...
echo The private Python runtime and dependencies are bundled. No admin rights required.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo Installation did not finish. Read the error above before closing this window.
  pause
  exit /b 1
)
echo.
echo Installation complete. Open EMA Pre-Cross Scanner from your Desktop.
pause
