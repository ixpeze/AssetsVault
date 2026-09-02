@echo off
title Obsidian Frost Launcher
color 0B
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

echo.
echo   =====================================================
echo      Obsidian Frost  ^|  3D Asset Directory Manager
echo   =====================================================
echo.
echo   [1] Dev Mode       (debug=ON,  admin=ON,  localhost:5000)
echo   [2] Production     (debug=OFF, admin=OFF, localhost:5000)  ^<-- public safe
echo   [3] Admin + Prod   (debug=OFF, admin=ON,  localhost:5000)
echo   [4] Custom Port    (prompt for port + settings)
echo   [5] Public IP Admin + Downloads  (token required)
echo   [6] Public IP Gallery Only       (admin=OFF)
echo   [7] Web Tunnel     (Cloudflare, admin=OFF, public safe, port 5050)
echo   [8] Admin Tunnel   (Cloudflare, admin=ON, requires token, port 5051)
echo.

set /p choice="  Select mode [1/2/3/4/5/6/7/8]: "

if "%choice%"=="1" goto devmode
if "%choice%"=="2" goto production
if "%choice%"=="3" goto adminprod
if "%choice%"=="4" goto customport
if "%choice%"=="5" goto publicadmin
if "%choice%"=="6" goto publicgallery
if "%choice%"=="7" goto webtunnel
if "%choice%"=="8" goto admintunnel

echo   Invalid choice. Starting Dev Mode...
goto devmode

:devmode
echo.
echo   Starting Obsidian Frost (Dev Mode)...
echo   Admin Panel: ENABLED
echo   Debug:       ON
echo   URL:         http://localhost:5000
echo.
set FLASK_DEBUG=1
set ADMIN_MODE=1
python run.py
goto end

:production
echo.
echo   Starting Obsidian Frost (Production Mode)...
echo   Admin Panel: DISABLED  ^<^<  Dashboard hidden from public
echo   Debug:       OFF
echo   URL:         http://localhost:5000
echo.
echo   NOTE: To expose publicly, use a reverse proxy (Nginx, Cloudflare Tunnel)
echo         See: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
echo.
set FLASK_DEBUG=0
set ADMIN_MODE=0
python run.py
goto end

:adminprod
echo.
echo   Starting Obsidian Frost (Admin + Production)...
echo   Admin Panel: ENABLED
echo   Debug:       OFF
echo   URL:         http://localhost:5000
echo.
set FLASK_DEBUG=0
set ADMIN_MODE=1
python run.py
goto end

:publicadmin
echo.
echo   Starting Obsidian Frost on your Public IP with admin/downloads enabled...
echo   WARNING: This exposes admin actions to the network.
echo   A token is required. Remote browsers will be prompted for it once.
echo.
call :prompt_public_ip
set /p PUBLIC_PORT="  Enter port [default 5000]: "
if "%PUBLIC_PORT%"=="" set PUBLIC_PORT=5000
set /p PUBLIC_ADMIN_TOKEN="  Enter admin token: "
if "%PUBLIC_ADMIN_TOKEN%"=="" (
    echo   Public admin mode cancelled: token is required.
    goto end
)
set "FLASK_DEBUG=0"
set "ADMIN_MODE=1"
set "ADMIN_TOKEN=%PUBLIC_ADMIN_TOKEN%"
set "PORT=%PUBLIC_PORT%"
echo.
echo   Local URL:   http://127.0.0.1:%PORT%
echo   Network URL: http://%PUBLIC_IP%:%PORT%
echo.
echo   Router/firewall must forward TCP port %PORT% to this PC.
echo   Downloads save on this server PC unless you set a UNC share path in Settings.
echo.
python run.py
goto end

:publicgallery
echo.
echo   Starting Obsidian Frost public gallery on your Public IP...
echo   Admin Panel: DISABLED
echo   Downloads/admin mutations: DISABLED
echo.
call :prompt_public_ip
set /p PUBLIC_PORT="  Enter port [default 5000]: "
if "%PUBLIC_PORT%"=="" set PUBLIC_PORT=5000
set "FLASK_DEBUG=0"
set "ADMIN_MODE=0"
set "ADMIN_TOKEN="
set "PORT=%PUBLIC_PORT%"
echo.
echo   Local URL:   http://127.0.0.1:%PORT%
echo   Network URL: http://%PUBLIC_IP%:%PORT%
echo.
echo   Router/firewall must forward TCP port %PORT% to this PC.
echo.
python run.py
goto end

