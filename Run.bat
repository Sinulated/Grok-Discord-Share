@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  Grok to WEBP – Launcher
::  Creates a venv, installs dependencies, then starts the app
:: ============================================================

title Grok to WEBP – Setup & Launch
cd /d "%~dp0"

echo.
echo  ========================================================
echo           Grok to WEBP  ·  Sinulated.Art
echo  ========================================================
echo.

:: ------------------------------------------------------------
:: 1. Locate Python
:: ------------------------------------------------------------
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python was not found on PATH.
    echo          Please install Python 3.10+ from https://python.org
    echo          and make sure "Add Python to PATH" is checked.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo  Found %PYVER%
echo.

:: ------------------------------------------------------------
:: 2. Create virtual environment if it doesn't exist
:: ------------------------------------------------------------
if not exist "venv\Scripts\python.exe" (
    echo  Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
    echo  venv created.
) else (
    echo  Virtual environment already exists.
)
echo.

:: ------------------------------------------------------------
:: 3. Activate venv
:: ------------------------------------------------------------
call "venv\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo  [ERROR] Could not activate venv.
    pause
    exit /b 1
)

:: ------------------------------------------------------------
:: 4. Upgrade pip and install dependencies
:: ------------------------------------------------------------
echo  Installing / updating dependencies...
echo.

python -m pip install --upgrade pip >nul

python -m pip install ^
    pillow ^
    tkinterdnd2 ^
    python-dotenv ^
    pywin32 ^
    win11toast ^
    pyperclip

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] One or more packages failed to install.
    echo          Check the output above for details.
    pause
    exit /b 1
)

echo.
echo  Dependencies ready.
echo.

:: ------------------------------------------------------------
:: 5. Launch the app
:: ------------------------------------------------------------
if not exist "app.py" (
    echo  [ERROR] app.py not found in this folder.
    echo          Make sure this .bat sits next to app.py.
    pause
    exit /b 1
)

echo  Starting Grok to WEBP...
echo.
python app.py

:: If the app exits with an error, keep the window open
if %errorlevel% neq 0 (
    echo.
    echo  App exited with an error code: %errorlevel%
    pause
)

endlocal
