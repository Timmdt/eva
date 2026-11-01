"""Native Windows integration. All coordinates returned to Qt are logical pixels."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRect


@dataclass
class Taskbar:
    edge: str
    rect: QRect
    native: bool = False


def fallback_taskbar(screen) -> Taskbar:
    full, work = screen.geometry(), screen.availableGeometry()
    gaps = {
        "left": work.left() - full.left(),
        "top": work.top() - full.top(),
        "right": full.right() - work.right(),
        "bottom": full.bottom() - work.bottom(),
    }
    edge = max(gaps, key=gaps.get)
    if gaps[edge] <= 0:
        return Taskbar("bottom", QRect(full.left(), full.bottom() + 1, full.width(), 0))
    if edge == "bottom":
        rect = QRect(full.left(), work.bottom() + 1, full.width(), gaps[edge])
    elif edge == "top":
        rect = QRect(full.left(), full.top(), full.width(), gaps[edge])
    elif edge == "left":
        rect = QRect(full.left(), full.top(), gaps[edge], full.height())
    else:
        rect = QRect(work.right() + 1, full.top(), gaps[edge], full.height())
    return Taskbar(edge, rect)


def taskbar_for_screen(screen) -> Taskbar:
    fallback = fallback_taskbar(screen)
    if sys.platform != "win32":
        return fallback
    try:
        from ctypes import wintypes as W

        user, shell = ctypes.windll.user32, ctypes.windll.shell32

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", W.DWORD),
                ("rcMonitor", W.RECT),
                ("rcWork", W.RECT),
                ("dwFlags", W.DWORD),
                ("szDevice", W.WCHAR * 32),
            ]

        class AppBarData(ctypes.Structure):
            _fields_ = [
                ("cbSize", W.DWORD),
                ("hWnd", W.HWND),
                ("uCallbackMessage", W.UINT),
                ("uEdge", W.UINT),
                ("rc", W.RECT),
                ("lParam", W.LPARAM),
            ]

        user.GetMonitorInfoW.argtypes = [W.HANDLE, ctypes.POINTER(MonitorInfo)]
        user.GetMonitorInfoW.restype = W.BOOL
        callback_type = ctypes.WINFUNCTYPE(
            W.BOOL, W.HANDLE, W.HDC, ctypes.POINTER(W.RECT), W.LPARAM
        )
        monitors = []

        def collect(handle, _dc, _rect, _param):
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(info)
            if user.GetMonitorInfoW(handle, ctypes.byref(info)):
                monitors.append(info)
            return True

        callback = callback_type(collect)
        user.EnumDisplayMonitors.argtypes = [W.HDC, ctypes.POINTER(W.RECT), callback_type, W.LPARAM]
        user.EnumDisplayMonitors(None, None, callback, 0)
        monitor = next(
            (info for info in monitors if info.szDevice.lower() == screen.name().lower()), None
        )
        if monitor is None:
            return fallback
        native = monitor.rcMonitor
        user.FindWindowW.argtypes = [W.LPCWSTR, W.LPCWSTR]
        user.FindWindowW.restype = W.HWND
        user.FindWindowExW.argtypes = [W.HWND, W.HWND, W.LPCWSTR, W.LPCWSTR]
        user.FindWindowExW.restype = W.HWND
        user.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
        candidates = []
        primary = user.FindWindowW("Shell_TrayWnd", None)
        if primary:
            candidates.append(primary)
        previous = None
        while True:
            previous = user.FindWindowExW(None, previous, "Shell_SecondaryTrayWnd", None)
            if not previous:
                break
            candidates.append(previous)
        rect = None
        for handle in candidates:
            candidate = W.RECT()
            if user.GetWindowRect(handle, ctypes.byref(candidate)):
                cx, cy = (
                    (candidate.left + candidate.right) / 2,
                    (candidate.top + candidate.bottom) / 2,
                )
                if native.left <= cx < native.right and native.top <= cy <= native.bottom:
                    rect = candidate
                    break
        if rect is None and monitor.dwFlags & 1:
            info = AppBarData()
            info.cbSize = ctypes.sizeof(info)
            shell.SHAppBarMessage.argtypes = [W.DWORD, ctypes.POINTER(AppBarData)]
            shell.SHAppBarMessage.restype = ctypes.c_size_t
            if shell.SHAppBarMessage(5, ctypes.byref(info)):  # ABM_GETTASKBARPOS
                rect = info.rc
        if rect is None:
            return fallback
        # Use the attached monitor's physical/logical transform, including negative origins.
        logical = screen.geometry()
        sx, sy = (
            logical.width() / (native.right - native.left),
            logical.height() / (native.bottom - native.top),
        )
        x = logical.x() + round((rect.left - native.left) * sx)
        y = logical.y() + round((rect.top - native.top) * sy)
        mapped = QRect(
            x,
            y,
            max(1, round((rect.right - rect.left) * sx)),
            max(1, round((rect.bottom - rect.top) * sy)),
        )
        distances = {
            "left": abs(rect.left - native.left),
            "right": abs(rect.right - native.right),
            "top": abs(rect.top - native.top),
            "bottom": abs(rect.bottom - native.bottom),
        }
        # A horizontal bar touches left and right too; classify by aspect first.
        edges = ("top", "bottom") if mapped.width() >= mapped.height() else ("left", "right")
        return Taskbar(min(edges, key=distances.get), mapped, True)
    except (OSError, AttributeError, ValueError, ZeroDivisionError):
        return fallback


def anchored_position(
    screen_rect: QRect,
    taskbar: Taskbar,
    width: int,
    height: int,
    anchor: tuple[float, float],
    fraction: float,
    vertical_offset: int = 0,
) -> QPoint:
    x = screen_rect.left() + round(screen_rect.width() * fraction - width * anchor[0])
    if taskbar.edge == "bottom":
        y = taskbar.rect.top() - round(height * anchor[1])
    elif taskbar.edge == "top":
        y = taskbar.rect.bottom() + 1
    else:
        y = screen_rect.bottom() + 1 - height
        x = taskbar.rect.right() + 1 if taskbar.edge == "left" else taskbar.rect.left() - width
    x = max(screen_rect.left(), min(screen_rect.right() + 1 - width, x))
    y = max(screen_rect.top(), min(screen_rect.bottom() + 1 - height, y + vertical_offset))
    return QPoint(x, y)


def idle_seconds() -> float | None:
    if sys.platform != "win32":
        return None
    from ctypes import wintypes as W

    class LastInput(ctypes.Structure):
        _fields_ = [("cbSize", W.UINT), ("dwTime", W.DWORD)]

    info = LastInput()
    info.cbSize = ctypes.sizeof(info)
    ctypes.windll.user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LastInput)]
    ctypes.windll.kernel32.GetTickCount.restype = W.DWORD
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        tick = ctypes.windll.kernel32.GetTickCount()
        return ((tick - info.dwTime) & 0xFFFFFFFF) / 1000
    return None


def set_autostart(enabled: bool):
    if sys.platform != "win32":
        if enabled:
            raise RuntimeError("Autostart steht unter Windows 10/11 zur Verfügung.")
        return
    import winreg

    python = Path(sys.executable)
    if getattr(sys, "frozen", False):
        command = subprocess.list2cmdline([str(python)])
    else:
        launcher = Path(__file__).resolve().parents[1] / "launch.py"
        pythonw = python.with_name("pythonw.exe")
        if pythonw.is_file():
            python = pythonw
        command = subprocess.list2cmdline([str(python), str(launcher)])
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
    ) as key:
        if enabled:
            winreg.SetValueEx(key, "EVADesktopAgent", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "EVADesktopAgent")
            except FileNotFoundError:
                pass


def native_hit_test(message, contains):
    """Layered alpha/mask handles other processes; HTTRANSPARENT handles same-thread windows."""
    if sys.platform != "win32":
        return None
    from ctypes import wintypes as W

    event = W.MSG.from_address(int(message))
    if event.message == 0x0084:  # WM_NCHITTEST
        x = ctypes.c_short(event.lParam & 0xFFFF).value
        y = ctypes.c_short((event.lParam >> 16) & 0xFFFF).value
        point = W.POINT(x, y)
        ctypes.windll.user32.ScreenToClient.argtypes = [W.HWND, ctypes.POINTER(W.POINT)]
        ctypes.windll.user32.ScreenToClient(event.hWnd, ctypes.byref(point))
        # Native client pixels -> Qt logical pixels is supplied by the widget.
        return 1 if contains(point.x, point.y) else -1
    return None
