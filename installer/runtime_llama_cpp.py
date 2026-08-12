"""Configure llama-cpp-python native libraries inside a PyInstaller bundle."""

import os
import sys
from pathlib import Path

_DLL_DIRECTORY_HANDLE = None

if getattr(sys, "frozen", False):
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    llama_lib_dir = bundle_dir / "llama_cpp" / "lib"
    os.environ["LLAMA_CPP_LIB_PATH"] = str(llama_lib_dir)
    if sys.platform == "win32" and llama_lib_dir.is_dir():
        _DLL_DIRECTORY_HANDLE = os.add_dll_directory(str(llama_lib_dir))
