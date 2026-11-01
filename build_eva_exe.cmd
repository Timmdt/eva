@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-eva-desktop\Scripts\python.exe" (
    echo Bitte zuerst start_eva_desktop.cmd ausfuehren.
    pause
    exit /b 1
)
".venv-eva-desktop\Scripts\python.exe" -m pip install "pyinstaller>=6,<7"
if errorlevel 1 goto failed
".venv-eva-desktop\Scripts\python.exe" -m PyInstaller --noconfirm deployment\eva_desktop.spec
if errorlevel 1 goto failed
echo Fertig: dist\EVA Desktop Agent\EVA Desktop Agent.exe
pause
exit /b 0
:failed
echo EXE-Build fehlgeschlagen. Fehlermeldung pruefen.
pause
exit /b 1
