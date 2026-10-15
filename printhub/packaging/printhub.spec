# PyInstaller spec — builds a self-contained PrintHub bundle on any OS.
#   pyinstaller --noconfirm packaging/printhub.spec
# Produces:  dist/PrintHub/          (onedir; folder of files + launcher)
#            dist/PrintHub.app/      (macOS, when built there)
#
# LibreOffice is NOT bundled — it stays an optional system dependency used
# only for Office->PDF conversion. PDF and image printing need nothing extra.
import os
import sys

# PyInstaller resolves relative paths against the .spec directory, not the CWD.
# Build every path from the repo root so the spec works no matter where it and
# the invoking shell live.
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
ASSETS = os.path.join(ROOT, "packaging", "assets")

app_name = "PrintHub"
icon = os.path.join(ASSETS, "printhub.ico" if sys.platform == "win32" else "printhub.png")

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ASSETS, "printhub.png"), "packaging/assets")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=app_name,
    console=False,          # GUI app: no console window on Windows
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.datas, name=app_name)

# macOS: wrap the onedir bundle into a proper .app
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{app_name}.app",
        icon=os.path.join(ASSETS, "printhub.icns"),
        bundle_identifier="io.printhub.PrintHub",
        info_plist={
            "CFBundleShortVersionString": "0.2.1",
            "NSHighResolutionCapable": True,
        },
    )
