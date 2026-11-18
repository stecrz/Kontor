#!/bin/bash
# Kontor entfernen (Doppelklick): Hintergrunddienst, Einstellungen, Daten, Protokoll und Datenschluessel -- auf Wunsch auch
# diesen Programmordner. Belege im Belegordner und MoneyMoney bleiben unangetastet. Dasselbe wie in Kontor unter
# Einstellungen -> Sicherung -> Deinstallieren.
cd "$(dirname "$0")"
read -r -p "Auch den Programmordner $(pwd) loeschen? [j/N] " P
if [ "$P" = "j" ] || [ "$P" = "J" ]; then
  python3 ./kontor.py --quiet uninstall --program
else
  python3 ./kontor.py --quiet uninstall
fi
read -r -p "Fenster mit Eingabetaste schliessen." _
