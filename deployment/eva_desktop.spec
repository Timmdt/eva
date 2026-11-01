# Build on Windows using build_eva_exe.cmd. The Linux host cannot validate the PE build.
from pathlib import Path

root = Path(SPECPATH).parent
analysis = Analysis(
    [str(root / "desktop_agent/launch.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "assets/character"), "assets/character")],
    hiddenimports=["keyring.backends.Windows"],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["torch", "cv2", "ollama", "psycopg", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="EVA Desktop Agent",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="EVA Desktop Agent")
