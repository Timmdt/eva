from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from core.env_loader import load_env_file
from voice.metrics import nvidia_memory_mb


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark LLM streaming through EVA into XTTS.")
    parser.add_argument(
        "message",
        nargs="?",
        default="Erkläre mir in drei kurzen Sätzen, wie EVA Sprache parallel erzeugt.",
    )
    parser.add_argument("--turns", type=int, default=1)
    parser.add_argument("--direct-main-model", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    root = Path(__file__).resolve().parents[1]
    load_env_file(root / ".env")
    from core.eva import EVA

    eva = EVA(run_module_tests=False)
    benchmark_history: list[tuple[str, str]] = []
    eva._append_history = lambda user, answer: benchmark_history.append((user, answer))
    eva._update_conversation_context = lambda *_args, **_kwargs: None
    if args.direct_main_model:
        from core.intent_router import IntentDecision

        eva._route_intent = lambda _message: IntentDecision(action="NONE")
        eva._execute_intent = lambda _decision, _message: (None, None)
    if not eva.warm_llm():
        print("LLM-Warmup fehlgeschlagen.")
        return 1
    qwen_gpu = nvidia_memory_mb()
    if not eva.start_voice():
        print(json.dumps(eva.voice_status(), indent=2, ensure_ascii=False))
        return 1
    both_gpu = nvidia_memory_mb()
    turns = []
    try:
        for index in range(max(1, args.turns)):
            started = time.perf_counter()
            response = "".join(eva.receive_stream(args.message))
            generated_ms = (time.perf_counter() - started) * 1000.0
            voice_completed = eva.voice.wait(eva.voice.config.worker_timeout)
            metrics = dict(eva.last_performance)
            metrics.update(eva.voice.metrics.snapshot())
            metrics.update(
                {
                    "turn": index + 1,
                    "response_chars": len(response),
                    "pipeline_wall_ms": round(generated_ms, 1),
                    "history_has_full_response": bool(
                        benchmark_history and benchmark_history[-1][1] == response
                    ),
                    "voice_completed": voice_completed,
                    "gpu": nvidia_memory_mb(),
                }
            )
            turns.append(metrics)
        print(
            json.dumps(
                {
                    "model": eva.model,
                    "num_ctx": eva.cfg.get("llm_num_ctx"),
                    "qwen_gpu": qwen_gpu,
                    "qwen_and_xtts_gpu": both_gpu,
                    "voice": eva.voice_status(),
                    "turns": turns,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0 if all(turn["voice_completed"] for turn in turns) else 1
    finally:
        eva.voice.shutdown()
        if eva.rag is not None and hasattr(eva.rag, "close"):
            eva.rag.close()


if __name__ == "__main__":
    raise SystemExit(main())
