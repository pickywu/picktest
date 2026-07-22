# -*- mode: python ; coding: utf-8 -*-

from importlib.util import find_spec
from pathlib import Path
import sys

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_data_files


project_root = Path(SPECPATH)
asset_tree = Tree(str(project_root / "assets"), prefix="assets")
# Ship the editable localization catalogs. They land in _internal/Localization;
# localization.py also honours a Localization folder placed next to the .exe so
# players/modders can override them without touching the bundle.
localization_tree = Tree(str(project_root / "Localization"), prefix="Localization")
arcade_package = Path(find_spec("arcade").origin).parent
# zhconv bundles its Traditional<->Simplified dictionary as package data.
zhconv_datas = collect_data_files("zhconv")

a = Analysis(
    ["rpg.py"],
    pathex=[],
    binaries=[],
    datas=zhconv_datas,
    hiddenimports=["zhconv"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.datas += asset_tree
a.datas += localization_tree
# Arcade 3.3's bundled hook targets ``arcade/VERSION`` as a directory,
# producing ``arcade/VERSION/VERSION``. Arcade expects VERSION to be a file.
a.datas = [
    entry for entry in a.datas
    if entry[0].replace("/", "\\") != "arcade\\VERSION\\VERSION"
]
a.datas.append(("arcade\\VERSION", str(arcade_package / "VERSION"), "DATA"))
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EmberKingdom",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EmberKingdom",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="EmberKingdom.app",
        icon=None,
        bundle_identifier="com.emberkingdom.game",
    )
