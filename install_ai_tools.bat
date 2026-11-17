@echo off
cd /d "%~dp0"
echo Installing AI tools (Python, Node.js, Claude Code, Codex)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_ai_tools.ps1"
echo.
pause
