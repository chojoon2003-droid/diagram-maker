@echo off
cd /d "%~dp0"
if exist "%USERPROFILE%\Desktop\Diagram Agent.lnk" del "%USERPROFILE%\Desktop\Diagram Agent.lnk"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Arch Image Agent.lnk'); $s.TargetPath='%~dp0run_windows.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Save()"
echo Shortcut "Arch Image Agent" created on your desktop.
pause
