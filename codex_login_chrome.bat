@echo off
cd /d "%~dp0"
py -3 -c "import sys" >nul 2>nul && (py -3 codex_login_chrome.py & exit /b)
python codex_login_chrome.py
