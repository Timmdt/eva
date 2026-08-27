from __future__ import annotations

import logging
from typing import Any

from core.events import EventBus, EventType, event_bus
from .camera import RTSPCamera
from .config import SentryConfig
from .presence import PresenceDetector, PresenceTracker
from .server_status import ServerStatus
from .shutdown import SafeShutdown
from .wol import WakeOnLan

logger = logging.getLogger(__name__)


class SentryController:
    def __init__(self, config: SentryConfig | None = None, *, camera: Any | None = None,
                 detector: Any | None = None, identity: Any | None = None,
                 status: Any | None = None, wol: Any | None = None,
                 shutdown: Any | None = None, bus: EventBus = event_bus) -> None:
        self.config = config or SentryConfig.from_env()
        self.camera = camera or RTSPCamera(
            self.config.rtsp_url, detection_fps=self.config.detection_fps,
            scale=self.config.frame_scale, timeout=self.config.camera_timeout,
            reconnect_delay=self.config.reconnect_delay)
        self.detector = detector or PresenceDetector()
        self.identity = identity
        self.status = status or ServerStatus(self.config.server_ip, self.config.health_url,
                                             self.config.health_timeout)
        self.wol = wol or WakeOnLan(self.config.server_mac, self.config.wol_broadcast,
                                   self.config.wol_cooldown)
        self.shutdown = shutdown or SafeShutdown(
            feature_enabled=self.config.enabled, allow_shutdown=self.config.allow_shutdown,
            keep_awake_file=self.config.keep_awake_file, inhibit_file=self.config.inhibit_file,
            boot_grace=self.config.boot_grace)
        self.bus = bus
        self.tracker = PresenceTracker(self.config.presence_timeout)
        self._was_present = False
        self._sleep_requested = False

    def process_presence(self, detected: bool, identity_name: str | None = None) -> None:
        qualifies = detected and (
            self.config.mode == "presence_only" or bool(identity_name)
        )
        present = self.tracker.update(qualifies)
        if present and not self._was_present:
            self._sleep_requested = False
            self.bus.publish(EventType.PRESENCE_DETECTED, identity=identity_name)
            if not self.status.ready():
                self.bus.publish(EventType.SERVER_WAKE_REQUESTED)
                if self.wol.wake():
                    logger.info("Wake-on-LAN-Paket gesendet.")
            elif not self._was_present:
                self.bus.publish(EventType.SERVER_READY)
        elif not present and self._was_present:
            self.bus.publish(EventType.PRESENCE_LOST)
        self._was_present = present
        if self.tracker.timed_out() and not self._sleep_requested:
            self._sleep_requested = True
            self.bus.publish(EventType.SERVER_SLEEP_REQUESTED)
            self.shutdown.request()

    def run(self) -> None:
        if not self.config.enabled:
            logger.info("Sentry ist deaktiviert.")
            return
        for frame in self.camera.frames():
            detected = self.detector.detect(frame)
            identity_name = None
            if detected and self.config.face_recognition_enabled and self.identity:
                result = self.identity.recognize(frame)
                identity_name = result.get("identity") if result else None
            self.process_presence(detected, identity_name)
