# EVA Voice: lokales XTTS-v2-Streaming

EVA verwendet XTTS v2 vollständig lokal. Das Hauptprogramm bleibt in `.venv`,
während `coqui-tts` und CUDA isoliert in `.venv-xtts` liegen. Ein persistenter
Worker lädt XTTS, Stimme und Speaker-Conditioning einmal und bleibt danach aktiv.
Es gibt keine Cloud-TTS-API und keinen extern erreichbaren Voice-Port.

## Architektur

```text
Ollama stream=True
  ├─ vollständiger Antwortpuffer → History / Memory
  └─ sichtbare Token → SpeechChunker → XTTS-Worker
                                      → PCM-Audiochunks
                                      → Audio-Queue → ALSA/aplay oder Datei
```

Der erste Sprachabschnitt ist bewusst kurz. Weitere Abschnitte sind länger, damit
die Prosodie natürlich bleibt. URLs, Markdown-Tabellen und Codeblöcke werden vor
der Synthese bereinigt. `VoiceService.stop()` verwirft ausstehende Text- und
Audiochunks und beendet die aktuelle Wiedergabe.

## Installation

Voraussetzungen sind Python 3.10 bis 3.12, NVIDIA-Treiber, eine funktionierende
CUDA-PyTorch-Kombination und optional `alsa-utils` für echte Wiedergabe.

```bash
cd ~/opt/eva
python3 -m venv .venv-xtts
.venv-xtts/bin/pip install --no-cache-dir \
  --index-url https://download.pytorch.org/whl/cu124 \
  torch==2.6.0 torchaudio==2.6.0
.venv-xtts/bin/pip install --no-cache-dir -r requirements-xtts.txt
```

`transformers==4.57.6` ist absichtlich festgelegt. Transformers 5.x entfernt eine
von XTTS verwendete Funktion und ist mit `coqui-tts 0.27.4` nicht kompatibel.

## Referenzstimme vorbereiten

Nur ausdrücklich bereitgestellte und rechtmäßig verwendbare Aufnahmen einsetzen.
EVA nimmt niemals automatisch Stimmen auf.

```env
EVA_VOICE_REFERENCE=data/voices/eva-reference.wav
EVA_VOICE_LANGUAGE=de
```

Mehrere Referenzen werden kommagetrennt angegeben:

```env
EVA_VOICE_REFERENCES=voice/reference/eva-1.wav,voice/reference/eva-2.wav
```

Prüfen und Speaker-Conditioning berechnen:

```bash
python -m voice.prepare_voice --validate-only
python -m voice.prepare_voice
```

Der zweite Befehl lädt beim ersten Mal XTTS-v2 und zeigt die Coqui-Lizenzabfrage.
Die Zustimmung muss der Benutzer selbst erteilen. Das Conditioning wird unter
`voice/cache/` mit restriktiven Dateirechten gespeichert; Referenz und Cache sind
in `.gitignore` ausgeschlossen.

Empfohlen sind saubere muttersprachlich deutsche WAV-Aufnahmen ohne Musik,
Hall, Rauschen oder Clipping. Eine englische Referenz ist zum Vergleich möglich,
kann aber deutschen Akzent und Rhythmus verschlechtern.

## Konfiguration

```env
EVA_TTS_ENABLED=true
EVA_TTS_ENGINE=xtts_v2
EVA_VOICE_REFERENCE=data/voices/eva-reference.wav
EVA_VOICE_LANGUAGE=de
EVA_TTS_DEVICE=cuda
EVA_TTS_LOW_VRAM_MODE=true
EVA_TTS_STREAMING=false
EVA_TTS_CACHE_SPEAKER=true
EVA_TTS_CACHE_DIR=voice/cache
EVA_TTS_XTTS_PYTHON=.venv-xtts/bin/python
EVA_TTS_XTTS_MODEL=tts_models/multilingual/multi-dataset/xtts_v2
EVA_TTS_STREAM_CHUNK_SIZE=20
EVA_TTS_TEMPERATURE=0.62
EVA_TTS_REPETITION_PENALTY=5.0
EVA_TTS_TOP_K=40
EVA_TTS_TOP_P=0.78
EVA_TTS_SPEED=0.98
EVA_TTS_SEED=42
EVA_TTS_TRIM_TRAILING_ARTIFACTS=true
EVA_TTS_SENTENCE_PAUSE_MS=25
EVA_TTS_GPT_COND_LEN=12
EVA_TTS_GPT_COND_CHUNK_LEN=4

EVA_TTS_FIRST_CHUNK_MIN_WORDS=5
EVA_TTS_FIRST_CHUNK_TARGET_WORDS=8
EVA_TTS_CHUNK_MIN_WORDS=10
EVA_TTS_CHUNK_TARGET_WORDS=18
EVA_TTS_CHUNK_MAX_WORDS=30
EVA_TTS_MAX_CHUNK_WAIT_MS=350
EVA_TTS_SENTENCE_CHUNKS_ONLY=true
EVA_TTS_RESPONSE_BUFFERING=true
EVA_TTS_RESPONSE_CHUNK_MAX_WORDS=55

EVA_TTS_READ_CODE=false
EVA_TTS_READ_URLS=false
EVA_AUDIO_DEVICE=
EVA_AUDIO_VOLUME=0.90
EVA_LLM_NUM_CTX=2048
EVA_OLLAMA_KEEP_ALIVE=30m
EVA_PERFORMANCE_DEBUG=false
```

