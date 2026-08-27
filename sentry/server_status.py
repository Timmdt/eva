from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Callable


class ServerStatus:
    def __init__(self, ip: str, health_url: str = "", timeout: float = 2.0,
                 *, runner: Callable[..., Any] = subprocess.run,
                 opener: Callable[..., Any] = urllib.request.urlopen) -> None:
        self.ip, self.health_url, self.timeout = ip, health_url, timeout
        self.runner, self.opener = runner, opener

    def ping(self) -> bool:
        if not self.ip:
            return False
        result = self.runner(["ping", "-c", "1", "-W", str(max(1, int(self.timeout))), self.ip],
                             capture_output=True, check=False, timeout=self.timeout + 1)
        return result.returncode == 0

    def health(self) -> dict[str, Any] | None:
        if not self.health_url:
            return None
        try:
            with self.opener(self.health_url, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, ValueError, urllib.error.URLError):
            return None

    def ready(self) -> bool:
        health = self.health()
        return health.get("status") == "ready" if health is not None else self.ping()

    def wait_ready(self, timeout: float = 180.0, interval: float = 2.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.ready():
                return True
            time.sleep(interval)
        return False
