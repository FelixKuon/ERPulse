#!/bin/bash
# Doppelklick startet den ERP Viewer (macOS). Beim ersten Start wird
# automatisch eine virtuelle Umgebung angelegt.

cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
    echo "Erster Start: lege virtuelle Umgebung an und installiere Pakete ..."
    python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt || {
        read -p "Installation fehlgeschlagen — Enter zum Schließen ..."; exit 1; }
fi

.venv/bin/python app.py
status=$?
echo ""
[ $status -ne 0 ] && echo "Fehler (Code $status) — siehe Meldungen oben." || echo "Anwendung beendet."
read -p "Fenster mit Enter schließen..."