:webtunnel
echo.
echo   Starting Obsidian Frost with Cloudflare Tunnel...
echo   Admin Panel: DISABLED  ^<^< public safe
echo   Debug:       OFF
echo   Local URL:   http://127.0.0.1:5050
echo.
set FLASK_DEBUG=0
set ADMIN_MODE=0
set PORT=5050
set ADMIN_TOKEN=
call :launch_tunnel
goto end

:admintunnel
echo.
echo   Starting Obsidian Frost Admin Tunnel...
echo   WARNING: This exposes admin features to the web.
echo   A token is required. Use it as X-Admin-Token or Authorization: Bearer TOKEN.
echo.
set /p TUNNEL_ADMIN_TOKEN="  Enter admin token: "
if "%TUNNEL_ADMIN_TOKEN%"=="" (
    echo   Admin tunnel cancelled: token is required.
    goto end
)
set FLASK_DEBUG=0
set ADMIN_MODE=1
set PORT=5051
set ADMIN_TOKEN=%TUNNEL_ADMIN_TOKEN%
call :launch_tunnel
goto end

:customport
set /p CUSTOM_PORT="  Enter port [default 5000]: "
if "%CUSTOM_PORT%"=="" set CUSTOM_PORT=5000
set /p CUSTOM_DEBUG="  Enable debug? [y/N]: "
set /p CUSTOM_ADMIN="  Enable admin panel? [Y/n]: "

if /i "%CUSTOM_DEBUG%"=="y" (set FLASK_DEBUG=1) else (set FLASK_DEBUG=0)
if /i "%CUSTOM_ADMIN%"=="n" (set ADMIN_MODE=0) else (set ADMIN_MODE=1)
set PORT=%CUSTOM_PORT%

echo.
echo   Starting on http://localhost:%CUSTOM_PORT%
echo   Debug: %FLASK_DEBUG%  Admin: %ADMIN_MODE%
echo.
python run.py
goto end

:launch_tunnel
where cloudflared >nul 2>nul
if errorlevel 1 (
    echo.
    echo   ERROR: cloudflared was not found in PATH.
    echo   Install it from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
    echo.
    exit /b 1
)
echo   Starting Flask in a separate window...
start "Obsidian Frost Flask" /D "%~dp0" cmd /k python run.py
echo   Waiting for Flask to respond on http://127.0.0.1:%PORT%...
call :wait_for_flask
if errorlevel 1 (
    echo.
    echo   ERROR: Flask did not respond on port %PORT%.
    echo   Check the "Obsidian Frost Flask" window for startup errors.
    echo.
    exit /b 1
)
echo.
echo   Starting Cloudflare Tunnel. Copy the https://*.trycloudflare.com URL below.
echo   Press Ctrl+C in this window to stop the tunnel.
echo.
if not exist logs mkdir logs
cloudflared tunnel --url http://127.0.0.1:%PORT% --loglevel info 2>&1 | powershell -NoProfile -ExecutionPolicy Bypass -Command "$input | Tee-Object -FilePath 'logs\cloudflared.log' -Append"
exit /b 0

:prompt_public_ip
set PUBLIC_IP=
for /f "delims=" %%i in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "try { (Invoke-RestMethod -Uri 'https://api.ipify.org' -TimeoutSec 5).Trim() } catch { '' }"') do set PUBLIC_IP=%%i
if "%PUBLIC_IP%"=="" set PUBLIC_IP=YOUR_PUBLIC_IP
set /p PUBLIC_IP_INPUT="  Public IP [%PUBLIC_IP%]: "
if not "%PUBLIC_IP_INPUT%"=="" set PUBLIC_IP=%PUBLIC_IP_INPUT%
exit /b 0

:wait_for_flask
for /L %%i in (1,1,30) do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%PORT%/api/stats' -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }" >nul 2>nul
    if not errorlevel 1 exit /b 0
    timeout /t 1 /nobreak >nul
)
exit /b 1

:end
pause
