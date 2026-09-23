from __future__ import annotations

import argparse
import math
import os
import sys
import wave
from array import array
from pathlib import Path

from .config import VoiceConfig
from core.env_loader import load_env_file


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate EVA voice references and cache XTTS conditioning.")
    parser.add_argument("references", nargs="*", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def _ensure_xtts_python(config: VoiceConfig) -> None:
    try:
        import TTS  # noqa: F401
        return
    except ImportError:
        pass
    python = config.python
    if not python.is_file():
        raise RuntimeError(f"XTTS-Umgebung fehlt: {python}")
    os.execv(str(python), [str(python), "-m", "voice.prepare_voice", *sys.argv[1:]])


def inspect_wav(path: Path) -> dict[str, float | int | str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        sample_rate = source.getframerate()
        frames = source.getnframes()
        compression = source.getcomptype()
        data = source.readframes(frames)
    if compression != "NONE":
        raise ValueError(f"{path}: komprimierte WAV wird nicht unterstützt ({compression}).")
    if width != 2:
        raise ValueError(f"{path}: erwartet werden 16-Bit-PCM, gefunden: {width * 8} Bit.")
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        raise ValueError(f"{path}: WAV enthält keine Samples.")
    peak = max(abs(value) for value in samples)
    rms = math.sqrt(sum(value * value for value in samples) / len(samples))
    clipping = sum(abs(value) >= 32760 for value in samples) / len(samples)
    silence = sum(abs(value) < 160 for value in samples) / len(samples)
    duration = frames / sample_rate
    return {
        "path": str(path),
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_seconds": round(duration, 2),
        "peak_dbfs": round(20 * math.log10(max(peak, 1) / 32767), 2),
        "rms_dbfs": round(20 * math.log10(max(rms, 1) / 32767), 2),
        "silence_percent": round(silence * 100, 1),
        "clipping_percent": round(clipping * 100, 3),
    }


def main() -> int:
    args = _arguments()
    root = Path(__file__).resolve().parents[1]
    load_env_file(root / ".env")
    config = VoiceConfig.from_env().resolved(root)
    references = [path if path.is_absolute() else root / path for path in args.references]
    references = references or list(config.references)
    if not references:
        print("Keine Referenz konfiguriert. Setze EVA_VOICE_REFERENCE oder übergib eine WAV-Datei.", file=sys.stderr)
        return 2
    for reference in references:
        info = inspect_wav(reference)
        print(
            f"{info['path']}: {info['duration_seconds']} s, {info['sample_rate']} Hz, "
            f"{info['channels']} Kanal/Kanäle, RMS {info['rms_dbfs']} dBFS, "
            f"Stille {info['silence_percent']} %, Clipping {info['clipping_percent']} %"
        )
        if float(info["duration_seconds"]) < 3.0:
            print("WARNUNG: Referenz ist kürzer als 3 Sekunden.")
        if float(info["clipping_percent"]) > 0.1:
            print("WARNUNG: Referenz enthält auffälliges Clipping.")
    if args.validate_only:
        return 0
    _ensure_xtts_python(config)
    from .xtts_engine import XTTSEngine
    engine = XTTSEngine(
        model_name=config.model,
        references=references,
        language=config.language,
        device=config.device,
        cache_dir=config.cache_dir,
        cache_speaker=config.cache_speaker,
        low_vram_mode=config.low_vram_mode,
        stream_chunk_size=config.stream_chunk_size,
    )
    info = engine.load()
    print(
        f"XTTS bereit: {info['device']}, Modell {config.model}, "
        f"Laden {info['load_ms']:.0f} ms, Conditioning {info['conditioning_ms']:.0f} ms, "
        f"Cache {'Treffer' if info['conditioning_cache_hit'] else 'neu erstellt'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
