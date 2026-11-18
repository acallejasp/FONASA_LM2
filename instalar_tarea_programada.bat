@echo off
chcp 65001 >nul
echo Instalando tarea programada para respaldo automatico...

:: Obtiene la ruta actual del proyecto
set "RUTA_PROYECTO=%~dp0"
set "RUTA_SCRIPT=%RUTA_PROYECTO%backup.bat"

:: Crea la tarea: se ejecuta cada 4 horas
schtasks /create /tn "GitBackup_Proyecto" ^
    /tr "\"%RUTA_SCRIPT%\"" ^
    /sc hourly /mo 4 ^
    /f

echo.
echo ✅ Tarea programada creada: cada 4 horas
echo    Nombre de la tarea: GitBackup_Proyecto
echo.
echo Para eliminarla: schtasks /delete /tn "GitBackup_Proyecto" /f
echo Para verla:      schtasks /query /tn "GitBackup_Proyecto"
echo.
pause