"""Subprocess entrypoint; never load pytest's global module replacement fixtures."""

import importlib
import ipaddress
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path.cwd().resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _inside_scratch(path):
    resolved = Path(os.fsdecode(path)).resolve()
    if not resolved.is_relative_to(SCRATCH):
        raise PermissionError(f"Native smoke refused write outside temporary directory: {resolved}")


def _audit(event, args):
    # This guards Python I/O, not arbitrary native code. No microphone APIs are called.
    if event == "open":
        path, mode, flags = args
        writing = (mode and any(char in mode for char in "wax+")) or (
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        )
        if writing and not isinstance(path, int) and os.fsdecode(path) != os.devnull:
            _inside_scratch(path)
    elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod"}:
        _inside_scratch(args[0])
    elif event in {"os.rename", "os.link", "os.symlink"}:
        _inside_scratch(args[0])
        _inside_scratch(args[1])
    elif event in {"socket.connect", "socket.bind", "socket.sendto", "socket.getaddrinfo"}:
        address = args[0] if event == "socket.getaddrinfo" else args[-1]
        host = address[0] if isinstance(address, tuple) else address
        if host == "localhost":
            return
        try:
            allowed = ipaddress.ip_address(host).is_loopback
        except ValueError:
            allowed = False
        if not allowed:
            raise PermissionError(f"Native smoke only permits loopback networking: {host}")


sys.addaudithook(_audit)
assert "tests.conftest" not in sys.modules
family, case = sys.argv[1].split(".")
module = importlib.import_module(f"_{family}_cases")
getattr(module, case)()
print(f"PASS {sys.argv[1]}")
