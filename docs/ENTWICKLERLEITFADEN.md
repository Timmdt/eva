# EVA-Entwicklerleitfaden

Dieser Leitfaden ist der Einstiegspunkt für Änderungen am EVA-Projekt. Die Beschreibungen bleiben absichtlich kurz; Details stehen in den jeweils verlinkten Spezialdokumenten.

## 1. Wo beginnt EVA?

Der normale Startpunkt ist `main.py`. Dort werden die Umgebung geladen, EVA erstellt, Ollama und XTTS vorbereitet und anschließend Eingaben an `EVA.receive_stream()` weitergegeben.

```text
main.py
  -> EVA.__init__()
  -> EVA.warm_llm()
  -> EVA.start_voice()
  -> EVA.receive_stream(Eingabe)
```

Wenn du nur eine Stelle zuerst lesen möchtest, beginne in `main.py` und springe danach zu `core/eva.py:receive_stream`.

## 2. Anfragefluss

```text
Benutzereingabe
  -> kurze feste Antworten und direkte Module
  -> IntentRouter bestimmt die benötigte Datenquelle
  -> optional: Wikipedia, Web, Memory oder RAG
  -> Antwort wird erzeugt oder direkt aus einer Quelle übernommen
  -> Text erscheint im Terminal
  -> VoiceService bereitet den Text für XTTS auf
  -> vollständige Antwort wird in der History gespeichert
```

Wikipedia-Überblicke werden direkt aus dem deutschen Quelltext erstellt. Andere Antworten verwenden standardmäßig dasselbe lokale Gemma-Modell, damit kein zweites LLM geladen werden muss.

## 3. Projektkarte

| Pfad | Aufgabe |
|---|---|
| `main.py` | Startet EVA und enthält die Terminal-Schleife. |
| `core/eva.py` | Verbindet Routing, Modelle, Quellen, Memory und Stimme. |
| `core/intent_router.py` | Entscheidet, welche Datenquelle eine Anfrage braucht. |
| `core/config.py` | Liest die allgemeinen Einstellungen aus der Umgebung. |
| `core/env_loader.py` | Lädt `.env` sicher ohne Shell-Ausführung. |
| `module/` | Enthält direkt ansprechbare EVA-Funktionen. |
| `memory/` | Speichert Gesprächszustand und Langzeitinformationen. |
| `rag/` | Sucht Wissen in PostgreSQL und pgvector. |
| `rag/json_store.py` | Enthält den ausdrücklich aktivierbaren JSON-RAG-Fallback. |
| `module/web_search_module.py` | Ruft Websuche, Wikipedia, URLs und Wetter ab. |
| `voice/` | Enthält die aktuelle lokale XTTS-Sprachausgabe. |
| `interfaces/` | Stellt HTTP- und Presence-Schnittstellen bereit. |
| `visual_cortex/` | Verarbeitet Kamera-, Identitäts- und Präsenzdaten. |
| `desktop_agent/` | Enthält Windows-Begleiter, Server-Bridge und optionale Schreibtisch-Präsenz. |
| `tools/` | Enthält Diagnose-, Benchmark- und Importprogramme. |
| `tests/` | Prüft Verhalten ohne echte Änderungen an Geräten. |
| `docs/` | Enthält Anleitungen für die einzelnen Teilsysteme. |

## 4. Wichtige Funktionen

### `core/eva.py`

