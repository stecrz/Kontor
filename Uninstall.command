#!/bin/bash
# Entfernt den Dienst. Daten und Belege bleiben, sofern nicht gewuenscht.
cd "$(dirname "$0")"
python3 ./kontor.py uninstall
DATA="$HOME/Library/Application Support/Kontor"
read -r -p "Datenordner ($DATA) und Datenschluessel im Schluesselbund ebenfalls loeschen? [j/N] " ANS
if [ "$ANS" = "j" ] || [ "$ANS" = "J" ]; then
  rm -rf "$DATA"
  security delete-generic-password -s kontor.datenschluessel -a kontor >/dev/null 2>&1 || true
  echo "Datenordner und Schluessel geloescht. Belege im Belegordner (Standard ~/Documents/Kontor-Belege) bleiben."
fi
echo "Programmordner kann jetzt in den Papierkorb."
read -r -p "Fenster mit Eingabetaste schliessen." _
