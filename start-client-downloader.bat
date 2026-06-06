@echo off
title Obsidian Frost Client Downloader
color 0B
cd /d "%~dp0"

echo.
echo   =====================================================
echo      Obsidian Frost  ^|  Client Download Agent
echo   =====================================================
echo.
echo   Run this on each teammate PC that should download files locally.
echo   Keep this window open while using the gallery in the browser.
echo.

set /p CLIENT_DOWNLOAD_DIR="  Download folder [default: %%USERPROFILE%%\Downloads\ObsidianFrost]: "
set /p CLIENT_AGENT_PORT="  Local agent port [default: 56789]: "
if "%CLIENT_AGENT_PORT%"=="" set CLIENT_AGENT_PORT=56789

if "%CLIENT_DOWNLOAD_DIR%"=="" (
    python scripts\client_download_agent.py --port %CLIENT_AGENT_PORT%
) else (
    python scripts\client_download_agent.py --port %CLIENT_AGENT_PORT% --download-dir "%CLIENT_DOWNLOAD_DIR%"
)

pause
