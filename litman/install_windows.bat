@echo off
chcp 65001 >nul
title litman v1.0.0 Installer

echo ============================================================
echo   litman v1.0.0 — Installer for Windows
echo ============================================================
echo.

:: ── Check prerequisites ──────────────────────────────────────
echo [1/6] Checking prerequisites...

where git >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Git is not installed.
    echo Download from: https://git-scm.com/download/win
    pause
    exit /b 1
)
echo   Git ... OK

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo   Python ... OK

python -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: pip is not available.
    pause
    exit /b 1
)
echo   pip ... OK
echo.

:: ── Git config ───────────────────────────────────────────────
echo [2/6] Git configuration
echo.

set /p USERNAME="  Your name (e.g. Taro Yamada): "
set /p USEREMAIL="  Your email: "

git config --global user.name "%USERNAME%"
git config --global user.email "%USEREMAIL%"
echo.
echo   Git user configured: %USERNAME% ^<%USEREMAIL%^>
echo.

:: ── GitHub authentication ────────────────────────────────────
echo [3/6] GitHub authentication (for shared library access)
echo.
echo   A Personal Access Token (PAT) is required to access
echo   the shared library repository (private).
echo.
echo   Opening GitHub token page in your browser...
echo   Create a token with "repo" scope checked.
echo.
start https://github.com/settings/tokens/new?scopes=repo^&description=litman
echo.
set /p PAT="  Paste your PAT here: "

git config --global credential.helper manager

:: Store credential
(
echo protocol=https
echo host=github.com
echo username=Shotaro-Tada
echo password=%PAT%
echo.
) | git credential-manager store >nul 2>&1

if %errorlevel% neq 0 (
    (
    echo protocol=https
    echo host=github.com
    echo username=Shotaro-Tada
    echo password=%PAT%
    echo.
    ) | git credential approve >nul 2>&1
)

echo.

:: ── Verify authentication ────────────────────────────────────
echo   Verifying authentication...
git ls-remote https://github.com/Shotaro-Tada/precam-litman-library.git >nul 2>&1
if %errorlevel% neq 0 (
    echo   WARNING: Could not access the shared library.
    echo   Check your PAT and try again later.
    echo   You can still use litman without sync.
) else (
    echo   Authentication ... OK
)
echo.

:: ── Clone repository ─────────────────────────────────────────
echo [4/6] Cloning repository...

cd /d "%USERPROFILE%"
if exist precam (
    echo   precam folder already exists. Pulling latest...
    git -C precam pull origin main
) else (
    git clone https://github.com/Shotaro-Tada/precam.git
)
echo.

:: ── Install dependencies ─────────────────────────────────────
echo [5/6] Installing dependencies...

cd /d "%USERPROFILE%\precam\litman"
python -m pip install -e . >nul 2>&1
if %errorlevel% neq 0 (
    python -m pip install --user -e .
)
echo   Dependencies installed.
echo.

:: ── Create launcher with book icon ──────────────────────────
echo [6/6] Creating desktop launcher...

:: Create assets directory
if not exist "%USERPROFILE%\precam\litman\assets" mkdir "%USERPROFILE%\precam\litman\assets"

:: Generate book icon using Pillow (installed with streamlit)
python -c "from PIL import Image,ImageDraw;img=Image.new('RGBA',(256,256),(0,0,0,0));d=ImageDraw.Draw(img);d.rounded_rectangle([30,20,226,236],radius=12,fill='#1565C0',outline='#0D47A1',width=4);d.rectangle([50,30,216,226],fill='#FAFAFA',outline='#E0E0E0',width=2);[d.line([(65,y),(200,y)],fill='#BDBDBD',width=2) for y in range(60,200,22)];d.line([(50,20),(50,236)],fill='#0D47A1',width=6);d.polygon([(180,20),(195,20),(195,70),(187,58),(180,70)],fill='#E53935');img.save(r'%USERPROFILE%\precam\litman\assets\book.ico',format='ICO',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

:: Create launch script (auto-detect location, conda init for desktop launch)
(
echo @echo off
echo if exist "%%USERPROFILE%%\anaconda3\Scripts\activate.bat" call "%%USERPROFILE%%\anaconda3\Scripts\activate.bat"
echo if exist "%%USERPROFILE%%\miniconda3\Scripts\activate.bat" call "%%USERPROFILE%%\miniconda3\Scripts\activate.bat"
echo cd /d "%%~dp0"
echo python -m streamlit run src/litman/gui.py
echo if errorlevel 1 pause
) > "%USERPROFILE%\precam\litman\litman.bat"

:: Create desktop shortcut (.lnk) with book icon
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\litman.lnk'); $sc.TargetPath = [Environment]::GetFolderPath('UserProfile') + '\precam\litman\litman.bat'; $sc.WorkingDirectory = [Environment]::GetFolderPath('UserProfile') + '\precam\litman'; $sc.IconLocation = [Environment]::GetFolderPath('UserProfile') + '\precam\litman\assets\book.ico,0'; $sc.Description = 'litman - Literature Manager'; $sc.Save()"

echo   Desktop shortcut created: litman.lnk (book icon)
echo.

:: ── Done ─────────────────────────────────────────────────────
echo ============================================================
echo   Installation complete!
echo ============================================================
echo.
echo   To launch litman:
echo     Double-click the "litman" icon on your Desktop
echo     Browser will open automatically at http://localhost:8501
echo.
echo   First time: Go to Sync page and click "Pull from GitHub"
echo.
pause
