from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


logger = logging.getLogger(__name__)

Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(
    name: str, default: float, minimum: float, maximum: float | None = None,
) -> float:
    try:
        value = max(minimum, float(os.getenv(name, str(default))))
        return min(maximum, value) if maximum is not None else value
    except ValueError:
        return default


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True)
class VoiceConfig:
    enabled: bool = False
    engine: str = "piper"
    model: Path = Path("data/voices/de_DE-kerstin-low.onnx")
    language: str = "de"
    chatterbox_python: Path = Path(".venv-chatterbox/bin/python")
    reference_audio: Path | None = None
    exaggeration: float = 0.60
    cfg_weight: float = 0.35
    chatterbox_device: str = "auto"
    chatterbox_model_version: str = "v3"
    chatterbox_timeout: float = 900.0
    qwen_python: Path = Path(".venv-qwen/bin/python")
    qwen_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    qwen_reference_text: Path | None = None
    qwen_device: str = "cuda:0"
    qwen_dtype: str = "float16"
    qwen_temperature: float = 0.65
    qwen_top_p: float = 0.85
    qwen_top_k: int = 30
    qwen_repetition_penalty: float = 1.08
    qwen_timeout: float = 900.0
    qwen_release_ollama: bool = True
    xtts_python: Path = Path(".venv-xtts/bin/python")
    xtts_model: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    xtts_device: str = "auto"
    xtts_timeout: float = 900.0
    xtts_release_ollama: bool = True
    rate: int = 165
    volume: float = 1.0
    length_scale: float = 1.06
    pitch: float = 1.06
    output_file: Path | None = None
    audio_player: str = "aplay"
    audio_device: str = "default"
    timeout: float = 120.0
    max_chars: int = 4000

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        reference_audio = os.getenv("EVA_TTS_REFERENCE_AUDIO", "").strip()
        qwen_reference_text = os.getenv(
            "EVA_TTS_QWEN_REFERENCE_TEXT", "",
        ).strip()
        output_file = os.getenv("EVA_TTS_OUTPUT_FILE", "").strip()
        return cls(
            enabled=_env_bool("EVA_TTS_ENABLED", False),
            engine=os.getenv("EVA_TTS_ENGINE", "piper").strip().lower(),
            model=Path(os.getenv(
                "EVA_TTS_MODEL",
                "data/voices/de_DE-kerstin-low.onnx",
            )),
            language=os.getenv("EVA_TTS_LANGUAGE", "de").strip() or "de",
            chatterbox_python=Path(os.getenv(
                "EVA_TTS_CHATTERBOX_PYTHON",
                ".venv-chatterbox/bin/python",
            )),
            reference_audio=(
                Path(reference_audio).expanduser() if reference_audio else None
            ),
            exaggeration=_env_float(
                "EVA_TTS_EXAGGERATION", 0.60, 0.0, 1.0,
            ),
            cfg_weight=_env_float("EVA_TTS_CFG_WEIGHT", 0.35, 0.0, 1.0),
            chatterbox_device=(
                os.getenv("EVA_TTS_CHATTERBOX_DEVICE", "auto").strip() or "auto"
            ),
            chatterbox_model_version=(
                os.getenv("EVA_TTS_CHATTERBOX_MODEL_VERSION", "v3").strip() or "v3"
            ),
            chatterbox_timeout=_env_float("EVA_TTS_CHATTERBOX_TIMEOUT", 900.0, 30.0),
            qwen_python=Path(os.getenv(
                "EVA_TTS_QWEN_PYTHON",
                ".venv-qwen/bin/python",
            )),
            qwen_model=(
                os.getenv(
                    "EVA_TTS_QWEN_MODEL",
                    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                ).strip()
                or "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
            ),
            qwen_reference_text=(
                Path(qwen_reference_text).expanduser()
                if qwen_reference_text
                else None
            ),
            qwen_device=(
                os.getenv("EVA_TTS_QWEN_DEVICE", "cuda:0").strip() or "cuda:0"
            ),
            qwen_dtype=(
                os.getenv("EVA_TTS_QWEN_DTYPE", "float16").strip() or "float16"
            ),
            qwen_temperature=_env_float(
                "EVA_TTS_QWEN_TEMPERATURE", 0.65, 0.1, 2.0,
            ),
            qwen_top_p=_env_float("EVA_TTS_QWEN_TOP_P", 0.85, 0.01, 1.0),
            qwen_top_k=_env_int("EVA_TTS_QWEN_TOP_K", 30, 1),
            qwen_repetition_penalty=_env_float(
                "EVA_TTS_QWEN_REPETITION_PENALTY", 1.08, 0.1, 2.0,
            ),
            qwen_timeout=_env_float("EVA_TTS_QWEN_TIMEOUT", 900.0, 30.0),
            qwen_release_ollama=_env_bool("EVA_TTS_QWEN_RELEASE_OLLAMA", True),
            xtts_python=Path(os.getenv(
                "EVA_TTS_XTTS_PYTHON",
                ".venv-xtts/bin/python",
            )),
            xtts_model=(
                os.getenv(
                    "EVA_TTS_XTTS_MODEL",
                    "tts_models/multilingual/multi-dataset/xtts_v2",
                ).strip()
                or "tts_models/multilingual/multi-dataset/xtts_v2"
            ),
            xtts_device=(
                os.getenv("EVA_TTS_XTTS_DEVICE", "auto").strip() or "auto"
            ),
            xtts_timeout=_env_float("EVA_TTS_XTTS_TIMEOUT", 900.0, 30.0),
            xtts_release_ollama=_env_bool("EVA_TTS_XTTS_RELEASE_OLLAMA", True),
            rate=_env_int("EVA_TTS_RATE", 165, 80),
            volume=_env_float("EVA_TTS_VOLUME", 1.0, 0.0),
            length_scale=_env_float("EVA_TTS_LENGTH_SCALE", 1.06, 0.5, 2.0),
            pitch=_env_float("EVA_TTS_PITCH", 1.06, 0.75, 1.25),
            output_file=Path(output_file).expanduser() if output_file else None,
            audio_player=os.getenv("EVA_TTS_AUDIO_PLAYER", "aplay").strip(),
            audio_device=os.getenv("EVA_TTS_AUDIO_DEVICE", "default").strip(),
            timeout=_env_float("EVA_TTS_TIMEOUT", 120.0, 1.0),
            max_chars=_env_int("EVA_TTS_MAX_CHARS", 4000, 100),
        )


