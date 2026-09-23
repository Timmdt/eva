#!/usr/bin/env python3
from __future__ import annotations

import argparse
import wave
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a WAV with Chatterbox.")
    parser.add_argument("--text-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--language", default="de")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--exaggeration", type=float, default=0.60)
    parser.add_argument("--cfg-weight", type=float, default=0.35)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--model-version", choices=("v2", "v3"), default="v3")
    parser.add_argument("--volume", type=float, default=1.0)
    return parser


def select_device(requested: str) -> str:
    import torch

    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA wurde angefordert, ist aber nicht verfügbar.")
    return requested


def write_wav(output: Path, audio, sample_rate: int, volume: float) -> None:
    import torch

    samples = audio.detach().float().cpu().squeeze()
    if samples.ndim != 1:
        raise ValueError(f"Unerwartete Chatterbox-Audioform: {tuple(samples.shape)}")
    samples = (samples * max(0.0, volume)).clamp(-1.0, 1.0)
    pcm = (samples * 32767.0).round().to(torch.int16).numpy().tobytes()
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(pcm)


def main() -> int:
    args = build_parser().parse_args()
    text = args.text_file.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("Der Chatterbox-Text ist leer.")
    if args.reference is not None and not args.reference.is_file():
        raise FileNotFoundError(f"Referenzaufnahme fehlt: {args.reference}")

    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    device = select_device(args.device)
    model = ChatterboxMultilingualTTS.from_pretrained(
        device=device,
        t3_model=args.model_version,
    )
    generate_options = {
        "language_id": args.language,
        "exaggeration": min(1.0, max(0.0, args.exaggeration)),
        "cfg_weight": min(1.0, max(0.0, args.cfg_weight)),
    }
    if args.reference is not None:
        generate_options["audio_prompt_path"] = str(args.reference)
    audio = model.generate(text, **generate_options)
    write_wav(args.output, audio, model.sr, args.volume)
    print(f"Chatterbox WAV gespeichert: {args.output} ({device}, {model.sr} Hz)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
