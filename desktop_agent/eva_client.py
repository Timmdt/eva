from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any


class EVAClient:
    def __init__(
        self,
        url: str,
        token: str = "",
        *,
        timeout: float = 2.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.url, self.token, self.timeout, self.opener = url, token, timeout, opener

    def report_desk_presence(
        self, *, presence: bool, identity: str | None = None, confidence: float = 0.0
    ) -> bool:
        if not self.url:
            return False
        payload = json.dumps(
            {
                "sensor": "desk",
                "presence": presence,
                "identity": identity,
                "confidence": confidence,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.url, data=payload, method="POST", headers=headers)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return response.status in {200, 202, 204}
        except (OSError, urllib.error.URLError):
            return False
