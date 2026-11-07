# Grid Peak Guard

*English: [README.md](README.md)*

Home-Assistant-Custom-Integration, die den **gemittelten Netzbezug je Messfenster** (Standard 15 Minuten) unter einem Ziel hält. Gedacht für leistungsbasierte Netzentgelte (z. B. Österreich ab 2027), nutzbar in allen Ländern und mit allen Geräten, die Home Assistant steuern kann.

## Funktionsweise

- **Hochrechnung** alle paar Sekunden: bisherige Fensterenergie + (aktueller Bezug + erwartete Zusatzlast) × Restzeit.
- **Wirksames Limit** = max(Ziel, verrechnete Mindestleistung, bisheriger Monats-Peak) – unter einen bereits verrechneten Peak zu regeln spart nichts.
- **Eskalation** nach Priorität, eine Stufe pro Wartezeit: Speicher (10) → Wallbox (20) → modulierender Verbraucher (25) → schaltbarer Verbraucher / Haushaltsgerät (30) → Wärmepumpe (35). An der **harten Grenze** (Limit + Abstand) werden alle Stufen sofort aktiviert.
- **Fensterende:** Jeder Eingriff wird aus einem persistierten Snapshot zurückgesetzt – auch nach einem Neustart, beim Entladen und beim Ausschalten der Steuerung.
- **Simulationsmodus** (standardmäßig an): Entscheidungen werden nur protokolliert und als Event `grid_peak_guard_action` gemeldet; kein Gerät wird verändert.

## Gerätekategorien

| Kategorie | Eingriff | Schutz |
|---|---|---|
| Speicher | Number/Select/Schalter setzen (z. B. Netzladen stoppen) | Mindest-Ladezustand |
| Wallbox | Ladestrom senken oder pausieren | nur während des Ladens |
| Modulierend | niedrigeren Sollwert/Leistungsstufe setzen | – |
| Schaltbar | ausschalten | nur bei Verbrauch, maximale Ausschaltdauer |
| Wärmepumpe | EVU-Sperrkontakt, SG-Ready oder Sollwert – optional | Mindestlaufzeit, max. Sperrdauer, max. Sperrzeit/Tag, Mindestpause |
| Haushaltsgerät | **nur Start verzögern**, nie unterbrechen | erst nach Ruhezeit, maximale Verzögerung |
| Beobachten | keiner | – |

Wärmepumpen lernen ihre Startzeiten je Stunde und Außentemperatur-Band (kalt < 2 °C ≤ mild < 12 °C ≤ warm), liefern den nächsten erwarteten Start und die Startwahrscheinlichkeit und können Budget für einen erwarteten Start reservieren. Ein externer Startzeitpunkt hat Vorrang.

Konkrete Gerätemodelle sind JSON-Profile in `custom_components/grid_peak_guard/profiles/<kategorie>/` mit Standardwerten und Entitätsvorschlägen – neue Modelle brauchen keinen Code.

## Installation

Siehe [docs/de/installation.md](docs/de/installation.md). Erfordert Home Assistant 2025.8 oder neuer.

## Sicherheit

Das Steuern von Speichern, Wallboxen, Wärmepumpen und Haushaltsgeräten kann Nebenwirkungen haben. Im Simulationsmodus starten, Events und Sensoren einige Tage prüfen und erst dann den Simulationsmodus ausschalten.

## Mitmachen

Siehe [CONTRIBUTING.md](CONTRIBUTING.md). Lizenz: [MIT](LICENSE).
