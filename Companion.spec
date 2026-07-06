# -*- mode: python ; coding: utf-8 -*-
# One-folder build with two exes sharing one _internal/:
#   Companion.exe   - the overlay tool
#   VisionProbe.exe - boss-pack calibration (tools/vision_probe.py)
#
# One-folder (not one-file) on purpose: with OpenCV + ONNX OCR models bundled, a one-file
# exe self-extracts hundreds of MB on every launch. config/ is NOT bundled -- it ships
# loose next to the exe so users can edit rules and boss packs (see companion/__main__.py's
# frozen-mode ROOT handling). tools/make_release.py assembles the final folder.

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
# scapy: runtime imports galore that a plain import scan misses.
for pkg in ("scapy",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

companion_a = Analysis(
    ["companion\\__main__.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
probe_a = Analysis(
    ["tools\\vision_probe.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

companion_pyz = PYZ(companion_a.pure)
probe_pyz = PYZ(probe_a.pure)

companion_exe = EXE(
    companion_pyz,
    companion_a.scripts,
    [],
    exclude_binaries=True,
    name="Companion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
probe_exe = EXE(
    probe_pyz,
    probe_a.scripts,
    [],
    exclude_binaries=True,
    name="VisionProbe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    companion_exe,
    probe_exe,
    companion_a.binaries,
    companion_a.datas,
    probe_a.binaries,
    probe_a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Companion",
)
