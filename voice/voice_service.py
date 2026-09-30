from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .audio_player import AudioPlayer
from .config import VoiceConfig
from .metrics import VoiceMetrics, nvidia_memory_mb
from .text_chunker import SpeechChunker


logger = logging.getLogger(__name__)


class VoiceService:
    """Persistent XTTS subprocess plus non-blocking text and audio queues."""

    def __init__(
        self,
        config: VoiceConfig | None = None,
        *,
        project_root: Path | None = None,
        audio_player: AudioPlayer | None = None,
    ) -> None:
        root = project_root or Path(__file__).resolve().parents[1]
        self.project_root = root
        self.config = (config or VoiceConfig.from_env()).resolved(root)
        self.metrics = VoiceMetrics()
        self.chunker = SpeechChunker(self.config)
        self.audio = audio_player or AudioPlayer(
            executable=self.config.audio_player,
            device=self.config.audio_device,
            volume=self.config.audio_volume,
            output_file=self.config.output_file,
            on_first_sound=lambda: self.metrics.mark("first_sound_at"),
        )
        if audio_player is not None and self.audio.on_first_sound is None:
            self.audio.on_first_sound = lambda: self.metrics.mark("first_sound_at")
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._ready_event = threading.Event()
        self._write_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._request_id = 0
        self._active_id: int | None = None
        self._ready = False
        self._error = ""
        self._worker_status: dict[str, Any] = {}
        self._response_fragments: list[str] = []

    @property
    def enabled(self) -> bool:
        return self.config.enabled and self.config.engine in {"xtts", "xtts_v2"}

    @property
    def ready(self) -> bool:
        return self.enabled and self._ready

    def start(self, *, wait: bool = True) -> bool:
        """Startet den XTTS-Unterprozess und wartet optional auf seine Bereitschaft."""
        if not self.enabled:
            return False
        if self._process is not None and self._process.poll() is None:
            return self._ready
        if not self.config.python.is_file():
            self._error = f"XTTS-Python fehlt: {self.config.python}"
            logger.error(self._error)
            return False
        missing = [path for path in self.config.references if not path.is_file()]
        if not self.config.references or missing:
            self._error = f"Voice-Referenz fehlt: {missing or 'nicht konfiguriert'}"
            logger.error(self._error)
            return False
        logger.info("Voice: loading")
        command = [
            str(self.config.python), "-m", "voice.xtts_worker",
            "--model", self.config.model,
            "--language", self.config.language,
            "--device", self.config.device,
            "--cache-dir", str(self.config.cache_dir),
            "--stream-chunk-size", str(self.config.stream_chunk_size),
            "--temperature", str(self.config.temperature),
            "--repetition-penalty", str(self.config.repetition_penalty),
            "--top-k", str(self.config.top_k),
            "--top-p", str(self.config.top_p),
            "--speed", str(self.config.speed),
            "--seed", str(self.config.seed),
            "--gpt-cond-len", str(self.config.gpt_cond_len),
            "--gpt-cond-chunk-len", str(self.config.gpt_cond_chunk_len),
        ]
        for reference in self.config.references:
            command.extend(["--reference", str(reference)])
        if not self.config.streaming:
            command.append("--no-streaming")
        if self.config.trim_trailing_artifacts:
            command.append("--trim-trailing-artifacts")
        if self.config.cache_speaker:
            command.append("--cache-speaker")
        if self.config.low_vram_mode:
            command.append("--low-vram")
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        self._ready_event.clear()
        self._process = subprocess.Popen(
            command,
            cwd=self.project_root,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_events, name="eva-voice-events", daemon=True)
        self._stderr_reader = threading.Thread(target=self._read_stderr, name="eva-voice-log", daemon=True)
        self._reader.start()
        self._stderr_reader.start()
        self.audio.start()
        if not wait:
            return True
        if not self._ready_event.wait(self.config.worker_timeout):
            self._error = "XTTS-Start hat das Zeitlimit überschritten."
            logger.error(self._error)
            self.stop()
            return False
        return self._ready

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            if line.strip():
                logger.info("[XTTS] %s", line.rstrip())

    def _read_events(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Ungültige XTTS-Worker-Ausgabe: %s", line.rstrip())
                continue
            kind = event.get("event")
            if kind == "ready":
                self._worker_status.update(event)
                self.metrics.update_worker(event)
                self._ready = True
                self._error = ""
                logger.info("Voice: model ready")
                logger.info("Voice: speaker ready")
                logger.info("Voice: warmed up")
                logger.info("Voice: ready")
                self._ready_event.set()
            elif kind == "fatal":
                self._error = str(event.get("error", "XTTS konnte nicht geladen werden."))
                self._ready = False
                self._ready_event.set()
                logger.error("Voice: %s", self._error)
            elif kind == "audio":
                request_id = int(event["request_id"])
                if request_id != self._active_id:
                    continue
                if event.get("first"):
                    self.metrics.mark("first_audio_at")
                self.audio.enqueue(
                    request_id,
                    base64.b64decode(event["pcm"]),
                    int(event.get("sample_rate", 24_000)),
                )
            elif kind in {"chunk_end", "response_end", "status"}:
                values = event.get("metrics", event)
                if isinstance(values, dict):
                    self._worker_status.update(values)
                    self.metrics.update_worker(values)
                if (
                    kind == "chunk_end"
                    and not event.get("canceled")
                    and int(event.get("request_id", 0)) == self._active_id
                    and self.config.sentence_pause_ms > 0
                ):
                    sample_rate = int(self._worker_status.get("sample_rate", 24_000))
                    samples = round(sample_rate * self.config.sentence_pause_ms / 1000.0)
                    self.audio.enqueue(self._active_id, b"\x00\x00" * samples, sample_rate)
                if kind == "response_end" and int(event.get("request_id", 0)) == self._active_id:
                    self.metrics.mark("synthesis_finished_at")
                    self.audio.finish(self._active_id)
                    self._active_id = None
                    if self.config.performance_debug:
                        logger.info("EVA VOICE PERFORMANCE %s", json.dumps(self.metrics.snapshot(), sort_keys=True))
            elif kind == "error":
                self._error = str(event.get("error", "XTTS-Fehler"))
                logger.error("Voice: %s", self._error)
        if process.poll() is not None and not self._ready_event.is_set():
            self._error = f"XTTS-Worker wurde mit Code {process.returncode} beendet."
            self._ready_event.set()

    def _send(self, command: str, **values: Any) -> bool:
        process = self._process
        if process is None or process.poll() is not None or process.stdin is None:
            return False
        line = json.dumps({"command": command, **values}, ensure_ascii=False)
        try:
            with self._write_lock:
                process.stdin.write(line + "\n")
                process.stdin.flush()
            return True
        except OSError:
            logger.exception("XTTS-Worker ist nicht erreichbar.")
            return False

    def start_response(self) -> int | None:
        """Bricht alte Audioausgabe ab und öffnet einen neuen Sprachauftrag."""
        if not self.ready:
            return None
        self.stop()
        with self._request_lock:
            self._request_id += 1
            self._active_id = self._request_id
            request_id = self._request_id
        self.chunker.reset()
        self._response_fragments.clear()
        self.metrics.begin()
        self.audio.begin(request_id)
        return request_id

    def feed_text(self, fragment: str) -> list[str]:
        """Nimmt weiteren Antworttext auf und sendet fertige Abschnitte an XTTS."""
        request_id = self._active_id
        if request_id is None:
            return []
        if self.config.response_buffering:
            self._response_fragments.append(fragment)
            return []
        chunks = self.chunker.feed(fragment)
        for chunk in chunks:
            self.metrics.mark("first_text_chunk_at")
            self._send("synthesize", request_id=request_id, text=chunk)
        return chunks

    def finish_response(self) -> list[str]:
        """Schließt die Antwort ab und startet die Synthese verbleibender Abschnitte."""
        request_id = self._active_id
        if request_id is None:
            return []
        if self.config.response_buffering:
            chunks = self.chunker.complete_response("".join(self._response_fragments))
            self._response_fragments.clear()
            self.chunker.reset()
        else:
            chunks = self.chunker.flush()
        for chunk in chunks:
            self.metrics.mark("first_text_chunk_at")
            self._send("synthesize", request_id=request_id, text=chunk)
        self._send("finish", request_id=request_id)
        return chunks

    def speak(self, text: str) -> bool:
        """Spricht einen bereits vollständigen Text als einzelnen Auftrag."""
        if not self.ready and not self.start(wait=True):
            return False
        if self.start_response() is None:
            return False
        self.feed_text(text)
        self.finish_response()
        return True

    def stop(self) -> None:
        """Bricht nur den aktuell laufenden Sprachauftrag ab."""
        request_id = self._active_id
        self.chunker.reset()
        self._response_fragments.clear()
        if request_id is not None:
            self._send("stop", request_id=request_id)
            self.audio.stop(request_id)
            self._active_id = None

    def wait(self, timeout: float | None = None) -> bool:
        """Wartet, bis die aktuelle Audioausgabe beendet ist."""
        return self.audio.wait(timeout)

    def status(self) -> dict[str, Any]:
        """Liefert Bereitschaft, Gerät, Fehler und Laufzeitmesswerte."""
        gpu = nvidia_memory_mb()
        return {
            "enabled": self.enabled,
            "ready": self.ready,
            "model": "xtts_v2" if self.enabled else self.config.engine,
            "device": self.config.device,
            "gpu": self._worker_status.get("gpu") or gpu.get("gpu"),
            "error": self._error or None,
            "active": self._active_id is not None,
            "metrics": self.metrics.snapshot(),
        }

    def shutdown(self) -> None:
        """Beendet den Worker und die Audioausgabe vollständig."""
        self.stop()
        self._send("shutdown")
        process = self._process
        if process is not None:
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.terminate()
        self.audio.shutdown()
        self._ready = False
