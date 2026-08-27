from __future__ import annotations

import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


def health_payload(eva: Any) -> dict[str, Any]:
    ollama_ok = False
    try:
        with urllib.request.urlopen(
            os.getenv("EVA_OLLAMA_HEALTH_URL", "http://127.0.0.1:11434/api/tags"),
            timeout=1.5,
        ) as response:
            ollama_ok = response.status == 200
    except OSError:
        pass
    rag_ok = bool(eva.rag and getattr(eva.rag, "health", lambda: False)())
    postgres_ok = rag_ok
    ready = ollama_ok and postgres_ok and rag_ok
    return {"status": "ready" if ready else "degraded", "ollama": ollama_ok,
            "postgres": postgres_ok, "rag": rag_ok}


def handler_factory(check: Callable[[], dict[str, Any]]) -> type[BaseHTTPRequestHandler]:
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/health":
                self.send_error(404)
                return
            payload = json.dumps(check()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *args: Any) -> None:
            return
    return HealthHandler


def serve(eva: Any, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), handler_factory(lambda: health_payload(eva)))
    server.serve_forever()


def start_in_thread(eva: Any, host: str = "127.0.0.1", port: int = 8765) -> threading.Thread:
    thread = threading.Thread(target=serve, args=(eva, host, port),
                              name="eva-health", daemon=True)
    thread.start()
    return thread
