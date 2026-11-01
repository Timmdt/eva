from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..companion_protocol import MAX_MESSAGE
from .capture import exclude_from_capture

STYLE = """
QWidget { background: #171115; color: #eee5e8; font-family: 'Segoe UI'; font-size: 13px; }
QLabel#title { font-size: 28px; font-weight: bold; color: #f0c5d0; }
QLabel#subtitle { color: #b2a0a8; }
QLabel#card { background: #251a21; border: 1px solid #51303e; border-radius: 10px; padding: 16px; }
QTextBrowser, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #21181e; border: 1px solid #51303e; border-radius: 7px; padding: 8px; selection-background-color: #78334d; }
QLineEdit:focus { border-color: #c45f81; }
QPushButton { background: #3a2530; border: 1px solid #6a3a4d; border-radius: 7px; padding: 9px 13px; }
QPushButton:hover { background: #593044; }
QPushButton:disabled { color: #80717a; background: #251d23; border-color: #3e3037; }
QPushButton#primary { background: #923e5b; color: #fff1f6; font-weight: bold; }
QListWidget { background: #20161c; border: 0; border-radius: 8px; padding: 8px; }
QListWidget::item { padding: 13px; border-radius: 6px; }
QListWidget::item:selected { background: #653047; color: #fff2f6; }
QCheckBox { spacing: 9px; padding: 4px; }
QScrollArea { border: 0; }
QMenu { background: #24191f; color: #eee5e8; border: 1px solid #78465a; }
QMenu::item { padding: 8px 22px; }
QMenu::item:selected { background: #653047; }
"""


def text(value, kind=None):
    widget = QLabel(value)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if kind:
        widget.setObjectName(kind)
    return widget


def button(title, callback, primary=False):
    widget = QPushButton(title)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


