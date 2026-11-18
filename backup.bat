@echo off
chcp 65001 >nul
echo ============================================
echo   RESPALDO AUTOMATICO EN GITHUB
echo ============================================

cd /d "%~dp0"

python auto_backup.py %*

echo.
pause