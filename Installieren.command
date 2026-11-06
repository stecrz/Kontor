#!/bin/bash
# Doppelklick-Installation. Falls macOS das Oeffnen blockiert (Quarantaene nach Download): im Terminal  bash install.sh
cd "$(dirname "$0")"
bash ./install.sh
echo
read -r -p "Fenster mit Eingabetaste schliessen." _
