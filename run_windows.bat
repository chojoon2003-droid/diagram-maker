@echo off
cd /d "%~dp0"

rem ---- find a real Python (the Microsoft Store "python" stub only prints "Python") ----
if defined PY goto HAVEPY
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY ( python -c "import sys" >nul 2>nul && set "PY=python" )
if not defined PY goto NOPY
:HAVEPY

if "%1"=="min" goto RUN

echo Using: %PY%
rem Install packages only when requirements.txt changed since the last successful install (fast start)
%PY% -c "import hashlib,pathlib,sys;h=hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest();p=pathlib.Path('.installed');sys.exit(0 if p.exists() and p.read_text().strip()==h else 1)"
if errorlevel 1 (
  echo Installing packages... ^(only after an update - may take a few minutes^)
  %PY% -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [!] Package install failed. Please send a screenshot of this window.
    pause
    exit /b
  )
  %PY% -c "import hashlib,pathlib;pathlib.Path('.installed').write_text(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest())"
)

rem Relaunch minimized so the console stays out of the way
start "Arch Image Agent (close this window to stop)" /min cmd /c ""%~f0" min"
exit /b

:RUN
rem launch.py starts the app and opens it in Chrome (or the default browser)
%PY% launch.py
if errorlevel 1 pause
exit /b

:NOPY
echo.
echo [!] Python is not installed (only the Microsoft Store shortcut was found).
echo.
echo  1. Install Python from https://www.python.org/downloads/
echo     On the first screen, CHECK "Add python.exe to PATH", then "Install Now".
echo  2. (If it still fails) Windows Settings - Apps - Advanced app settings
echo     - App execution aliases: turn OFF "python.exe" and "python3.exe".
echo  3. Run Arch Image Agent again.
echo.
start "" https://www.python.org/downloads/
pause
exit /b
