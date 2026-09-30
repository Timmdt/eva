# EVA: LLM- und TTS-Benchmark auf der RTX 2070

Stand: 30. September 2026
## Aktuelle lokale Modellaufteilung

XTTS bleibt vollständig installiert, ist derzeit aber mit `EVA_TTS_ENABLED=false` deaktiviert.
EVA verwendet `gemma4:e2b` mit 2048 Tokens und deaktiviertem Thinking. Für den späteren
Desktop-Agenten ist `maternion/mai-ui:2b` mit dauerhaftem Keep-Alive reserviert; dessen interne
Aktionsprompts sollten
Englisch sein. Bei dauerhaft geladenem MAI-UI zuerst und Gemma danach belegen beide zusammen
etwa 6668 MB VRAM und lassen rund 1119 MB frei.

| Modell | Aufgabe | TTFT/Antwortbeginn | Token/s | VRAM |
|---|---|---:|---:|---:|
| Gemma 4 E2B Q4_K_M | EVA-Dialog | 88 ms TTFT, 433 ms erster Satz | 75,5 | 3102 MB |
| Gemma 4 E4B Q4_K_M | Qualitätsvergleich | 123 ms TTFT, 506 ms erster Satz | 65,0 | 4754 MB |
| MAI-UI 2B Q8_0 | GUI-Grounding | etwa 0,6 s warm | etwa 105-130 | 3592 MB bei 2048 Kontext |

MAI-UI traf im englisch formulierten Test den Mittelpunkt von „Abbrechen“ nahezu exakt. Ein
deutscher Aktionsprompt wählte dagegen einmal „Löschen“; GUI-Aktionen benötigen deshalb weiterhin
Validierung und eine Bestätigung für gefährliche Schritte. Kleine lokale Modelle erfinden außerdem
weiterhin Fakten. Benannte Themen und aktuelle Angaben müssen über Wikipedia, Web oder RAG belegt
werden.


## Frühere XTTS-Baseline

Für diesen älteren Vergleich verwendete EVA `gemma3:4b-it-q4_K_M` über Ollama und XTTS v2 über CUDA.
Alle LLM-Aufgaben verwenden dasselbe Modell. Das vermeidet Modellwechsel und erneute Ladezeiten.
Der Kontext bleibt bei 4096 Tokens, Thinking ist deaktiviert und vollständige Sätze werden schon während
der laufenden LLM-Ausgabe an XTTS übergeben.

Die Auswahl priorisiert gutes, knappes Deutsch. Qwen3 ist die sparsamere Rückfalloption, falls parallel
weitere GPU-Dienste hinzukommen.

## Testsystem

- GPU: NVIDIA GeForce RTX 2070, 8192 MiB VRAM
- RAM in der EVA-VM: 14.650.834.944 Byte, also 13,65 GiB sichtbar
- Ollama: 0.13.1
- Ollama-Python-Paket: 0.6.2
- TTS: Coqui XTTS v2, CUDA, persistenter Worker, deutsche Referenzstimme
- Ausgabe im Test: MP3-Datei; „erster Ton“ ist der erste PCM-Block am Audio-Sink
- STT ist nicht Teil dieses Repositories. Die Gesamtlatenz beginnt deshalb bei Übergabe des fertigen
  Benutzertexts, nicht beim Ende einer Spracheingabe.

## Ausgangszustand

Das bisherige Hauptmodell war `qwen2.5:3b-instruct`:

- 3.085.938.688 Parameter
- GGUF, Q4_K_M
- Ollama/llama.cpp-Runner
- Modellkontext maximal 32768, in EVA aktiv 4096
- etwa 1,9 GB Modelldatei
- separates `qwen2.5:1.5b` für Router und Suchanfragen
- TTS-Antwortpufferung aktiv; XTTS begann erst nach der vollständigen Antwort

