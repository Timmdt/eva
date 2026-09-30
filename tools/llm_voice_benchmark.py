from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psutil


DEFAULT_PROMPTS: tuple[tuple[str, list[dict[str, str]]], ...] = (
    (
        "himmel",
        [{"role": "user", "content": "Erkläre mir einfach, warum der Himmel blau ist."}],
    ),
    (
        "training",
        [{"role": "user", "content": (
            "Ich habe morgen um 13:50 Training. Was könnte ich vorher essen?"
        )}],
    ),
    (
        "smalltalk",
        [{"role": "user", "content": (
            "Schreibe eine kurze natürliche Antwort auf: Hey, was machst du gerade?"
        )}],
    ),
    (
        "ram_vram",
        [{"role": "user", "content": (
            "Erkläre mir den Unterschied zwischen RAM und VRAM."
        )}],
    ),
    (
        "dialog",
        [
            {"role": "user", "content": (
                "Ich möchte einen leisen lokalen Sprachassistenten bauen. "
                "Antwortzeit ist wichtiger als sehr lange Antworten."
            )},
            {"role": "assistant", "content": (
                "Dann sollten Modell und Sprachausgabe dauerhaft geladen bleiben."
            )},
            {"role": "user", "content": (
                "Welche zwei Prioritäten würdest du daraus für die technische "
                "Umsetzung ableiten? Antworte natürlich und knapp."
            )},
        ],
    ),
    (
        "grimm",
        [{"role": "user", "content": (
            "Erzähle in etwa 140 Wörtern als ruhige Gute-Nacht-Geschichte das "
            "bekannte Grimm-Märchen Die Sterntaler. Erfinde keine anderen Figuren."
        )}],
    ),
)


def _post(path: str, payload: dict[str, Any], timeout: float) -> Any:
    request = urllib.request.Request(
        "http://127.0.0.1:11434" + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=timeout)


def _gpu_sample() -> tuple[float, float]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        memory, load = result.stdout.strip().splitlines()[0].split(",")
        return float(memory.strip()), float(load.strip())
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return 0.0, 0.0


def _ollama_rss_mb() -> float:
    total = 0
    for process in psutil.process_iter(["name", "cmdline", "memory_info"]):
        try:
            command = " ".join(process.info["cmdline"] or [])
            if "ollama" in (process.info["name"] or "").casefold() or "/ollama " in command:
                total += process.info["memory_info"].rss
        except (psutil.Error, TypeError):
            continue
    return total / 1024 / 1024


@dataclass
class ResourcePeak:
    gpu_vram_mb: float = 0.0
    gpu_load_percent: float = 0.0
    system_ram_used_mb: float = 0.0
    ollama_rss_mb: float = 0.0
    cpu_percent: float = 0.0


class ResourceMonitor:
    def __init__(self, interval: float = 0.25) -> None:
        self.interval = interval
        self.peak = ResourcePeak()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        gpu_memory, gpu_load = _gpu_sample()
        memory = psutil.virtual_memory()
        self.peak.gpu_vram_mb = max(self.peak.gpu_vram_mb, gpu_memory)
        self.peak.gpu_load_percent = max(self.peak.gpu_load_percent, gpu_load)
        self.peak.system_ram_used_mb = max(
            self.peak.system_ram_used_mb,
            (memory.total - memory.available) / 1024 / 1024,
        )
        self.peak.ollama_rss_mb = max(self.peak.ollama_rss_mb, _ollama_rss_mb())
        self.peak.cpu_percent = max(
            self.peak.cpu_percent,
            psutil.cpu_percent(interval=None),
        )

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._sample()

    def __enter__(self) -> "ResourceMonitor":
        psutil.cpu_percent(interval=None)
        self._sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._sample()


@dataclass
class RunResult:
    name: str
    ttft_ms: float
    first_sentence_ms: float
    total_ms: float
    output_tokens: int
    prompt_tokens: int
    tokens_per_second: float
    prompt_tokens_per_second: float
    response: str
    resources: ResourcePeak


def _rate(tokens: int, duration_ns: int) -> float:
    return tokens / (duration_ns / 1_000_000_000) if duration_ns > 0 else 0.0


