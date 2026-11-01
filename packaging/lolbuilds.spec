# -*- mode: python ; coding: utf-8 -*-
# Recette PyInstaller de l'exe Windows (dossier dist/lolbuilds/), utilisée en local et par la CI :
#   pyinstaller --noconfirm --clean packaging/lolbuilds.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent

datas = [(str(root / "src" / "lolbuilds" / "app" / "ui"), "lolbuilds/app/ui")]  # HTML/CSS/JS + polices
binaries = []
hiddenimports = []
for package in ("webview",):  # pywebview : DLL WebView2 et modules chargés dynamiquement
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root / "src")],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="lolbuilds",
    icon=str(root / "packaging" / "lolbuilds.ico"),
    console=False,  # application fenêtrée : pas de console noire
    upx=False,  # UPX augmente les faux positifs des antivirus
)
coll = COLLECT(exe, a.binaries, a.datas, name="lolbuilds", upx=False)
