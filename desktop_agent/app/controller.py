from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from ..companion_protocol import MAX_MESSAGE, needs_screen_context
from .ai import ChatTask, create_backend
from .capture import exclude_from_capture, screenshot
from .character import DEFAULT_OUTFIT, CharacterState, Outfit
from .pet import CharacterWindow
from .storage import Conversations, Preferences, credential_token
from .ui import STYLE, CompactChat, MainWindow
from .windows import idle_seconds, set_autostart


class Companion(QObject):
    def __init__(self, directory: Path | None = None):
        super().__init__()
        self.preferences = Preferences(directory)
        self.conversations = Conversations(self.preferences.directory)
        self.views = []
        self.status = (
            "EVA bereit · Offline"
            if self.preferences.get("backend") == "none"
            else "EVA bereit · Verbindung noch nicht geprüft"
        )
        self.notice = (
            "Noch keine KI konfiguriert. EVA funktioniert offline; die Verbindung kannst du im Hauptmenü einrichten."
            if self.preferences.get("backend") == "none"
            else ""
        )
        self.draft = ""
        self.busy = False
        self.task = None
        self.tasks = []
        self.request_mode = None
        self.request_id = 0
        self.quitting = False
        self.token = ""
        self.sharing = False
        self.generation = 0
        self.observation = "Bildschirmfreigabe aus."
        manifest = self.preferences.get("outfit")
        if manifest.replace("\\", "/").endswith("/assets/character/outfits/gothic.json"):
            # Earlier builds persisted the bundled outfit's absolute installation
            # path. Always use the current package's copy after an update.
            manifest = ""
            self.preferences.update({"outfit": ""})
        try:
            self.outfit = Outfit(Path(manifest)) if manifest else Outfit()
        except (OSError, ValueError, TypeError) as exc:
            self.outfit = Outfit()
            self.notice = (
                "Gespeichertes Outfit konnte nicht geladen werden; Gothic-Standard aktiv. "
                + str(exc)
            )
        self.state = CharacterState(
            self.preferences.get("pose")
            if self.preferences.get("pose") in self.outfit.poses
            else "idle"
        )
        self.pet = CharacterWindow(self.preferences, self.outfit, self.state)
        icon_path = next(iter(self.outfit.expressions.values()), self.outfit.pose("idle").frames[0])
        self.icon = QIcon(str(icon_path))
        self.compact = CompactChat(self)
        self.main_window = MainWindow(self)
        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip("EVA Desktop Agent · Bildschirmfreigabe aus")
        self.tray.setContextMenu(self.tray_menu())
        self.tray.activated.connect(
            lambda reason: (
                self.show_character()
                if reason == QSystemTrayIcon.ActivationReason.Trigger
                else None
            )
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.pet.clicked.connect(self.open_chat)
        self.pet.context_requested.connect(self.open_context)
        self.state.changed.connect(lambda _name: self.schedule_render())
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.render)
        self.observer = QTimer(self)
        self.observer.timeout.connect(self.observe)
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.tick)
        self.tick_timer.start(1000)
        app = QApplication.instance()
        app.screenAdded.connect(self.screens_changed)
        app.screenRemoved.connect(self.screens_changed)
        for screen in app.screens():
            self.connect_screen(screen)
        if self.preferences.get("remember_token"):
            try:
                self.token = credential_token(self.preferences.get("url"))
                self.main_window.token.setText(self.token)
            except Exception:
                self.notice = (
                    "Gespeicherten Token nicht geladen. Bitte in den Einstellungen erneut eingeben."
                )
        self.render()
        self.pet.show()

    def connect_screen(self, screen):
        screen.geometryChanged.connect(lambda _geometry: self.pet.reposition())
        screen.availableGeometryChanged.connect(lambda _geometry: self.pet.reposition())
        screen.logicalDotsPerInchChanged.connect(lambda _dpi: self.pet.reposition())

    def screens_changed(self, screen):
        self.set_sharing(False)
        if screen in QApplication.screens():
            self.connect_screen(screen)
        self.pet.layout_signature = None
        self.pet.reposition()
        self.main_window.refresh_monitors()
        self.schedule_render()

    def schedule_render(self):
        if not self.render_timer.isActive():
            self.render_timer.start(40)

    def render(self):
        if self.quitting:
            return
        for view in self.views:
            view.refresh()
        self.main_window.refresh()

    def tick(self):
        idle = idle_seconds()
        if idle is not None:
            if idle < 2 and self.state.manual not in {"sleeping", "tired"}:
                self.state.activity()
            self.state.last_activity = max(self.state.last_activity, self.state.clock() - idle)
        self.state.tick(
            auto_tired=self.preferences.get("auto_tired"),
            tired_after=self.preferences.get("tired_after"),
            sleep_after=self.preferences.get("sleep_after"),
            chat_visible=self.compact.isVisible() or self.main_window.isVisible(),
        )

    def set_pose(self, name):
        if name not in self.outfit.poses:
            return
        self.preferences.update({"pose": name})
        self.state.activity()
        self.state.manual = name
        if not self.busy:
            self.state.set(name)
        self.schedule_render()

    def open_chat(self):
        self.state.activity()
        if not self.busy:
            self.state.set("listening", seconds=8)
        area = self.pet.selected_screen().availableGeometry()
        size = self.compact.size()
        x = self.pet.x() + self.pet.width() + 10
        if x + size.width() > area.right() + 1:
            x = self.pet.x() - size.width() - 10
        y = self.pet.y() + self.pet.height() - size.height()
        x = max(area.left(), min(x, area.right() + 1 - size.width()))
        y = max(area.top(), min(y, area.bottom() + 1 - size.height()))
        self.compact.move(x, y)
        self.compact.show()
        self.compact.raise_()
        self.compact.activateWindow()
        self.compact.view.input.setFocus()
        self.render()
    def open_main(self, section="Dashboard"):
        self.state.activity()
        self.main_window.select(section)
        self.main_window.showNormal()
        self.main_window.raise_()
        self.main_window.activateWindow()
        self.render()

    def open_context(self, point):
        menu = QMenu()
        menu.setStyleSheet(STYLE)
        menu.addAction("Chat öffnen", self.open_chat)
        menu.addAction("Hauptmenü öffnen", lambda: self.open_main())
        poses = menu.addMenu("Pose wechseln")
        for name, pose in self.outfit.poses.items():
            action = poses.addAction(pose.label)
            action.triggered.connect(lambda _checked=False, key=name: self.set_pose(key))
        menu.addAction("EVA verstecken", self.hide_character)
        if self.sharing:
            menu.addAction("Bildschirmfreigabe ausschalten", lambda: self.set_sharing(False))
        menu.addSeparator()
        menu.addAction("EVA beenden", self.quit)
        menu.ensurePolished()
        area = self.pet.selected_screen().availableGeometry()
        wanted = menu.sizeHint()
        point = QPoint(
            max(area.left(), min(point.x(), area.right() + 1 - wanted.width())),
            max(area.top(), min(point.y(), area.bottom() + 1 - wanted.height())),
        )
        menu.exec(point)

    def tray_menu(self):
        menu = QMenu()
        menu.setStyleSheet(STYLE)
        menu.addAction("EVA anzeigen", self.show_character)
        menu.addAction("Chat öffnen", self.open_chat)
        menu.addAction("Hauptmenü öffnen", lambda: self.open_main())
        menu.addAction("Bildschirmfreigabe ausschalten", lambda: self.set_sharing(False))
        menu.addSeparator()
        menu.addAction("EVA beenden", self.quit)
        return menu

    def hide_character(self):
        self.pet.hide()
        if not self.tray.isVisible():
            # A system without tray support must retain a way to reveal/quit EVA.
            self.open_main()

    def show_character(self):
        self.pet.reposition()
        self.pet.show()

    def save_preferences(self, values, token):
        if self.busy:
            raise RuntimeError(
                "Bitte die laufende KI-Anfrage beenden, bevor die Verbindung geändert wird."
            )
        if values["backend"] != "none":
            create_backend(values["backend"], values["url"], values["model"], token)
        if values["sleep_after"] <= values["tired_after"]:
            raise ValueError("Schlafen muss später als Müdigkeit beginnen.")
        old_url = self.preferences.get("url")
        remember = values["remember_token"]
        if remember and sys.platform != "win32":
            raise ValueError("Token-Speicherung verwendet den Windows-Anmeldeinformationstresor.")
        if remember:
            try:
                credential_token(values["url"], token)
            except Exception as exc:
                raise RuntimeError(
                    "Windows-Tresor nicht verfügbar; Token für diese Sitzung verwenden."
                ) from exc
        elif self.preferences.get("remember_token"):
            try:
                credential_token(old_url, delete=True)
            except Exception as exc:
                raise RuntimeError(
                    "Gespeicherter Token konnte nicht aus dem Windows-Tresor entfernt werden."
                ) from exc
        if values["autostart"] != self.preferences.get("autostart"):
            set_autostart(values["autostart"])
        if old_url != values["url"] or self.preferences.get("monitor") != values["monitor"]:
            self.set_sharing(False)
        self.token = token
        self.preferences.update(values)
        self.pet.apply_preferences()
        self.apply_capture_preferences()
        self.status = (
            "Einstellungen gespeichert · Verbindung noch nicht geprüft"
            if values["backend"] != "none"
            else "EVA bereit · Offline"
        )
        self.notice = ""
        if self.sharing:
            self.observer.start(round(self.preferences.get("observe_interval") * 1000))
        self.schedule_render()

    def apply_capture_preferences(self):
        exclude = not self.preferences.get("include_eva_in_screenshots")
        for window in (self.pet, self.compact, self.main_window):
            window.capture_excluded = exclude_from_capture(window, exclude)

    def load_outfit(self, manifest):
        try:
            candidate = Outfit(manifest)
            # Validate every referenced PNG before changing the active character.
            for pose in candidate.poses.values():
                for frame in pose.frames:
                    candidate.pixmap(frame)
            for path in candidate.expressions.values():
                candidate.pixmap(path)
            self.outfit = candidate
            self.preferences.update(
                {"outfit": "" if manifest.resolve() == DEFAULT_OUTFIT.resolve() else str(manifest)}
            )
            self.pet.set_outfit(candidate)
            self.main_window.pose.blockSignals(True)
            self.main_window.pose.clear()
            for name, pose in candidate.poses.items():
                self.main_window.pose.addItem(pose.label, name)
            self.main_window.pose.blockSignals(False)
            self.main_window.expression.clear()
            self.main_window.expression.addItems(list(candidate.expressions))
            self.main_window.preview_expression()
            self.schedule_render()
        except (OSError, ValueError, TypeError) as exc:
            self.notice = "Outfit nicht geladen: " + str(exc)
            self.schedule_render()

    def default_outfit(self):
        self.load_outfit(DEFAULT_OUTFIT)

    def new_conversation(self):
        if self.busy:
            return
        self.conversations.new()
        self.notice = self.draft = ""
        self.schedule_render()

    def delete_conversation(self):
        if self.busy:
            return
        selected = self.conversations.current
        self.conversations.items = [
            row for row in self.conversations.items if row["id"] != selected
        ]
        if not self.conversations.items:
            self.conversations.new()
        else:
            self.conversations.current = self.conversations.items[-1]["id"]
            self.conversations.save()
        self.notice = self.draft = ""
        self.schedule_render()

    def switch_conversation(self, selected):
        if self.busy or selected == self.conversations.current:
            return
        self.conversations.current = selected
        self.conversations.save()
        self.notice = self.draft = ""
        self.schedule_render()

    def send(self, message):
        message = message.strip()
        if not message or len(message) > MAX_MESSAGE or self.busy:
            return False
        self.state.activity()
        try:
            backend = create_backend(
                self.preferences.get("backend"),
                self.preferences.get("url"),
                self.preferences.get("model"),
                self.token,
            )
        except ValueError as exc:
            self.notice = str(exc)
            self.status = "Keine KI-Verbindung"
            self.schedule_render()
            return False
        self.begin_request(backend, message, "chat")
        return True

    def set_sharing(self, enabled):
        self.generation += 1
        self.sharing = bool(enabled)
        self.observer.stop()
        if enabled:
            self.observation = (
                "Freigabe aktiv · Der gewählte Monitor wird bei Anfragen aufgenommen."
            )
            self.observer.start(round(self.preferences.get("observe_interval") * 1000))
            QTimer.singleShot(0, self.observe)
        else:
            self.observation = "Bildschirmfreigabe aus. Keine neuen Aufnahmen; bereits gesendete Bilder können noch verarbeitet werden."
            if self.busy and self.request_mode == "observe":
                self.cancel_request()
        self.tray.setToolTip(
            "EVA Desktop Agent · "
            + ("Bildschirmfreigabe aktiv" if enabled else "Bildschirmfreigabe aus")
        )
        self.schedule_render()

    def observe(self):
        if self.sharing and not self.busy:
            try:
                backend = create_backend(
                    self.preferences.get("backend"),
                    self.preferences.get("url"),
                    self.preferences.get("model"),
                    self.token,
                )
            except ValueError as exc:
                self.observation = str(exc)
                self.schedule_render()
                return
            self.begin_request(
                backend,
                "Beschreibe kurz die gerade sichtbare Tätigkeit auf diesem Bildschirm.",
                "observe",
            )

    def begin_request(self, backend, message, mode):
        self.request_id += 1
        request_id = self.request_id
        self.busy = self.state.busy = True
        self.request_mode = mode
        self.state.set("thinking")
        self.status = "EVA denkt nach …"
        self.notice = self.draft = ""
        generation = self.generation
        capture_requested = self.sharing and needs_screen_context(
            message, self.conversations.active["messages"], mode
        )
        hidden = []
        if capture_requested and not self.preferences.get("include_eva_in_screenshots"):
            for window in (self.pet, self.compact, self.main_window):
                if window.isVisible() and not window.capture_excluded:
                    hidden.append(window)
                    window.hide()

        def capture_and_launch():
            if self.quitting:
                return
            image = None
            error = None
            try:
                if capture_requested and self.sharing and generation == self.generation:
                    image = screenshot(self.pet.selected_screen())
            except (RuntimeError, OSError) as exc:
                error = str(exc)
            finally:
                for window in hidden:
                    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
                    window.show()
            if not self.busy or request_id != self.request_id:
                return
            if error:
                self.set_sharing(False)
                self.finish_error(error)
            elif mode == "observe" and image is None:
                self.reset_request()
            else:
                self.launch(backend, message, mode, image, generation)

        QTimer.singleShot(180 if hidden else 0, capture_and_launch)
        self.schedule_render()

    def launch(self, backend, message, mode, image, generation):
        history = list(self.conversations.active["messages"]) if mode == "chat" else []
        if mode == "chat":
            self.conversations.append("user", message)
        task = ChatTask(backend, message, history, image, mode, self)
        self.task = task
        self.tasks.append(task)
        task.delta.connect(lambda text: self.receive_delta(task, text, mode))
        task.done.connect(lambda result: self.finish(task, result, mode, generation))
        task.error.connect(lambda error: self.finish_error(error) if self.task is task else None)
        task.stopped.connect(lambda: self.task_stopped(task))
        task.start()

    def receive_delta(self, task, text, mode):
        if self.task is not task or self.quitting:
            return
        if mode == "chat":
            self.draft += text
            self.state.set("talking")
            self.status = "EVA antwortet …"
            self.schedule_render()

    def finish(self, task, result, mode, generation):
        if self.task is not task or self.quitting:
            return
        if mode == "chat":
            self.conversations.append("assistant", result)
            self.draft = ""
        elif self.sharing and generation == self.generation:
            self.observation = time.strftime("%H:%M:%S") + " · " + result
        self.reset_request()

    def finish_error(self, error):
        self.notice = error
        if self.draft:
            self.notice += "\n\nUnvollständige Antwort:\n" + self.draft
            self.draft = ""
        self.reset_request()
        self.status = "KI-Verbindung fehlgeschlagen"

    def reset_request(self):
        self.busy = self.state.busy = False
        self.task = None
        self.request_mode = None
        self.status = "EVA bereit"
        self.state.activity()
        self.state.set("listening", seconds=5)
        self.schedule_render()

    def cancel_request(self):
        self.request_id += 1
        if self.task is not None:
            self.task.cancel()
        self.draft = ""
        self.reset_request()
        self.notice = "Anfrage beendet."

    def task_stopped(self, task):
        # QObject stays alive until its worker has emitted all signals and returned.
        if task in self.tasks:
            self.tasks.remove(task)
        task.deleteLater()

    def quit(self):
        if self.quitting:
            return
        self.quitting = True
        self.tick_timer.stop()
        self.observer.stop()
        self.render_timer.stop()
        self.pet.stop()
        self.compact.hide()
        self.main_window.hide()
        self.tray.hide()
        for task in list(self.tasks):
            task.cancel()
        for task in list(self.tasks):
            if task.thread is not None:
                task.thread.join(timeout=6)
        self.conversations.save()
        QApplication.instance().quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EVA Desktop Agent")
    app.setOrganizationName("EVA")
    app.setQuitOnLastWindowClosed(False)
    try:
        controller = Companion()
    except (OSError, ValueError) as exc:
        QMessageBox.critical(
            None,
            "EVA kann nicht starten",
            "Charakterassets oder Einstellungen prüfen.\n" + str(exc),
        )
        return
    app.aboutToQuit.connect(controller.quit)
    sys.exit(app.exec())
