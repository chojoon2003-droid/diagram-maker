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
echo Checking packages... (first time takes 1-2 minutes)
%PY% -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo [!] Package install failed. Please send a screenshot of this window.
  pause
  exit /b
)

rem Relaunch minimized so the console stays out of the way
start "Diagram Agent (close this window to stop)" /min cmd /c ""%~f0" min"
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
echo  3. Run Diagram Agent again.
echo.
start "" https://www.python.org/downloads/
pause
exit /b
