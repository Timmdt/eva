from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QBitmap, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from .capture import exclude_from_capture
from .windows import anchored_position, native_hit_test, taskbar_for_screen


class CharacterWindow(QWidget):
    clicked = Signal()
    context_requested = Signal(QPoint)

    def __init__(self, preferences, outfit, state):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.preferences, self.outfit, self.state = preferences, outfit, state
        self.capture_excluded = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("EVA · Desktop Agent")
        self.setToolTip("Klicken: Chat · Rechtsklick: Menü · Position ist gesperrt")
        self.frame_index = 0
        self.frame = None
        self.image = None
        self.taskbar = None
        self.layout_signature = None
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.next_frame)
        self.geometry_timer = QTimer(self)
        self.geometry_timer.timeout.connect(self.reposition)
        self.geometry_timer.start(1500)
        state.changed.connect(self.pose_changed)
        self.apply_preferences()

    def selected_screen(self):
        return next(
            (
                screen
                for screen in QApplication.screens()
                if screen.name() == self.preferences.get("monitor")
            ),
            QApplication.primaryScreen(),
        )

    def apply_preferences(self):
        visible = self.isVisible()
        self.setWindowFlag(
            Qt.WindowType.WindowStaysOnTopHint, self.preferences.get("always_on_top")
        )
        self.setWindowOpacity(self.preferences.get("opacity"))
        self.layout_signature = None
        self.pose_changed(self.state.current)
        if visible:
            self.show()

    def set_outfit(self, outfit):
        self.outfit = outfit
        self.pose_changed(self.state.current)

    def pose_changed(self, _name):
        self.frame_index = 0
        self.frame_timer.stop()
        pose = self.outfit.pose(self.state.current)
        if self.preferences.get("animations") and len(pose.frames) > 1:
            self.frame_timer.start(
                round(pose.duration_ms / self.preferences.get("animation_speed"))
            )
        self.layout_signature = None
        self.reposition()

    def next_frame(self):
        pose = self.outfit.pose(self.state.current)
        self.frame_index = (self.frame_index + 1) % len(pose.frames)
        self.layout_signature = None
        self.reposition()

    def reposition(self):
        screen = self.selected_screen()
        if screen is None:
            return
        bar = taskbar_for_screen(screen)
        pose = self.outfit.pose(self.state.current)
        signature = (
            screen.name(),
            tuple(screen.geometry().getRect()),
            bar.edge,
            tuple(bar.rect.getRect()),
            pose.name,
            self.frame_index,
            self.preferences.get("size"),
            self.preferences.get("position"),
            self.preferences.get("taskbar_offset"),
        )
        if signature == self.layout_signature:
            return
        source = self.outfit.pixmap(pose.frames[self.frame_index])
        available = screen.availableGeometry()
        wanted = min(round(self.preferences.get("size") * pose.scale), available.height() - 12)
        width_limit = max(80, min(available.width() - 12, round(wanted * 2.5)))
        self.frame = source.scaled(
            width_limit,
            max(40, wanted),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image = self.frame.toImage()
        self.resize(self.frame.size())
        # Native region and per-pixel alpha ensure transparent areas pass clicks to other apps.
        self.setMask(QBitmap.fromImage(self.image.createAlphaMask()))
        position = anchored_position(
            screen.geometry(),
            bar,
            self.width(),
            self.height(),
            pose.anchor,
            self.preferences.get("position"),
            self.preferences.get("taskbar_offset"),
        )
        self.move(position)
        self.taskbar, self.layout_signature = bar, signature
        self.update()

    def hit(self, point):
        if self.image is None or not self.rect().contains(point):
            return False
        return self.image.pixelColor(point).alpha() >= 24

    def paintEvent(self, _event):
        if self.frame is not None:
            painter = QPainter(self)
            painter.drawPixmap(0, 0, self.frame)

    def mousePressEvent(self, event):
        if not self.hit(event.position().toPoint()):
            event.ignore()
            return
        self.state.activity()
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def contextMenuEvent(self, event):
        if self.hit(event.pos()):
            self.state.activity()
            self.context_requested.emit(event.globalPos())

    def nativeEvent(self, kind, message):
        ratio = self.devicePixelRatioF()
        result = native_hit_test(
            message, lambda x, y: self.hit(QPoint(round(x / ratio), round(y / ratio)))
        )
        if result is not None:
            return True, result
        return super().nativeEvent(kind, message)

    def showEvent(self, event):
        super().showEvent(event)
        self.capture_excluded = exclude_from_capture(
            self, not self.preferences.get("include_eva_in_screenshots")
        )
        self.geometry_timer.start(1500)
        pose = self.outfit.pose(self.state.current)
        if self.preferences.get("animations") and len(pose.frames) > 1:
            self.frame_timer.start(
                round(pose.duration_ms / self.preferences.get("animation_speed"))
            )

    def hideEvent(self, event):
        self.geometry_timer.stop()
        self.frame_timer.stop()
        super().hideEvent(event)

    def stop(self):
        self.frame_timer.stop()
        self.geometry_timer.stop()
        self.hide()
