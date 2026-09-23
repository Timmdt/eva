# Frühere lokale TTS-Backends

Die aktuelle EVA-Sprachausgabe verwendet persistentes XTTS-v2-Streaming. Die
Installation, Konfiguration und Diagnose stehen in [VOICE.md](VOICE.md). Dieses
Dokument beschreibt nur noch die älteren Qwen-, Chatterbox-, Piper- und
eSpeak-Backends.

EVA kann Antworten und Presence-Begrüßungen lokal vorlesen. Die primäre Engine
ist jetzt XTTS v2. Qwen3-TTS, Chatterbox und Piper bleiben als experimentelle
Alternativen verfügbar. Ohne aktivierte oder funktionsfähige TTS bleibt die
normale Textausgabe erhalten.

## Qwen3-TTS: feste EVA-Stimme

VoiceDesign wird nur zum Entwerfen der Stimme verwendet. Für normale Antworten
klont Qwen3-TTS Base die gespeicherte WAV-Aufnahme zusammen mit ihrem exakten
Referenztext. Dadurch wird nicht für jede Antwort eine neue Stimme entworfen.

Die isolierte Umgebung wird so installiert:

```bash
cd ~/opt/eva
python3 -m venv .venv-qwen
. .venv-qwen/bin/pip install --no-cache-dir \
  --index-url https://download.pytorch.org/whl/cu124 \
  torch==2.6.0 torchaudio==2.6.0
.venv-qwen/bin/pip install --no-cache-dir -r requirements-qwen.txt
```

Konfiguration für die lokale RTX 2070 und MP3-Ausgabe:

```env
EVA_TTS_ENABLED=true
EVA_TTS_ENGINE=qwen
EVA_TTS_LANGUAGE=de
EVA_TTS_REFERENCE_AUDIO=data/voices/eva-qwen-reference.wav
EVA_TTS_QWEN_REFERENCE_TEXT=data/voices/eva-qwen-reference.txt
EVA_TTS_QWEN_PYTHON=.venv-qwen/bin/python
EVA_TTS_QWEN_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base
EVA_TTS_QWEN_DEVICE=cuda:0
EVA_TTS_QWEN_DTYPE=float16
EVA_TTS_QWEN_TEMPERATURE=0.65
EVA_TTS_QWEN_TOP_P=0.85
EVA_TTS_QWEN_TOP_K=30
EVA_TTS_QWEN_REPETITION_PENALTY=1.08
EVA_TTS_QWEN_TIMEOUT=900
EVA_TTS_QWEN_RELEASE_OLLAMA=true
EVA_TTS_OUTPUT_FILE=data/tts/eva-qwen-clone.mp3
```

Die Referenz-WAV und ihr Text müssen exakt zusammenpassen. Der erste Aufruf lädt
das Qwen-Base-Modell herunter. Auf einer 8-GB-GPU dürfen VoiceDesign, Qwen Base
und große Ollama-Modelle nicht gleichzeitig im VRAM liegen.

## Chatterbox Multilingual V3

Chatterbox läuft in einer eigenen Python-Umgebung, damit seine fest vorgegebenen
NumPy- und PyTorch-Versionen nicht mit EVA, OpenCV oder Piper kollidieren:

```bash
cd ~/opt/eva
python3 -m venv .venv-chatterbox
.venv-chatterbox/bin/pip install -r requirements-chatterbox.txt
```

Für eine MP3-Hörprobe ohne Lautsprecher:

```env
EVA_TTS_ENABLED=true
EVA_TTS_ENGINE=chatterbox
EVA_TTS_LANGUAGE=de
EVA_TTS_CHATTERBOX_PYTHON=.venv-chatterbox/bin/python
EVA_TTS_REFERENCE_AUDIO=
EVA_TTS_EXAGGERATION=0.60
EVA_TTS_CFG_WEIGHT=0.35
EVA_TTS_CHATTERBOX_DEVICE=auto
EVA_TTS_CHATTERBOX_MODEL_VERSION=v3
EVA_TTS_CHATTERBOX_TIMEOUT=900
EVA_TTS_VOLUME=1.0
EVA_TTS_OUTPUT_FILE=data/tts/eva-chatterbox.mp3
```