| Funktion | Kurze Erklärung |
|---|---|
| `EVA.__init__()` | Lädt Konfiguration, Zustand, Module, RAG und VoiceService. |
| `receive()` | Gibt eine vollständige Antwort als String zurück. |
| `receive_stream()` | Führt den gesamten Anfragepfad aus und liefert Textstücke sofort. |
| `_route_intent()` | Fragt den IntentRouter nach der passenden Datenquelle. |
| `_execute_intent()` | Führt die gewählte Web- oder Memory-Aktion aus. |
| `_build_messages()` | Baut den normalen Prompt für das Hauptmodell. |
| `generate_response_stream()` | Erzeugt eine Antwort als laufenden Ollama-Stream. |
| `_direct_wikipedia_response()` | Übernimmt einen kurzen Wikipedia-Text ohne großes LLM. |
| `_build_web_answer_messages()` | Baut einen quellengebundenen Prompt für Webdaten. |
| `_build_message_history()` | Gibt nur vollständige User/EVA-Paare an das Modell. |
| `_append_history()` | Speichert eine fertige Unterhaltung atomar. |
| `_build_rag_context()` | Holt passende lokale Dokumentabschnitte. |
| `_memory_context_from_decision()` | Lädt nur die vom Router gewählten Erinnerungen. |
| `warm_llm()` | Lädt das Hauptmodell vor der ersten Anfrage. |
| `start_voice()` | Startet den dauerhaften XTTS-Worker. |
| `shutdown()` | Beendet Voice, RAG und andere Ressourcen sauber. |

### `core/intent_router.py`

| Funktion | Kurze Erklärung |
|---|---|
| `route()` | Liefert eine `IntentDecision` für die aktuelle Nachricht. |
| `_fast_route()` | Erkennt eindeutige Fälle ohne Modellaufruf. |
| `is_conversational()` | Erkennt Smalltalk und kurze Rückfragen. |
| `resets_context()` | Erkennt Nachrichten, die alten Suchkontext verwerfen. |
| `_encyclopedic_query()` | Extrahiert das Thema einer Überblicksfrage. |
| `_explicit_web_query()` | Bereinigt einen ausdrücklichen Suchauftrag. |
| `_parse()` | Wandelt die JSON-Ausgabe des Routers in ein Python-Objekt um. |

### `voice/`

| Funktion | Kurze Erklärung |
|---|---|
| `VoiceConfig.from_env()` | Liest alle aktuellen Voice-Einstellungen aus `.env`. |
| `sanitize_for_speech()` | Entfernt Markdown, Code und Quellen aus gesprochenem Text. |
| `SpeechChunker.complete_response()` | Bündelt kurze Antworten und teilt lange an Satzgrenzen. |
| `VoiceService.start()` | Startet XTTS als dauerhaften Unterprozess. |
| `VoiceService.start_response()` | Öffnet einen neuen, abbrechbaren Sprachauftrag. |
| `VoiceService.feed_text()` | Sammelt Textstücke der laufenden Antwort. |
| `VoiceService.finish_response()` | Bündelt den Text und startet die Synthese. |
| `VoiceService.stop()` | Bricht nur den aktuellen Sprachauftrag ab. |
| `VoiceService.shutdown()` | Beendet Worker und Audioausgabe vollständig. |
| `XTTSEngine.load()` | Lädt Modell und gespeicherte Sprechermerkmale auf die GPU. |
| `XTTSEngine.stream_pcm()` | Wandelt einen Text in rohe PCM-Audiodaten um. |
| `AudioPlayer._save_output()` | Speichert das fertige Audio als WAV oder MP3. |

### Andere wichtige Stellen

| Funktion | Kurze Erklärung |
|---|---|
| `WebSearchModule.execute()` | Führt die bereits ausgewählte externe Datenabfrage aus. |
| `RAGRetriever.search()` | Sucht semantisch ähnliche Dokumentabschnitte. |
| `load_state()` | Lädt Gesprächsverlauf und Laufzeitstatus. |
| `modify_state()` | Ändert den Zustand mit Dateisperre und atomarem Schreiben. |
| `health_payload()` | Baut die JSON-Antwort für `/health`. |
| `PresenceFusion.update()` | Verbindet Raum- und Schreibtisch-Präsenz. |
| `PresenceAutomation.handle_report()` | Entscheidet, ob eine Präsenzmeldung gesprochen wird. |

## 5. Wo liegen Daten?

