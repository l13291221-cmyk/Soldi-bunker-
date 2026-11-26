@echo off
rem AVVIA IL BOT: apre BotSparatutto.exe (quello in questa cartella).
rem La prima volta mette anche l'icona "Bot Sparatutto" sul desktop.
title Bot Sparatutto
cd /d "%~dp0"
if not exist "%~dp0BotSparatutto.exe" (
  echo.
  echo  Non trovo BotSparatutto.exe in questa cartella.
  echo  Estrai TUTTO lo zip (tasto destro sullo zip - Estrai tutto) e riprova da li'.
  echo.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $d=[Environment]::GetFolderPath('Desktop'); $l=Join-Path $d 'Bot Sparatutto.lnk'; if (-not (Test-Path $l)) { $s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); $s.TargetPath='%~dp0BotSparatutto.exe'; $s.WorkingDirectory='%~dp0'; $s.Save() } } catch { }" >nul 2>&1
"%~dp0BotSparatutto.exe"
if errorlevel 1 pause
