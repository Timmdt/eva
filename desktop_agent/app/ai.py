"""Replaceable chat backends with cancellable streaming transport."""

from __future__ import annotations

import http.client
import json
import socket
import threading
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, Signal

from ..companion_client import bounded_history
from ..companion_protocol import model_messages, validate_url


class Backend:
    def request(self, message, history, image, mode):
        raise NotImplementedError


class OllamaBackend(Backend):
    def __init__(self, url, model, token=""):
        self.url, self.model = validate_url(url), model.strip()
        if not self.model:
            raise ValueError("Bitte einen Ollama-Modellnamen eintragen.")

    def request(self, message, history, image, mode):
        payload = {
            "message": message,
            "history": bounded_history(history),
            "image": image,
            "mode": mode,
        }
        return (
            self.url,
            "/api/chat",
            {
                "model": self.model,
                "messages": model_messages(payload),
                "stream": True,
                "keep_alive": "5m",
                "options": {"num_ctx": 8192, "num_predict": 160 if mode == "observe" else 1024},
            },
            {},
        )


class BridgeBackend(Backend):
    def __init__(self, url, model="", token=""):
        self.url, self.token = validate_url(url), token.strip()
        if len(self.token) < 32 or not self.token.isascii():
            raise ValueError(
                "Für die EVA-Bridge den separaten Token eintragen (mindestens 32 ASCII-Zeichen)."
            )

    def request(self, message, history, image, mode):
        return (
            self.url,
            "/desktop/chat",
            {
                "message": message,
                "history": bounded_history(history),
                "image": image,
                "mode": mode,
            },
            {"Authorization": "Bearer " + self.token},
        )


BACKENDS = {"ollama": OllamaBackend, "bridge": BridgeBackend}


def create_backend(name, url, model, token=""):
    if name == "none":
        raise ValueError(
            "Noch keine KI verbunden. Im Hauptmenü unter Einstellungen Ollama oder die EVA-Bridge einrichten. Die Figur funktioniert auch offline."
        )
    if name not in BACKENDS:
        raise ValueError("Unbekanntes KI-Backend.")
    return BACKENDS[name](url, model, token)


class ChatTask(QObject):
    delta = Signal(str)
    done = Signal(str)
    error = Signal(str)
    stopped = Signal()

    def __init__(self, backend, message, history, image=None, mode="chat", parent=None):
        super().__init__(parent)
        self.arguments = (backend, message, history, image, mode)
        self.cancelled = threading.Event()
        self.connection = None
        self.socket = None
        self.response = None
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.run, name="eva-ai", daemon=True)
        self.thread.start()

    def cancel(self):
        self.cancelled.set()
        connection = self.connection
        active_socket = self.socket or (connection.sock if connection is not None else None)
        if active_socket is not None:
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def run(self):
        try:
            backend, message, history, image, mode = self.arguments
            url, path, payload, headers = backend.request(message, history, image, mode)
            address = urlsplit(url)
            cls = (
                http.client.HTTPSConnection
                if address.scheme == "https"
                else http.client.HTTPConnection
            )
            connection = cls(address.hostname, address.port, timeout=5)
            self.connection = connection
            connection.connect()
            self.socket = connection.sock
            if self.cancelled.is_set():
                return
            connection.sock.settimeout(180)
            connection.request(
                "POST",
                path,
                body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", **headers},
            )
            response = connection.getresponse()
            self.response = response
            if response.status != 200:
                errors = {
                    401: "Zugriff verweigert. Bridge-Token prüfen.",
                    404: "Endpunkt oder Ollama-Modell nicht gefunden. Adresse und Modellinstallation prüfen.",
                    409: "Die EVA-Bridge ist gerade beschäftigt. Gleich erneut versuchen.",
                }
                raise RuntimeError(
                    errors.get(response.status, f"KI-Dienst meldet HTTP {response.status}.")
                )
            result = ""
            while not self.cancelled.is_set():
                line = response.readline(262145)
                if len(line) > 262144:
                    raise RuntimeError("Ungültige Streaming-Antwort.")
                if not line:
                    raise RuntimeError("KI-Verbindung vor Ende der Antwort getrennt.")
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise RuntimeError("Ungültige Streaming-Antwort.")
                if event.get("error") or event.get("type") == "error":
                    raise RuntimeError(
                        "KI-Anfrage fehlgeschlagen. Modellname, Modellinstallation und Dienst prüfen."
                    )
                text = (
                    event.get("text", "")
                    if event.get("type") == "delta"
                    else event.get("message", {}).get("content", "")
                )
                if text:
                    result += text
                    self.delta.emit(text)
                if event.get("done") or event.get("type") == "done":
                    if not self.cancelled.is_set():
                        self.done.emit(result)
                    return
        except (
            OSError,
            ValueError,
            RuntimeError,
            TypeError,
            AttributeError,
            http.client.HTTPException,
        ) as exc:
            if not self.cancelled.is_set():
                if isinstance(exc, RuntimeError):
                    self.error.emit(str(exc))
                else:
                    self.error.emit(
                        "KI-Dienst nicht erreichbar oder Antwort ungültig. Verbindungseinstellungen prüfen."
                    )
        finally:
            if self.response is not None:
                self.response.close()
            if self.connection is not None:
                self.connection.close()
            if self.socket is not None:
                self.socket.close()
            self.arguments = None
            self.stopped.emit()
