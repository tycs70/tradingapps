@echo off
setlocal
title Trend Chaser Nifty Midcap 50 - Windows installation
cd /d "%~dp0"
echo Installing Trend Chaser Nifty Midcap 50 1.0.0 for this Windows user...
echo The private Python runtime and dependencies are bundled. No admin rights required.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo Installation did not finish. Read the error above before closing this window.
  pause
  exit /b 1
)
echo.
echo Installation complete. Open Trend Chaser Nifty Midcap 50 from your Desktop.
pause
