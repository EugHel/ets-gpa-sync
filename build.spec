# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Build-Spec für ETS GPA Sync
========================================

Erstellt ein One-Directory-Bundle (empfohlen für tkinterdnd2 + Code-Signing).

Verwendung:
    pip install pyinstaller
    pyinstaller build.spec

Ausgabe: dist/ETS-GPA-Sync/ETS-GPA-Sync.exe

One-File-Variante (optional, langsamer beim Start):
    Unten EXE(exclude_binaries=False) setzen und COLLECT-Block entfernen.

Hinweis zu tkinterdnd2:
    Version 0.4.3 (patch-frei, läuft auch unter Python 3.14). Die DLL und
    TCL-Dateien werden manuell eingeschlossen, da PyInstaller sie über Tcl
    nicht automatisch findet.
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

# ── Pfade ──────────────────────────────────────────────────────────────────
PROJECT = Path(SPECPATH)
ASSETS  = PROJECT / 'gpa_ga_sync' / 'assets'

# ── tkinterdnd2: DLL + alle TCL-Dateien manuell einschließen ──────────────
import tkinterdnd2 as _tkdnd2
_tkdnd2_dir = Path(_tkdnd2.__file__).parent
tkdnd_datas = [
    (str(_tkdnd2_dir / 'tkdnd' / 'win-x64'), 'tkinterdnd2/tkdnd/win-x64'),
]

# ── customtkinter: Themes, Icons, Bilder ──────────────────────────────────
ctk_datas = collect_data_files('customtkinter')
ctk_binaries = []
ctk_hiddenimports = []

# ── App-eigene Assets ──────────────────────────────────────────────────────
app_datas = [
    (str(ASSETS), 'gpa_ga_sync/assets'),
]

# ── Hidden Imports ─────────────────────────────────────────────────────────
# cryptography wird über Fernet (Licensing) und knxproj-Entschlüsselung genutzt.
extra_hidden = [
    'tkinterdnd2',
    'tkinterdnd2.TkinterDnD',
    'cryptography',
    'cryptography.fernet',
    'cryptography.hazmat.primitives.ciphers',
    'cryptography.hazmat.primitives.kdf.pbkdf2',
    'cryptography.hazmat.backends',
    'cryptography.hazmat.backends.openssl',
    'cryptography.hazmat.backends.openssl.backend',
    'xml.etree.ElementTree',
    'zipfile',
]

# ══════════════════════════════════════════════════════════════════════════
a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT)],
    binaries=ctk_binaries,
    datas=app_datas + tkdnd_datas + ctk_datas,
    hiddenimports=ctk_hiddenimports + extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest', '_pytest',
        'unittest',
        'doctest', 'pydoc',
        'pdb', 'debugpy',
        'numpy', 'pandas', 'matplotlib', 'scipy',
        'IPython', 'jupyter',
        'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL._tkinter_finder',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,       # False → One-File (COLLECT-Block dann entfernen)
    name='ETS-GPA-Sync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                   # UPX deaktiviert — Pflicht für Code-Signing
    console=False,               # Kein Konsolenfenster (GUI-App)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ASSETS / 'app_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ETS-GPA-Sync',
)
