@echo off
setlocal enabledelayedexpansion
title S2V Setup
color 0A
cd /d "%~dp0"

echo.
echo  ================================================
echo   S2V -- Script-to-Video Pipeline
echo   First-time setup
echo  ================================================
echo.

:: ── Step 1: Check Python ──────────────────────────────────────────────────────
echo [1/5] Checking Python installation...

python --version >nul 2>&1
if %errorlevel% neq 0 (
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

for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo    Found Python %PYVER%

:: Check version is 3.10+
python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  Python 3.10 or newer is required.
    echo  You have Python %PYVER%.
    echo  Please download the latest version from python.org and run setup.bat again.
    echo.
    pause
    exit /b 1
)

:: ── Step 2: Check / download FFmpeg ──────────────────────────────────────────
echo.
echo [2/5] Checking FFmpeg...

if exist "vendor\ffmpeg\bin\ffmpeg.exe" (
    echo    FFmpeg already installed in vendor\ffmpeg\
    goto ffmpeg_done
)

:: Check if FFmpeg is on the system PATH
ffmpeg -version >nul 2>&1
if %errorlevel% equ 0 (
    echo    FFmpeg found on system PATH -- skipping vendor download.
    goto ffmpeg_done
)

echo    FFmpeg not found. Downloading static Windows build (~80 MB)...
echo    Please wait -- this may take a few minutes depending on your connection.
echo.

if not exist "vendor\ffmpeg" mkdir "vendor\ffmpeg"

:: Download FFmpeg essentials build from gyan.dev
set FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
set FFMPEG_ZIP=vendor\ffmpeg_download.zip

powershell -NoProfile -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ^
    $wc = New-Object System.Net.WebClient; ^
    $wc.DownloadFile('%FFMPEG_URL%', '%FFMPEG_ZIP%')"

if not exist "%FFMPEG_ZIP%" (
    echo.
    echo  ERROR: FFmpeg download failed.
    echo  Please check your internet connection and try again.
    echo  If the problem persists, download FFmpeg manually from:
    echo    https://www.gyan.dev/ffmpeg/builds/
    echo  Place ffmpeg.exe in vendor\ffmpeg\bin\ffmpeg.exe
    echo.
    pause
    exit /b 1
)

echo    Extracting FFmpeg...
powershell -NoProfile -Command ^
    "Expand-Archive -Path '%FFMPEG_ZIP%' -DestinationPath 'vendor\ffmpeg_extract' -Force"

:: Find the bin folder inside the extracted archive (folder name changes with version)
for /d %%D in (vendor\ffmpeg_extract\*) do (
    if exist "%%D\bin\ffmpeg.exe" (
        xcopy "%%D\bin" "vendor\ffmpeg\bin\" /E /I /Q /Y >nul
    )
)

:: Clean up temp files
del /q "%FFMPEG_ZIP%" >nul 2>&1
rmdir /s /q "vendor\ffmpeg_extract" >nul 2>&1

if not exist "vendor\ffmpeg\bin\ffmpeg.exe" (
    echo.
    echo  ERROR: Could not extract FFmpeg correctly.
    echo  Please manually place ffmpeg.exe in vendor\ffmpeg\bin\
    echo.
    pause
    exit /b 1
)

echo    FFmpeg installed successfully.

:ffmpeg_done

:: ── Step 3: Install Python packages ──────────────────────────────────────────
echo.
echo [3/5] Installing Python packages...
echo    (This includes PyTorch for Whisper -- may take 5-15 minutes on first install)
echo.

:: Install CPU-only PyTorch first to avoid the 2GB GPU download
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --quiet

if %errorlevel% neq 0 (
    echo.
    echo  Warning: PyTorch CPU install returned an error. Trying standard install...
    pip install torch --quiet
)

:: Install the rest of the requirements
pip install -r requirements.txt --quiet

if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Package installation failed.
    echo  Try running this command manually to see the full error:
    echo    pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo    All packages installed.

