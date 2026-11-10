@echo off
cd /d "%~dp0"
py -3 -c "import sys" >nul 2>nul && (py -3 claude_login_chrome.py & exit /b)
python claude_login_chrome.py
