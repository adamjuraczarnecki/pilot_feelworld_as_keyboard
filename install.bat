@echo off
setlocal enabledelayedexpansion
title FEELWORLD-05 Installer

echo.
echo  ==========================================
echo    FEELWORLD-05  Controller  Installer
echo  ==========================================
echo.
call :beep_start

cd /d "%~dp0"

echo [1/3] Checking uv...
where uv >nul 2>&1
if errorlevel 1 (
    echo   [..] uv not found, installing...
    powershell -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%APPDATA%\Local\uv\bin;%PATH%"
    where uv >nul 2>&1
    if errorlevel 1 (
        call :beep_err
        echo  [ERROR] uv installation failed.
        echo         Install manually: https://docs.astral.sh/uv/getting-started/installation/
        pause
        exit /b 1
    )
)
for /f "tokens=*" %%v in ('uv --version 2^>^&1') do set UVVER=%%v
echo   [OK] !UVVER!
call :beep_ok

echo.
echo [2/3] Installing dependencies...
uv sync
if errorlevel 1 (
    call :beep_err
    echo  [ERROR] Dependency installation failed.
    pause
    exit /b 1
)
echo   [OK] Dependencies installed
call :beep_ok

echo.
echo [3/3] Verifying imports...
uv run python -c "import bleak, pynput, importlib.metadata; print('  [OK] bleak', importlib.metadata.version('bleak'))"
if errorlevel 1 (
    call :beep_err
    echo  [ERROR] Failed to import bleak/pynput.
    pause
    exit /b 1
)
call :beep_ok

echo.
echo Checking Bluetooth...
sc query bthserv >nul 2>&1
if errorlevel 1 (
    echo   [!] Bluetooth Support Service not running.
    echo       Enable Bluetooth in Windows Settings.
) else (
    echo   [OK] Bluetooth service running
    call :beep_ok
)

powershell -NoProfile -Command "if ((Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Where-Object Status -eq 'OK').Count -gt 0) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo   [!] No active Bluetooth adapter detected.
) else (
    echo   [OK] Bluetooth adapter OK
)

if not exist "device_mac.txt" (
    echo.
    echo   If the remote has not been paired yet:
    echo     1. Open Windows Settings - Bluetooth and devices
    echo     2. Click "Add device" - Bluetooth
    echo     3. Press the power button on the remote to make it discoverable
    echo     4. Select FEELWORLD-05 from the list
    echo.
    pause
)

echo.
call :beep_done
echo  ==========================================
echo    Done! Launching controller...
echo  ==========================================
echo.
echo  Click on the browser window with the teleprompter,
echo  then use the remote. Press Ctrl+C to stop.
echo.

uv run controller.py
pause
goto :eof

:beep_start
powershell -NoProfile -Command "[Console]::Beep(523,120);[Console]::Beep(659,120);[Console]::Beep(784,200)" 2>nul
goto :eof

:beep_ok
powershell -NoProfile -Command "[Console]::Beep(880,120);[Console]::Beep(1047,200)" 2>nul
goto :eof

:beep_err
powershell -NoProfile -Command "[Console]::Beep(200,400);[Console]::Beep(150,600)" 2>nul
goto :eof

:beep_done
powershell -NoProfile -Command "[Console]::Beep(523,100);[Console]::Beep(659,100);[Console]::Beep(784,100);[Console]::Beep(1047,400)" 2>nul
goto :eof
