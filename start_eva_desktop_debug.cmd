@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-eva-desktop\Scripts\python.exe" (
    echo Bitte zuerst start_eva_desktop.cmd ausfuehren.
    pause
    exit /b 1
)
".venv-eva-desktop\Scripts\python.exe" -m desktop_agent.companion
pause
