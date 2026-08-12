# celsius.spec - PyInstaller spec file for Celsius (One-Dir mode)

import ast
import importlib.util
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).resolve()

BUNDLE_MODELS = os.environ.get("CELSIUS_BUNDLE_MODELS", "0") == "1"
MODEL_ID = os.environ.get("CELSIUS_BUNDLE_MODEL_ID", "qwen2.5-vl-7b-q4km")


def model_artifacts(model_id):
    """Read artifact names from the model registry without importing the app."""
    tree = ast.parse((PROJECT_ROOT / "core" / "config.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "GGUFModel":
            continue
        values = {
            keyword.arg: ast.literal_eval(keyword.value) for keyword in node.keywords if keyword.arg
        }
        if values.get("id") == model_id:
            return [name for name in (values.get("filename"), values.get("mmproj_file")) if name]
    raise RuntimeError(f"Modelo de bundle nao registrado: {model_id}")


datas = []

llama_cpp_spec = importlib.util.find_spec("llama_cpp")
if llama_cpp_spec is None or not llama_cpp_spec.submodule_search_locations:
    raise RuntimeError("Pacote llama_cpp nao encontrado no ambiente de build.")

llama_cpp_lib_dir = Path(next(iter(llama_cpp_spec.submodule_search_locations))) / "lib"
llama_cpp_libraries = sorted(
    path
    for path in llama_cpp_lib_dir.iterdir()
    if path.is_file()
    and (path.suffix.lower() in {".dll", ".dylib", ".so"} or ".so." in path.name.lower())
)
if not llama_cpp_libraries:
    raise RuntimeError(f"Bibliotecas nativas do llama_cpp ausentes em {llama_cpp_lib_dir}")
for library in llama_cpp_libraries:
    # Keep the exact directory expected by llama_cpp._ctypes_extensions.
    datas.append((str(library), "llama_cpp/lib"))

if BUNDLE_MODELS:
    for fname in model_artifacts(MODEL_ID):
        p = PROJECT_ROOT / "resources" / fname
        if p.exists():
            datas.append((str(p), "resources"))
            digest = p.with_name(f"{p.name}.sha256")
            if digest.exists():
                datas.append((str(digest), "resources"))

for dll in (PROJECT_ROOT / "resources").glob("*.dll"):
    datas.append((str(dll), "resources"))

public_key = PROJECT_ROOT / "resources" / "license_public_key.pem"
if public_key.exists():
    datas.append((str(public_key), "resources"))

datas.append((str(PROJECT_ROOT / "logo"), "logo"))
datas.append((str(PROJECT_ROOT / "core" / "web_api" / "static"), "core/web_api/static"))
datas.append((str(PROJECT_ROOT / "pyproject.toml"), "."))

a = Analysis(
    ["main.py"],
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
        "pdfplumber",
        "pypdfium2",
        "rapidocr",
        "onnxruntime",
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
        "fastapi",
        "uvicorn",
        "core.chat_attachments",
        "core.chat_service",
        "core.web_api.app",
        "core.web_api.auth",
        "core.web_api.chat",
        "core.web_api.events",
        "core.web_api.server",
        "core.llama_cpp",
        "core.config",
        "core.commands",
        "core.memory",
        "core.mobile_voice",
        "core.logging_config",
        "core.license",
        "core.agenda",
        "core.business_records",
        "core.charts",
        "core.embeddings",
        "core.inference_guard",
        "core.model_catalog",
        "core.module_schema",
        "core.modules",
        "core.notifications",
        "core.suppliers",
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
        "ui.chat",
        "ui.controllers.conversation_manager",
        "ui.controllers.theme_controller",
        "ui.controllers.worker_controller",
        "ui.inventory_panel",
        "ui.kanban_view",
        "ui.state.theme_manager",
        "matplotlib.backends.backend_agg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(PROJECT_ROOT / "installer" / "runtime_llama_cpp.py")],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Celsius",
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
    icon=str(PROJECT_ROOT / "logo" / "logo.ico")
    if (PROJECT_ROOT / "logo" / "logo.ico").exists()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Celsius",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Celsius.app",
        icon=str(PROJECT_ROOT / "logo" / "logo.icns")
        if (PROJECT_ROOT / "logo" / "logo.icns").exists()
        else None,
        bundle_identifier="com.celso.celsius",
        info_plist={
            "NSHighResolutionCapable": "True",
            "LSMinimumSystemVersion": "10.15",
        },
    )