`EVA_AUDIO_DEVICE` bleibt für den ALSA-Standardausgang leer. Verfügbare Ausgänge:

```bash
python -m tools.audio_devices
```

Ohne angeschlossenen Lautsprecher kann eine Hörprobe gespeichert werden:

```env
EVA_TTS_OUTPUT_FILE=data/tts/eva-xtts.mp3
```

Für direkte Wiedergabe muss `EVA_TTS_OUTPUT_FILE` leer sein.

## Diagnose und Benchmarks

```bash
python -m tools.voice_diagnostics
python -m tools.voice_benchmark
python -m tools.eva_voice_benchmark
python -m tools.eva_voice_benchmark --turns 10
```

Die Werkzeuge geben nur gemessene Werte aus: XTTS-Ladezeit, Conditioning-Zeit,
Time-to-first-audio, Time-to-first-sound, Real-Time-Factor und VRAM. Der letzte
Befehl ist der Zehn-Turn-Stresstest. Für den Vergleich des KV-Caches zuerst mit
`EVA_LLM_NUM_CTX=2048`, danach kontrolliert mit `4096` testen.

## RTX 2070 und Low-VRAM-Modus

Die RTX 2070 besitzt 8 GB VRAM. EVA lädt Gemma 3 4B Q4 mit `num_ctx=2048` und
danach XTTS. Hauptantwort, Router, Webantwort und Suchanfrage verwenden dasselbe
LLM; dadurch wird kein zweites Sprachmodell ein- und ausgelagert. Audiochunks
werden direkt auf die CPU übertragen und Speaker-Latents wiederverwendet.

Vollständiges GPU-Offloading ist trotz knapper Reserve schneller als teilweises
CPU-Offloading. Im Test sank Gemma mit 32 von 34 GPU-Schichten von 91 auf 22
Token/s und belastete die CPU vollständig. Darum bleibt das Modell ganz auf der
GPU und der Kontext bewusst bei 2048 Tokens.

### Aktuelle Messwerte auf diesem EVA-Rechner

Gemessen mit RTX 2070 8 GB, Gemma 3 4B Q4_K_M, XTTS v2, CUDA, Satz-Streaming und
Dateiausgabe. „Erster Ton“ bedeutet ohne Lautsprecher, dass der erste PCM-Block
die Audioausgabe erreicht hat.

| Test | Erster Textabschnitt | Erstes Audio | Erster Ton | VRAM-Spitze | TTS-RTF |
|---|---:|---:|---:|---:|---:|
| 4096 Kontext, 1 Antwort | 972 ms | 1418 ms | 1427 ms | 7660 MB | 0,307 |

Der Intent-Router benötigte dabei 1,7 ms. Ein 8192er Kontext erhöht den
LLM-VRAM-Verbrauch ohne messbaren Qualitätsgewinn und ist für den gemeinsamen
Betrieb mit XTTS daher nicht die Standardwahl.

Die vollständige Modellauswahl steht in [LLM_TTS_BENCHMARK.md](LLM_TTS_BENCHMARK.md).

## Health-Status

`GET /health` enthält zusätzlich:

```json
{
  "voice": {
    "enabled": true,
    "ready": true,
    "model": "xtts_v2",
    "device": "cuda",
    "gpu": "NVIDIA GeForce RTX 2070"
  }
}
```

## Troubleshooting

- `CUDA ist nicht verfügbar`: `python -m tools.voice_diagnostics` ausführen und
  NVIDIA-Treiber sowie Torch-Version prüfen.
- `XTTS-Python fehlt`: `.venv-xtts` nach der Installationsanleitung erstellen.
- `Voice-Referenz fehlt`: Pfad in `EVA_VOICE_REFERENCE` prüfen.
- Kein Ton: `python -m tools.audio_devices` ausführen oder zunächst eine
  Ausgabedatei konfigurieren.
- CUDA OOM: laufende fremde GPU-Prozesse prüfen, `EVA_LLM_NUM_CTX=2048` verwenden
  und keine weiteren TTS-/LLM-Modelle parallel laden.
- Cache neu erzeugen: EVA beenden und nur den passenden Inhalt von
  `voice/cache/` löschen; die Originalaufnahme bleibt davon unberührt.

Voice vollständig deaktivieren:

```env
EVA_TTS_ENABLED=false
```

Die normale Textausgabe, History, Memory, RAG und Websuche funktionieren dann
unverändert weiter.
