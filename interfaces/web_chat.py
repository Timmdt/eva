from __future__ import annotations

import logging
import mimetypes
import os
import secrets
import shutil
import threading
from pathlib import Path
from typing import Any, Iterator


logger = logging.getLogger(__name__)


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


class WebChat:
    """Verbindet EVAs bestehenden Antwortstream mit dem Browser-Frontend."""

    def __init__(self, eva: Any, project_root: Path) -> None:
        self.eva = eva
        self.project_root = project_root
        self.max_message_chars = _env_int("EVA_WEB_MAX_MESSAGE_CHARS", 4000)
        self.history_messages = _env_int("EVA_WEB_HISTORY_MESSAGES", 40)
        self.voice_timeout = float(os.getenv("EVA_WEB_VOICE_TIMEOUT", "900"))
        self.audio_retention = _env_int("EVA_WEB_AUDIO_RETENTION", 20)
        configured_dir = Path(os.getenv("EVA_WEB_AUDIO_DIR", "data/web_audio"))
        self.audio_dir = (
            configured_dir
            if configured_dir.is_absolute()
            else self.project_root / configured_dir
        )
        self._chat_lock = threading.Lock()
        self._audio_lock = threading.Lock()
        self._audio_files: dict[str, Path] = {}

    @property
    def busy(self) -> bool:
        return self._chat_lock.locked()

    def begin_chat(self) -> bool:
        return self._chat_lock.acquire(blocking=False)

    def history(self) -> list[dict[str, str]]:
        raw = list(getattr(self.eva, "state", {}).get("history", []))
        normalizer = getattr(self.eva, "_normalize_history", None)
        if callable(normalizer):
            raw = normalizer(raw)
        messages: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str):
                messages.append({"role": role, "content": content})
        return messages[-self.history_messages :]

    def status(self) -> dict[str, Any]:
        voice = getattr(self.eva, "voice", None)
        config = getattr(voice, "config", None)
        output_file = getattr(config, "output_file", None)
        voice_status = getattr(
            self.eva,
            "voice_status",
            lambda: {"enabled": False, "ready": False},
        )()
        return {
            "name": str(getattr(self.eva, "name", "EVA")),
            "busy": self.busy,
            "voice": voice_status,
            "browser_audio": bool(output_file),
        }

    @staticmethod
    def _signature(path: Path | None) -> tuple[int, int] | None:
        if path is None:
            return None
        try:
            stat = path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def _voice_output(self) -> Path | None:
        voice = getattr(self.eva, "voice", None)
        config = getattr(voice, "config", None)
        output = getattr(config, "output_file", None)
        return Path(output) if output else None

    def _snapshot_audio(
        self,
        source: Path | None,
        before: tuple[int, int] | None,
    ) -> str | None:
        if source is None:
            return None
        voice = getattr(self.eva, "voice", None)
        wait = getattr(voice, "wait", None)
        if callable(wait) and not wait(self.voice_timeout):
            logger.warning("Browser-Audio wurde nicht rechtzeitig fertig.")
            return None
        after = self._signature(source)
        if after is None or after == before:
            return None
        suffix = source.suffix.lower()
        if suffix not in {".mp3", ".wav"}:
            return None

        audio_id = secrets.token_hex(16)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        destination = self.audio_dir / f"{audio_id}{suffix}"
        shutil.copyfile(source, destination)
        with self._audio_lock:
            self._audio_files[audio_id] = destination
            self._cleanup_audio_locked()
        return audio_id

    def _cleanup_audio_locked(self) -> None:
        ordered = sorted(
            self._audio_files.items(),
            key=lambda item: item[1].stat().st_mtime_ns if item[1].exists() else 0,
            reverse=True,
        )
        for audio_id, path in ordered[self.audio_retention :]:
            self._audio_files.pop(audio_id, None)
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def audio(self, audio_id: str) -> tuple[Path, str] | None:
        if len(audio_id) != 32 or any(
            char not in "0123456789abcdef" for char in audio_id
        ):
            return None
        with self._audio_lock:
            path = self._audio_files.get(audio_id)
        if path is None or not path.is_file():
            return None
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return path, media_type

    def events(self, message: str) -> Iterator[dict[str, Any]]:
        """Nach begin_chat vollständig konsumieren, damit der Lock frei wird."""
        source = self._voice_output()
        before = self._signature(source)
        try:
            yield {"type": "start"}
            for chunk in self.eva.receive_stream(message):
                if chunk:
                    yield {"type": "delta", "text": chunk}
            audio_id = self._snapshot_audio(source, before)
            yield {
                "type": "done",
                "audio_url": f"/api/audio/{audio_id}" if audio_id else None,
            }
        except Exception as exc:
            logger.exception("Webchat-Anfrage ist fehlgeschlagen.")
            yield {"type": "error", "error": str(exc)}
        finally:
            self._chat_lock.release()