class ChatView(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        layout.addWidget(self.browser, 1)
        self.status = text("EVA bereit.", "subtitle")
        layout.addWidget(self.status)
        compose = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Schreib EVA …")
        self.input.setMaxLength(MAX_MESSAGE)
        self.input.returnPressed.connect(self.send)
        self.input.textEdited.connect(lambda _value: controller.state.activity())
        compose.addWidget(self.input, 1)
        self.send_button = button("Senden", self.send, True)
        compose.addWidget(self.send_button)
        self.cancel_button = button("Stopp", controller.cancel_request)
        compose.addWidget(self.cancel_button)
        layout.addLayout(compose)
        controller.views.append(self)

    def send(self):
        if self.controller.send(self.input.text()):
            self.input.clear()

    def refresh(self):
        rows = self.controller.conversations.active["messages"]
        body = "\n\n".join(
            ("DU" if row["role"] == "user" else "EVA") + "\n" + row["content"] for row in rows
        )
        if self.controller.draft:
            body += "\n\nEVA\n" + self.controller.draft
        if not body:
            body = "EVA\nIch bin da. Woran arbeiten wir?"
        if self.controller.notice:
            body += "\n\n" + self.controller.notice
        if self.browser.toPlainText() != body:
            self.browser.setPlainText(body)
            self.browser.moveCursor(QTextCursor.MoveOperation.End)
        self.status.setText(self.controller.status)
        self.send_button.setEnabled(not self.controller.busy)
        self.cancel_button.setEnabled(self.controller.busy)


class CompactChat(QDialog):
    def __init__(self, controller):
        super().__init__(None, Qt.WindowType.Tool)
        self.controller = controller
        self.capture_excluded = False
        self.setWindowTitle("EVA · Chat")
        self.resize(430, 360)
        self.setMinimumSize(340, 260)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(text("EVA", "title"))
        heading.addStretch()
        heading.addWidget(button("Hauptmenü", lambda: controller.open_main("Chat")))
        heading.addWidget(button("×", self.hide))
        layout.addLayout(heading)
        self.view = ChatView(controller)
        layout.addWidget(self.view)

    def showEvent(self, event):
        super().showEvent(event)
        self.capture_excluded = exclude_from_capture(
            self, not self.controller.preferences.get("include_eva_in_screenshots")
        )

    def closeEvent(self, event):
        self.hide()
        event.ignore()


class MainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.capture_excluded = False
        self.setWindowTitle("EVA Desktop Agent")
        self.resize(980, 710)
        self.setMinimumSize(760, 560)
        self.setStyleSheet(STYLE)
        self.setWindowIcon(controller.icon)
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        self.nav = QListWidget()
        self.nav.setFixedWidth(155)
        self.sections = ["Dashboard", "Chat", "Charakter", "Outfits", "Einstellungen"]
        self.nav.addItems(self.sections)
        root.addWidget(self.nav)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.build_dashboard()
        self.build_chat()
        self.build_character()
        self.build_outfits()
        self.build_settings()
        self.nav.setCurrentRow(0)

    def page(self, title, subtitle):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(14)
        layout.addWidget(text(title, "title"))
        layout.addWidget(text(subtitle, "subtitle"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.stack.addWidget(scroll)
        return layout

    def build_dashboard(self):
        layout = self.page("EVA", "Desktop Agent · Gothic Edition")
        self.dashboard_status = text("", "card")
        layout.addWidget(self.dashboard_status)
        layout.addWidget(button("Mit EVA schreiben", lambda: self.controller.open_chat(), True))
        layout.addWidget(button("EVA anzeigen", self.controller.show_character))
        self.share = QCheckBox("Bildschirmfreigabe für den gewählten Monitor aktivieren")
        self.share.toggled.connect(self.controller.set_sharing)
        layout.addWidget(self.share)
        self.observation = text("Bildschirmfreigabe aus.", "card")
        layout.addWidget(self.observation)
        layout.addWidget(
            button(
                "Was siehst du?",
                lambda: self.controller.send("Was siehst du gerade auf meinem Bildschirm?"),
            )
        )
        layout.addWidget(
            text(
                "Freigabe ist bei jedem Start aus. Aufnahmen werden nicht gespeichert. Schließen des Hauptmenüs stoppt eine aktive Freigabe nicht.",
                "subtitle",
            )
        )
        layout.addStretch()

    def build_chat(self):
        layout = self.page(
            "Unterhaltungen",
            "Gespräche werden lokal gespeichert. Bilder bleiben außerhalb des Verlaufs.",
        )
        top = QHBoxLayout()
        self.conversation = QComboBox()
        self.conversation.currentIndexChanged.connect(self.switch_conversation)
        top.addWidget(self.conversation, 1)
        top.addWidget(button("Neu", self.controller.new_conversation))
        top.addWidget(button("Löschen", self.controller.delete_conversation))
        layout.addLayout(top)
        self.chat = ChatView(self.controller)
        self.chat.setMinimumHeight(320)
        layout.addWidget(self.chat, 1)
        layout.addWidget(
            button("KI-Adresse und Modell einstellen", lambda: self.select("Einstellungen"))
        )

    def build_character(self):
        layout = self.page("Charakter", "EVA aus deinem Character Sheet · Originales Gothic-Outfit")
        form = QFormLayout()
        self.pose = QComboBox()
        for name, pose in self.controller.outfit.poses.items():
            self.pose.addItem(pose.label, name)
        self.pose.currentIndexChanged.connect(self.select_pose)
        form.addRow("Pose", self.pose)
        self.pose_note = text("", "subtitle")
        form.addRow("Asset-Status", self.pose_note)
        self.expression = QComboBox()
        for name in self.controller.outfit.expressions:
            self.expression.addItem(name)
        self.expression.currentIndexChanged.connect(self.preview_expression)
        form.addRow("Gesichtsausdruck", self.expression)
        layout.addLayout(form)
        self.expression_preview = QLabel()
        self.expression_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.expression_preview.setMinimumHeight(180)
        layout.addWidget(self.expression_preview)
        layout.addWidget(
            text(
                "Ausdrücke werden als separate Porträts getestet. Fehlende Ganzkörperframes werden nicht durch Gesichtsverformung ersetzt.",
                "subtitle",
            )
        )
        layout.addWidget(
            button(
                "Größe, Monitor und Animationen einstellen", lambda: self.select("Einstellungen")
            )
        )
        layout.addStretch()
        self.preview_expression()

    def build_outfits(self):
        layout = self.page(
            "Outfits", "Externe Asset-Pakete mit JSON-Manifest · Keine neuen Outfits erzeugt"
        )
        self.outfit_info = text("", "card")
        layout.addWidget(self.outfit_info)
        layout.addWidget(button("Outfit-Manifest laden …", self.choose_outfit))
        layout.addWidget(
            button("Originales Gothic-Outfit verwenden", self.controller.default_outfit)
        )
        layout.addWidget(
            text(
                "Ein Outfit definiert Metadaten, transparente PNG-Frames, Posen, Skalierung und Anker. Details und Schema stehen in der Installationsanleitung.",
                "subtitle",
            )
        )
        layout.addStretch()

    def build_settings(self):
        prefs = self.controller.preferences
        layout = self.page(
            "Einstellungen", "Lokal gespeichert · Zugangstoken optional im Windows-Tresor"
        )
        form = QFormLayout()
        self.controls = {}

        def check(key, title):
            widget = QCheckBox()
            widget.setChecked(prefs.get(key))
            self.controls[key] = widget
            form.addRow(title, widget)
            return widget

        def integer(key, title, low, high):
            widget = QSpinBox()
            widget.setRange(low, high)
            widget.setValue(int(prefs.get(key)))
            self.controls[key] = widget
            form.addRow(title, widget)

        def decimal(key, title, low, high, step):
            widget = QDoubleSpinBox()
            widget.setRange(low, high)
            widget.setSingleStep(step)
            widget.setValue(prefs.get(key))
            self.controls[key] = widget
            form.addRow(title, widget)

        check("autostart", "Mit Windows starten")
        check("always_on_top", "Immer im Vordergrund")
        check("include_eva_in_screenshots", "EVA und Chat in Screenshots anzeigen")
        integer("size", "Figurgröße (Sitzhöhe)", 100, 480)
        decimal("opacity", "Deckkraft", 0.3, 1.0, 0.05)
        decimal("position", "Position auf der Taskleistenkante", 0.05, 0.95, 0.05)
        integer("taskbar_offset", "Taskleisten-Feinabgleich (px; + nach unten)", -24, 24)
        self.monitor = QComboBox()
        self.refresh_monitors()
        form.addRow("Monitor", self.monitor)
        check("animations", "Vorhandene Bewegungsframes abspielen")
        decimal("animation_speed", "Animationsgeschwindigkeit", 0.25, 2.0, 0.25)
        check("auto_tired", "Automatisch müde werden / schlafen")
        integer("tired_after", "Müde nach Inaktivität (Sekunden)", 60, 7200)
        integer("sleep_after", "Schlafen nach Inaktivität (Sekunden)", 120, 14400)
        integer("observe_interval", "Bildschirmbeobachtung alle (Sekunden)", 30, 300)
        self.backend = QComboBox()
        for title, key in [
            ("Keine KI · Offline", "none"),
            ("Ollama-Server direkt · Erweitert", "ollama"),
            ("EVA-Bridge · Modell läuft auf dem Server", "bridge"),
        ]:
            self.backend.addItem(title, key)
        self.backend.setCurrentIndex(max(0, self.backend.findData(prefs.get("backend"))))
        form.addRow("KI-Backend", self.backend)
        self.url = QLineEdit(prefs.get("url"))
        form.addRow("API-Adresse (ohne Pfad)", self.url)
        self.model = QLineEdit(prefs.get("model"))
        form.addRow("Ollama-Modell", self.model)
        self.token = QLineEdit(self.controller.token)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Bridge-Token", self.token)
        check("remember_token", "Token im Windows-Tresor speichern")
        self.language = QComboBox()
        self.language.addItem("Deutsch", "de")
        form.addRow("Sprache / Oberfläche", self.language)
        layout.addLayout(form)
        layout.addWidget(
            text(
                "Mit der EVA-Bridge laufen Sprach- und Bildmodell auf dem EVA-Server. Auf dem Haupt-PC sind nur Figur, Chat und Bildschirmaufnahme aktiv. Hier wird kein KI-Modell geladen. Der Server bestimmt das Modell.",
                "subtitle",
            )
        )
        self.backend.currentIndexChanged.connect(self.backend_changed)
        self.backend_changed()
        self.settings_message = text("", "subtitle")
        layout.addWidget(self.settings_message)
        layout.addWidget(button("Einstellungen speichern", self.save_settings, True))
        layout.addStretch()

    def backend_changed(self):
        backend = self.backend.currentData()
        self.model.setEnabled(backend == "ollama")
        self.token.setEnabled(backend == "bridge")
        if backend == "bridge" and self.url.text().rstrip("/") in {
            "http://127.0.0.1:11434",
            "http://localhost:11434",
        }:
            self.url.setText("http://192.168.2.15:8766")
        self.model.setToolTip(
            "Das Modell wird auf dem EVA-Server über EVA_COMPANION_MODEL gewählt."
            if backend == "bridge"
            else "Installierter Modellname auf dem Ollama-Server."
        )

    def refresh_monitors(self):
        from PySide6.QtWidgets import QApplication

        self.monitor.clear()
        for screen in QApplication.screens():
            self.monitor.addItem(screen.name(), screen.name())
        self.monitor.setCurrentIndex(
            max(0, self.monitor.findData(self.controller.preferences.get("monitor")))
        )

    def save_settings(self):
        values = {
            key: widget.isChecked() if isinstance(widget, QCheckBox) else widget.value()
            for key, widget in self.controls.items()
        }
        values.update(
            monitor=self.monitor.currentData() or "",
            backend=self.backend.currentData(),
            url=self.url.text().strip(),
            model=self.model.text().strip(),
            language=self.language.currentData(),
        )
        try:
            self.controller.save_preferences(values, self.token.text().strip())
            self.settings_message.setText("Gespeichert.")
        except (ValueError, RuntimeError, OSError) as exc:
            self.settings_message.setText(str(exc))

    def select(self, section):
        self.nav.setCurrentRow(self.sections.index(section))

    def select_pose(self):
        name = self.pose.currentData()
        if name:
            self.controller.set_pose(name)

    def preview_expression(self):
        if not hasattr(self, "expression_preview"):
            return
        path = self.controller.outfit.expressions.get(self.expression.currentText())
        if path:
            image = self.controller.outfit.pixmap(path)
            self.expression_preview.setPixmap(
                image.scaled(
                    240,
                    200,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def switch_conversation(self):
        selected = self.conversation.currentData()
        if selected:
            self.controller.switch_conversation(selected)

    def choose_outfit(self):
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "Outfit-Manifest laden",
            str(self.controller.preferences.directory),
            "Outfit (*.json)",
        )
        if filename:
            self.controller.load_outfit(Path(filename))

    def refresh(self):
        c = self.controller
        pose = c.outfit.pose(c.state.current)
        self.dashboard_status.setText(
            f"Status: {c.status}\nPose: {pose.label}\nKI: {c.preferences.get('backend')}\nMonitor: {c.pet.selected_screen().name()}\nTaskleiste: {c.pet.taskbar.edge if c.pet.taskbar else 'unbekannt'}"
        )
        self.observation.setText(c.observation)
        self.share.blockSignals(True)
        self.share.setChecked(c.sharing)
        self.share.blockSignals(False)
        self.pose.blockSignals(True)
        self.pose.setCurrentIndex(max(0, self.pose.findData(c.state.current)))
        self.pose.blockSignals(False)
        self.pose_note.setText(
            f"{len(pose.frames)} Frame(s) · {pose.note or 'Standbild; Bewegungsframes fehlen.'}"
        )
        self.outfit_info.setText(
            c.outfit.name + "\n" + c.outfit.description + "\n" + str(c.outfit.manifest)
        )
        self.conversation.blockSignals(True)
        self.conversation.clear()
        for row in c.conversations.items:
            self.conversation.addItem(row["title"], row["id"])
        self.conversation.setCurrentIndex(
            max(0, self.conversation.findData(c.conversations.current))
        )
        self.conversation.blockSignals(False)
        self.conversation.setEnabled(not c.busy)

    def showEvent(self, event):
        super().showEvent(event)
        self.capture_excluded = exclude_from_capture(
            self, not self.controller.preferences.get("include_eva_in_screenshots")
        )

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
