# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = Path(__file__).resolve().parents[2]

datas = []
for name in ["config.gui-dev.example.yaml", "config.example.yaml", "README.md"]:
    p = project_root / name
    if p.exists():
        datas.append((str(p), "."))

datas += collect_data_files("PySide6")
hiddenimports = collect_submodules("PySide6")

block_cipher = None

a = Analysis(
    [
        str(project_root / "medaudit_diff_watcher" / "gui_launcher.py"),
        str(project_root / "medaudit_diff_watcher" / "__main__.py"),
    ],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
gui_exe = EXE(
    pyz,
    [a.scripts[0]],
    [],
    exclude_binaries=True,
    name="medaudit-diff-watcher-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
cli_exe = EXE(
    pyz,
    [a.scripts[1]],
    [],
    exclude_binaries=True,
    name="medaudit-diff-watcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    gui_exe,
    cli_exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="medaudit-diff-watcher-gui",
)
