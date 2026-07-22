# celsius.spec - PyInstaller spec file for Celsius

import sys
from pathlib import Path

# Get project root
PROJECT_ROOT = Path(__file__).parent

# Platform-specific binary names
if sys.platform == "win32":
    LLAMA_SERVER_BIN = "llama-server.exe"
elif sys.platform == "darwin":
    LLAMA_SERVER_BIN = "llama-server-macos"
else:
    LLAMA_SERVER_BIN = "llama-server-linux"

# Model file (update with your actual model filename)
MODEL_FILE = "qwen2.5-vl-7b-q4_k_m.gguf"

a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # Bundled resources
        (str(PROJECT_ROOT / "resources" / LLAMA_SERVER_BIN), "resources"),
        (str(PROJECT_ROOT / "resources" / MODEL_FILE), "resources"),
        # UI assets
        (str(PROJECT_ROOT / "logo"), "logo"),
        # Config files
        (str(PROJECT_ROOT / "pyproject.toml"), "."),
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtWidgets",
        "PySide6.QtGui",
        "sentence_transformers",
        "chromadb",
        "duckduckgo_search",
        "speech_recognition",
        "sounddevice",
        "scipy",
        "edge_tts",
        "pygame",
        "pypdf",
        "docx",
        "PIL",
        "whisper",
        "odfpy",
        "fpdf",
        "pydub",
        "playwright",
        "numpy",
        "core.llama_cpp",
        "core.config",
        "core.commands",
        "core.memory",
        "core.logging_config",
        "ai.react",
        "ai.tools",
        "ai.engine",
        "ai.rag",
        "ai.browser",
        "ai.agents",
        "workers.ai_worker",
        "workers.tts_worker",
        "workers.mic_worker",
        "workers.code_worker",
        "processors.text",
        "processors.pdf",
        "processors.docx",
        "processors.odf",
        "processors.image",
        "processors.audio",
        "processors.report",
        "processors.base",
        "ui.window",
        "ui.sidebar",
        "ui.dialogs",
        "ui.command_palette",
        "ui.styles",
        "ui.theme",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Celsius',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "logo" / "logo.ico") if (PROJECT_ROOT / "logo" / "logo.ico").exists() else None,
)

# For macOS .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name='Celsius.app',
        icon=str(PROJECT_ROOT / "logo" / "logo.icns") if (PROJECT_ROOT / "logo" / "logo.icns").exists() else None,
        bundle_identifier='com.celso.celsius',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSMinimumSystemVersion': '10.15',
        },
    )