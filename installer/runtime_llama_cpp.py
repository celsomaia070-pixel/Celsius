"""Configure llama-cpp-python native libraries inside a PyInstaller bundle."""

import os
import sys
from pathlib import Path

_DLL_DIRECTORY_HANDLES = []

if getattr(sys, "frozen", False):
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    llama_lib_dir = bundle_dir / "llama_cpp" / "lib"
    os.environ["LLAMA_CPP_LIB_PATH"] = str(llama_lib_dir)
    if sys.platform == "win32":
        # Load Qt before optional native engines (OCR, audio and inference).
        # Those engines can otherwise change Windows' DLL resolution for the
        # process before PySide6 imports QtCore.
        for qt_dir in (bundle_dir / "PySide6", bundle_dir / "shiboken6"):
            if qt_dir.is_dir():
                _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(qt_dir)))

        from PySide6 import QtCore  # noqa: F401

        # llama-cpp-python keeps dependent native DLLs next to its own runtime.
        # Register only that directory; PyInstaller's PySide6 hook configures Qt.
        if llama_lib_dir.is_dir():
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(llama_lib_dir)))
            os.environ["PATH"] = f"{llama_lib_dir}{os.pathsep}{os.environ.get('PATH', '')}"
