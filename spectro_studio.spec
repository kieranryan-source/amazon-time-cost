# PyInstaller spec for spectro_studio — builds a macOS .app bundle.
#
#   pyinstaller --noconfirm spectro_studio.spec
#
# Builds for the architecture of the machine it runs on. The release CI
# uses an Apple Silicon runner, so the produced .app is arm64. For an
# Intel build, run this on an x86_64 Mac; for a single fat binary set
# target_arch='universal2' below (requires universal2 wheels for every
# dependency).

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# These three need their data files / native libs explicitly gathered:
# soundfile ships libsndfile, pyqtgraph has lazily-imported submodules,
# PyOpenGL resolves platform modules dynamically.
for _pkg in ('soundfile', 'pyqtgraph', 'OpenGL'):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

block_cipher = None

a = Analysis(
    ['spectro_studio.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Keep other Qt bindings out so pyqtgraph resolves to PySide6 and the
    # bundle stays lean.
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'tkinter', 'matplotlib'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Spectro Studio',
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
    name='Spectro Studio',
)

app = BUNDLE(
    coll,
    name='Spectro Studio.app',
    icon=None,
    bundle_identifier='com.github.spectro-studio',
    info_plist={
        'CFBundleName': 'Spectro Studio',
        'CFBundleDisplayName': 'Spectro Studio',
        'CFBundleShortVersionString': '16.0',
        'CFBundleVersion': '16.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
        'NSPrincipalClass': 'NSApplication',
        'LSApplicationCategoryType': 'public.app-category.graphics-design',
    },
)
