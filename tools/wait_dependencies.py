from __future__ import annotations

import os
import sys
import time
import urllib.request

from tools.rag_ingest import create_retriever


def ollama_ready() -> bool:
    try:
        with urllib.request.urlopen(
            os.getenv("EVA_OLLAMA_HEALTH_URL", "http://127.0.0.1:11434/api/tags"),
            timeout=2,
        ) as response:
            return response.status == 200
    except OSError:
        return False


def main() -> None:
    timeout = float(os.getenv("EVA_DEPENDENCY_TIMEOUT", "120"))
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            rag = create_retriever()
            if ollama_ready() and rag.health():
                rag.close()
                print("EVA dependencies ready")
                return
            rag.close()
        except Exception as exc:
            last_error = str(exc)
        time.sleep(2)
    print(f"EVA dependencies not ready after {timeout:.0f}s: {last_error}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
