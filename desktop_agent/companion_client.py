"""Desktop transport. No EVA core, camera, database or model dependency."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .companion_protocol import MAX_HISTORY, MAX_HISTORY_CHARS, MAX_MESSAGE, validate_url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the bearer token or screenshot to a redirected host.
        return None


def bounded_history(history: list[dict]) -> list[dict]:
    result = []
    remaining = MAX_HISTORY_CHARS
    for item in reversed(history[-MAX_HISTORY:]):
        content = item["content"][-MAX_MESSAGE:]
        if len(content) > remaining:
            break
        remaining -= len(content)
        result.append({"role": item["role"], "content": content})
    return list(reversed(result))


class CompanionClient:
    def __init__(self, url: str, token: str):
        self.url = validate_url(url)
        self.token = token.strip()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def _open(self, path: str, payload=None, timeout=180):
        request = urllib.request.Request(
            self.url + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            return self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            messages = {
                401: "Token stimmt nicht. Verbindungseinstellungen prüfen.",
                409: "EVA ist gerade beschäftigt. Gleich erneut versuchen.",
                404: "EVA-Bridge nicht gefunden. Adresse und Port 8766 prüfen.",
            }
            raise RuntimeError(messages.get(exc.code, f"Serverfehler HTTP {exc.code}.")) from exc
        except OSError as exc:
            raise RuntimeError(
                "Keine Verbindung zur EVA-Bridge. Serveradresse, Dienst und Firewall prüfen."
            ) from exc

    def status(self):
        with self._open("/desktop/status", timeout=5) as response:
            return json.load(response)

    def stream(self, message: str, history: list[dict], image: str | None, mode="chat"):
        with self._open(
            "/desktop/chat",
            {
                "message": message,
                "history": bounded_history(history),
                "image": image,
                "mode": mode,
            },
        ) as response:
            for line in response:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("type") == "error":
                    raise RuntimeError(event.get("error", "Antwort fehlgeschlagen."))
                if event.get("type") == "delta":
                    yield event["text"]
                if event.get("type") == "done":
                    return
        raise RuntimeError("Verbindung wurde vor Ende der Antwort getrennt.")
