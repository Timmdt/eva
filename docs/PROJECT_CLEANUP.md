# EVA · Projektbereinigung

Stand: 31. Oktober 2026 (UTC).

## Ergebnis

Der gepflegte Projektcode, Tests, Dienstvorlagen, Desktop-Assets und Anleitungen
wurden auf Syntax, Imports, Altdateien, Duplikate und überholte Verweise geprüft.
54 alte oder doppelte Dateien wurden entfernt beziehungsweise ausgelagert.
Der Quellprojektbestand einschließlich Auslieferungsdateien schrumpfte von
153.9 MB auf etwa 55.6 MB; virtuelle Umgebungen,
Git-Historie und lokale Laufzeitdaten sind dabei jeweils ausgenommen.
Die Sicherung liegt außerhalb des Projekts und benötigt zusätzlich Speicherplatz.

- Nicht mehr eingebundene EVA-Kopie, alter Decision-/Context-/Suchquery-Code,
  provisorische Einstiege, CPU/RAM-Dauerschleife und leere Platzhalter entfernt.
- Die aktuellen Einstiege nutzen dieselbe CLI-Start-/Abschaltlogik. Bei Exit,
  Strg+C, Eingabeende und Streamfehler wird EVA genau einmal geschlossen.
  Die doppelte Reflection nach Strg+C entfällt.
- Der weiterhin unterstützte JSON-RAG-Fallback liegt jetzt in `rag/json_store.py`.
  Das ehemalige RAG-Textbeispiel bleibt als lokale Datei unter
  `data/documents/legacy-rag-example.txt` erhalten.
- Doppelte Modulkonfiguration, ungenutzte Einstellungen/Imports und die nicht
  mehr direkt benötigte `tqdm`-Anforderung entfernt. Installierte Pakete wurden
  nicht deinstalliert; andere Bibliotheken können sie weiterhin benötigen.
- Python-Code einheitlich formatiert; Ruff-Konfiguration und separate
  Entwicklungsabhängigkeiten unter `requirements-dev.txt` ergänzt.
- Verworfene Charakterentwürfe, alte NOVA-Starter/-Pakete, historische
  Körperatlas-Zwischenstände und identische Bildkopien aus dem Projekt entfernt.
  Die 17 Desktop-Zustände teilen sich zehn unveränderte Original-Körperbilder.
- Das Atlas-Werkzeug schützt die aktuell eingebundenen Original-PNGs vor
  versehentlichem Überschreiben. Ausdrucksporträts und ihre Quelle bleiben erhalten.
- Entwicklungstranskripte und Debug-Log archiviert; reproduzierbare Python- und
  Ruff-Caches entfernt. Installations-/Entwickleranleitungen aktualisiert.
- Modultests verwenden temporäre Speicherdateien und isolierte RAG-/Voice-Objekte.
  Sie greifen nicht mehr auf den persönlichen Gesprächsspeicher zu.

## Validierung

- Gesamte Suite: **124 Tests erfolgreich, keine übersprungenen Tests**;
  Server, RAG, Routing, Memory-Kontext, Stimme, Desktop, HTTP-Streaming und
  die neuen Abschalt-/Originalbildschutz-Prüfungen eingeschlossen.
- `ruff check .` und `ruff format --check .` erfolgreich.
- Interne Python-Importpfade vollständig auf vorhandene Ziele geprüft.
- `node --check interfaces/web/app.js` und `git diff --check` erfolgreich.
- Die Gesprächs-/Routingprompts und alle Original-Körperbilder wurden gegen
  den vorherigen Stand beziehungsweise ihre ursprünglichen Prüfsummen geprüft.
- Vor und nach der normalen Testsuite waren `.env`, `memory/state.json` und
  `memory/memory.json` identisch.
- Bereinigtes `dist/EVA-Windows.zip`: 44 Dateien, etwa
  25.5 MB. ZIP-Prüfsummen,
  erlaubte Dateiliste und die Original-Prüfsummen sämtlicher Posen geprüft.
