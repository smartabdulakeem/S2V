@echo off
setlocal enabledelayedexpansion
title Smart Studio Setup
color 0A
cd /d "%~dp0"

echo.
echo  ================================================
echo   Smart Studio -- Script to Video
echo   First-time setup
echo  ================================================
echo.

:: ── Step 1: Check Python ──────────────────────────────────────────────────────
echo [1/5] Checking Python installation...

:: Try 'py' launcher first (most reliable on Windows), then 'python'
set PYCMD=
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYCMD=py
) else (
    python --version >nul 2>&1
    if %errorlevel% equ 0 (
        set PYCMD=python
    )
)

if "%PYCMD%"=="" (
    echo.
    echo  Python was not found on this computer.
    echo  Please install Python 3.10 or newer from:
    echo.
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: On the installer screen, tick the box that says
    echo  "Add Python to PATH" before clicking Install.
    echo.
    echo  After installing Python, run this setup.bat again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%V in ('%PYCMD% --version 2^>^&1') do set PYVER=%%V
echo    Found Python %PYVER% (using: %PYCMD%)

:: Check version is 3.10+
%PYCMD% -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  Python 3.10 or newer is required.
    echo  You have Python %PYVER%.
    echo  Please download the latest version from python.org and run setup.bat again.
    echo.
    pause
    exit /b 1
)

:: ── Step 2: Check FFmpeg ───────────────────────────────────────────────────
echo.
echo [2/5] Checking FFmpeg...

ffmpeg -version >nul 2>&1
if %errorlevel% equ 0 (
    echo    FFmpeg found on system PATH.
    goto ffmpeg_done
)

if exist "vendor\ffmpeg\bin\ffmpeg.exe" (
    echo    FFmpeg found in vendor\ffmpeg\
    goto ffmpeg_done
)

echo.
echo  FFmpeg is not installed on this computer. Smart Studio needs it to build
echo  video and to measure narration. Install it from https://ffmpeg.org/download.html,
echo  make sure it is on your PATH, then restart Smart Studio.
echo.
echo  Setup will continue, but video rendering will be unavailable until FFmpeg is installed.
echo.

:ffmpeg_done

:: ── Step 3: Install Python packages ──────────────────────────────────────────
echo.
echo [3/5] Installing Python packages...
echo    (This includes PyTorch for Whisper -- may take 5-15 minutes on first install)
echo.

:: Install CPU-only PyTorch first to avoid the 2GB GPU download
%PYCMD% -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --quiet

if %errorlevel% neq 0 (
    echo.
    echo  Warning: PyTorch CPU install returned an error. Trying standard install...
    %PYCMD% -m pip install torch --quiet
)

:: Install the rest of the requirements
%PYCMD% -m pip install -r requirements.txt --quiet

if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Package installation failed.
    echo  Try running this command manually to see the full error:
    echo    %PYCMD% -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo    All packages installed.

:: ── Step 4: Pre-download Whisper base model ───────────────────────────────────
echo.
echo [4/5] Pre-downloading Whisper speech-to-text model (~150 MB)...
echo    This only happens once. Future runs will use the cached model.
echo.

%PYCMD% -c "import whisper; whisper.load_model('base'); print('Whisper model ready.')"

if %errorlevel% neq 0 (
    echo.
    echo  Warning: Whisper model pre-download failed.
    echo  It will be downloaded automatically on first render instead.
    echo.
)

:: ── Step 5: Validate sample script ───────────────────────────────────────────
echo.
echo [5/5] Running validation test with sample script...

%PYCMD% pipeline\validator.py samples\sample_script.json

if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Validation test failed. The installation may be incomplete.
    echo  Please check the error above and contact support.
    echo.
    pause
    exit /b 1
)

:: ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo  ================================================
echo   Setup complete!
echo.
echo   Double-click run.bat to start the app.
echo  ================================================
echo.
pause
