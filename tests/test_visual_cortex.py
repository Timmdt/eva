import tempfile
import unittest
from pathlib import Path

from memory.profile_policy import access_for_identity
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


if __name__ == "__main__":
    unittest.main()
