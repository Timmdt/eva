from __future__ import annotations

import logging
import queue
import shutil
import subprocess
import threading
import wave
from array import array
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioEvent:
    kind: str
    request_id: int
    pcm: bytes = b""
    sample_rate: int = 24_000


class AudioPlayer:
    def __init__(
        self,
        *,
        executable: str = "aplay",
        device: str = "",
        volume: float = 1.0,
        output_file: Path | None = None,
        on_first_sound: Callable[[], None] | None = None,
        sink: Callable[[bytes, int], None] | None = None,
    ) -> None:
        self.executable = executable
        self.device = device
        self.volume = volume
        self.output_file = output_file
        self.on_first_sound = on_first_sound
        self.sink = sink
        self._queue: queue.Queue[AudioEvent | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._current_id: int | None = None
        self._buffer = bytearray()
        self._sample_rate = 24_000
        self._first_written = False
        self._idle = threading.Event()
        self._idle.set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="eva-audio", daemon=True)
        self._thread.start()

    def begin(self, request_id: int) -> None:
        self.start()
        self._idle.clear()
        self._queue.put(AudioEvent("begin", request_id))

    def enqueue(self, request_id: int, pcm: bytes, sample_rate: int) -> None:
        if pcm:
            self._queue.put(AudioEvent("audio", request_id, pcm, sample_rate))

    def finish(self, request_id: int) -> None:
        self._queue.put(AudioEvent("end", request_id))

    def stop(self, request_id: int | None = None) -> None:
        with self._lock:
            if request_id is None or request_id == self._current_id:
                self._close_process(terminate=True)
                self._current_id = None
                self._buffer.clear()
        self._drain(request_id)
        self._idle.set()

    def shutdown(self) -> None:
        self.stop()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=2.0)

    def wait(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    def _drain(self, request_id: int | None) -> None:
        retained: list[AudioEvent | None] = []
        try:
            while True:
                item = self._queue.get_nowait()
                if item is None or (request_id is not None and item.request_id != request_id):
                    retained.append(item)
        except queue.Empty:
            pass
        for item in retained:
            self._queue.put(item)

    def _scaled(self, pcm: bytes) -> bytes:
        if abs(self.volume - 1.0) < 0.001:
            return pcm
        samples = array("h")
        samples.frombytes(pcm)
        for index, sample in enumerate(samples):
            samples[index] = max(-32768, min(32767, round(sample * self.volume)))
        return samples.tobytes()

    def _open_process(self, sample_rate: int) -> None:
        if self.output_file is not None or self.sink is not None:
            return
        player = shutil.which(self.executable)
        if player is None:
            raise FileNotFoundError(f"Audio-Player '{self.executable}' wurde nicht gefunden.")
        command = [player, "-q", "-t", "raw", "-f", "S16_LE", "-r", str(sample_rate), "-c", "1"]
        if self.device:
            command.extend(["-D", self.device])
        self._process = subprocess.Popen(command, stdin=subprocess.PIPE)

    def _close_process(self, *, terminate: bool = False) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            if terminate and process.poll() is None:
                process.terminate()
            process.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass

    def _save_output(self) -> None:
        if self.output_file is None or not self._buffer:
            return
        destination = self.output_file
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.suffix.lower() == ".wav":
            with wave.open(str(destination), "wb") as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(self._sample_rate)
                target.writeframes(self._buffer)
            return
        if destination.suffix.lower() != ".mp3":
            raise ValueError("EVA_TTS_OUTPUT_FILE muss auf .wav oder .mp3 enden.")
        import lameenc

        encoder = lameenc.Encoder()
        encoder.set_bit_rate(128)
        encoder.set_in_sample_rate(self._sample_rate)
        encoder.set_channels(1)
        encoder.set_quality(2)
        destination.write_bytes(encoder.encode(bytes(self._buffer)) + encoder.flush())

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                return
            try:
                with self._lock:
                    if event.kind == "begin":
                        self._close_process(terminate=True)
                        self._current_id = event.request_id
                        self._buffer.clear()
                        self._first_written = False
                    elif event.kind == "audio" and event.request_id == self._current_id:
                        pcm = self._scaled(event.pcm)
                        self._sample_rate = event.sample_rate
                        if self.output_file is not None:
                            self._buffer.extend(pcm)
                        elif self.sink is not None:
                            self.sink(pcm, event.sample_rate)
                        else:
                            if self._process is None:
                                self._open_process(event.sample_rate)
                            if self._process and self._process.stdin:
                                self._process.stdin.write(pcm)
                                self._process.stdin.flush()
                        if not self._first_written:
                            self._first_written = True
                            if self.on_first_sound:
                                self.on_first_sound()
                    elif event.kind == "end" and event.request_id == self._current_id:
                        self._close_process()
                        self._save_output()
                        self._current_id = None
                        self._buffer.clear()
                        self._idle.set()
            except Exception:
                logger.exception("Audioausgabe ist fehlgeschlagen.")
                self._idle.set()
