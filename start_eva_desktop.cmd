@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-eva-desktop\eva-desktop-ready" if exist ".venv-eva-desktop\Scripts\pythonw.exe" goto launch
where py >nul 2>nul
if errorlevel 1 (
    echo Python 3.11 oder neuer fehlt. Bitte von https://www.python.org/downloads/windows/ installieren.
    pause
    exit /b 1
)
py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 11))"
if errorlevel 1 (
    echo EVA benoetigt Python 3.11 oder neuer.
    pause
    exit /b 1
)
py -3 -m venv .venv-eva-desktop
if errorlevel 1 goto failed
".venv-eva-desktop\Scripts\python.exe" -m pip install -r requirements-desktop.txt
if errorlevel 1 goto failed
type nul > ".venv-eva-desktop\eva-desktop-ready"
:launch
".venv-eva-desktop\Scripts\pythonw.exe" -m desktop_agent.companion
exit /b 0
:failed
echo Installation fehlgeschlagen. start_eva_desktop.cmd nach Beheben des Fehlers erneut starten.
pause
exit /b 1
