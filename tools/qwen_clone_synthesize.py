from __future__ import annotations

import argparse
import sys
from pathlib import Path


LANGUAGE_ALIASES = {
    "de": "German",
    "de-de": "German",
    "en": "English",
    "en-us": "English",
    "en-gb": "English",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clone EVAs fixed Qwen3-TTS voice.")
    parser.add_argument("--text-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--reference-text-file", required=True, type=Path)
    parser.add_argument("--language", default="de")
    parser.add_argument(
        "--model",
        default="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    )
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", default="float16")
    parser.add_argument("--temperature", type=float, default=0.65)
    parser.add_argument("--top-p", type=float, default=0.85)
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--repetition-penalty", type=float, default=1.08)
    parser.add_argument("--volume", type=float, default=1.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    dtype_name = args.dtype.strip().lower()
    dtypes = {
        "float16": torch.float16,
        "fp16": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    if dtype_name not in dtypes:
        raise ValueError(f"Unsupported dtype: {args.dtype}")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA wurde angefordert, ist in Qwen-TTS aber nicht verfügbar.")

    text = args.text_file.read_text(encoding="utf-8").strip()
    reference_text = args.reference_text_file.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("Der Zieltext ist leer.")
    if not reference_text:
        raise ValueError("Der Referenztext ist leer.")
    if not args.reference.is_file():
        raise FileNotFoundError(args.reference)

    language_key = args.language.strip().lower()
    language = LANGUAGE_ALIASES.get(language_key, args.language.strip())
    model = Qwen3TTSModel.from_pretrained(
        args.model,
        device_map=args.device,
        dtype=dtypes[dtype_name],
        attn_implementation="sdpa",
    )
    wavs, sample_rate = model.generate_voice_clone(
        text=text,
        language=language,
        ref_audio=str(args.reference),
        ref_text=reference_text,
        x_vector_only_mode=False,
        non_streaming_mode=True,
        temperature=args.temperature,
        top_p=args.top_p,
        top_k=args.top_k,
        repetition_penalty=args.repetition_penalty,
    )
    audio = np.asarray(wavs[0], dtype=np.float32)
    if args.volume != 1.0:
        audio = np.clip(audio * max(0.0, args.volume), -1.0, 1.0)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, audio, sample_rate, subtype="PCM_16")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Qwen-TTS-Fehler: {exc}", file=sys.stderr)
        raise
