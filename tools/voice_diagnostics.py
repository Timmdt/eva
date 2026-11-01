from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path


def _run(command: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    from core.env_loader import load_env_file

    load_env_file(root / ".env")
    model = os.getenv("EVA_MODEL", "gemma4:e2b")
    gpu = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    gpu_values = (
        [value.strip() for value in gpu.stdout.splitlines()[0].split(",")]
        if gpu.returncode == 0 and gpu.stdout.strip()
        else []
    )
    ollama = _run(["ollama", "ps"])
    model_loaded = any(model in line for line in ollama.stdout.splitlines())
    processes = _run(["ps", "-eo", "args"])
    xtts_loaded = "voice.xtts_worker" in processes.stdout
    python = root / ".venv-xtts/bin/python"
    probe = (
        _run(
            [
                str(python),
                "-c",
                "import json,torch,TTS,transformers; print(json.dumps({"
                "'torch':torch.__version__,'cuda_runtime':torch.version.cuda,"
                "'cuda_available':torch.cuda.is_available(),'coqui':TTS.__version__,"
                "'transformers':transformers.__version__}))",
            ],
            timeout=30.0,
        )
        if python.is_file()
        else None
    )
    versions = json.loads(probe.stdout.splitlines()[-1]) if probe and probe.returncode == 0 else {}
    print(f"Python: {platform.python_version()}")
    print(f"Torch: {versions.get('torch', 'nicht installiert')}")
    print(f"Coqui-TTS: {versions.get('coqui', 'nicht installiert')}")
    print(f"Transformers: {versions.get('transformers', 'nicht installiert')}")
    print(f"CUDA runtime: {versions.get('cuda_runtime', 'unbekannt')}")
    print(f"CUDA: {'available' if versions.get('cuda_available') else 'unavailable'}")
    if gpu_values:
        print(f"GPU: {gpu_values[0]}")
        print(f"VRAM: {gpu_values[1]} MB total, {gpu_values[2]} MB used, {gpu_values[3]} MB free")
        print(f"NVIDIA driver: {gpu_values[4]}")
    else:
        print("GPU: nicht verfügbar")
    print(f"LLM ({model}) loaded: {'yes' if model_loaded else 'no'}")
    print(f"XTTS loaded: {'yes' if xtts_loaded else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
