@echo off
cd /d "%~dp0"
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY ( python -c "import sys" >nul 2>nul && set "PY=python" )
if not defined PY (
  echo [!] Python not found. Run install_ai_tools.bat first.
  pause
  exit /b
)
echo Starting Claude Code connection tester... (close this window to stop)
%PY% claude_test_launch.py
pause
