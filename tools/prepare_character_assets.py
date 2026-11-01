"""Split background-extracted reference atlases into PNG cells without redrawing pixels.

The built-in image tool performs background extraction first. This script finds
actual atlas gutters, masks neighboring fragments, crops and adds transparent
padding without redrawing the existing character pixels.
Development dependency: Pillow (not needed by the Windows runtime).
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from shutil import copyfile

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
POSES = [
    "idle",
    "listening",
    "typing",
    "reading",
    "tired",
    "falling_asleep",
    "sleeping",
    "rising",
    "stretching",
    "happy",
    "thinking",
    "sitting_down",
    "alert",
    "waving",
]
EXPRESSIONS = [
    "Neutral",
    "Aufmerksam",
    "Freundlich",
    "Neugierig",
    "Überrascht",
    "Nachdenklich",
    "Amüsiert",
    "Genervt",
]


def padded(image):
    box = image.getchannel("A").getbbox()
    if box is None:
        raise ValueError("Leere Asset-Zelle.")
    cropped = image.crop(box)
    result = Image.new("RGBA", (cropped.width + 8, cropped.height + 8))
    result.paste(cropped, (4, 4))
    return result


def cells(path, columns, rows):
    image = Image.open(path).convert("RGBA")
    for row in range(rows):
        for column in range(columns):
            box = (
                round(column * image.width / columns),
                round(row * image.height / rows),
                round((column + 1) * image.width / columns),
                round((row + 1) * image.height / rows),
            )
            yield padded(image.crop(box))


def row_boundaries(image, rows):
    """Find actual horizontal gutters near the nominal grid, not the canvas midpoint."""
    alpha = image.getchannel("A")
    width, height = image.size
    values = alpha.tobytes()
    result = [0]
    for row in range(1, rows):
        expected = round(row * height / rows)
        radius = max(8, round(height / rows * 0.2))
        runs = []
        start = None
        for y in range(
            max(result[-1] + 1, expected - radius), min(height - 1, expected + radius) + 1
        ):
            occupied = sum(value >= 12 for value in values[y * width : (y + 1) * width])
            if occupied == 0:
                start = y if start is None else start
            elif start is not None:
                runs.append((start, y))
                start = None
        if start is not None:
            runs.append((start, min(height, expected + radius + 1)))
        if not runs:
            raise ValueError(
                "Keine transparente Trennzeile im Posenatlas gefunden; Raster manuell prüfen."
            )
        gutter = max(
            runs, key=lambda span: ((span[1] - span[0]), -abs((span[0] + span[1]) / 2 - expected))
        )
        result.append((gutter[0] + gutter[1]) // 2)
    return [*result, height]


def separator_seam(alpha, expected, radius=28):
    """Follow transparent space between adjacent figures instead of a straight cut."""
    width, height = alpha.size
    pixels = alpha.tobytes()
    left, right = max(1, expected - radius), min(width - 1, expected + radius)
    count = right - left + 1
    costs = [0.0] * count
    previous_rows = []
    for y in range(height):
        current, previous = [], []
        for column in range(count):
            x = left + column
            choices = range(max(0, column - 1), min(count, column + 2))
            parent = min(choices, key=costs.__getitem__)
            # Alpha dominates; the small position term prevents wandering through
            # the neighboring character when both sides are transparent.
            value = pixels[y * width + x]
            current.append(costs[parent] + value * value + 0.3 * (x - expected) ** 2)
            previous.append(parent)
        costs = current
        previous_rows.append(previous)
    column = min(range(count), key=costs.__getitem__)
    path = [0] * height
    for y in range(height - 1, -1, -1):
        path[y] = left + column
        column = previous_rows[y][column]
    return path


def principal_figure(image):
    """Keep the figure's connected alpha body and its soft edge; drop isolated atlas debris."""
    alpha = image.getchannel("A")
    values = alpha.tobytes()
    width, height = image.size
    seen = bytearray(width * height)
    largest = []
    for seed in range(width * height):
        if seen[seed] or values[seed] < 96:
            continue
        queue = deque([seed])
        seen[seed] = 1
        component = []
        while queue:
            index = queue.popleft()
            component.append(index)
            x, y = index % width, index // width
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < width and 0 <= yy < height:
                        other = yy * width + xx
                        if not seen[other] and values[other] >= 96:
                            seen[other] = 1
                            queue.append(other)
        if len(component) > len(largest):
            largest = component
    if not largest:
        raise ValueError("Leere Posenfigur.")
    mask_values = bytearray(width * height)
    for index in largest:
        mask_values[index] = 255
    mask = Image.frombytes("L", image.size, bytes(mask_values)).filter(ImageFilter.MaxFilter(5))
    # Keep original alpha/color values, including antialiasing. No body pixels are
    # painted or generated; only disconnected fragments outside the figure go.
    result = image.copy()
    result.putalpha(
        Image.frombytes(
            "L",
            image.size,
            bytes(value if keep else 0 for value, keep in zip(values, mask.tobytes())),
        )
    )
    return result


