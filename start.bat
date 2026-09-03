@echo off
title 3DSkyFree Asset Manager
color 0B
cd /d "%~dp0"

:: Use the virtual environment Python directly - 100% reliable
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo.
    echo   [ERROR] Virtual environment not found at .venv\Scripts\python.exe
    echo   Please check your .venv folder.
    echo.
    pause
    exit /b 1
)

echo.
echo   =====================================================
echo      Obsidian Frost  ^|  3D Asset Directory Manager
echo   =====================================================
echo.
echo   [1] Start Web App          (Localhost:5000 - Full Access)
echo   [2] Sync from Google Drive (Download latest cloud batches)
echo   [3] Check Catalog Progress (View visual stats ^& progress bar)
echo.

set "choice="
set /p choice="  Select option [1/2/3] (Press Enter for [1]): "
if "%choice%"=="" set choice=1

if "%choice%"=="1" goto start_app
if "%choice%"=="2" goto sync_drive
if "%choice%"=="3" goto check_progress

echo   Invalid choice. Defaulting to Start Web App...
goto start_app

:start_app
echo.
echo   Starting 3DSkyFree Web App...
echo   Open your browser at: http://localhost:5000
echo.
set "FLASK_DEBUG=1"
set "ADMIN_MODE=1"
"%PY%" run.py
goto end

:sync_drive
echo.
echo   Syncing batches from Google Drive...
echo.
"%PY%" scripts\pipeline\sync_from_gdrive.py
echo.
pause
goto end

:check_progress
echo.
"%PY%" scripts\pipeline\check_progress.py
echo.
pause
goto end

:end
