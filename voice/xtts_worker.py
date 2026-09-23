from __future__ import annotations

import argparse
import base64
import contextlib
import json
import queue
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

from .xtts_engine import XTTSEngine


class Protocol:
    def __init__(self) -> None:
        self.stdout = sys.stdout
        self.lock = threading.Lock()

    def emit(self, event: str, **values: Any) -> None:
        payload = json.dumps({"event": event, **values}, ensure_ascii=False)
        with self.lock:
            self.stdout.write(payload + "\n")
            self.stdout.flush()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--language", default="de")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--reference", action="append", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--cache-speaker", action="store_true")
    parser.add_argument("--low-vram", action="store_true")
    parser.add_argument("--stream-chunk-size", type=int, default=20)
    parser.add_argument("--no-streaming", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.75)
    parser.add_argument("--repetition-penalty", type=float, default=5.0)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--top-p", type=float, default=0.85)
    parser.add_argument("--speed", type=float, default=0.98)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--trim-trailing-artifacts", action="store_true")
    parser.add_argument("--gpt-cond-len", type=int, default=12)
    parser.add_argument("--gpt-cond-chunk-len", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    protocol = Protocol()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            engine = XTTSEngine(
                model_name=args.model,
                references=args.reference,
                language=args.language,
                device=args.device,
                cache_dir=args.cache_dir,
                cache_speaker=args.cache_speaker,
                low_vram_mode=args.low_vram,
                streaming=not args.no_streaming,
                stream_chunk_size=args.stream_chunk_size,
                temperature=args.temperature,
                repetition_penalty=args.repetition_penalty,
                top_k=args.top_k,
                top_p=args.top_p,
                trim_trailing_artifacts=args.trim_trailing_artifacts,
                speed=args.speed,
                seed=args.seed,
                gpt_cond_len=args.gpt_cond_len,
                gpt_cond_chunk_len=args.gpt_cond_chunk_len,
            )
            info = engine.load()
            info["warmup_ms"] = engine.warmup()
        protocol.emit("ready", **info)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        protocol.emit("fatal", error=str(exc))
        return 1

    tasks: queue.Queue[dict[str, Any] | None] = queue.Queue()
    canceled: set[int] = set()
    current_id: int | None = None
    cancel = threading.Event()

    def synthesize() -> None:
        nonlocal current_id, cancel
        while True:
            task = tasks.get()
            if task is None:
                return
            request_id = int(task["request_id"])
            kind = str(task["kind"])
            if kind == "finish":
                if request_id not in canceled:
                    protocol.emit("response_end", request_id=request_id, metrics=engine.status())
                canceled.discard(request_id)
                continue
            if request_id in canceled:
                continue
            current_id = request_id
            cancel = threading.Event()
            try:
                protocol.emit("chunk_start", request_id=request_id)
                first = True
                with contextlib.redirect_stdout(sys.stderr):
                    for pcm in engine.stream_pcm(str(task["text"]), cancel):
                        if request_id in canceled:
                            break
                        protocol.emit(
                            "audio",
                            request_id=request_id,
                            sample_rate=engine.sample_rate,
                            first=first,
                            pcm=base64.b64encode(pcm).decode("ascii"),
                        )
                        first = False
                protocol.emit(
                    "chunk_end",
                    request_id=request_id,
                    canceled=cancel.is_set() or request_id in canceled,
                    metrics=getattr(engine, "last_metrics", {}),
                )
            except Exception as exc:
                traceback.print_exc(file=sys.stderr)
                protocol.emit("error", request_id=request_id, error=str(exc))
            finally:
                current_id = None

    thread = threading.Thread(target=synthesize, name="xtts-synthesis", daemon=True)
    thread.start()
    for line in sys.stdin:
        try:
            command = json.loads(line)
            action = command.get("command")
            request_id = int(command.get("request_id", 0))
            if action == "synthesize":
                tasks.put({"kind": "synthesize", "request_id": request_id, "text": command["text"]})
            elif action == "finish":
                tasks.put({"kind": "finish", "request_id": request_id})
            elif action == "stop":
                canceled.add(request_id)
                if current_id == request_id:
                    cancel.set()
                protocol.emit("stopped", request_id=request_id)
            elif action == "status":
                protocol.emit("status", **engine.status())
            elif action == "shutdown":
                cancel.set()
                tasks.put(None)
                thread.join(timeout=5.0)
                return 0
        except Exception as exc:
            protocol.emit("error", request_id=0, error=f"Ungültiger Worker-Befehl: {exc}")
    cancel.set()
    tasks.put(None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
