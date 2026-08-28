from __future__ import annotations

import json
import os
import hmac
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from core.activity import INGESTION_LOCK, KEEP_AWAKE_FILE, activity_registry
from interfaces.presence_state import presence_fusion
from core.safe_shutdown import SafeShutdown


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
    fused = presence_fusion.current()
    expected_identity = fused.identity if fused.personal_context_allowed else None
    if getattr(eva, "current_identity", None) != expected_identity:
        eva.set_identity(expected_identity)
    return {"status": "ready" if ready else "degraded", "ollama": ollama_ok,
            "postgres": postgres_ok, "rag": rag_ok, "eva": True,
            "active_request": activity_registry.active("request"),
            "ingestion": activity_registry.active("ingestion") or INGESTION_LOCK.exists(),
            "critical_task": activity_registry.active("critical"),
            "keep_awake": KEEP_AWAKE_FILE.exists(),
            "presence": fused.to_dict()}


def handler_factory(check: Callable[[], dict[str, Any]], eva: Any | None = None) -> type[BaseHTTPRequestHandler]:
    class HealthHandler(BaseHTTPRequestHandler):
        def _json(self, status: int, value: dict[str, Any]) -> None:
            payload = json.dumps(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _authorized(self, env_name: str) -> bool:
            token = os.getenv(env_name, "").strip()
            if not token:
                return env_name == "EVA_PRESENCE_TOKEN"
            supplied = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            return hmac.compare_digest(token, supplied)

        def do_GET(self) -> None:
            if self.path != "/health":
                self.send_error(404)
                return
            self._json(200, check())

        def do_POST(self) -> None:
            if self.path == "/presence":
                if not self._authorized("EVA_PRESENCE_TOKEN"):
                    self._json(401, {"error": "unauthorized"})
                    return
                try:
                    length = min(int(self.headers.get("Content-Length", "0")), 16_384)
                    report = json.loads(self.rfile.read(length).decode("utf-8"))
                    fused = presence_fusion.update(report)
                    if eva is not None:
                        eva.set_identity(fused.identity if fused.personal_context_allowed else None)
                    self._json(202, fused.to_dict())
                except (ValueError, json.JSONDecodeError) as exc:
                    self._json(400, {"error": str(exc)})
                return
            if self.path == "/shutdown":
                if not self._authorized("EVA_SERVER_CONTROL_TOKEN"):
                    self._json(401, {"error": "unauthorized"})
                    return
                shutdown = SafeShutdown(
                    feature_enabled=True,
                    allow_shutdown=os.getenv("EVA_ALLOW_REMOTE_SHUTDOWN", "false").lower()
                    in {"1", "true", "yes", "on"},
                    keep_awake_file=Path(os.getenv(
                        "EVA_KEEP_AWAKE_FILE", str(KEEP_AWAKE_FILE))),
                    inhibit_file=Path(os.getenv(
                        "EVA_SHUTDOWN_INHIBIT_FILE", "/tmp/eva_shutdown_inhibit")),
                    boot_grace=float(os.getenv("EVA_REMOTE_SHUTDOWN_BOOT_GRACE", "600")),
                )
                fused = presence_fusion.current()
                if fused.room_presence:
                    self._json(409, {"status": "inhibited", "reason": "erlaubter Nutzer anwesend"})
                    return
                decision = shutdown.evaluate()
                if not decision.allowed:
                    self._json(409, {"status": "inhibited", "reason": decision.reason})
                    return
                self._json(202, {"status": "accepted", "dry_run": decision.dry_run})
                if decision.dry_run:
                    shutdown.request()
                else:
                    def delayed_shutdown() -> None:
                        time.sleep(0.25)
                        shutdown.request()
                    threading.Thread(target=delayed_shutdown, daemon=True).start()
                return
            self.send_error(404)

        def log_message(self, _format: str, *args: Any) -> None:
            return
    return HealthHandler


def serve(eva: Any, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), handler_factory(lambda: health_payload(eva), eva))
    server.serve_forever()


def start_in_thread(eva: Any, host: str = "127.0.0.1", port: int = 8765) -> threading.Thread:
    thread = threading.Thread(target=serve, args=(eva, host, port),
                              name="eva-health", daemon=True)
    thread.start()
    return thread
