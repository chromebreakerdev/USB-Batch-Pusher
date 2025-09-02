@echo off
setlocal EnableDelayedExpansion

echo =====================================
echo   USB Batch Pusher - Auto Build EXE
echo =====================================
echo.

REM ---------- 0) Go to the script directory ----------
pushd %~dp0

REM ---------- 1) Find Python (python or py) ----------
set "PYEXE="
where python >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE (
  where py >nul 2>&1 && set "PYEXE=py"
)

REM ---------- 2) If no Python, try Winget ----------
if not defined PYEXE (
  echo [*] Python not found. Attempting install via Winget...
  where winget >nul 2>&1
  if not errorlevel 1 (
    winget install -e --id Python.Python.3 -h --accept-package-agreements --accept-source-agreements
  ) else (
    echo [!] Winget is not available. Will download the Python installer instead.
  )
)

REM After Winget attempt, check again
if not defined PYEXE (
  where python >nul 2>&1 && set "PYEXE=python"
  if not defined PYEXE where py >nul 2>&1 && set "PYEXE=py"
)

REM ---------- 3) If still no Python, download installer ----------
if not defined PYEXE (
  echo [*] Downloading official Python for Windows (x64)...
  set "PY_VER=3.12.5"
  set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-amd64.exe"
  set "TMP_EXE=%TEMP%\python-installer-%RANDOM%.exe"
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try {Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%TMP_EXE%'; exit 0} catch {exit 1}"
  if errorlevel 1 (
    echo [!] Could not download Python installer. Please install Python manually and re-run.
    echo     https://www.python.org/downloads/windows/
    pause
    exit /b 1
  )

  echo [*] Installing Python silently (this may take a minute)...
  "%TMP_EXE%" /quiet PrependPath=1 Include_pip=1 Shortcuts=0
  set "TMP_EXE="
  REM give PATH a moment to refresh
  timeout /t 8 >nul

  REM try to locate python again (common per-user path)
  if not defined PYEXE (
    for /f "delims=" %%P in ('where python 2^>nul') do set "PYEXE=python"
  )
  if not defined PYEXE (
    for /f "delims=" %%P in ('where py 2^>nul') do set "PYEXE=py"
  )

  if not defined PYEXE (
    echo [!] Python still not found in PATH after install.
    echo     Close this window, open a NEW Command Prompt, and run build_exe.bat again.
    pause
    exit /b 1
  )
)

echo [OK] Using Python launcher: %PYEXE%
echo.

REM ---------- 4) Ensure pip works and install PyInstaller ----------
echo [*] Upgrading pip...
%PYEXE% -m pip install --upgrade pip

echo [*] Ensuring PyInstaller is installed...
%PYEXE% -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
  %PYEXE% -m pip install pyinstaller
)

REM ---------- 5) Build EXE ----------
if not exist "usb_batch_pusher.py" (
  echo [!] Could not find usb_batch_pusher.py in this folder:
  echo     %cd%
  pause
  exit /b 1
)

echo [*] Building exe with PyInstaller...
%PYEXE% -m PyInstaller --noconfirm --onefile --windowed usb_batch_pusher.py

if not exist "dist\usb_batch_pusher.exe" (
  echo [!] Build failed. Check the messages above for errors.
  pause
  exit /b 1
)

REM ---------- 6) Move EXE to project root and clean ----------
echo [*] Moving exe to project root...
copy /y "dist\usb_batch_pusher.exe" ".\usb_batch_pusher.exe" >nul

echo [*] Cleaning up build files...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q usb_batch_pusher.spec 2>nul

echo.
echo ✅ Build complete!
echo    Your exe is here:
echo    %cd%\usb_batch_pusher.exe
echo.
pause
endlocal
