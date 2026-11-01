from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.activity import INGESTION_LOCK, activity_registry

logger = logging.getLogger(__name__)


def system_uptime() -> float:
    try:
        return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


@dataclass(frozen=True)
class ShutdownDecision:
    allowed: bool
    reason: str
    dry_run: bool = True


class SafeShutdown:
    """Server-local safety gates for authenticated remote shutdown requests."""

    def __init__(
        self,
        *,
        feature_enabled: bool,
        allow_shutdown: bool,
        keep_awake_file: Path,
        inhibit_file: Path,
        boot_grace: float = 600.0,
        uptime: Callable[[], float] = system_uptime,
        executor: Callable[[], None] | None = None,
    ) -> None:
        self.feature_enabled, self.allow_shutdown = feature_enabled, allow_shutdown
        self.keep_awake_file, self.inhibit_file = keep_awake_file, inhibit_file
        self.boot_grace, self.uptime = boot_grace, uptime
        self.executor = executor or self._system_shutdown

    @staticmethod
    def _system_shutdown() -> None:
        subprocess.run(["systemctl", "poweroff"], check=True)

    def evaluate(self) -> ShutdownDecision:
        if not self.feature_enabled:
            return ShutdownDecision(False, "Remote-Shutdown ist deaktiviert")
        if activity_registry.active("request"):
            return ShutdownDecision(False, "aktive EVA-Anfrage")
        if activity_registry.active("ingestion") or INGESTION_LOCK.exists():
            return ShutdownDecision(False, "laufende Ingestion")
        if activity_registry.active("critical"):
            return ShutdownDecision(False, "kritischer Task")
        if self.inhibit_file.exists():
            return ShutdownDecision(False, "Inhibit-Lock aktiv")
        if self.keep_awake_file.exists():
            return ShutdownDecision(False, "Keep-Awake aktiv")
        if self.uptime() < self.boot_grace:
            return ShutdownDecision(False, "Boot-Grace aktiv")
        return ShutdownDecision(
            True, "alle Sicherheitsbedingungen erfüllt", dry_run=not self.allow_shutdown
        )

    def request(self) -> ShutdownDecision:
        decision = self.evaluate()
        if not decision.allowed:
            logger.info("Shutdown verhindert: %s", decision.reason)
        elif decision.dry_run:
            logger.warning("Would shut down EVA server now.")
        else:
            self.executor()
        return decision