Der alte LLM-Benchmark ergab 164 ms TTFT, 428 ms bis zum ersten Satz, 124,8 Token/s und
2471 MB VRAM. Die Geschwindigkeit war gut, das Deutsch aber mehrfach fehlerhaft. Beispiele waren
„die Blauer Teil“ und „Muesli-Soße“; das Grimm-Märchen wurde inhaltlich erfunden.

## LLM-Vergleich

Alle Werte stammen aus denselben sechs deutschen Prompts, `think=false`, 4096 Kontext und maximal
220 Ausgabetokens. Der VRAM-Wert ist die Spitze des reinen LLM-Laufs.

| Modell | Quantisierung | TTFT | Erster Satz | Token/s | VRAM | Qualitätsurteil |
|---|---|---:|---:|---:|---:|---|
| Qwen2.5 3B Instruct | Q4_K_M | 164 ms | 428 ms | 124,8 | 2471 MB | schnell, aber auffällig fehlerhaftes Deutsch |
| Qwen3 4B Instruct 2507 | Q4_K_M | 160 ms | 434 ms | 94,2 | 3219 MB | sparsam, teils unnatürliche Wortwahl |
| Gemma 3 4B IT | Q4_K_M | 319 ms | 506 ms | 91,2 | 4777 MB | bestes, knappstes Deutsch im Test |
| Phi-4 Mini 3.8B | Q4_K_M | 204 ms | 547 ms | 110,1 | 3507 MB | Fehler wie „Kurzzeit-Rohrelement“ |
| Ministral 3 3B | Q4_K_M | – | – | – | – | Ollama 0.13.1 lehnt das Modell ab; Upgrade erforderlich |

Gemma halluzinierte wie die anderen kleinen Modelle das Märchen „Die Sterntaler“. EVA beantwortet
die erkannten Grimm-Anfragen deshalb aus der lokalen, geprüften Geschichtensammlung. Das ist kein
Benchmark-Trick für allgemeine Fragen, sondern verhindert gezielt die zuvor beobachteten falschen
Märchen und Wikipedia-Quellen.

## Kontextvergleich für Gemma

| Kontext | TTFT | Erster Satz | Token/s | LLM-VRAM |
|---:|---:|---:|---:|---:|
| 4096 | 319 ms | 506 ms | 91,2 | 4777 MB |
| 8192 | 323 ms | 576 ms | 90,8 | 4857 MB |
| 16384 | 321 ms | 531 ms | 91,2 | 5017 MB |

Die kurzen Sprachdialoge profitieren nicht von 8192 oder 16384 Tokens. EVA begrenzt zusätzlich den
Verlauf auf acht Nachrichten und 6000 Zeichen. 4096 liefert daher die beste VRAM-Reserve.

## Quantisierung und GPU/CPU-Aufteilung

Q4_K_M bleibt die sinnvolle Quantisierung. Q5/Q8 benötigen mehr VRAM, obwohl Gemma Q4 zusammen mit
XTTS bereits 7660 MB erreicht. Eine höhere Quantisierung würde die OOM-Reserve verkleinern oder
CPU-Offload erzwingen.

Gemma besitzt 34 Textblöcke. Zwei gemessene Teil-Offload-Varianten waren deutlich langsamer:

| GPU-Blöcke | Token/s | TTFT | LLM-VRAM | CPU-Spitze |
|---:|---:|---:|---:|---:|
| alle | 91,2 | 319 ms | 4777 MB | 14,7 % |
| 32 | 22,3 | 397 ms | 3731 MB | 100 % |
| 28 | 18,0 | 438 ms | 3473 MB | 100 % |

Darum wird nicht aggressiv auf die CPU ausgelagert. Wenn zusätzliche GPU-Software parallel laufen
soll, ist Qwen3 4B Q4 die bessere Rückfalloption als ein langsames Teil-Offload von Gemma.

## TTS-Auswahl

