# ha-dwarf-mini

Home Assistant Integration für das [DwarfLab DWARF mini](https://www.dwarflab.com/us/products/dwarf-mini-smart-telescope) Smart Telescope im heimischen WLAN.

**Status:** v1 + Phase 2 (Live-View, GoTo, Fokus) — in Entwicklung, Phase 2 noch nicht gegen echte Hardware getestet.

## Unterstützte Entities

- `binary_sensor` Verbindungsstatus
- `binary_sensor` Tracking
- `sensor` Batteriestand (%)
- `sensor` Aufnahmestatus (idle/running/stopping/stopped) mit Fortschritts-Attributen
- `sensor` Fokusposition
- `sensor` GoTo-Status (idle/running/stopping/stopped) mit Zielname-Attribut
- `button` Aufnahme starten / stoppen
- `button` GoTo stoppen
- `button` Autofokus
- `camera` Live-View Tele / Weitwinkel (RTSP über HAs eingebaute `stream`-Komponente)
- `select` GoTo-Ziel (fest hinterlegte DSOs sowie Sonne/Mond/Planeten über den
  experimentellen Solar-System-Pfad, siehe unten)
- Dienst `dwarf_mini.goto_coordinates` — GoTo zu einem beliebigen RA/Dec-Ziel
  (für Automationen/Skripte), nutzt denselben verifizierten DSO-Pfad wie das
  `select`

Nicht enthalten (noch offen, siehe interne Design-Notizen):
Speicherplatz- und Ladestatus-Sensoren (Payload-Format noch unbekannt, braucht
Live-Investigation).

**Hinweis Solar-System-GoTo (Sonne/Mond/Planeten):** Dieser Pfad
(`ReqOneClickGotoSolarSystem`) ist **experimentell und unverifiziert** — er
wurde nie gegen echte Hardware getestet, nur die Nachrichtenstruktur ist aus
den Protokollquellen bekannt. Die betroffenen Optionen im `select`-Dropdown
sind entsprechend mit „(experimentell)“ gekennzeichnet. Ein fehlerhaft
kodiertes GoTo auf die Sonne ist potenziell ein Risiko für die Optik/den
Sensor, nicht nur kosmetisch — vor produktivem Einsatz gegen echte Hardware
verifizieren.

## Installation

Über HACS als Custom Repository (`https://github.com/Xunil99/ha-dwarf-mini`,
Kategorie „Integration“) oder manuell nach `<config>/custom_components/dwarf_mini`
kopieren.

## Konfiguration

Einstellungen → Geräte & Dienste → Integration hinzufügen → „DWARF mini“ → IP-Adresse
des Geräts im WLAN eingeben.

## Attribution

Diese Integration portiert Protokoll-Wissen (Protobuf-Nachrichten, WebSocket-Envelope)
aus [dwarfAlp](https://github.com/acocalypso/dwarfAlp) von acocalypso, lizenziert unter
GPLv3. Daher steht auch dieses Repository unter GPLv3 (siehe [LICENSE](LICENSE)).

## Lizenz

[GPLv3](LICENSE)
