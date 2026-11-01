"""Build a portable Windows source package from an explicit public file allowlist."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
CORE_FILES = (
    "desktop_agent/__init__.py",
    "desktop_agent/eva_client.py",
    "desktop_agent/companion.py",
    "desktop_agent/companion_client.py",
    "desktop_agent/companion_protocol.py",
    "desktop_agent/launch.py",
    "requirements-desktop.txt",
    "start_eva_desktop.cmd",
    "start_eva_desktop_debug.cmd",
    "docs/DESKTOP_COMPANION.md",
    "assets/character/ASSET_LIMITS.md",
    "build_eva_exe.cmd",
    "deployment/eva_desktop.spec",
    "docs/DESKTOP_SERVER_LINK.md",
)
APP_FILES = tuple(
    f"desktop_agent/app/{name}.py"
    for name in (
        "__init__",
        "storage",
        "character",
        "windows",
        "capture",
        "ai",
        "pet",
        "ui",
        "controller",
    )
)
CHARACTER_FILES = tuple(
    str(path.relative_to(ROOT))
    for path in sorted((ROOT / "assets/character").rglob("*"))
    if path.is_file() and path.suffix.lower() in {".png", ".json"}
)
FILES = CORE_FILES + APP_FILES + CHARACTER_FILES


def package(destination: Path) -> Path:
    for filename in FILES:
        if not (ROOT / filename).is_file():
            raise FileNotFoundError(filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for filename in FILES:
            archive.write(ROOT / filename, "EVA/" + filename)
        archive.writestr(
            "EVA/README.md", (ROOT / "docs/DESKTOP_COMPANION.md").read_text(encoding="utf-8")
        )
        archive.writestr(
            "EVA/LIES_MICH.txt",
            (
                "EVA Desktop Agent fuer Windows 10 / 11 - Gothic Edition\n\n"
                "1. ZIP vollstaendig entpacken. Python 3.11+ installieren.\n"
                "2. start_eva_desktop.cmd doppelklicken. Beim ersten Start werden Abhaengigkeiten installiert.\n"
                "3. EVA sitzt an der Taskleiste. Linksklick: Chat. Rechtsklick: Menue.\n"
                "4. Hauptmenue > Einstellungen: EVA-Bridge, http://192.168.2.15:8766 und privaten Server-Token eintragen.\n"
                "   KI und Bildmodell laufen auf dem EVA-Server, kein Modell auf dem Haupt-PC.\n"
                "5. Monitor, Groesse, Posen und Autostart im Hauptmenue einstellen.\n\n"
                "Die Position ist gesperrt; sie wird ueber die Einstellungen geaendert.\n"
                "Die App funktioniert auch ohne KI. Alle gelieferten Posen sind Standbilder.\n"
                "Beenden: Rechtsklick auf Figur oder Taskleistensymbol > EVA beenden.\n"
                "Bei Startproblemen start_eva_desktop_debug.cmd verwenden.\n"
                "Details: docs/DESKTOP_COMPANION.md und assets/character/ASSET_LIMITS.md.\n"
            ),
        )
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/EVA-Windows.zip")
    print(package(parser.parse_args().output))


if __name__ == "__main__":
    main()
