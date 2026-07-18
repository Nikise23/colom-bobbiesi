@echo off
REM Ejecutar backup semanal del consultorio (producción vía BACKUP_DATABASE_URL).
REM Ajustá las rutas según tu PC.
REM En .env: DATABASE_URL=localhost y BACKUP_DATABASE_URL=URL de Render.

set PROJECT_DIR=C:\Users\nicfe\Downloads\colom-bobbiesi-main\colom-bobbiesi-web
set BACKUP_DIR=C:\Backups\colom-bobbiesi
set PYTHON=python

cd /d "%PROJECT_DIR%"
"%PYTHON%" scripts\backup_postgres.py --output-dir "%BACKUP_DIR%" --keep 8
if errorlevel 1 (
    echo Backup fallo con codigo %errorlevel%
    exit /b %errorlevel%
)
