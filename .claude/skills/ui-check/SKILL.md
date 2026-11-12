---
name: ui-check
description: Kontors Oberfläche mit erfundenen Daten im Browser ansehen – hell und dunkel, MacBook und iPhone – und nach Apples Human Interface Guidelines prüfen. Bei jeder sichtbaren Änderung verwenden.
---

# Oberfläche prüfen

1. Bilder erzeugen (simuliertes MoneyMoney, erfundene Daten):
   `python3 tests/preview.py <scratch-ordner>/ui '#bookings' '#rules'` – ohne Seiten: alle Hauptseiten.
   Optionen: `--lang en`, `--nur dunkel`, `--nur mac`. Für Zustände (Dialoge, aufgeklappte Abschnitte) das Skript als
   Vorlage nehmen und mit Playwright klicken.
2. Jedes Bild mit Read ansehen. Prüfen:
   - Hierarchie: ein Seitentitel, klare Abschnitte, das Wichtigste oben; nichts doppelt.
   - Dunkelmodus gut lesbar (Kontrast, keine Pastelltöne), heller Modus ebenso.
   - Ausrichtung und Abstände; Zahlen rechtsbündig, negative rot; lange Namen und große Beträge brechen sauber um.
   - iPhone: nichts abgeschnitten, keine waagrechte Scrollleiste, Bedienelemente groß genug.
   - Zustände: leer, lädt, Fehler, sehr viele Einträge.
   - Texte: Deutsch kurz und ohne Fachbegriffe, Einzahl/Mehrzahl, Englisch vorhanden; keine Erklärtexte, die schon im Tooltip oder in der Hilfe stehen.
   - Bedienung: bekannte Muster und Kürzel (⌘S speichert, Esc schließt, Enter bestätigt).
3. Fehler beheben und erneut ansehen, bis nichts mehr auffällt.
