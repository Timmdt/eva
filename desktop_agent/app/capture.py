from __future__ import annotations

import base64
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt

from ..companion_protocol import MAX_IMAGE
from . import windows


def exclude_from_capture(widget, exclude=True):
    """Return whether capture exclusion is active; exclude=False resets WDA_NONE."""
    if sys.platform != "win32":
        return False
    try:
        from ctypes import wintypes as W

        function = windows.ctypes.windll.user32.SetWindowDisplayAffinity
        function.argtypes = [W.HWND, W.DWORD]
        function.restype = W.BOOL
        return bool(function(int(widget.winId()), 0x11 if exclude else 0)) and exclude
    except (OSError, AttributeError):
        return False


def screenshot(screen):
    pixmap = screen.grabWindow(0)
    if pixmap.isNull():
        raise RuntimeError("Monitoraufnahme nicht verfügbar. Windows-Berechtigungen prüfen.")
    pixmap = pixmap.scaled(
        1600, 1000, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    success = pixmap.save(buffer, "JPEG", 78)
    buffer.close()
    if not success or len(data) > MAX_IMAGE:
        raise RuntimeError("Monitoraufnahme konnte nicht erstellt werden.")
    return base64.b64encode(bytes(data)).decode("ascii")