:: ── Step 4: Pre-download Whisper base model ───────────────────────────────────
echo.
echo [4/6] Pre-downloading Whisper speech-to-text model (~150 MB)...
echo    This only happens once. Future runs will use the cached model.
echo.

python -c "import whisper; whisper.load_model('base'); print('Whisper model ready.')"

if %errorlevel% neq 0 (
    echo.
    echo  Warning: Whisper model pre-download failed.
    echo  It will be downloaded automatically on first render instead.
    echo.
)

:: ── Step 5: Download Piper TTS (offline voice engine) ─────────────────────────
echo.
echo [5/6] Checking Piper TTS (offline voice engine)...

if exist "vendor\piper\piper.exe" (
    echo    Piper already installed in vendor\piper\
    goto piper_done
)

echo    Downloading Piper TTS for Windows (~30 MB)...
echo    This gives you offline voice options that work without internet.
echo.

if not exist "vendor\piper" mkdir "vendor\piper"
if not exist "vendor\piper\voices" mkdir "vendor\piper\voices"

set PIPER_URL=https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip
set PIPER_ZIP=vendor\piper_download.zip

powershell -NoProfile -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ^
    $wc = New-Object System.Net.WebClient; ^
    $wc.DownloadFile('%PIPER_URL%', '%PIPER_ZIP%')"

if not exist "%PIPER_ZIP%" (
    echo.
    echo  Warning: Piper download failed. Offline voices will not be available.
    echo  You can still use Gemini and Edge TTS voices without Piper.
    echo  To retry Piper later, delete vendor\piper\ and run setup.bat again.
    echo.
    goto piper_done
)

echo    Extracting Piper...
powershell -NoProfile -Command ^
    "Expand-Archive -Path '%PIPER_ZIP%' -DestinationPath 'vendor\piper_extract' -Force"

:: Copy piper.exe and any .dll files from extracted folder
for /d %%D in (vendor\piper_extract\*) do (
    if exist "%%D\piper.exe" (
        copy /Y "%%D\piper.exe" "vendor\piper\piper.exe" >nul
        copy /Y "%%D\*.dll"    "vendor\piper\" >nul 2>&1
        copy /Y "%%D\*.onnx"   "vendor\piper\" >nul 2>&1
    )
)
:: Also handle flat zip (piper.exe at root level)
if exist "vendor\piper_extract\piper.exe" (
    copy /Y "vendor\piper_extract\piper.exe" "vendor\piper\piper.exe" >nul
    copy /Y "vendor\piper_extract\*.dll"     "vendor\piper\" >nul 2>&1
)

del /q "%PIPER_ZIP%" >nul 2>&1
rmdir /s /q "vendor\piper_extract" >nul 2>&1

if not exist "vendor\piper\piper.exe" (
    echo.
    echo  Warning: Could not extract Piper correctly. Offline voices unavailable.
    echo.
    goto piper_done
)

echo    Downloading Piper voice: en_US-ryan-high (~65 MB)...
set VOICE_BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high

powershell -NoProfile -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ^
    $wc = New-Object System.Net.WebClient; ^
    $wc.DownloadFile('%VOICE_BASE%/en_US-ryan-high.onnx', 'vendor\piper\voices\en_US-ryan-high.onnx')" >nul 2>&1

powershell -NoProfile -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ^
    $wc = New-Object System.Net.WebClient; ^
    $wc.DownloadFile('%VOICE_BASE%/en_US-ryan-high.onnx.json', 'vendor\piper\voices\en_US-ryan-high.onnx.json')" >nul 2>&1

if exist "vendor\piper\voices\en_US-ryan-high.onnx" (
    echo    Piper voice en_US-ryan-high downloaded.
) else (
    echo    Warning: Voice download failed. Piper will not produce audio without voice files.
)

:piper_done

:: ── Step 6: Validate sample script ───────────────────────────────────────────
echo.
echo [6/6] Running validation test with sample script...

python pipeline\validator.py samples\sample_script.json

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
