"""Configure and optionally start the EVA server's desktop bridge.

No models or inference engines are installed on the Windows desktop. Tokens are
written only to the private server .env and shown only by --show-client.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import urllib.request
from pathlib import Path

from desktop_agent.companion_protocol import validate_url

ROOT = Path(__file__).resolve().parents[1]


def env_values(path: Path):
    """Read literal values without changing this process or executing shell text."""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=(.*)$", line)
        if match:
            value = match[2].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            values[match[1]] = value
    return values


def update_env(path: Path, updates: dict[str, str]):
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    written = set()
    result = []
    for line in lines:
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=", line)
        key = match[1] if match else None
        if key in updates:
            if key not in written:
                result.append(key + "=" + updates[key])
                written.add(key)
        else:
            result.append(line)
    missing = [key for key in updates if key not in written]
    if missing:
        result.extend(["", "# Desktop-Agent: inference stays on this EVA server."])
        result.extend(key + "=" + updates[key] for key in missing)
    temporary = path.with_suffix(path.suffix + ".companion.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write("\n".join(result) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def unit_text(project_root: Path, python: Path):
    # systemd's quoted arguments and %-specifier escaping are distinct from shell quoting.
    def argument(path):
        return '"' + str(path).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"') + '"'

    return (
        "[Unit]\nDescription=EVA Desktop Bridge - server-side vision\nAfter=network-online.target\n\n"
        "[Service]\nType=simple\n"
        f"WorkingDirectory={str(project_root).replace('%', '%%')}\n"
        f"ExecStart={argument(python)} -m desktop_agent.companion_server\n"
        "Environment=PYTHONUNBUFFERED=1\nRestart=on-failure\nRestartSec=5\nNoNewPrivileges=true\n\n"
        "[Install]\nWantedBy=default.target\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="LAN-IP des EVA-Servers, z.B. 192.168.2.15")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--model", help="Bereits auf dem Server installiertes Vision-Modell")
    parser.add_argument(
        "--chat-model", help="Bereits installiertes Gesprächsmodell auf demselben Server"
    )
    parser.add_argument("--install-user-service", action="store_true")
    parser.add_argument(
        "--show-client",
        action="store_true",
        help="Serveradresse und privaten Token zum lokalen Übertragen anzeigen",
    )
    args = parser.parse_args()
    path = ROOT / ".env"
    values = env_values(path)
    if args.show_client:
        token = values.get("EVA_COMPANION_TOKEN", "")
        if not token:
            parser.error("Noch keine Desktop-Bridge eingerichtet.")
        host = values.get("EVA_COMPANION_HOST", "127.0.0.1")
        if host == "0.0.0.0":
            host = "EVA_SERVER_LAN_IP"
        print("KI-Backend: EVA-Bridge auf dem EVA-Rechner")
        print(f"API-Adresse: http://{host}:{values.get('EVA_COMPANION_PORT', '8766')}")
        print("Bridge-Token: " + token)
        print("Im Desktop-Agenten speichern und im Dashboard Bildschirmfreigabe aktivieren.")
        return
    host = args.host or values.get("EVA_COMPANION_HOST", "127.0.0.1")
    model = (
        args.model
        or values.get("EVA_COMPANION_MODEL")
        or values.get("EVA_DESKTOP_VISION_MODEL", "qwen3-vl:2b-instruct-q4_K_M")
    )
    chat_model = (
        args.chat_model or values.get("EVA_COMPANION_CHAT_MODEL") or values.get("EVA_MODEL", model)
    )
    url = validate_url(values.get("EVA_COMPANION_OLLAMA_URL", "http://127.0.0.1:11434"))
    request = urllib.request.Request(
        url + "/api/show",
        data=json.dumps({"model": model}).encode(),
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        metadata = json.load(response)
    if "vision" not in metadata.get("capabilities", []):
        parser.error("Das ausgewählte serverseitige Modell meldet keine Vision-Unterstützung.")
    request = urllib.request.Request(
        url + "/api/show",
        data=json.dumps({"model": chat_model}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with opener.open(request, timeout=10) as response:
        metadata = json.load(response)
    if "completion" not in metadata.get("capabilities", []):
        parser.error("Das ausgewählte Gesprächsmodell meldet keine Textgenerierung.")
    token = values.get("EVA_COMPANION_TOKEN", "")
    if not token or token.startswith("CHANGE_ME"):
        token = secrets.token_hex(32)
    if len(token) < 32 or not token.isascii() or any(char.isspace() for char in token):
        parser.error(
            "Vorhandenen Companion-Token prüfen; mindestens 32 ASCII-Zeichen ohne Leerzeichen."
        )
    if not 1 <= args.port <= 65535 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", host):
        parser.error("Ungültige Bind-Adresse oder Port.")
    update_env(
        path,
        {
            "EVA_COMPANION_HOST": host,
            "EVA_COMPANION_PORT": str(args.port),
            "EVA_COMPANION_TOKEN": token,
            "EVA_COMPANION_MODEL": model,
            "EVA_COMPANION_CHAT_MODEL": chat_model,
            "EVA_COMPANION_OLLAMA_URL": url,
        },
    )
    print(
        f"Desktop-Bridge konfiguriert: {host}:{args.port}, Chat {chat_model}, Vision {model}; beide auf dem Server."
    )
    print("Privaten Token anzeigen: python3 -m tools.setup_desktop_bridge --show-client")
    if args.install_user_service:
        unit = Path.home() / ".config/systemd/user/eva-companion.service"
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(unit_text(ROOT, ROOT / ".venv/bin/python"), encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "eva-companion.service"], check=True
        )
        subprocess.run(["systemctl", "--user", "restart", "eva-companion.service"], check=True)
        print("Benutzerdienst eva-companion.service aktiviert und gestartet.")


if __name__ == "__main__":
    main()
