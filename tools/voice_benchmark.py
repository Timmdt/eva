from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

from core.env_loader import load_env_file
from voice.audio_player import AudioPlayer
from voice.config import VoiceConfig
from voice.metrics import nvidia_memory_mb
from voice.voice_service import VoiceService

TEXTS = [
    "Hallo, schön dich zu sehen.",
    "Ich habe die aktuellen Informationen geprüft und dabei etwas Interessantes gefunden.",
    (
        "Die RTX 2070 besitzt acht Gigabyte Grafikspeicher. EVA hält Gemma und XTTS "
        "gleichzeitig geladen, verarbeitet die Antwort in natürlichen Abschnitten und "
        "gibt fertige Audioblöcke sofort an die lokale Wiedergabe weiter."
    ),
]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    load_env_file(root / ".env")
    config = replace(VoiceConfig.from_env(), output_file=None)
    sink = AudioPlayer(volume=config.audio_volume, sink=lambda _pcm, _rate: None)
    service = VoiceService(config, project_root=root, audio_player=sink)
    idle = nvidia_memory_mb()
    if not service.start(wait=True):
        print(json.dumps(service.status(), indent=2, ensure_ascii=False))
        return 1
    results = []
    for text in TEXTS:
        started = time.perf_counter()
        request_id = service.start_response()
        if request_id is None:
            return 1
        service.feed_text(text)
        service.finish_response()
        completed = service.wait(config.worker_timeout)
        result = service.metrics.snapshot()
        result["wall_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
        result["completed"] = completed
        result["text"] = text
        results.append(result)
    payload = {
        "engine": "xtts_v2",
        "idle_gpu": idle,
        "loaded_gpu": nvidia_memory_mb(),
        "status": service.status(),
        "tests": results,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    service.shutdown()
    return 0 if all(item["completed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
