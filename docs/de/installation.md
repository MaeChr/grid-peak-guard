# Installation und Einrichtung

## Voraussetzungen

- Home Assistant 2025.8 oder neuer
- Ein Sensor für die Netzleistung (W oder kW). Positiv = Bezug, negativ = Einspeisung; das Vorzeichen lässt sich in der Einrichtung umkehren.
- Optional: ein Zähler für den Netzbezug (kWh). Wenn gesetzt, wird die Fensterenergie daraus statt aus der integrierten Leistung berechnet.

## Installation über HACS

1. HACS → Drei-Punkte-Menü → **Benutzerdefinierte Repositories** → `https://github.com/MaeChr/grid-peak-guard` mit Kategorie **Integration** hinzufügen.
2. **Grid Peak Guard** installieren und Home Assistant neu starten.

Manuell: `custom_components/grid_peak_guard` in den Ordner `config/custom_components/` kopieren und neu starten.

## Einrichtung

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Grid Peak Guard.**
2. Netzleistungssensor und Ziel-Mittelleistung wählen, **Im Simulationsmodus starten** eingeschaltet lassen.
3. Über **Konfigurieren** Geräte, Tarif und allgemeine Einstellungen ergänzen.

### Allgemeine Einstellungen

| Option | Bedeutung |
|---|---|
| Ziel-Mittelleistung | Mittlerer Bezug je Fenster, der nicht überschritten werden soll |
| Verrechnete Mindestleistung | Mindestens verrechnete Leistung pro Monat (z. B. 2 kW) |
| Abstand der harten Grenze | Bei Limit + Abstand werden alle Stufen sofort aktiviert |
| Messfenster | Bei den meisten Netzbetreibern 15 Minuten |
| Wartezeit | Zeit zwischen zwei Eskalationsstufen |
| Einschwingzeit | In den ersten Sekunden eines Fensters keine Eskalation (Hochrechnung unruhig) |
| Limit auf Monats-Peak anheben | Nicht unter einen in diesem Monat bereits verrechneten Peak regeln |

### Geräte

Kategorie wählen, dann ein Modellprofil. Das Profil setzt Standardwerte und schlägt passende Entitäten vor – den Vorschlag immer prüfen. **Wert während der Reduktion** wird während eines Eingriffs auf die Steuer-Entität gesetzt (`on`/`off` bei Schaltern, eine Zahl, ein Optionstext oder eine Temperatur); der vorherige Wert wird am Fensterende wiederhergestellt.

Haushaltsgeräte (Geschirrspüler, Waschmaschine …) werden nur ausgeschaltet, wenn sie die eingestellte Zeit geruht haben – ein laufendes Programm wird nie unterbrochen. Nur mit Geräten verwenden, die einen verzögerten Start nach Stromwiederkehr beibehalten bzw. fortsetzen, oder eine „Start erlaubt“-Entität des Herstellers nutzen.

## Entitäten

- Sensoren: Hochrechnung Fenstermittel, bisheriges Fenstermittel, wirksames Limit, erforderliche Reduktion, Monats-Peak, Mittel letztes Fenster, Fensterenergie, Eskalationsstufe, monatlicher Leistungspreis, monatliche Kostenschätzung; je Wärmepumpe: nächster erwarteter Start und Startwahrscheinlichkeit.
- Binärsensoren: Limit gefährdet, Eingriff aktiv.
- Schalter: Steuerung (aus = alles zurücksetzen und anhalten), Simulationsmodus.

Jeder Eingriff löst das Event `grid_peak_guard_action` aus mit `device_id`, `name`, `category`, `action` (`reduce`/`restore`), `entity_id`, `value` und `simulation`.

## Scharf schalten

1. Einige Tage im Simulationsmodus laufen lassen und die Events mit den Erwartungen vergleichen.
2. Simulationsmodus ausschalten. Im Simulationsmodus gesetzte Eingriffe werden vorher (ohne Service-Aufrufe) zurückgesetzt.
3. Bei Auffälligkeiten den Diagnose-Download nutzen (Geräteseite → Diagnose herunterladen); Entitäts-IDs werden geschwärzt.
