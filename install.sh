#!/bin/bash
# Kontor einrichten oder aktualisieren -- jederzeit wiederholbar (idempotent).
# Richtet den Dienst als Hintergrundprogramm ein (startet beim Anmelden, laeuft dauerhaft),
# uebersetzt den Touch-ID-Helfer und oeffnet die Oberflaeche. Einstellungen und Daten bleiben erhalten.
# Aufruf:  bash install.sh      (im Programmordner, z. B. ~/Kontor)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
if [ "$(uname)" != "Darwin" ]; then echo "Kontor laeuft nur unter macOS (MoneyMoney)."; exit 1; fi
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Die Kommandozeilen-Werkzeuge fehlen (python3, swiftc). Installation wird angestossen -- danach bitte install.sh erneut ausfuehren."
  xcode-select --install || true
  exit 1
fi
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then echo "python3 nicht gefunden."; exit 1; fi
"$PY" - <<'PYCHK' || { echo "Python 3.9 oder neuer wird gebraucht."; exit 1; }
import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)
PYCHK
if ! pgrep -x MoneyMoney >/dev/null 2>&1; then
  echo "Hinweis: MoneyMoney laeuft gerade nicht -- Kontor wartet, bis es geoeffnet und entsperrt ist."
fi
chmod +x "$HERE/kontor.py" "$HERE/install.sh" "$HERE"/*.command 2>/dev/null || true
# Quarantaene-Attribut (Download aus dem Browser) entfernen, sonst blockiert Gatekeeper den Doppelklick auf *.command
xattr -dr com.apple.quarantine "$HERE" 2>/dev/null || true
echo "Python: $PY ($("$PY" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'))  Kontor $(cat "$HERE/VERSION")"
"$PY" "$HERE/kontor.py" install
sleep 2
"$PY" "$HERE/kontor.py" open || true
cat <<TXT

Fertig. Die Oberflaeche laeuft dauerhaft unter http://127.0.0.1:8765/  (python3 kontor.py open)
Erster Schritt dort: Passwort festlegen, dann der Einrichtungsassistent.
Beim ersten Zugriff fragt macOS, ob das Programm MoneyMoney steuern darf -- bitte erlauben.
Datenordner (verschluesselt): ~/Library/Application Support/Kontor
TXT
