"""Token-protected Ollama bridge. Runs on EVA's host, never on the capture PC."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .companion_protocol import (
    DEFAULT_MODEL,
    MAX_BODY,
    model_messages,
    prepare_turn,
    validate_payload,
    validate_url,
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def ollama_events(url: str, model: str, payload: dict):
    request = urllib.request.Request(
        url + "/api/chat",
        data=json.dumps(
            {
                "model": model,
                "messages": model_messages(payload),
                "stream": True,
                "keep_alive": "30s" if payload["image"] else "5m",
                "options": {
                    "num_ctx": 8192,
                    "num_predict": 160 if payload["mode"] == "observe" else 1024,
                    "temperature": 0.15 if payload["image"] else 0.3,
                },
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=180) as response:
        for line in response:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("error"):
                raise RuntimeError(
                    "Ollama konnte die Antwort nicht erzeugen; Modell und Serverlog prüfen."
                )
            content = event.get("message", {}).get("content", "")
            if content:
                yield {"type": "delta", "text": content}
            if event.get("done"):
                yield {"type": "done"}
                return
    raise RuntimeError("Ollama hat die Antwort vorzeitig beendet.")


def handler_factory(
    token: str,
    ollama_url: str,
    model: str = DEFAULT_MODEL,
    event_source=ollama_events,
    *,
    chat_model: str | None = None,
):
    if len(token) < 32 or token.startswith("CHANGE_ME") or not token.isascii():
        raise ValueError(
            "EVA_COMPANION_TOKEN benötigt mindestens 32 ASCII-Zeichen (zufällig erzeugen)."
        )
    ollama_url = validate_url(ollama_url)
    chat_model = chat_model or model
    busy = threading.BoundedSemaphore(1)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        # Limits slow or incomplete request bodies and idle keep-alive sockets.
        timeout = 15

        def reply(self, status: int, payload: dict):
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            self.wfile.write(raw)

        def authorized(self):
            supplied = self.headers.get("Authorization", "").encode("utf-8")
            if not hmac.compare_digest(supplied, ("Bearer " + token).encode("ascii")):
                self.reply(401, {"error": "Zugriff verweigert. Token prüfen."})
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            if self.path != "/desktop/status":
                self.reply(404, {"error": "Unbekannter Endpunkt."})
                return
            # Connectivity check is deliberately independent from model loading.
            self.reply(
                200,
                {
                    "name": "EVA",
                    "model": model,
                    "vision_model": model,
                    "chat_model": chat_model,
                    "protocol": 1,
                },
            )

        def do_POST(self):
            if not self.authorized():
                return
            if self.path != "/desktop/chat":
                self.reply(404, {"error": "Unbekannter Endpunkt."})
                return
            if self.headers.get("Transfer-Encoding"):
                self.reply(400, {"error": "Content-Length erforderlich."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    self.reply(413, {"error": "Anfrage ist zu groß oder leer."})
                    return
                payload = prepare_turn(validate_payload(json.loads(self.rfile.read(length))))
            except (ValueError, UnicodeDecodeError):
                self.reply(400, {"error": "Ungültige Nachricht, Verlauf oder JPEG-Bild."})
                return
            except (OSError, TimeoutError):
                self.close_connection = True
                return
            if not busy.acquire(blocking=False):
                self.reply(409, {"error": "EVA antwortet gerade. Gleich erneut versuchen."})
                return
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                try:
                    selected_model = model if payload["image"] is not None else chat_model
                    for event in event_source(ollama_url, selected_model, payload):
                        self.write_event(event)
                except urllib.error.HTTPError as exc:
                    self.write_event(
                        {
                            "type": "error",
                            "error": (
                                f"Ollama meldet HTTP {exc.code}. Ist das Modell {selected_model} installiert?"
                            ),
                        }
                    )
                except (OSError, ValueError, RuntimeError):
                    self.write_event(
                        {
                            "type": "error",
                            "error": (
                                "Modellserver nicht bereit oder Antwort abgebrochen. Ollama und Modell prüfen."
                            ),
                        }
                    )
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
            finally:
                busy.release()

        def write_event(self, event):
            self.wfile.write(json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n")
            self.wfile.flush()

        def log_message(self, *_args):
            # Neither screenshots nor chat contents or tokens enter HTTP logs.
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description="EVA Desktop-Bridge für den EVA-Rechner")
    parser.add_argument(
        "--env-file", type=Path, default=Path(__file__).resolve().parents[1] / ".env"
    )
    args = parser.parse_args()
    from core.env_loader import load_env_file

    load_env_file(args.env_file)
    token = os.getenv("EVA_COMPANION_TOKEN", "").strip()
    host = os.getenv("EVA_COMPANION_HOST", "127.0.0.1")
    port = int(os.getenv("EVA_COMPANION_PORT", "8766"))
    model = os.getenv("EVA_COMPANION_MODEL", DEFAULT_MODEL)
    chat_model = os.getenv("EVA_COMPANION_CHAT_MODEL", os.getenv("EVA_MODEL", model))
    handler = handler_factory(
        token,
        os.getenv("EVA_COMPANION_OLLAMA_URL", "http://127.0.0.1:11434"),
        model,
        chat_model=chat_model,
    )
    with ThreadingHTTPServer((host, port), handler) as server:
        print(
            f"EVA Bridge auf {host}:{port}, Chat {chat_model}, Vision {model}. Beenden: Strg+C.",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
