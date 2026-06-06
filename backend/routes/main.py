from pathlib import Path

from flask import Blueprint, render_template, send_from_directory, abort, request, Response
from ..constants import BASE_DIR, DATA_DIR, ADMIN_MODE

main_bp = Blueprint('main', __name__)

@main_bp.route("/")
def index():
    """Serve the gallery SPA."""
    return render_template("index.html", admin_mode=ADMIN_MODE)

@main_bp.route("/dashboard")
def dashboard():
    """Serve the admin dashboard. Protected by ADMIN_MODE flag."""
    if not ADMIN_MODE:
        abort(404)
    return render_template("dashboard.html", admin_mode=ADMIN_MODE)

@main_bp.route("/images/<path:filepath>")
def serve_image(filepath):
    """Serve local preview images from the data directory."""
    data_root = DATA_DIR.resolve()
    full_path = (data_root / filepath).resolve()
    try:
        full_path.relative_to(data_root)
    except ValueError:
        abort(404)
    if not full_path.exists() or not full_path.is_file():
        abort(404)
    return send_from_directory(str(full_path.parent), full_path.name)

@main_bp.route("/bookmarklet")
def bookmarklet_page():
    """Serve a page with the bookmarklet code and instructions."""
    return render_template("bookmarklet.html", admin_mode=ADMIN_MODE)


@main_bp.route("/client-download-agent.py")
def client_download_agent_py():
    """Serve the self-contained local client downloader script."""
    agent_path = BASE_DIR / "scripts" / "client_download_agent.py"
    if not agent_path.exists():
        abort(404)
    return send_from_directory(str(agent_path.parent), agent_path.name, as_attachment=True)


@main_bp.route("/install-client-downloader.bat")
def install_client_downloader_bat():
    """Generate a Windows installer for the local client downloader."""
    base_url = request.url_root.rstrip("/")
    installer = f"""@echo off
setlocal
title Obsidian Frost Client Downloader Installer
color 0B

set "AGENT_DIR=%LOCALAPPDATA%\\ObsidianFrostAgent"
set "AGENT_SCRIPT=%AGENT_DIR%\\client_download_agent.py"
set "RUNNER_SCRIPT=%AGENT_DIR%\\run-agent.ps1"
set "STARTUP_SCRIPT=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\Obsidian Frost Client Downloader.cmd"
set "BASE_URL={base_url}"
set "PORT=56789"

echo.
echo   =====================================================
echo      Obsidian Frost  ^|  Client Download Agent Installer
echo   =====================================================
echo.
echo   This installs a local downloader on this PC.
echo   Gallery downloads will save on this PC, not the server.
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo   ERROR: Python was not found on this PC.
    echo   Install Python 3.10+ from https://www.python.org/downloads/
    echo   Then run this installer again.
    pause
    exit /b 1
)

if not exist "%AGENT_DIR%" mkdir "%AGENT_DIR%"

echo   Installing Python dependencies...
python -m pip install --user --quiet flask requests
if errorlevel 1 (
    echo   ERROR: Could not install Flask/requests.
    pause
    exit /b 1
)

echo   Downloading client agent from %BASE_URL%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing '%BASE_URL%/client-download-agent.py' -OutFile '%AGENT_SCRIPT%'"
if errorlevel 1 (
    echo   ERROR: Could not download the client agent.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-Content -Path '%RUNNER_SCRIPT%' -Encoding UTF8 -Value @('cd ''%AGENT_DIR%''','python ''%AGENT_SCRIPT%'' --port %PORT%')"

echo   Creating startup shortcut...
(
    echo @echo off
    echo start "" powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%RUNNER_SCRIPT%"
) > "%STARTUP_SCRIPT%"

echo   Registering startup task...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ''' + $env:RUNNER_SCRIPT + ''''); $trigger = New-ScheduledTaskTrigger -AtLogOn; Register-ScheduledTask -TaskName 'Obsidian Frost Client Downloader' -Action $action -Trigger $trigger -Force | Out-Null"
if errorlevel 1 (
    echo   WARNING: Could not create startup task. The agent will still run now.
)

echo   Starting client downloader...
start "Obsidian Frost Client Downloader" /min powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%RUNNER_SCRIPT%"

echo.
echo   Installed. You can close this window.
echo   The downloader will start automatically when this Windows user logs in.
echo.
pause
"""
    return Response(
        installer,
        mimetype="application/x-bat",
        headers={"Content-Disposition": "attachment; filename=install-client-downloader.bat"},
    )