XTTS v2 bleibt aktiv. Es unterstützt Deutsch und Streaming, übernimmt die vorhandene Referenzstimme
und war in diesem Projekt subjektiv die beste der bereits erzeugten Hörproben.

| TTS | Entscheidung | Grund |
|---|---|---|
| XTTS v2 | ausgewählt | deutsche Referenzstimme, Streaming, gemessene RTF 0,307 |
| Chatterbox Multilingual | derzeit nicht aktiv | frühere Projektprobe gefiel nicht; V3 wäre ein eigener neuer Hörtest |
| Resemble Enhance | entfernt | verschlechterte die Stimme im direkten Hörvergleich |
| F5-TTS | nicht integriert | deutsches Modell ist Community-Finetune; zusätzlicher Integrations- und VRAM-Aufwand |
| Voxtral TTS 4B | nicht passend für diese GPU | zusammen mit einem 4B-LLM zu groß für 8 GB VRAM |

Offizielle Referenzen:

- [Coqui XTTS v2](https://github.com/coqui-ai/TTS/blob/dev/docs/source/models/xtts.md)
- [Chatterbox](https://github.com/resemble-ai/chatterbox)
- [F5-TTS](https://github.com/SWivid/F5-TTS)
- [Voxtral TTS](https://mistral.ai/news/voxtral-tts/)
- [Gemma 3](https://ai.google.dev/gemma/docs/core/gemma_library)
- [Qwen3 4B Instruct 2507](https://ollama.com/library/qwen3%3A4b-instruct-2507-q4_K_M)
- [Phi-4 Mini](https://ollama.com/library/phi4-mini)
- [Ministral 3 3B](https://docs.mistral.ai/models/ministral-3-3b-25-12)

## Finale Gesamtmessung

Prompt: „Erkläre in drei kurzen, natürlichen Sätzen, warum Blätter im Herbst ihre Farbe ändern.“

| Messpunkt | Ergebnis |
|---|---:|
| Intent-Router | 1,7 ms |
| LLM erstes Token | 703 ms |
| erster fertiger TTS-Textabschnitt | 972 ms |
| erstes Audio von XTTS | 1418 ms |
| erster PCM-Block am Audio-Sink | 1427 ms |
| vollständige LLM-Antwort | 1910 ms |
| erzeugte Audiodauer | 18,85 s |
| TTS Real-Time-Factor | 0,307 |
| gemeinsame VRAM-Spitze | 7660 MB |
| kaltes XTTS-Laden | 17,0 s |
| Speaker-Conditioning aus Cache | 2,4 ms |

Die kalte XTTS-Ladezeit tritt beim Start auf. Im Dialog bleibt der Worker geladen. Auch Ollama erhält
`EVA_OLLAMA_KEEP_ALIVE=-1m`, sodass Gemma nicht zwischen Gesprächsrunden entladen wird.

## Umgesetzte Pipeline

```text
Benutzertext
  -> deterministischer Router für klare Absichten
  -> ein dauerhaft geladenes Gemma-Modell
  -> Ollama-Tokenstream
  -> Satz-Chunker
  -> persistenter XTTS-Worker
  -> Audio-Sink
```

Quellenblöcke, Markdown-Links und URLs werden weiterhin im sichtbaren Text behalten, aber vor der
Sprachausgabe entfernt. Der Chunker wartet auf vollständige Satzgrenzen, damit XTTS nicht mitten im
Wort oder an einem Komma startet.

## Reproduzieren

```bash
python -m tools.llm_voice_benchmark \
  qwen3:4b-instruct-2507-q4_K_M \
  gemma4:e2b \
  phi4-mini:3.8b-q4_K_M \
  --context 4096 --num-predict 220

python -m tools.eva_voice_benchmark \
  "Erkläre in drei kurzen, natürlichen Sätzen, warum Blätter im Herbst ihre Farbe ändern."
```

Die JSON-Rohdaten werden unter `data/benchmarks/` gespeichert und sind absichtlich nicht Teil von Git.
