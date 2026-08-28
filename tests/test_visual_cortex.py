import tempfile
import unittest
from pathlib import Path

from memory.profile_policy import access_for_identity
from interfaces.presence_state import PresenceFusion
from visual_cortex.identity import IdentityStore
from visual_cortex.state import VisualConfig


class VisualCortexTest(unittest.TestCase):
    def test_registered_and_unknown_face(self):
        vectors = {"tim": [1.0, 0.0], "unknown": [0.0, 1.0]}
        with tempfile.TemporaryDirectory() as directory:
            store = IdentityStore(Path(directory, "faces.json"), threshold=0.9,
                                  extractor=lambda frame: vectors[frame])
            store.enroll("Tim", "tim")
            known = store.recognize("tim")
            unknown = store.recognize("unknown")
            self.assertEqual(known["identity"], "Tim")
            self.assertTrue(known["registered"])
            self.assertIsNone(unknown["identity"])
            self.assertFalse(unknown["registered"])

    def test_privacy_defaults_and_profile_policy(self):
        self.assertFalse(VisualConfig().save_frames)
        self.assertFalse(access_for_identity(None).allow_private_memory)
        self.assertFalse(access_for_identity("Visitor").allow_private_memory)
        self.assertTrue(access_for_identity("Tim").allow_private_memory)

    def test_room_and_desk_presence_fusion_gates_personal_context(self):
        fusion = PresenceFusion()
        room = fusion.update({"sensor": "room", "presence": True,
                              "identity": "Tim", "confidence": 0.95})
        self.assertTrue(room.room_presence)
        self.assertFalse(room.personal_context_allowed)
        desk = fusion.update({"sensor": "desk", "presence": True,
                              "identity": "Tim", "confidence": 0.91})
        self.assertTrue(desk.desk_presence)
        self.assertTrue(desk.personal_context_allowed)
        unknown = fusion.update({"sensor": "desk", "presence": True,
                                 "identity": None, "confidence": 0.0})
        self.assertFalse(unknown.personal_context_allowed)

    def test_stale_desk_presence_cannot_keep_private_context_open(self):
        now = [0.0]
        fusion = PresenceFusion(ttl_seconds=10, clock=lambda: now[0])
        self.assertTrue(fusion.update({"sensor": "desk", "presence": True,
                                      "identity": "Tim"}).personal_context_allowed)
        now[0] = 10.1
        self.assertFalse(fusion.current().personal_context_allowed)


if __name__ == "__main__":
    unittest.main()