def prepare_spoken_text(text: str, max_chars: int = 4000) -> str:
    """Turn a Markdown-ish assistant response into useful spoken text."""
    spoken = str(text or "")
    fence = re.escape(chr(96) * 3)
    spoken = re.sub(f"{fence}.*?{fence}", " Codebeispiel im Terminal. ", spoken, flags=re.DOTALL)
    spoken = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", spoken)
    spoken = re.sub(r"https?://\S+", " Link ", spoken)
    spoken = re.sub(r"\[(?:LOAD_DOSSIER|WEB_SEARCH):[^\]]+\]", " ", spoken)
    spoken = spoken.replace(chr(96), "")
    spoken = re.sub(r"(?m)^\s{0,3}(?:[-*+] |#{1,6}\s*)", "", spoken)
    spoken = re.sub(r"[*_~]", "", spoken)
    spoken = " ".join(spoken.split()).strip()
    if len(spoken) <= max_chars:
        return spoken
    shortened = spoken[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{shortened}."


class TextToSpeech:
    """Synchronous, serialized local TTS with Piper and eSpeak-NG backends."""

    def __init__(
        self,
        config: VoiceConfig | None = None,
        *,
        runner: Runner = subprocess.run,
        which: Which = shutil.which,
        python_executable: str = sys.executable,
    ) -> None:
        self.config = config or VoiceConfig.from_env()
        self.runner = runner
        self.which = which
        self.python_executable = python_executable
        self.project_root = Path(__file__).resolve().parents[1]
        self._lock = threading.Lock()
        self._warnings: set[str] = set()

    def _warn_once(self, key: str, message: str, *args: object) -> None:
        if key in self._warnings:
            return
        self._warnings.add(key)
        logger.warning(message, *args)

    def _run(
        self, command: Sequence[str], *, timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            return self.runner(
                list(command),
                capture_output=True,
                text=True,
                timeout=self.config.timeout if timeout is None else timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.error("TTS-Befehl hat das Zeitlimit überschritten.")
        except OSError as exc:
            logger.error("TTS-Befehl konnte nicht gestartet werden: %s", exc)
        return None

    def _synthesize_piper(self, text: str, output: Path) -> bool:
        model = self.config.model.expanduser()
        config_path = model.with_suffix(model.suffix + ".json")
        if not model.is_file() or not config_path.is_file():
            self._warn_once(
                "piper-model",
                "Piper-Stimme fehlt: %s und passende .json-Datei benötigt.",
                model,
            )
            return False
        command = [
            self.python_executable,
            "-m",
            "piper",
            "-m",
            str(model),
            "-f",
            str(output),
            "--volume",
            str(self.config.volume),
            "--length-scale",
            str(self.config.length_scale),
            "--",
            text,
        ]
        result = self._run(command)
        if result is None or result.returncode != 0 or not output.is_file():
            error = (result.stderr if result is not None else "").strip()
            logger.error("Piper konnte Sprache nicht erzeugen: %s", error[-500:])
            return False
        return self._adjust_wav_pitch(output)

    def _project_path(self, path: Path) -> Path:
        expanded = path.expanduser()
        return expanded if expanded.is_absolute() else self.project_root / expanded

    def _synthesize_chatterbox(self, text: str, output: Path) -> bool:
        python = self._project_path(self.config.chatterbox_python)
        worker = self.project_root / "tools" / "chatterbox_synthesize.py"
        reference = (
            self._project_path(self.config.reference_audio)
            if self.config.reference_audio is not None
            else None
        )
        if not python.is_file():
            self._warn_once(
                "chatterbox-python",
                "Chatterbox-Umgebung fehlt: %s",
                python,
            )
            return False
        if reference is not None and not reference.is_file():
            self._warn_once(
                "chatterbox-reference",
                "Chatterbox-Referenzaufnahme fehlt: %s",
                reference,
            )
            return False
        text_file = output.with_suffix(".txt")
        try:
            text_file.write_text(text, encoding="utf-8")
        except OSError as exc:
            logger.error("Chatterbox-Text konnte nicht vorbereitet werden: %s", exc)
            return False
        command = [
            str(python),
            str(worker),
            "--text-file",
            str(text_file),
            "--output",
            str(output),
            "--language",
            self.config.language,
            "--exaggeration",
            str(self.config.exaggeration),
            "--cfg-weight",
            str(self.config.cfg_weight),
            "--device",
            self.config.chatterbox_device,
            "--model-version",
            self.config.chatterbox_model_version,
            "--volume",
            str(self.config.volume),
        ]
        if reference is not None:
            command.extend(["--reference", str(reference)])
        result = self._run(
            command,
            timeout=self.config.chatterbox_timeout,
        )
        if (
            result is None
            or result.returncode != 0
            or not output.is_file()
            or output.stat().st_size <= 44
        ):
            error = (result.stderr if result is not None else "").strip()
            logger.error("Chatterbox konnte Sprache nicht erzeugen: %s", error[-1000:])
            return False
        return True

    def _release_ollama_vram(self, enabled: bool) -> None:
        if not enabled:
            return
        ollama = self.which("ollama")
        if ollama is None:
            return
        result = self._run([ollama, "ps"], timeout=10.0)
        if result is None or result.returncode != 0:
            return
        for line in result.stdout.splitlines()[1:]:
            fields = line.split()
            if not fields:
                continue
            stopped = self._run([ollama, "stop", fields[0]], timeout=30.0)
            if stopped is None or stopped.returncode != 0:
                logger.warning("Ollama-Modell konnte nicht entladen werden: %s", fields[0])

    def _synthesize_qwen(self, text: str, output: Path) -> bool:
        python = self._project_path(self.config.qwen_python)
        worker = self.project_root / "tools" / "qwen_clone_synthesize.py"
        reference = (
            self._project_path(self.config.reference_audio)
            if self.config.reference_audio is not None
            else None
        )
        reference_text = (
            self._project_path(self.config.qwen_reference_text)
            if self.config.qwen_reference_text is not None
            else None
        )
        if not python.is_file():
            self._warn_once("qwen-python", "Qwen-TTS-Umgebung fehlt: %s", python)
            return False
        if reference is None or not reference.is_file():
            self._warn_once(
                "qwen-reference",
                "Qwen-Referenzaufnahme fehlt: %s",
                reference or "nicht konfiguriert",
            )
            return False
        if reference_text is None or not reference_text.is_file():
            self._warn_once(
                "qwen-reference-text",
                "Qwen-Referenztext fehlt: %s",
                reference_text or "nicht konfiguriert",
            )
            return False
        text_file = output.with_suffix(".txt")
        try:
            text_file.write_text(text, encoding="utf-8")
        except OSError as exc:
            logger.error("Qwen-TTS-Text konnte nicht vorbereitet werden: %s", exc)
            return False
        self._release_ollama_vram(self.config.qwen_release_ollama)
        command = [
            str(python),
            str(worker),
            "--text-file", str(text_file),
            "--output", str(output),
            "--reference", str(reference),
            "--reference-text-file", str(reference_text),
            "--language", self.config.language,
            "--model", self.config.qwen_model,
            "--device", self.config.qwen_device,
            "--dtype", self.config.qwen_dtype,
            "--temperature", str(self.config.qwen_temperature),
            "--top-p", str(self.config.qwen_top_p),
            "--top-k", str(self.config.qwen_top_k),
            "--repetition-penalty", str(self.config.qwen_repetition_penalty),
            "--volume", str(self.config.volume),
        ]
        result = self._run(command, timeout=self.config.qwen_timeout)
        if (
            result is None
            or result.returncode != 0
            or not output.is_file()
            or output.stat().st_size <= 44
        ):
            error = (result.stderr if result is not None else "").strip()
            logger.error("Qwen-TTS konnte Sprache nicht erzeugen: %s", error[-1500:])
            return False
        return True

    def _adjust_wav_pitch(self, audio_file: Path) -> bool:
        """Raise pitch by changing the WAV sample rate without lossy re-encoding."""
        if abs(self.config.pitch - 1.0) < 0.001:
            return True
        adjusted = audio_file.with_name(f"{audio_file.stem}-pitched.wav")
        try:
            with wave.open(str(audio_file), "rb") as source:
                channels = source.getnchannels()
                sample_width = source.getsampwidth()
                sample_rate = source.getframerate()
                frame_count = source.getnframes()
                compression_type = source.getcomptype()
                compression_name = source.getcompname()
                frames = source.readframes(frame_count)
            with wave.open(str(adjusted), "wb") as target:
                target.setnchannels(channels)
                target.setsampwidth(sample_width)
                target.setframerate(round(sample_rate * self.config.pitch))
                target.setcomptype(compression_type, compression_name)
                target.writeframes(frames)
            adjusted.replace(audio_file)
            return True
        except (OSError, wave.Error) as exc:
            logger.error("TTS-Tonhöhe konnte nicht angepasst werden: %s", exc)
            try:
                adjusted.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def _synthesize_espeak(self, text: str, output: Path) -> bool:
        executable = self.which("espeak-ng") or self.which("espeak")
        if executable is None:
            self._warn_once(
                "espeak-missing",
                "eSpeak-NG fehlt; installiere espeak-ng oder verwende Piper.",
            )
            return False
        result = self._run([
            executable,
            "-v",
            self.config.language,
            "-s",
            str(self.config.rate),
            "-a",
            str(min(200, round(self.config.volume * 100))),
            "-p",
            str(min(99, max(0, round(50 + (self.config.pitch - 1.0) * 100)))),
            "-w",
            str(output),
            text,
        ])
        if result is None or result.returncode != 0 or not output.is_file():
            error = (result.stderr if result is not None else "").strip()
            logger.error("eSpeak-NG konnte Sprache nicht erzeugen: %s", error[-500:])
            return False
        return True

    def _save_output(self, audio_file: Path) -> bool:
        destination = self.config.output_file
        if destination is None:
            return False
        destination = destination.expanduser()
        suffix = destination.suffix.lower()
        if suffix not in {".wav", ".mp3"}:
            logger.error("TTS-Dateiformat muss .wav oder .mp3 sein: %s", destination)
            return False
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if suffix == ".wav":
                shutil.copy2(audio_file, destination)
            else:
                try:
                    import lameenc
                except ImportError:
                    self._warn_once(
                        "mp3-encoder",
                        "MP3-Encoder fehlt; installiere: pip install lameenc",
                    )
                    return False
                with wave.open(str(audio_file), "rb") as source:
                    if source.getsampwidth() != 2:
                        logger.error("MP3-Export unterstützt nur 16-Bit-PCM.")
                        return False
                    encoder = lameenc.Encoder()
                    encoder.set_bit_rate(128)
                    encoder.set_in_sample_rate(source.getframerate())
                    encoder.set_channels(source.getnchannels())
                    encoder.set_quality(2)
                    encoded = encoder.encode(source.readframes(source.getnframes()))
                    encoded += encoder.flush()
                destination.write_bytes(encoded)
        except (OSError, ValueError, wave.Error) as exc:
            logger.error("TTS-Datei konnte nicht gespeichert werden: %s", exc)
            return False
        logger.info("TTS-Datei gespeichert: %s", destination)
        return True

    def _play(self, audio_file: Path) -> bool:
        player = self.which(self.config.audio_player)
        if player is None:
            self._warn_once(
                "audio-player",
                "Audio-Player '%s' fehlt; unter Debian hilft: sudo apt install alsa-utils",
                self.config.audio_player,
            )
            return False
        command = [player, "-q"]
        if self.config.audio_device:
            command.extend(["-D", self.config.audio_device])
        command.append(str(audio_file))
        result = self._run(command)
        if result is None or result.returncode != 0:
            error = (result.stderr if result is not None else "").strip()
            logger.error("Audioausgabe fehlgeschlagen: %s", error[-500:])
            return False
        return True

    def speak(self, text: str) -> bool:
        if not self.config.enabled:
            return False
        spoken = prepare_spoken_text(text, self.config.max_chars)
        if not spoken:
            return False
        engine = self.config.engine
        if engine not in {"piper", "chatterbox", "qwen", "espeak"}:
            self._warn_once(
                "engine",
                "Unbekannte TTS-Engine '%s'; erlaubt: piper, chatterbox, qwen, espeak.",
                engine,
            )
            return False
        with self._lock, tempfile.TemporaryDirectory(prefix="eva-tts-") as directory:
            output = Path(directory, "speech.wav")
            if engine == "piper":
                synthesized = self._synthesize_piper(spoken, output)
            elif engine == "chatterbox":
                synthesized = self._synthesize_chatterbox(spoken, output)
            elif engine == "qwen":
                synthesized = self._synthesize_qwen(spoken, output)
            else:
                synthesized = self._synthesize_espeak(spoken, output)
            if not synthesized:
                return False
            if self.config.output_file is not None:
                return self._save_output(output)
            return self._play(output)
