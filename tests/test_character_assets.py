import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HAS_PIL = importlib.util.find_spec("PIL") is not None
if HAS_PIL:
    from PIL import Image, ImageDraw

    from tools.prepare_character_assets import (
        pose_cells,
        prepare,
        principal_figure,
        row_boundaries,
        support_anchor,
    )


@unittest.skipUnless(
    HAS_PIL, "Asset-Prüfung benötigt die optionale Entwicklungsabhängigkeit Pillow"
)
class CharacterAssetTest(unittest.TestCase):
    def test_atlas_tool_cannot_overwrite_user_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "assets/character/outfits/gothic.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"pose_sources": {"idle": {"sha256": "original"}}}))
            before = manifest.read_bytes()
            with (
                patch("tools.prepare_character_assets.ROOT", root),
                self.assertRaisesRegex(ValueError, "Original-PNGs"),
            ):
                prepare(root / "absent.png", root / "absent.png", root / "absent.png")
            self.assertEqual(manifest.read_bytes(), before)
            self.assertFalse((root / "assets/character/poses").exists())

    def test_rows_follow_real_gutter_instead_of_cutting_at_half_height(self):
        image = Image.new("RGBA", (120, 100))
        draw = ImageDraw.Draw(image)
        draw.rectangle((5, 8, 52, 56), fill="red")
        draw.rectangle((66, 6, 112, 56), fill="blue")
        draw.rectangle((6, 65, 54, 94), fill="green")
        draw.rectangle((67, 65, 113, 94), fill="yellow")
        boundary = row_boundaries(image, 2)[1]
        self.assertTrue(57 <= boundary <= 65)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "atlas.png"
            image.save(path)
            result = list(pose_cells(path, columns=2, rows=2))
        self.assertEqual(result[0].height, 57)
        # Lower-row crops must not contain the red/blue pixels from the upper row.
        for crop in result[2:]:
            opaque_colors = {pixel[:3] for pixel in crop.getdata() if pixel[3] > 128}
            self.assertFalse({(255, 0, 0), (0, 0, 255)} & opaque_colors)

    def test_disconnected_strip_and_neighbor_fragment_are_removed(self):
        image = Image.new("RGBA", (100, 120))
        draw = ImageDraw.Draw(image)
        draw.rectangle((25, 25, 75, 112), fill=(40, 20, 30, 255))
        draw.rectangle((1, 2, 98, 4), fill="red")
        draw.rectangle((91, 30, 98, 42), fill="blue")
        clean = principal_figure(image)
        self.assertEqual(clean.getpixel((50, 3))[3], 0)
        self.assertEqual(clean.getpixel((95, 35))[3], 0)
        self.assertEqual(clean.getpixel((50, 80)), image.getpixel((50, 80)))

    def test_contact_anchor_uses_visible_central_support_not_canvas_bottom(self):
        image = Image.new("RGBA", (100, 120))
        draw = ImageDraw.Draw(image)
        draw.rectangle((30, 20, 70, 100), fill="red")
        draw.point((2, 115), fill="red")
        self.assertEqual(support_anchor(image), [0.5, 101 / 120])


if __name__ == "__main__":
    unittest.main()
