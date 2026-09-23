from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _references() -> tuple[Path, ...]:
    raw = (
        os.getenv("EVA_VOICE_REFERENCES", "").strip()
        or os.getenv("EVA_VOICE_REFERENCE", "").strip()
        or os.getenv("EVA_TTS_REFERENCE_AUDIO", "").strip()
    )
    if not raw:
        return ()
    return tuple(Path(item.strip()).expanduser() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class VoiceConfig:
    enabled: bool = False
    engine: str = "xtts_v2"
    language: str = "de"
    references: tuple[Path, ...] = ()
    python: Path = Path(".venv-xtts/bin/python")
    model: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    device: str = "cuda"
    low_vram_mode: bool = True
    streaming: bool = True
    cache_speaker: bool = True
    cache_dir: Path = Path("voice/cache")
    worker_timeout: float = 900.0
    stream_chunk_size: int = 20
    temperature: float = 0.75
    repetition_penalty: float = 5.0
    top_k: int = 50
    top_p: float = 0.85
    speed: float = 0.98
    seed: int = 42
    trim_trailing_artifacts: bool = False
    sentence_pause_ms: int = 25
    gpt_cond_len: int = 12
    gpt_cond_chunk_len: int = 4
    audio_device: str = ""
    audio_volume: float = 1.0
    audio_player: str = "aplay"
    output_file: Path | None = None
    read_code: bool = False
    read_urls: bool = False
    pronunciation_rules: Path = Path("voice/pronunciation_rules.json")
    first_chunk_min_words: int = 5
    first_chunk_target_words: int = 8
    chunk_min_words: int = 10
    chunk_target_words: int = 18
    chunk_max_words: int = 30
    max_chunk_wait_ms: int = 350
    sentence_chunks_only: bool = True
    response_buffering: bool = True
    response_chunk_max_words: int = 55
    performance_debug: bool = False

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        output = os.getenv("EVA_TTS_OUTPUT_FILE", "").strip()
        return cls(
            enabled=_env_bool("EVA_TTS_ENABLED", False),
            engine=os.getenv("EVA_TTS_ENGINE", "xtts_v2").strip().lower(),
            language=(
                os.getenv("EVA_VOICE_LANGUAGE", "").strip()
                or os.getenv("EVA_TTS_LANGUAGE", "de").strip()
                or "de"
            ),
            references=_references(),
            python=Path(os.getenv("EVA_TTS_XTTS_PYTHON", ".venv-xtts/bin/python")),
            model=(
                os.getenv(
                    "EVA_TTS_XTTS_MODEL",
                    "tts_models/multilingual/multi-dataset/xtts_v2",
                ).strip()
                or "tts_models/multilingual/multi-dataset/xtts_v2"
            ),
            device=(os.getenv("EVA_TTS_DEVICE", "cuda").strip() or "cuda"),
            low_vram_mode=_env_bool("EVA_TTS_LOW_VRAM_MODE", True),
            streaming=_env_bool("EVA_TTS_STREAMING", True),
            cache_speaker=_env_bool("EVA_TTS_CACHE_SPEAKER", True),
            cache_dir=Path(os.getenv("EVA_TTS_CACHE_DIR", "voice/cache")),
            worker_timeout=_env_float("EVA_TTS_XTTS_TIMEOUT", 900.0, 30.0),
            stream_chunk_size=_env_int("EVA_TTS_STREAM_CHUNK_SIZE", 20, 4),
            temperature=_env_float("EVA_TTS_TEMPERATURE", 0.75, 0.01),
            repetition_penalty=_env_float("EVA_TTS_REPETITION_PENALTY", 5.0, 1.0),
            top_k=_env_int("EVA_TTS_TOP_K", 50, 1),
            top_p=_env_float("EVA_TTS_TOP_P", 0.85, 0.01),
            trim_trailing_artifacts=_env_bool(
                "EVA_TTS_TRIM_TRAILING_ARTIFACTS", False
            ),
            speed=_env_float("EVA_TTS_SPEED", 0.98, 0.5),
            seed=_env_int("EVA_TTS_SEED", 42, 0),
            sentence_pause_ms=_env_int("EVA_TTS_SENTENCE_PAUSE_MS", 25, 0),
            gpt_cond_len=_env_int("EVA_TTS_GPT_COND_LEN", 12, 2),
            gpt_cond_chunk_len=_env_int("EVA_TTS_GPT_COND_CHUNK_LEN", 4, 2),
            audio_device=os.getenv("EVA_AUDIO_DEVICE", "").strip(),
            audio_volume=_env_float("EVA_AUDIO_VOLUME", 1.0, 0.0),
            audio_player=os.getenv("EVA_TTS_AUDIO_PLAYER", "aplay").strip() or "aplay",
            output_file=Path(output).expanduser() if output else None,
            read_code=_env_bool("EVA_TTS_READ_CODE", False),
            read_urls=_env_bool("EVA_TTS_READ_URLS", False),
            pronunciation_rules=Path(os.getenv(
                "EVA_TTS_PRONUNCIATION_RULES", "voice/pronunciation_rules.json"
            )),
            first_chunk_min_words=_env_int("EVA_TTS_FIRST_CHUNK_MIN_WORDS", 5, 1),
            first_chunk_target_words=_env_int("EVA_TTS_FIRST_CHUNK_TARGET_WORDS", 8, 1),
            chunk_min_words=_env_int("EVA_TTS_CHUNK_MIN_WORDS", 10, 1),
            chunk_target_words=_env_int("EVA_TTS_CHUNK_TARGET_WORDS", 18, 1),
            chunk_max_words=_env_int("EVA_TTS_CHUNK_MAX_WORDS", 30, 2),
            max_chunk_wait_ms=_env_int("EVA_TTS_MAX_CHUNK_WAIT_MS", 350, 50),
            sentence_chunks_only=_env_bool("EVA_TTS_SENTENCE_CHUNKS_ONLY", True),
            response_buffering=_env_bool("EVA_TTS_RESPONSE_BUFFERING", True),
            response_chunk_max_words=_env_int("EVA_TTS_RESPONSE_CHUNK_MAX_WORDS", 55, 15),
            performance_debug=_env_bool(
                "EVA_PERFORMANCE_DEBUG",
                _env_bool("EVA_PERFORMANCE_LOGGING", False),
            ),
        )

    def resolved(self, project_root: Path) -> "VoiceConfig":
        def local(path: Path) -> Path:
            return path if path.is_absolute() else project_root / path

        return VoiceConfig(
            **{
                **self.__dict__,
                "references": tuple(local(path) for path in self.references),
                "python": local(self.python),
                "cache_dir": local(self.cache_dir),
                "pronunciation_rules": local(self.pronunciation_rules),
                "output_file": local(self.output_file) if self.output_file else None,
            }
        )