Lass EVA_TTS_REFERENCE_AUDIO zunächst leer. Trage später nur eine saubere,
rechtmäßig nutzbare WAV-Aufnahme von ungefähr 8 bis 15 Sekunden ein. Beim ersten
Start lädt Chatterbox das Modell herunter; das kann einige Minuten dauern.
EVA_TTS_PITCH und EVA_TTS_LENGTH_SCALE gelten nur für Piper.

## Piper-Fallback auf der EVA-VM

Die VM benötigt einen erreichbaren ALSA-Audioausgang. Das Audiogerät ist in
dieser Installation bereits unter `/dev/snd` sichtbar. Installiere den Player:

```bash
sudo apt update
sudo apt install -y alsa-utils
sudo usermod -aG audio "$USER"
```

Melde dich danach einmal ab und wieder an oder starte die VM neu, damit die
neue Gruppenmitgliedschaft wirksam wird.

Installiere Piper in genau der Python-Umgebung, mit der EVA startet:

```bash
cd ~/opt/eva
. .venv/bin/activate
pip install "piper-tts>=1.7,<2"
mkdir -p data/voices
python -m piper.download_voices \
  --data-dir data/voices \
  de_DE-kerstin-low
```

Die Lizenzhinweise liegen beim Stimmenmodell und sollten vor einer
Weiterverteilung geprüft werden.

## Konfiguration

Trage in `.env` ein:

```env
EVA_TTS_ENABLED=true
EVA_TTS_ENGINE=piper
EVA_TTS_MODEL=data/voices/de_DE-kerstin-low.onnx
EVA_TTS_VOLUME=1.0
EVA_TTS_LENGTH_SCALE=1.06
EVA_TTS_PITCH=1.06
EVA_TTS_AUDIO_PLAYER=aplay
EVA_TTS_AUDIO_DEVICE=default
```

`EVA_TTS_PITCH=1.06` hebt die Stimme um sechs Prozent an.
`EVA_TTS_LENGTH_SCALE=1.06` gleicht das dadurch leicht erhöhte Sprechtempo aus.
Für einen natürlicheren, weniger kindlichen Klang eignet sich `1.03` bei beiden
Werten; `1.08` wirkt jünger. Werte über `1.12` klingen meist künstlich.

Danach EVA neu starten. Antworten werden weiterhin sofort gestreamt angezeigt
und nach Abschluss gesprochen. Codeblöcke und URLs werden für die Aussprache
vereinfacht. Temporäre WAV-Dateien werden nach dem Abspielen entfernt.

## MP3-Datei statt Lautsprecher

Installiere den lokalen MP3-Encoder und setze einen Ausgabepfad. Sobald dieser
Wert gesetzt ist, speichert EVA die Sprache und startet `aplay` nicht.

```bash
pip install "lameenc>=1.8.4,<2"
```

```env
EVA_TTS_OUTPUT_FILE=data/tts/eva-stimme.mp3
```

## Audio testen

```bash
speaker-test -D default -c 2 -t wav
```

Piper und EVA ohne vollständigen Dialog testen:

```bash
python -c 'from core.env_loader import load_env_file; load_env_file(".env"); from interfaces.voice import TextToSpeech; raise SystemExit(0 if TextToSpeech().speak("Hallo Tim, meine Sprachausgabe funktioniert.") else 1)'
```

Falls `aplay` ein unbekanntes Gerät meldet, zeigt `aplay -L` die verfügbaren
Gerätenamen. Setze anschließend `EVA_TTS_AUDIO_DEVICE` auf den passenden Namen.

## Leichter Fallback

Für eine kompaktere, aber deutlich synthetischere Stimme:

```bash
sudo apt install -y espeak-ng alsa-utils
```

```env
EVA_TTS_ENGINE=espeak
EVA_TTS_LANGUAGE=de
EVA_TTS_RATE=165
```