- Die laufende EVA-Bridge ist weiterhin erreichbar und verwendet unverändert
  `qwen3:4b-instruct-2507-q4_K_M` für Chat und
  `qwen3-vl:2b-instruct-q4_K_M` für Bilder.

Die GUI-Prüfungen laufen mit Qt im Linux-Offscreen-Modus. Ein zusätzlicher
Test auf dem Windows-Haupt-PC wurde in diesem Durchlauf nicht durchgeführt.

## Sicherung

Vor dem ersten Löschen wurden Quellcode und Löschkandidaten außerhalb des
Projekts gesichert (203 Dateien; Archiv und Prüfsummenmanifest nur für den
Benutzer lesbar):

- Archiv: `/home/kati/opt/eva-backups/cleanup-20261031T234208Z.tar.gz`
- Manifest: `/home/kati/opt/eva-backups/cleanup-20261031T234208Z.manifest.json`

Das Archiv enthält auch die originale `eva.zip`, vorherige Entwürfe und die
alten Auslieferungspakete. Die entfernten leeren Platzhalter enthalten keine
wiederherzustellenden Daten. Persönliche Konfiguration, Datenbank, Erinnerungen,
Stimmdaten, Modelle und Python-Umgebungen wurden nicht gelöscht.

Einzelne Dateien lassen sich bei Bedarf beispielsweise so zurückholen:

```bash
tar -xzf /home/kati/opt/eva-backups/cleanup-20261031T234208Z.tar.gz -C /home/kati/opt/eva core/eva_old.py
```

## Entfernte oder verlagerte Pfade

- `actions/action_router.py`
- `actions/device_actions.py`
- `actions/service_actions.py`
- `actions/system_actions.py`
- `assets/character/poses/alert.png`
- `assets/character/poses/falling_asleep.png`
- `assets/character/poses/rising.png`
- `assets/character/poses/sitting_down.png`
- `assets/character/poses/thinking.png`
- `assets/references/eva-idle-knees-up-extracted.png`
- `assets/references/eva-poses-before-originals.zip`
- `assets/references/eva-poses-extracted.png`
- `assets/references/eva-standing-extracted.png`
- `core/context_builder.py`
- `core/decision.py`
- `core/eva_old.py`
- `core/run.py`
- `core/scheduler.py`
- `core/state.py`
- `core/test.py`
- `debug.log`
- `desktop_agent/assets/EVA_CHARACTER.md`
- `desktop_agent/assets/EVA_CHARACTER_ANIME.md`
- `desktop_agent/assets/EVA_CHARACTER_CREATURE.md`
- `desktop_agent/assets/EVA_CHARACTER_ROBOT_V1.md`
- `desktop_agent/assets/NOVA_CHARACTER.md`
- `desktop_agent/assets/eva-anime.png`
- `desktop_agent/assets/eva-creature.png`
- `desktop_agent/assets/eva-robot-feminine.png`
- `desktop_agent/assets/eva-robot.png`
- `desktop_agent/assets/nova.png`
- `dist/EVA-Sitzposen-Vorschau.png`
- `dist/NOVA-Windows.zip`
- `eva.zip`
- `interfaces/api_server.py`
- `interfaces/cli.py`
- `memory/session_hisotry.json`
- `mind/base_ai.py`
- `mind/intennt_ai.py`
- `mind/memory_ai.py`
- `mind/planning_ai.py`
- `mind/reflection.py`
- `module/module.py`
- `module/search_query_llm.py`
- `perception/audio.py`
- `perception/text.py`
- `perception/vivison.py`
- `rollout-2026-08-28T14-49-04-01a048d8-85b7-7a63-83db-e3ed6c66f613.jsonl`
- `start_nova.cmd`
- `start_nova_debug.cmd`
- `tools/logger.py`
- `tools/package_nova.py`
- `yui/RAG_Creator.py`
- `yui/test.txt`
