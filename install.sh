#!/bin/bash
# Kontor installieren oder aktualisieren (macOS) -- eine Zeile im Terminal:
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/stecrz/Kontor/main/install.sh)
#
# Laedt Kontor nach ~/Applications/Kontor (der Programme-Ordner des Benutzers; git, ohne git als ZIP), richtet den Hintergrunddienst ein (startet beim Anmelden),
# uebersetzt den Touch-ID-Helfer, baut Kontors eigene App (Kontor.app) und oeffnet sie. Jederzeit wiederholbar; Einstellungen und Daten bleiben.
# Im Programmordner aufgerufen (bash install.sh) wird nichts geladen, nur eingerichtet.
# Variablen: KONTOR_HOME (Zielordner), KONTOR_REPO (Standard stecrz/Kontor), KONTOR_REF (Zweig, Standard main).
set -euo pipefail
if [ "$(uname)" != "Darwin" ]; then echo "Kontor laeuft nur unter macOS (MoneyMoney)."; exit 1; fi
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Die Kommandozeilen-Werkzeuge von Apple fehlen (python3, git, swiftc)."
  echo "Im Fenster von macOS bitte \"Installieren\" waehlen -- danach geht es hier von selbst weiter (abbrechen mit ctrl-C)."
  xcode-select --install || true
  until xcode-select -p >/dev/null 2>&1 && [ -x "$(xcode-select -p)/usr/bin/git" ]; do sleep 5; done
fi

SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$SELF" ] && [ -f "$SELF/kontor.py" ] && [ -f "$SELF/service.py" ]; then
  DIR="$SELF"                                   # im Programmordner aufgerufen
else
  REPO="${KONTOR_REPO:-stecrz/Kontor}"
  DIR="${KONTOR_HOME:-$HOME/Applications/Kontor}"
  mkdir -p "$(dirname "$DIR")"
  REF="${KONTOR_REF:-main}"
  if [ -d "$DIR/.git" ]; then
    echo "Aktualisiere $DIR ..."
    git -C "$DIR" fetch --quiet origin
    git -C "$DIR" checkout --quiet "$REF" 2>/dev/null || true
    git -C "$DIR" reset --hard --quiet "origin/$REF"
  else
    echo "Lade $REPO nach $DIR ..."
    git clone --quiet --depth 1 --branch "$REF" "https://github.com/$REPO.git" "$DIR"
  fi
fi
cd "$DIR"
# Quarantaene-Attribut (Download aus dem Browser) entfernen, sonst blockiert Gatekeeper den Doppelklick auf *.command
xattr -dr com.apple.quarantine "$DIR" 2>/dev/null || true
chmod +x "$DIR/kontor.py" "$DIR/install.sh" "$DIR"/*.command 2>/dev/null || true

PY="$(command -v python3 || true)"
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "Python 3.9 oder neuer wird gebraucht (kommt mit den Kommandozeilen-Werkzeugen von Apple)."; exit 1
fi
if ! pgrep -x MoneyMoney >/dev/null 2>&1; then
  echo "Hinweis: MoneyMoney laeuft gerade nicht -- Kontor wartet, bis es geoeffnet und entsperrt ist."
fi
echo "Kontor $(cat VERSION) in $DIR (Python $("$PY" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'))"
"$PY" kontor.py install
"$PY" kontor.py open || true
cat <<TXT

Fertig. Kontor laeuft dauerhaft unter http://127.0.0.1:8765/
Dort zuerst ein Passwort festlegen, dann fuehrt die Einrichtung Schritt fuer Schritt weiter.
Kontor als eigene App: Kontor.app im Programmordner (oeffnet sich jetzt) -- im Dock: rechte Maustaste, Optionen -> Im Dock behalten.
Fragt macOS, ob Kontor MoneyMoney steuern darf: bitte erlauben.
Entfernen: Doppelklick auf Uninstall.command im Programmordner (oder in Kontor unter Einstellungen -> Sicherung).
TXT
