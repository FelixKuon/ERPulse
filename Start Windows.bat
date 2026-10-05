@echo off
rem Doppelklick startet den ERP Viewer (Windows).
rem Beim ersten Start wird automatisch eine virtuelle Umgebung angelegt.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Erster Start: lege virtuelle Umgebung an und installiere Pakete ...
    py -3 -m venv .venv || python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt || goto :fehler
)

.venv\Scripts\python.exe app.py
if errorlevel 1 goto :fehler
goto :ende

:fehler
echo.
echo Es ist ein Fehler aufgetreten - siehe Meldungen oben.
:ende
pause
