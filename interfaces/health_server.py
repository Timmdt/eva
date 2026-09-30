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
from interfaces.presence_automation import (
    PresenceAutomation,
    PresenceAutomationConfig,
)
from interfaces.presence_state import presence_fusion
from interfaces.web_chat import WebChat
from core.safe_shutdown import SafeShutdown


def health_payload(
    eva: Any,
    automation: PresenceAutomation | None = None,
) -> dict[str, Any]:
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
    voice_status = {"enabled": False, "ready": False}
    status_provider = getattr(eva, "voice_status", None)
    if callable(status_provider):
        try:
            voice_status = status_provider()
        except Exception:
            voice_status = {
                "enabled": True, "ready": False, "error": "status unavailable",
            }
    ready = ollama_ok and postgres_ok and rag_ok and (
        not voice_status.get("enabled") or voice_status.get("ready")
    )
    fused = presence_fusion.current()
    expected_identity = fused.identity if fused.personal_context_allowed else None
    if getattr(eva, "current_identity", None) != expected_identity:
        eva.set_identity(expected_identity)
    payload = {"status": "ready" if ready else "degraded", "ollama": ollama_ok,
            "postgres": postgres_ok, "rag": rag_ok, "eva": True,
            "active_request": activity_registry.active("request"),
            "ingestion": activity_registry.active("ingestion") or INGESTION_LOCK.exists(),
            "critical_task": activity_registry.active("critical"),
            "keep_awake": KEEP_AWAKE_FILE.exists(),
            "presence": fused.to_dict(),
            "voice": voice_status}
    if automation is not None:
        payload["presence_automation"] = automation.status()
    return payload


def handler_factory(
    check: Callable[[], dict[str, Any]],
    eva: Any | None = None,
    automation: PresenceAutomation | None = None,
) -> type[BaseHTTPRequestHandler]:
    web_enabled = os.getenv("EVA_WEB_ENABLED", "false").lower() in {
        "1", "true", "yes", "on",
    }
    web = (
        WebChat(eva, Path(__file__).resolve().parents[1])
        if web_enabled and eva is not None
        else None
    )
    web_root = Path(__file__).with_name("web")
    security_headers = {
        "Content-Security-Policy": (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; media-src 'self' blob:; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        ),
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }

    class HealthHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _bytes(
            self,
            status: int,
            payload: bytes,
            content_type: str,
            *,
            cache_control: str = "no-store",
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", cache_control)
            for name, value in security_headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, status: int, value: dict[str, Any]) -> None:
            self._bytes(
                status,
                json.dumps(value, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _authorized(self, env_name: str) -> bool:
            token = os.getenv(env_name, "").strip()
            if not token:
                return env_name == "EVA_PRESENCE_TOKEN"
            supplied = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            return hmac.compare_digest(token, supplied)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/health":
                self._json(200, check())
                return
            if web is None:
                self.send_error(404)
                return
            if path in {"/", "/index.html", "/styles.css", "/app.js"}:
                filename = "index.html" if path in {"/", "/index.html"} else path[1:]
                asset = web_root / filename
                if not asset.is_file():
                    self.send_error(404)
                    return
                content_type = {
                    ".html": "text/html; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".js": "text/javascript; charset=utf-8",
                }.get(asset.suffix, "application/octet-stream")
                self._bytes(
                    200,
                    asset.read_bytes(),
                    content_type,
                    cache_control=(
                        "no-store"
                        if filename == "index.html"
                        else "public, max-age=3600"
                    ),
                )
                return
            if path == "/api/status":
                if not self._authorized("EVA_WEB_TOKEN"):
                    self._json(401, {"error": "unauthorized"})
                    return
                self._json(200, web.status())
                return
            if path == "/api/history":
                if not self._authorized("EVA_WEB_TOKEN"):
                    self._json(401, {"error": "unauthorized"})
                    return
                self._json(200, {"messages": web.history()})
                return
            if path.startswith("/api/audio/"):
                if not self._authorized("EVA_WEB_TOKEN"):
                    self._json(401, {"error": "unauthorized"})
                    return
                audio = web.audio(path.removeprefix("/api/audio/"))
                if audio is None:
                    self._json(404, {"error": "audio not found"})
                    return
                audio_path, media_type = audio
                self._bytes(200, audio_path.read_bytes(), media_type)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if self.path == "/api/chat":
                if web is None:
                    self.send_error(404)
                    return
                if not self._authorized("EVA_WEB_TOKEN"):
                    self._json(401, {"error": "unauthorized"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 65_536:
                        self._json(413, {"error": "request too large"})
                        return
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    message = payload.get("message", "")
                    if not isinstance(message, str) or not message.strip():
                        self._json(400, {"error": "message is required"})
                        return
                    message = message.strip()
                    if len(message) > web.max_message_chars:
                        self._json(413, {"error": "message is too long"})
                        return
                except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                    self._json(400, {"error": str(exc)})
                    return
                if not web.begin_chat():
                    self._json(409, {"error": "busy"})
                    return

                self.send_response(200)
                self.send_header(
                    "Content-Type", "application/x-ndjson; charset=utf-8"
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                connected = True
                for event in web.events(message):
                    if not connected:
                        continue
                    line = (
                        json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"
                    )
                    try:
                        self.wfile.write(line)
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        connected = False
                return
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
                    if automation is not None:
                        automation.submit_report(report)
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


def _weather_provider(eva: Any) -> Callable[[str], str | None]:
    def provide(location: str) -> str | None:
        manager = getattr(eva, "module_manager", None)
        module = manager.get_module("WebSearchCore") if manager is not None else None
        weather = getattr(module, "weather", None)
        if not callable(weather):
            return None
        data = weather(location)
        if not data:
            return None
        return (
            f"In {data['location']} sind es {data['temperature']} Grad, "
            f"gefühlt {data['feels_like']} Grad. {data['description']}."
        )
    return provide


def serve(eva: Any, host: str = "127.0.0.1", port: int = 8765) -> None:
    automation = PresenceAutomation(
        PresenceAutomationConfig.from_env(),
        weather_provider=_weather_provider(eva),
        announcer=eva.speak,
        start_worker=True,
    )
    server = ThreadingHTTPServer(
        (host, port),
        handler_factory(lambda: health_payload(eva, automation), eva, automation),
    )
    server.serve_forever()


def start_in_thread(eva: Any, host: str = "127.0.0.1", port: int = 8765) -> threading.Thread:
    thread = threading.Thread(target=serve, args=(eva, host, port),
                              name="eva-health", daemon=True)
    thread.start()
    return thread
