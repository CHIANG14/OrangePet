@echo off
chcp 65001 >nul
setlocal
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

if exist "%PROJECT_DIR%OrangePet.exe" (
    start "" "%PROJECT_DIR%OrangePet.exe"
    exit /b 0
)

if not exist "%PROJECT_DIR%.venv\Scripts\pythonw.exe" goto setup_needed
"%PROJECT_DIR%.venv\Scripts\python.exe" -c "import PySide6.QtWidgets; import winrt.windows.media.control" >nul 2>&1
if errorlevel 1 goto setup_needed
start "" "%PROJECT_DIR%.venv\Scripts\pythonw.exe" "%PROJECT_DIR%main.py"
exit /b 0

:setup_needed
echo OrangePet.exe or the project environment is missing.
echo Open a terminal in this folder, then run:
echo.
echo     python -m venv .venv
echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
echo Then double-click this launcher again.
echo See README.md for details. No global packages are installed by this launcher.
pause
exit /b 1
