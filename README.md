# ha-dwarf-mini

Home Assistant Integration für das [DwarfLab DWARF mini](https://www.dwarflab.com/us/products/dwarf-mini-smart-telescope) Smart Telescope im heimischen WLAN.

**Status:** in Entwicklung (v1).

## Unterstützte Entities (v1)

- `binary_sensor` Verbindungsstatus
- `sensor` Batteriestand (%)
- `sensor` Aufnahmestatus (idle/running/stopping/stopped) mit Fortschritts-Attributen
- `button` Aufnahme starten / stoppen

Nicht enthalten (siehe [Design-Dokument](../ha-dwarf-mini-notes) für Details, warum):
Speicherplatz, Ladestatus, Live-View, GoTo/Kalibrierung/Tracking, Fokus.

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
