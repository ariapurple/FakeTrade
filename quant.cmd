@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title Quant 模拟盘
echo.
echo Double-click this file, then pick a number.
echo 請雙擊本檔，再輸入數字。
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\quant-control.ps1" %*
set ERR=%ERRORLEVEL%
echo.
pause
exit /b %ERR%
