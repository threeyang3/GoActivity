# -*- mode: python ; coding: utf-8 -*-
"""Build the desktop manager using external service environments."""
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / "desktop_launcher.py")], pathex=[str(root)],
    datas=[(str(root / "desktop/assets"), "desktop/assets")], hiddenimports=[],
    excludes=["numpy", "scipy", "pandas", "matplotlib", "torch", "onnxruntime", "app"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="GoActivity",
          console=False, debug=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="GoActivity", strip=False, upx=False)
