# celsius.spec - PyInstaller spec file for Celsius (One-Dir mode)

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(os.getcwd())

BUNDLE_MODELS = os.environ.get("CELSIUS_BUNDLE_MODELS", "0") == "1"
MODEL_FILE = "qwen2.5-vl-7b-q4_k_m.gguf"
MMPROJ_FILE = "mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf"

datas = []

if BUNDLE_MODELS:
    for fname in [MODEL_FILE, MMPROJ_FILE]:
        p = PROJECT_ROOT / "resources" / fname
        if p.exists():
            datas.append((str(p), "resources"))

for dll in (PROJECT_ROOT / "resources").glob("*.dll"):
    datas.append((str(dll), "resources"))

datas.append((str(PROJECT_ROOT / "logo"), "logo"))
datas.append((str(PROJECT_ROOT / "pyproject.toml"), "."))

a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
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
        "qrcode",
        "qrcode.image.pil",
        "whisper",
        "faster_whisper",
        "odfpy",
        "fpdf",
        "pydub",
        "playwright",
        "numpy",
        "cryptography",
        "cryptography.hazmat.primitives.asymmetric.padding",
        "cryptography.hazmat.primitives.serialization",
        "core.llama_cpp",
        "core.config",
        "core.commands",
        "core.memory",
        "core.mobile_voice",
        "core.logging_config",
        "core.license",
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
        "ui.activation_dialog",
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
    [],
    exclude_binaries=True,
    name='Celsius',
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
    icon=str(PROJECT_ROOT / "logo" / "logo.ico") if (PROJECT_ROOT / "logo" / "logo.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Celsius',
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name='Celsius.app',
        icon=str(PROJECT_ROOT / "logo" / "logo.icns") if (PROJECT_ROOT / "logo" / "logo.icns").exists() else None,
        bundle_identifier='com.celso.celsius',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSMinimumSystemVersion': '10.15',
        },
    )
