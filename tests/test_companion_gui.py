"""Qt integration tests for the actual Gothic desktop application."""

import base64
import importlib.util
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HAS_QT = importlib.util.find_spec("PySide6") is not None
if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from http.server import BaseHTTPRequestHandler

    from PySide6.QtCore import QPoint, QRect, QSize, Qt
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from desktop_agent.app.capture import screenshot
    from desktop_agent.app.character import DEFAULT_OUTFIT, CharacterState, Outfit
    from desktop_agent.app.controller import Companion
    from desktop_agent.app.storage import Conversations, Preferences
    from desktop_agent.app.windows import Taskbar, anchored_position, fallback_taskbar
    from tests.test_companion import serving


@unittest.skipUnless(HAS_QT, "Optional: requirements-desktop.txt installieren")
class DesktopCoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setQuitOnLastWindowClosed(False)

    def test_preferences_restore_and_do_not_accept_secret_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            prefs = Preferences(Path(directory))
            prefs.update(
                {"size": 280, "opacity": 0.8, "monitor": "DISPLAY2", "token": "must-not-save"}
            )
            restored = Preferences(Path(directory))
            self.assertEqual(restored.get("size"), 280)
            self.assertEqual(restored.get("monitor"), "DISPLAY2")
            self.assertNotIn("token", json.loads(prefs.path.read_text()))
            prefs.path.write_text(
                '{"size":"invalid", "opacity":4, "backend":"bad", "always_on_top":"false"}'
            )
            checked = Preferences(Path(directory))
            self.assertEqual(checked.get("size"), 220)
            self.assertEqual(checked.get("opacity"), 1)
            self.assertEqual(checked.get("backend"), "none")
            self.assertTrue(checked.get("always_on_top"))

    def test_conversations_round_trip_and_separate_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Conversations(Path(directory))
            first = store.current
            store.append("user", "Eine Frage")
            store.append("assistant", "Eine Antwort")
            store.new()
            store.append("user", "Anderer Kontext")
            restored = Conversations(Path(directory))
            self.assertEqual(len(restored.items), 2)
            self.assertNotEqual(first, restored.current)
            self.assertEqual(restored.active["messages"][0]["content"], "Anderer Kontext")

    def test_asset_pack_has_all_required_states_and_explicit_static_fallbacks(self):
        outfit = Outfit()
        required = {
            "idle",
            "listening",
            "thinking",
            "talking",
            "happy",
            "annoyed",
            "tired",
            "sleeping",
            "standing",
            "waving",
        }
        self.assertTrue(required <= set(outfit.poses))
        self.assertEqual(len(outfit.expressions), 8)
        self.assertIn("statisch", outfit.pose("talking").note)
        self.assertIn("Ersatz", outfit.pose("annoyed").note)
        for pose in outfit.poses.values():
            image = outfit.pixmap(pose.frames[0]).toImage()
            self.assertTrue(image.hasAlphaChannel())
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0)

    def test_outfit_rejects_path_escape(self):
        original = json.loads(DEFAULT_OUTFIT.read_text())
        original["poses"]["idle"]["frames"] = ["../../../private.png"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outfits/invalid.json"
            path.parent.mkdir()
            path.write_text(json.dumps(original))
            with self.assertRaises(ValueError):
                Outfit(path)

    def test_taskbar_anchors_handle_all_edges_and_negative_monitor_origin(self):
        screen = QRect(-1920, 0, 1920, 1080)
        bars = {
            "bottom": QRect(-1920, 1040, 1920, 40),
            "top": QRect(-1920, 0, 1920, 40),
            "left": QRect(-1920, 0, 60, 1080),
            "right": QRect(-60, 0, 60, 1080),
        }
        for edge, rect in bars.items():
            with self.subTest(edge=edge):
                position = anchored_position(screen, Taskbar(edge, rect), 220, 350, (0.5, 1.0), 0.8)
                bounds = QRect(position, QSize(220, 350))
                self.assertTrue(screen.contains(bounds))
                if edge == "bottom":
                    self.assertEqual(position.y() + 350, 1040)
                if edge == "top":
                    self.assertEqual(position.y(), 40)
        fake = SimpleNamespace(
            geometry=lambda: QRect(0, 0, 1920, 1080),
            availableGeometry=lambda: QRect(0, 0, 1920, 1040),
        )
        self.assertEqual(fallback_taskbar(fake).edge, "bottom")
        baseline = anchored_position(
            screen, Taskbar("bottom", bars["bottom"]), 220, 350, (0.5, 1), 0.8
        )
        adjusted = anchored_position(
            screen, Taskbar("bottom", bars["bottom"]), 220, 350, (0.5, 1), 0.8, 3
        )
        self.assertEqual(adjusted.y(), baseline.y() + 3)

    def test_idle_state_transitions_and_manual_return(self):
        now = [0.0]
        state = CharacterState(clock=lambda: now[0])
        state.set("waving", seconds=2)
        now[0] = 3
        state.tick(auto_tired=True, tired_after=60, sleep_after=120)
        self.assertEqual(state.current, "idle")
        now[0] = 80
        state.tick(auto_tired=True, tired_after=60, sleep_after=120)
        self.assertEqual(state.current, "tired")
        now[0] = 150
        state.tick(auto_tired=True, tired_after=60, sleep_after=120)
        self.assertEqual(state.current, "sleeping")
        state.activity()
        self.assertEqual(state.current, "listening")


@unittest.skipUnless(HAS_QT, "Optional: requirements-desktop.txt installieren")
class CompanionGuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.controller = Companion(Path(self.directory.name))
        self.application.processEvents()

    def tearDown(self):
        self.controller.quit()
        for window in (self.controller.pet, self.controller.compact, self.controller.main_window):
            window.deleteLater()
        self.application.processEvents()
        self.directory.cleanup()

    def pump_until(self, condition, timeout=4):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.01)
        self.assertTrue(condition(), "Operation did not complete")
        self.application.processEvents()

    def test_startup_is_character_only_and_operates_without_ai(self):
        c = self.controller
        self.assertTrue(c.pet.isVisible())
        self.assertFalse(c.main_window.isVisible())
        self.assertFalse(c.compact.isVisible())
        self.assertFalse(c.sharing)
        self.assertFalse(c.send("Hallo"))
        self.assertIn("Noch keine KI", c.notice)
        self.assertFalse(c.busy)
        c.open_chat()
        self.assertTrue(c.compact.isVisible())
        self.assertEqual(c.state.current, "listening")
        self.assertIn("keine KI", c.compact.view.browser.toPlainText())

    def test_all_poses_stay_inside_monitor_and_keep_taskbar_anchor(self):
        c = self.controller
        screen = c.pet.selected_screen().geometry()
        bar = Taskbar("bottom", QRect(screen.left(), screen.bottom() - 39, screen.width(), 40))
        with patch("desktop_agent.app.pet.taskbar_for_screen", return_value=bar):
            c.pet.reposition()
            for name in c.outfit.poses:
                c.set_pose(name)
                self.application.processEvents()
                self.assertTrue(screen.contains(c.pet.geometry()), name)
                pose = c.outfit.pose(name)
                anchor = c.pet.y() + round(c.pet.height() * pose.anchor[1])
                self.assertLessEqual(abs(anchor - c.pet.taskbar.rect.top()), 1, name)

    def test_transparent_regions_are_not_clickable_and_position_is_locked(self):
        c = self.controller
        c.set_pose("listening")
        self.assertFalse(c.pet.hit(QPoint(0, 0)))
        opaque = next(
            QPoint(x, y)
            for y in range(0, c.pet.height(), 3)
            for x in range(0, c.pet.width(), 3)
            if c.pet.hit(QPoint(x, y))
        )
        before = c.pet.pos()
        QTest.mousePress(c.pet, Qt.MouseButton.LeftButton, pos=opaque)
        QTest.mouseMove(c.pet, opaque + QPoint(50, 30))
        QTest.mouseRelease(c.pet, Qt.MouseButton.LeftButton, pos=opaque + QPoint(50, 30))
        self.assertEqual(c.pet.pos(), before)
        self.assertTrue(c.compact.isVisible())

    def test_main_menu_pages_and_expression_preview(self):
        c = self.controller
        for section in c.main_window.sections:
            c.open_main(section)
            self.assertEqual(c.main_window.nav.currentItem().text(), section)
        self.assertFalse(c.main_window.expression_preview.pixmap().isNull())
        c.main_window.hide()
        c.hide_character()
        c.show_character()
        self.assertTrue(c.pet.isVisible())

    def test_bundled_outfit_does_not_pin_an_old_installation_path(self):
        c = self.controller
        c.default_outfit()
        self.assertEqual(c.preferences.get("outfit"), "")

    def test_capture_preferences_reset_windows_affinity_to_allow_screenshots(self):
        from unittest.mock import MagicMock

        from desktop_agent.app import capture
        from desktop_agent.app.capture import exclude_from_capture

        function = MagicMock(return_value=1)
        fake_windows = SimpleNamespace(user32=SimpleNamespace(SetWindowDisplayAffinity=function))
        with (
            patch.object(capture.sys, "platform", "win32"),
            patch.object(capture.windows.ctypes, "windll", fake_windows, create=True),
        ):
            widget = SimpleNamespace(winId=lambda: 501)
            self.assertTrue(exclude_from_capture(widget, True))
            function.assert_called_with(501, 0x11)
            self.assertFalse(exclude_from_capture(widget, False))
            function.assert_called_with(501, 0)

    def test_own_screenshot_keeps_eva_and_chat_visible_when_enabled(self):
        c = self.controller
        self.assertTrue(c.preferences.get("include_eva_in_screenshots"))
        c.open_chat()
        c.sharing = True

        def capture_visible(_screen):
            self.assertTrue(c.pet.isVisible())
            self.assertTrue(c.compact.isVisible())
            return "synthetic-test-image"

        def launch(_backend, _message, _mode, image, _generation):
            self.assertEqual(image, "synthetic-test-image")
            c.reset_request()

        with (
            patch("desktop_agent.app.controller.screenshot", side_effect=capture_visible),
            patch.object(c, "launch", side_effect=launch),
        ):
            c.begin_request(object(), "Was siehst du auf meinem Monitor?", "chat")
            self.pump_until(lambda: not c.busy)
        self.assertTrue(c.pet.isVisible())
        self.assertTrue(c.compact.isVisible())

    def test_capture_visibility_setting_is_saved_and_applied_to_all_windows(self):
        c = self.controller
        checkbox = c.main_window.controls["include_eva_in_screenshots"]
        self.assertTrue(checkbox.isChecked())
        checkbox.setChecked(False)
        with patch(
            "desktop_agent.app.controller.exclude_from_capture", return_value=True
        ) as exclusion:
            c.main_window.save_settings()
            self.assertEqual(exclusion.call_count, 3)
            self.assertTrue(all(call.args[1] for call in exclusion.call_args_list))
        self.assertFalse(Preferences(Path(self.directory.name)).get("include_eva_in_screenshots"))
        checkbox.setChecked(True)
        with patch(
            "desktop_agent.app.controller.exclude_from_capture", return_value=False
        ) as exclusion:
            c.main_window.save_settings()
            self.assertTrue(all(not call.args[1] for call in exclusion.call_args_list))
        self.assertTrue(Preferences(Path(self.directory.name)).get("include_eva_in_screenshots"))

    def test_escape_closes_small_chat_and_settings_save_applies_to_character(self):
        c = self.controller
        c.open_chat()
        QTest.keyClick(c.compact, Qt.Key.Key_Escape)
        self.application.processEvents()
        self.assertFalse(c.compact.isVisible())
        self.assertTrue(c.pet.isVisible())
        c.main_window.controls["size"].setValue(260)
        c.main_window.controls["opacity"].setValue(0.8)
        c.main_window.save_settings()
        self.assertEqual(c.main_window.settings_message.text(), "Gespeichert.")
        self.assertEqual(Preferences(Path(self.directory.name)).get("size"), 260)
        self.assertAlmostEqual(c.pet.windowOpacity(), 0.8, places=2)

    def test_pausing_before_capture_discards_pending_observation(self):
        c = self.controller
        c.preferences.update({"backend": "ollama", "url": "http://127.0.0.1:1"})
        with patch(
            "desktop_agent.app.controller.screenshot",
            side_effect=AssertionError("unexpected screenshot"),
        ):
            c.set_sharing(True)
            c.observe()
            c.set_sharing(False)
            self.pump_until(lambda: not c.busy)
        self.assertFalse(c.sharing)
        self.assertFalse(c.observer.isActive())
        self.assertEqual(c.conversations.active["messages"], [])

    def test_ollama_stream_changes_character_state_and_persists_complete_answer(self):
        started, release = threading.Event(), threading.Event()
        captured = []

        class FakeOllama(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"message":{"content":"Hallo "},"done":false}\n')
                self.wfile.flush()
                started.set()
                release.wait(3)
                self.wfile.write(b'{"message":{"content":"von EVA."},"done":true}\n')

            def log_message(self, *_args):
                pass

        with serving(FakeOllama) as url:
            c = self.controller
            c.preferences.update({"backend": "ollama", "url": url, "model": "test-model"})
            with patch(
                "desktop_agent.app.controller.screenshot",
                side_effect=AssertionError("unexpected screenshot"),
            ):
                self.assertTrue(c.send("Hallo EVA"))
                self.assertEqual(c.state.current, "thinking")
                self.pump_until(lambda: c.draft == "Hallo ")
                self.assertEqual(c.state.current, "talking")
                release.set()
                self.pump_until(lambda: not c.busy)
            self.assertEqual(c.conversations.active["messages"][-1]["content"], "Hallo von EVA.")
            self.assertEqual(c.state.current, "listening")
            self.assertEqual(captured[0]["model"], "test-model")
            self.assertNotIn("images", captured[0]["messages"][-1])

    def test_screen_encoding_is_jpeg_and_resized(self):
        pixmap = QPixmap(3840, 2160)
        pixmap.fill(QColor("#345678"))
        encoded = screenshot(SimpleNamespace(grabWindow=lambda _handle: pixmap))
        image = QPixmap()
        self.assertTrue(image.loadFromData(base64.b64decode(encoded), "JPEG"))
        self.assertLessEqual(image.width(), 1600)
        self.assertLessEqual(image.height(), 1000)

    def test_enabled_sharing_does_not_capture_monitor_for_smalltalk_or_math(self):
        captured = []

        class FakeOllama(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"message":{"content":"10"},"done":true}\n')

            def log_message(self, *_args):
                pass

        with serving(FakeOllama) as url:
            c = self.controller
            c.preferences.update({"backend": "ollama", "url": url, "model": "test"})
            c.sharing = True
            with patch(
                "desktop_agent.app.controller.screenshot",
                side_effect=AssertionError("unnecessary capture"),
            ):
                for message in ("wie geht es dir", "was ist 5+5"):
                    self.assertTrue(c.send(message))
                    self.pump_until(lambda: not c.busy)
            self.assertTrue(all("images" not in request["messages"][-1] for request in captured))

    def test_cancel_closes_a_pending_stream_even_when_server_uses_http_10(self):
        release = threading.Event()

        class SlowOllama(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"message":{"content":"Start"},"done":false}\n')
                self.wfile.flush()
                release.wait(3)

            def log_message(self, *_args):
                pass

        with serving(SlowOllama) as url:
            try:
                c = self.controller
                c.preferences.update({"backend": "ollama", "url": url, "model": "test"})
                c.send("Test")
                self.pump_until(lambda: c.draft == "Start")
                task = c.task
                c.cancel_request()
                self.pump_until(lambda: not task.thread.is_alive(), timeout=1)
                self.assertFalse(c.busy)
            finally:
                release.set()


if __name__ == "__main__":
    unittest.main()