| Pfad | Inhalt | Manuell bearbeiten? |
|---|---|---|
| `.env` | Echte lokale Einstellungen und geheime Tokens. | Ja, aber nie veröffentlichen. |
| `.env.example` | Dokumentierte Vorlage ohne echte Geheimnisse. | Ja. |
| `memory/state.json` | Gesprächsverlauf und aktueller EVA-Zustand. | Nur bei beendeter EVA und mit Sicherung. |
| `memory/memory.json` | Langzeitwissen und Projektdossiers. | Vorsichtig und nur gültiges JSON. |
| PostgreSQL | RAG-Dokumente und Vektoren. | Über die RAG-Werkzeuge. |
| `data/voices/` | Referenzaufnahmen und lokale Stimmmodelle. | Referenzen bewusst austauschen. |
| `data/tts/` | Erzeugte Hörproben und aktuelle Sprachausgabe. | Ja; Dateien sind Ergebnisse. |
| `voice/cache/` | Berechnete XTTS-Sprechermerkmale. | Nur bei beendeter EVA löschen. |
| `data/presence_automation.json` | Status der Präsenz-Automation. | Normalerweise nicht. |

Die Dateien mit der Endung `.orig`, virtuelle Umgebungen und Modell-Caches sind keine Einstiegspunkte für Änderungen.

## 6. Häufige Änderungen

### EVAs Persönlichkeit ändern

Bearbeite `EVA_CORE_PROMPT` am Anfang von `core/eva.py`. Regeln sollten kurz, eindeutig und widerspruchsfrei sein.

### Ein Modell wechseln

Ändere `EVA_MODEL`, `EVA_WEB_MODEL` oder `EVA_ROUTER_MODEL` in `.env`. Danach EVA vollständig neu starten.

### Eine Aussprache korrigieren

Ergänze eine Zuordnung in `voice/pronunciation_rules.json`. Beispiel: `"E46": "E sechsundvierzig"`.

### Einen neuen direkten Befehl hinzufügen

Erstelle ein Modul auf Basis von `module/base_module.py` und trage es in `core/config.py` unter `modules` ein.

### Eine neue Datenquelle hinzufügen

Erweitere zuerst die Aktionen im IntentRouter und implementiere danach die Ausführung in einem Modul. Routing und Datenabruf bleiben getrennt.

### Die Stimme abstimmen

Ändere zuerst nur einen Wert in `.env`, erzeuge eine versionierte Hörprobe und vergleiche sie mit der vorherigen Datei.

## 7. Sicherer Arbeitsablauf

1. Laufende EVA mit `Strg+C` beenden.
2. Nur einen kleinen Bereich ändern.
3. Syntax mit `python3 -m py_compile DATEI.py` prüfen.
4. Passende Tests aus `tests/` ausführen.
5. Danach die gesamte Suite starten:

```bash
python3 -m unittest discover -s tests -v
```

6. EVA neu starten und das Verhalten praktisch testen.

## 8. Namensmuster im Code

- Namen mit führendem `_` sind interne Hilfsfunktionen.
- `from_env()` erstellt eine Konfiguration aus Umgebungsvariablen.
- `start()`, `stop()` und `shutdown()` steuern die Lebensdauer eines Dienstes.
- `feed_*()` nimmt weitere Daten für einen laufenden Vorgang an.
- `finish_*()` beendet einen Vorgang kontrolliert.
- Funktionen mit `stream` liefern mehrere Teile statt eines fertigen Gesamtwerts.
- `status()` liefert nur lesbare Diagnoseinformationen.

## 9. Weiterführende Dokumente

- `docs/ARCHITECTURE.md`: technischer Gesamtaufbau
- `docs/VOICE.md`: aktuelle XTTS-Architektur
- `docs/RAG.md`: PostgreSQL- und pgvector-Wissen
- `docs/PRESENCE_AUTOMATION.md`: automatische Präsenzreaktionen
- `docs/VISUAL_CORTEX.md`: Kamera und Identität
- `docs/INSTALL.md`: Installation und Dienste
