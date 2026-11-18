#!/bin/bash
# Kontor mit einer Zeile installieren oder aktualisieren (macOS, Terminal):
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/stecrz/Kontor/main/get.sh)
#
# Laedt das Repo nach ~/Kontor (git clone bzw. git pull; ohne git als ZIP), entfernt das
# Quarantaene-Attribut und ruft install.sh auf (Dienst einrichten, Oberflaeche oeffnen).
# Einstellungen und Daten (~/Library/Application Support/Kontor) bleiben unangetastet.
# Variablen: KONTOR_HOME (Zielordner), KONTOR_REPO (Repo, Standard stecrz/Kontor), KONTOR_REF (Zweig/Tag, Standard main).
set -euo pipefail
REPO="${KONTOR_REPO:-stecrz/Kontor}"
DIR="${KONTOR_HOME:-$HOME/Kontor}"
REF="${KONTOR_REF:-main}"
if [ "$(uname)" != "Darwin" ]; then echo "Kontor laeuft nur unter macOS (MoneyMoney)."; exit 1; fi
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Die Kommandozeilen-Werkzeuge von Apple fehlen (python3, git, swiftc)."
  echo "Im Fenster von macOS bitte \"Installieren\" waehlen -- danach geht es hier von selbst weiter."
  xcode-select --install || true
  echo "(Warte auf die Installation -- abbrechen mit ctrl-C.)"
  until xcode-select -p >/dev/null 2>&1 && [ -x "$(xcode-select -p)/usr/bin/git" ]; do sleep 5; done
  echo "Kommandozeilen-Werkzeuge sind da."
fi
if [ -d "$DIR/.git" ]; then
  echo "Aktualisiere $DIR ..."
  git -C "$DIR" fetch --quiet origin
  git -C "$DIR" checkout --quiet "$REF" 2>/dev/null || true
  git -C "$DIR" pull --ff-only --quiet origin "$REF" 2>/dev/null || git -C "$DIR" reset --hard "origin/$REF" --quiet
elif command -v git >/dev/null 2>&1; then
  echo "Lade $REPO nach $DIR ..."
  git clone --quiet --branch "$REF" "https://github.com/$REPO.git" "$DIR"
else
  echo "Lade $REPO als ZIP nach $DIR ..."
  TMP="$(mktemp -d)"
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/$REF.zip" -o "$TMP/kontor.zip"
  ditto -x -k "$TMP/kontor.zip" "$TMP/x"
  SRC="$(find "$TMP/x" -maxdepth 1 -mindepth 1 -type d | head -1)"
  mkdir -p "$DIR"
  ditto "$SRC" "$DIR"
  rm -rf "$TMP"
fi
xattr -dr com.apple.quarantine "$DIR" 2>/dev/null || true
cd "$DIR"
exec bash install.sh
