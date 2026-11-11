@echo off
title Bot Sparatutto
echo.
echo  ==============================================================
echo    BOT SPARATUTTO
echo    La prima volta scarica il programma per il PC (circa 100 MB)
echo    e lo mette in Documenti\BotSparatutto. Poi lo avvia.
echo  ==============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installa.ps1"
if errorlevel 1 (
  echo.
  echo  Qualcosa e' andato storto: controlla la connessione a internet e riprova.
  echo.
  pause
)
