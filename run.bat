@echo off
cd /d "%~dp0"

REM A virtual environment inside the app folder wins, so an install never
REM depends on which Python the machine happens to have. This used to name one
REM absolute path with a username in it, which no other machine could have.
set PYEXE=%~dp0.venv\Scripts\python.exe
if exist "%PYEXE%" goto found_python

REM Fall back to whatever python is on PATH
where python >nul 2>&1
if %errorlevel% equ 0 (
    set PYEXE=python
    goto found_python
)

where python3 >nul 2>&1
if %errorlevel% equ 0 (
    set PYEXE=python3
    goto found_python
)

echo.
echo  Python was not found. Please install Python 3.10 or newer from:
echo  https://www.python.org/downloads/
echo  Make sure to tick "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found_python
"%PYEXE%" app.py
if %errorlevel% neq 0 (
    echo.
    echo  The app encountered an error. Check the logs\ folder for details.
    echo.
    pause
)