def pose_cells(path, columns=7, rows=2):
    image = Image.open(path).convert("RGBA")
    edges = row_boundaries(image, rows)
    for row in range(rows):
        strip = image.crop((0, edges[row], image.width, edges[row + 1]))
        alpha = strip.getchannel("A")
        seams = [[0] * strip.height]
        seams.extend(
            separator_seam(alpha, round(column * strip.width / columns))
            for column in range(1, columns)
        )
        seams.append([strip.width] * strip.height)
        for column in range(columns):
            left, right = min(seams[column]), max(seams[column + 1])
            crop = strip.crop((left, 0, right, strip.height))
            values = bytearray(crop.getchannel("A").tobytes())
            for y in range(crop.height):
                start, end = seams[column][y] - left, seams[column + 1][y] - left
                offset = y * crop.width
                values[offset : offset + start] = b"\0" * start
                values[offset + end : offset + crop.width] = b"\0" * (crop.width - end)
            crop.putalpha(Image.frombytes("L", crop.size, bytes(values)))
            yield padded(principal_figure(crop))


def support_anchor(image):
    """Place the central seat/feet contact on the surface, not transparent padding."""
    alpha = image.getchannel("A")
    left, right = round(image.width * 0.25), round(image.width * 0.75)
    for y in range(image.height - 1, -1, -1):
        if any(alpha.getpixel((x, y)) >= 96 for x in range(left, right)):
            return [0.5, (y + 1) / image.height]
    raise ValueError("Kein Kontaktpunkt der Pose gefunden.")


def prepare(pose_atlas, standing, expression_atlas):
    manifest = ROOT / "assets/character/outfits/gothic.json"
    if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")).get("pose_sources"):
        raise ValueError(
            "Die Original-PNGs sind geschützt. Erzeuge neue Atlas-Assets in einer separaten Projektkopie."
        )
    poses = ROOT / "assets/character/poses"
    expressions = ROOT / "assets/character/expressions"
    references = ROOT / "assets/references"
    for directory in (poses, expressions, references, ROOT / "assets/character/outfits"):
        directory.mkdir(parents=True, exist_ok=True)
    for source, name in [
        (pose_atlas, "eva-poses-extracted.png"),
        (standing, "eva-standing-extracted.png"),
        (expression_atlas, "eva-expressions-extracted.png"),
    ]:
        if source.resolve() != (references / name).resolve():
            copyfile(source, references / name)
    entries = {}
    for name, image in zip(POSES, pose_cells(pose_atlas), strict=True):
        image.save(poses / f"{name}.png")
        scale = 0.72 if name in {"sleeping", "falling_asleep"} else 1.0
        entries[name] = {
            "frames": [f"../poses/{name}.png"],
            "scale": scale,
            "anchor": support_anchor(image),
            "frame_ms": 180,
            "note": "Einzelbild aus der bereitgestellten Pose; Bewegungsframes fehlen.",
        }
    image = padded(Image.open(standing).convert("RGBA"))
    image.save(poses / "standing.png")
    entries["standing"] = {
        "frames": ["../poses/standing.png"],
        "scale": 1.7,
        "anchor": support_anchor(image),
        "frame_ms": 180,
        "note": "Standbild, vollständig skaliert; keine Bewegungsframes.",
    }
    # The source's knees-up idle ends midway down the shins. Use the existing
    # fully folded-leg pose as default rather than inventing missing boots.
    copyfile(poses / "idle.png", references / "eva-idle-knees-up-extracted.png")
    copyfile(poses / "rising.png", poses / "idle.png")
    entries["idle"] = {
        **entries["rising"],
        "frames": ["../poses/idle.png"],
        "label": "Sitzen · Beine untergeschlagen",
        "note": "Vorhandene vollständige Sitzpose; keine abgeschnittenen Unterschenkel, keine Bewegungsframes.",
    }
    for name, fallback, note in [
        ("talking", "listening", "Zuhör-Pose als statischer Ersatz; keine Mundbewegungsframes."),
        (
            "annoyed",
            "idle",
            "Idle-Pose als statischer Ersatz; genervter Ausdruck separat im Porträt verfügbar.",
        ),
    ]:
        entries[name] = {**entries[fallback], "note": note}
    expression_paths = {}
    for index, (name, image) in enumerate(
        zip(EXPRESSIONS, cells(expression_atlas, 4, 2), strict=True)
    ):
        filename = f"expression-{index:02}.png"
        image.save(expressions / filename)
        expression_paths[name] = "../expressions/" + filename
    manifest = {
        "version": 1,
        "id": "eva-original-gothic",
        "name": "EVA · Original Gothic",
        "description": "Schwarz-bordeauxrotes Gothic-Outfit aus dem bereitgestellten Character Sheet. Alle Posen sind Standbilder.",
        "poses": entries,
        "expressions": expression_paths,
        "provenance": "Background extraction with built-in image tool; cropped without redraw by tools/prepare_character_assets.py.",
    }
    (ROOT / "assets/character/outfits/gothic.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pose_atlas", type=Path)
    parser.add_argument("standing", type=Path)
    parser.add_argument("expression_atlas", type=Path)
    args = parser.parse_args()
    prepare(args.pose_atlas, args.standing, args.expression_atlas)
