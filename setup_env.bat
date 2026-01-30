@echo off
setlocal

echo [INFO] Phoenix Agent Environment Setup
echo ========================================

:: 1. Check for Python 3.12 via py launcher
echo [INFO] Checking for Python 3.12...
py -3.12 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py -3.12
    goto :FoundPython
)

:: 2. Fallback to standard python command
python --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PV=%%v
    echo [INFO] Found default Python version: %PV%
    set PYTHON_CMD=python
    goto :FoundPython
)

echo [ERROR] Python 3.12 or higher not found. Please install Python 3.12+.
pause
exit /b 1

:FoundPython
echo [INFO] Using Python command: %PYTHON_CMD%

:: 3. Create Virtual Environment
if exist ".venv" (
    echo [INFO] Virtual environment .venv already exists.
) else (
    echo [INFO] Creating virtual environment .venv ...
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [INFO] Virtual environment created.
)

:: 4. Activate and Install
echo [INFO] Activating .venv and installing requirements...
call .venv\Scripts\activate.bat

echo [INFO] Upgrading pip...
python -m pip install --upgrade pip

if exist "requirements.txt" (
    echo [INFO] Installing dependencies from requirements.txt...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install requirements.
        pause
        exit /b 1
    )
    echo [SUCCESS] Dependencies installed successfully.
) else (
    echo [WARN] requirements.txt not found! Skipping installation.
)

echo ========================================
echo [SUCCESS] Setup complete! 
echo To activate venv manually: call .venv\Scripts\activate
echo ========================================
pause