def run_prompt(
    model: str,
    name: str,
    messages: list[dict[str, str]],
    *,
    context: int,
    num_predict: int,
    num_gpu: int | None,
    timeout: float,
) -> RunResult:
    system = {
        "role": "system",
        "content": (
            "Antworte ausschließlich auf natürlichem, grammatisch sauberem Deutsch. "
            "Sprich den Benutzer mit du an. Antworte direkt, ohne Denkprotokoll, "
            "Meta-Kommentar oder Quellenliste. Verwende vollständige Sätze."
        ),
    }
    payload = {
        "model": model,
        "messages": [system, *messages],
        "stream": True,
        "think": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.25,
            "top_p": 0.85,
            "num_ctx": context,
            "num_predict": num_predict,
            "repeat_penalty": 1.1,
        },
    }
    if num_gpu is not None:
        payload["options"]["num_gpu"] = num_gpu
    started = time.perf_counter()
    first_token_at = 0.0
    first_sentence_at = 0.0
    pieces: list[str] = []
    final: dict[str, Any] = {}

    with ResourceMonitor() as resources:
        with _post("/api/chat", payload, timeout) as response:
            for raw in response:
                event = json.loads(raw)
                content = str(event.get("message", {}).get("content", "") or "")
                if content:
                    if not first_token_at:
                        first_token_at = time.perf_counter()
                    pieces.append(content)
                    if (
                        not first_sentence_at
                        and re.search(r"[.!?](?:[\"'»)]*)?(?:\s|$)", "".join(pieces))
                    ):
                        first_sentence_at = time.perf_counter()
                if event.get("done"):
                    final = event

    finished = time.perf_counter()
    text = "".join(pieces).strip()
    eval_count = int(final.get("eval_count", 0))
    prompt_count = int(final.get("prompt_eval_count", 0))
    return RunResult(
        name=name,
        ttft_ms=round(
            ((first_token_at or finished) - started) * 1000.0,
            1,
        ),
        first_sentence_ms=round(
            ((first_sentence_at or finished) - started) * 1000.0,
            1,
        ),
        total_ms=round((finished - started) * 1000.0, 1),
        output_tokens=eval_count,
        prompt_tokens=prompt_count,
        tokens_per_second=round(
            _rate(eval_count, int(final.get("eval_duration", 0))),
            2,
        ),
        prompt_tokens_per_second=round(
            _rate(prompt_count, int(final.get("prompt_eval_duration", 0))),
            2,
        ),
        response=text,
        resources=resources.peak,
    )


def warm_model(model: str, context: int, num_gpu: int | None, timeout: float) -> tuple[float, ResourcePeak]:
    started = time.perf_counter()
    payload = {
        "model": model,
        "prompt": "Antworte nur mit: bereit",
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0,
            "num_ctx": context,
            "num_predict": 3,
        },
    }
    if num_gpu is not None:
        payload["options"]["num_gpu"] = num_gpu
    with ResourceMonitor() as resources:
        with _post("/api/generate", payload, timeout) as response:
            json.load(response)
    return round((time.perf_counter() - started) * 1000.0, 1), resources.peak


def model_info(model: str, timeout: float) -> dict[str, Any]:
    with _post("/api/show", {"model": model}, timeout) as response:
        data = json.load(response)
    return {
        "details": data.get("details", {}),
        "capabilities": data.get("capabilities", []),
        "model_info": {
            key: value
            for key, value in data.get("model_info", {}).items()
            if key in {
                "general.parameter_count",
                "general.architecture",
                "general.file_type",
                "general.finetune",
                "qwen2.context_length",
                "qwen3.context_length",
                "gemma3.context_length",
                "mistral3.context_length",
            }
        },
    }


def unload(model: str, timeout: float) -> None:
    try:
        with _post(
            "/api/generate",
            {"model": model, "prompt": "", "stream": False, "keep_alive": 0},
            timeout,
        ) as response:
            response.read()
    except OSError:
        pass


def aggregate(runs: list[RunResult]) -> dict[str, float]:
    def mean(name: str) -> float:
        return round(statistics.mean(float(getattr(run, name)) for run in runs), 2)
    return {
        "ttft_ms": mean("ttft_ms"),
        "first_sentence_ms": mean("first_sentence_ms"),
        "total_ms": mean("total_ms"),
        "tokens_per_second": mean("tokens_per_second"),
        "prompt_tokens_per_second": mean("prompt_tokens_per_second"),
        "peak_gpu_vram_mb": round(max(run.resources.gpu_vram_mb for run in runs), 1),
        "peak_gpu_load_percent": round(
            max(run.resources.gpu_load_percent for run in runs), 1
        ),
        "peak_system_ram_used_mb": round(
            max(run.resources.system_ram_used_mb for run in runs), 1
        ),
        "peak_ollama_rss_mb": round(
            max(run.resources.ollama_rss_mb for run in runs), 1
        ),
        "peak_cpu_percent": round(max(run.resources.cpu_percent for run in runs), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reproduzierbarer deutscher Ollama-Benchmark für EVA"
    )
    parser.add_argument("models", nargs="+")
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--num-predict", type=int, default=220)
    parser.add_argument("--num-gpu", type=int)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    with ResourceMonitor() as baseline_monitor:
        time.sleep(0.3)
    report: dict[str, Any] = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "context": args.context,
        "num_predict": args.num_predict,
        "num_gpu": args.num_gpu,
        "baseline": asdict(baseline_monitor.peak),
        "models": [],
    }

    for model in args.models:
        print(f"Benchmark: {model}", flush=True)
        cold_load_ms, warm_resources = warm_model(
            model, args.context, args.num_gpu, args.timeout)
        runs: list[RunResult] = []
        for name, messages in DEFAULT_PROMPTS:
            print(f"  {name}", flush=True)
            runs.append(
                run_prompt(
                    model,
                    name,
                    messages,
                    context=args.context,
                    num_predict=args.num_predict,
                    num_gpu=args.num_gpu,
                    timeout=args.timeout,
                )
            )
        entry = {
            "model": model,
            "info": model_info(model, args.timeout),
            "cold_load_ms": cold_load_ms,
            "warm_resources": asdict(warm_resources),
            "aggregate": aggregate(runs),
            "runs": [asdict(run) for run in runs],
        }
        report["models"].append(entry)
        unload(model, args.timeout)
        time.sleep(1.0)

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Gespeichert: {args.output}", flush=True)
    else:
        print(payload)


if __name__ == "__main__":
    main()
