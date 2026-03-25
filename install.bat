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

echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    call :beep_err
    echo.
    echo  [ERROR] Python is not installed or not in PATH.
    echo         Download from: https://python.org
    echo         Make sure to check "Add to PATH" during installation.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] !PYVER!
call :beep_ok

echo.
echo [2/4] Virtual environment...
if exist "venv\Scripts\python.exe" (
    echo  [OK] venv already exists
) else (
    python -m venv venv
    if errorlevel 1 (
        call :beep_err
        echo  [ERROR] Could not create venv.
        pause
        exit /b 1
    )
    echo  [OK] venv created
)
call :beep_ok

echo.
echo [3/4] Installing dependencies (bleak, pynput)...
venv\Scripts\pip install --upgrade pip -q 2>nul
venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    call :beep_err
    echo  [ERROR] Dependency installation failed.
    pause
    exit /b 1
)
echo  [OK] Dependencies installed
call :beep_ok

echo.
echo [4/4] Verifying imports...
venv\Scripts\python -c "import bleak, pynput, importlib.metadata; print('  [OK] bleak', importlib.metadata.version('bleak'))"
if errorlevel 1 (
    call :beep_err
    echo  [ERROR] Failed to import bleak/pynput.
    pause
    exit /b 1
)
call :beep_ok

echo.
call :beep_done
echo  ==========================================
echo    Done! Launching controller...
echo  ==========================================
echo.
echo  Click on the browser window with the teleprompter,
echo  then use the remote. Press Ctrl+C to stop.
echo.

venv\Scripts\python controller.py
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
