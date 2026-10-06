# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_dir = Path(SPECPATH)

analysis = Analysis(
    [str(project_dir / "main.py")],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[
        (str(project_dir / "ae_trends_final.sql"), "."),
        (str(project_dir / "ae-logo.jpg"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AE Trends",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_dir / "ae-trends.ico"),
)

coll = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AE Trends",
)
