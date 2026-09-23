from __future__ import annotations

import json
import logging
import os
import queue
import threading
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


logger = logging.getLogger(__name__)

WeatherProvider = Callable[[str], str | None]
Announcer = Callable[[str], None]
Clock = Callable[[], datetime]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_seconds(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _parse_time(value: str, fallback: time) -> time:
    try:
        hour, minute = value.strip().split(":", 1)
        return time(hour=int(hour), minute=int(minute))
    except (AttributeError, TypeError, ValueError):
        return fallback


@dataclass(frozen=True)
class PresenceAutomationConfig:
    enabled: bool = False
    timezone_name: str = "Europe/Berlin"
    weather_location: str = ""
    return_briefing_after: float = 900.0
    greeting_cooldown: float = 14_400.0
    morning_start: time = time(5, 0)
    morning_end: time = time(11, 30)
    state_path: Path = Path("data/presence_automation.json")
    max_pending_events: int = 50

    @classmethod
    def from_env(cls) -> "PresenceAutomationConfig":
        return cls(
            enabled=_env_bool("EVA_PRESENCE_AUTOMATION_ENABLED", False),
            timezone_name=os.getenv("EVA_TIMEZONE", "Europe/Berlin").strip(),
            weather_location=os.getenv("EVA_WEATHER_LOCATION", "").strip(),
            return_briefing_after=_env_seconds(
                "EVA_PRESENCE_RETURN_BRIEFING_AFTER", 900.0),
            greeting_cooldown=_env_seconds(
                "EVA_PRESENCE_GREETING_COOLDOWN", 14_400.0),
            morning_start=_parse_time(
                os.getenv("EVA_MORNING_GREETING_START", "05:00"), time(5, 0)),
            morning_end=_parse_time(
                os.getenv("EVA_MORNING_GREETING_END", "11:30"), time(11, 30)),
            state_path=Path(os.getenv(
                "EVA_PRESENCE_AUTOMATION_STATE_FILE",
                "data/presence_automation.json",
            )),
        )


class PresenceAutomation:
    """Turns trusted room-presence transitions into non-critical announcements.

    This class deliberately has no Wake-on-LAN or shutdown capability. Reports
    are processed on one worker so the HTTP camera/presence path never waits for
    weather lookups or output devices.
    """

    def __init__(
        self,
        config: PresenceAutomationConfig,
        *,
        weather_provider: WeatherProvider | None = None,
        announcer: Announcer | None = None,
        clock: Clock | None = None,
        start_worker: bool = False,
    ) -> None:
        self.config = config
        self.weather_provider = weather_provider
        self.announcer = announcer
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        try:
            self.timezone = ZoneInfo(config.timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning("Unbekannte Zeitzone %s; verwende UTC.", config.timezone_name)
            self.timezone = ZoneInfo("UTC")
        self._lock = threading.RLock()
        self._reports: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=256)
        self._state = self._load_state()
        # Live presence cannot be trusted across process restarts. Persistent
        # timestamps and pending events remain useful for the next report.
        self._state["room_present"] = False
        self._state["known_present"] = False
        self._worker: threading.Thread | None = None
        if start_worker and config.enabled:
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="eva-presence-automation",
                daemon=True,
            )
            self._worker.start()

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "room_present": False,
            "known_present": False,
            "identity": None,
            "away_since": None,
            "last_seen": None,
            "last_morning_greeting": None,
            "last_greeting_at": None,
            "last_announcement": None,
            "last_announcement_at": None,
            "pending_events": [],
        }

    def _load_state(self) -> dict[str, Any]:
        state = self._default_state()
        try:
            loaded = json.loads(self.config.state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state.update(loaded)
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError):
            logger.exception("Präsenz-Automationszustand konnte nicht geladen werden.")
        if not isinstance(state.get("pending_events"), list):
            state["pending_events"] = []
        return state

    def _save_state_locked(self) -> None:
        path = self.config.state_path
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(self._state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            logger.exception("Präsenz-Automationszustand konnte nicht gespeichert werden.")

    def _now(self) -> datetime:
        current = self.clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current.astimezone(self.timezone)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _is_morning(self, current: datetime) -> bool:
        local_time = current.timetz().replace(tzinfo=None)
        start, end = self.config.morning_start, self.config.morning_end
        if start <= end:
            return start <= local_time <= end
        return local_time >= start or local_time <= end

    @staticmethod
    def _format_duration(seconds: float) -> str:
        minutes = max(1, int(round(seconds / 60)))
        if minutes < 60:
            return "einer Minute" if minutes == 1 else f"{minutes} Minuten"
        hours, remaining = divmod(minutes, 60)
        if hours < 24:
            hour_text = "einer Stunde" if hours == 1 else f"{hours} Stunden"
            if remaining:
                return f"{hour_text} und {remaining} Minuten"
            return hour_text
        days, remaining_hours = divmod(hours, 24)
        day_text = "einem Tag" if days == 1 else f"{days} Tagen"
        if remaining_hours:
            return f"{day_text} und {remaining_hours} Stunden"
        return day_text

    def _greeting_cooldown_elapsed(self, current: datetime) -> bool:
        previous = self._parse_datetime(self._state.get("last_greeting_at"))
        if previous is None:
            return True
        return (current - previous.astimezone(self.timezone)).total_seconds() >= (
            self.config.greeting_cooldown)

    def submit_report(self, report: dict[str, Any]) -> None:
        if not self.config.enabled:
            return
        try:
            self._reports.put_nowait(dict(report))
        except queue.Full:
            logger.warning("Präsenz-Automationsqueue ist voll; Report verworfen.")

    def _worker_loop(self) -> None:
        while True:
            report = self._reports.get()
            try:
                self.handle_report(report)
            except Exception:
                logger.exception("Präsenz-Report konnte nicht automatisiert werden.")
            finally:
                self._reports.task_done()

    def record_event(self, summary: str, *, category: str = "info") -> bool:
        """Store a future Home-Assistant/EVA event only while the user is away."""
        summary = " ".join(str(summary).split()).strip()
        if not self.config.enabled or not summary:
            return False
        with self._lock:
            if not self._state.get("away_since"):
                return False
            events = list(self._state.get("pending_events", []))
            events.append({
                "summary": summary[:300],
                "category": str(category)[:50],
                "created_at": self._now().isoformat(),
            })
            self._state["pending_events"] = events[-self.config.max_pending_events:]
            self._save_state_locked()
        return True

    def handle_report(self, report: dict[str, Any]) -> str | None:
        if not self.config.enabled:
            return None
        if str(report.get("sensor", "")).strip().lower() != "room":
            return None

        current = self._now()
        presence = bool(report.get("presence"))
        identity = str(report.get("identity") or "").strip() or None
        known_now = bool(presence and identity)
        morning = False
        initial_greeting = False
        away_duration: float | None = None
        events: list[dict[str, Any]] = []

        with self._lock:
            was_known = bool(self._state.get("known_present"))
            away_since = self._parse_datetime(self._state.get("away_since"))
            self._state["room_present"] = presence

            if known_now:
                self._state["known_present"] = True
                self._state["identity"] = identity
                self._state["last_seen"] = current.isoformat()
                if not was_known:
                    today = current.date().isoformat()
                    morning = (
                        self._is_morning(current)
                        and self._state.get("last_morning_greeting") != today
                    )
                    if morning:
                        self._state["last_morning_greeting"] = today
                    if away_since is not None:
                        away_duration = max(
                            0.0,
                            (current - away_since.astimezone(self.timezone)).total_seconds(),
                        )
                        events = list(self._state.get("pending_events", []))
                        self._state["pending_events"] = []
                    elif not morning and self._greeting_cooldown_elapsed(current):
                        initial_greeting = True
                    self._state["away_since"] = None
            elif not presence:
                self._state["known_present"] = False
                self._state["identity"] = None
                if not self._state.get("away_since"):
                    self._state["away_since"] = current.isoformat()
            else:
                # Unknown faces never receive a greeting and do not clear an
                # already running absence interval for the enrolled user.
                self._state["known_present"] = False
                self._state["identity"] = None

            should_brief = (
                away_duration is not None
                and away_duration >= self.config.return_briefing_after
            )
            should_announce = bool(morning or initial_greeting or should_brief)
            if should_announce:
                self._state["last_greeting_at"] = current.isoformat()
            self._save_state_locked()

        if not should_announce or identity is None:
            return None

        parts: list[str] = []
        if morning:
            parts.append(f"Guten Morgen, {identity}.")
            weather = self._weather_summary()
            if weather:
                parts.append(weather)
        elif should_brief:
            parts.append(f"Willkommen zurück, {identity}.")
        else:
            parts.append(f"Hallo, {identity}.")

        if should_brief and away_duration is not None:
            parts.append(
                f"Du warst ungefähr {self._format_duration(away_duration)} weg."
            )
            summaries = [
                str(event.get("summary", "")).strip()
                for event in events
                if str(event.get("summary", "")).strip()
            ]
            if summaries:
                parts.append("Währenddessen: " + "; ".join(summaries[:3]) + ".")
                if len(summaries) > 3:
                    parts.append(
                        f"Außerdem gibt es {len(summaries) - 3} weitere Meldungen."
                    )
            else:
                parts.append("Währenddessen wurden keine besonderen Ereignisse erfasst.")

        announcement = " ".join(parts)
        self._emit(announcement, current)
        return announcement

    def _weather_summary(self) -> str | None:
        if not self.weather_provider or not self.config.weather_location:
            return None
        try:
            return self.weather_provider(self.config.weather_location)
        except Exception:
            logger.exception("Wetter für die Morgenbegrüßung konnte nicht geladen werden.")
            return None

    def _emit(self, announcement: str, current: datetime) -> None:
        with self._lock:
            self._state["last_announcement"] = announcement
            self._state["last_announcement_at"] = current.isoformat()
            self._save_state_locked()
        if self.announcer:
            try:
                self.announcer(announcement)
            except Exception:
                logger.exception("Präsenz-Ankündigung konnte nicht ausgegeben werden.")

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.config.enabled,
                "room_present": bool(self._state.get("room_present")),
                "known_present": bool(self._state.get("known_present")),
                "away_since": self._state.get("away_since"),
                "pending_event_count": len(self._state.get("pending_events", [])),
                "last_announcement": self._state.get("last_announcement"),
                "last_announcement_at": self._state.get("last_announcement_at"),
            }
