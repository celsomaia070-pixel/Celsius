import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal


@dataclass
class CodeResult:
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class CodeWorker(QThread):
    resultado = Signal(object)
    status = Signal(str)

    def __init__(self, codigo: str, timeout: int = 30):
        super().__init__()
        self.codigo = codigo
        self.timeout = timeout

    def run(self):
        self.status.emit("Executando código...")
        resultado = executar_codigo(self.codigo, self.timeout)
        self.resultado.emit(resultado)


# Allowed imports for safe execution
ALLOWED_IMPORTS = frozenset({
    # Built-ins
    "math", "random", "statistics", "decimal", "fractions",
    "datetime", "time", "calendar", "zoneinfo",
    "collections", "itertools", "functools", "operator",
    "string", "re", "textwrap", "difflib", "hashlib",
    "json", "csv", "html", "xml.etree.ElementTree",
    "urllib.parse", "urllib.request", "base64", "binascii",
    "typing", "dataclasses", "enum", "uuid",
    # Data science (if installed)
    "numpy", "pandas", "matplotlib.pyplot", "plotly",
    "scipy", "sklearn",
})

BLOCKED_IMPORTS = frozenset({
    "os", "sys", "subprocess", "shutil", "pathlib", "glob",
    "socket", "http", "urllib", "requests", "ftplib", "telnetlib",
    "importlib", "pkgutil", "runpy", "compileall", "py_compile",
    "ctypes", "multiprocessing", "threading", "asyncio",
    "pickle", "shelve", "marshal", "dbm", "sqlite3",
    "webbrowser", "tkinter", "PySide6", "PyQt6",
})


def _validate_code(code: str) -> str | None:
    """Basic static analysis to catch dangerous patterns."""
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Syntax error: {e}"

    for node in ast.walk(tree):
        # Block imports of dangerous modules
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] in BLOCKED_IMPORTS:
                    return f"Blocked import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split('.')[0] in BLOCKED_IMPORTS:
                return f"Blocked import: {node.module}"

        # Block dangerous function calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in {"eval", "exec", "compile", "__import__", "open", "input"}:
                    return f"Blocked function: {node.func.id}"
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in {"system", "popen", "spawn", "fork", "exec"}:
                    return f"Blocked method: {node.func.attr}"

        # Block access to dangerous attributes
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                if node.attr in {"__globals__", "__code__", "__class__", "__bases__", "__subclasses__", "__mro__"}:
                    return f"Blocked attribute access: {node.attr}"

    return None


def _create_restricted_globals() -> dict:
    """Create a restricted globals dict for exec()."""
    import builtins

    safe_builtins = {
        k: v for k, v in builtins.__dict__.items()
        if k not in {
            "eval", "exec", "compile", "__import__", "open", "input",
            "exit", "quit", "help", "copyright", "credits", "license",
            "breakpoint", "memoryview", "object", "property", "staticmethod",
            "classmethod", "super", "type", "vars", "dir", "globals", "locals"
        }
    }

    # Add safe builtins back
    safe_builtins.update({
        "print": print,
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "map": map,
        "filter": filter,
        "sum": sum,
        "max": max,
        "min": min,
        "abs": abs,
        "round": round,
        "sorted": sorted,
        "reversed": reversed,
        "any": any,
        "all": all,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "hasattr": hasattr,
        "getattr": getattr,
        "setattr": setattr,
        "delattr": delattr,
        "type": type,
        "id": id,
        "hash": hash,
        "repr": repr,
        "ord": ord,
        "chr": chr,
        "divmod": divmod,
        "pow": pow,
        "complex": complex,
        "bytes": bytes,
        "bytearray": bytearray,
        "memoryview": memoryview,
        "Exception": Exception,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "IndexError": IndexError,
        "KeyError": KeyError,
        "AttributeError": AttributeError,
        "StopIteration": StopIteration,
    })

    return {"__builtins__": safe_builtins}


def _build_wrapper_code(codigo: str, timeout: int) -> str:
    """Build the wrapper code with platform-appropriate resource limits."""
    if hasattr(os, 'fork'):  # Unix
        wrapper = f"""
import sys
import resource

# Set resource limits
resource.setrlimit(resource.RLIMIT_CPU, ({timeout}, {timeout}))
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))  # 256MB
resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))  # 10MB files
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))

{codigo}
"""
    else:  # Windows - no resource module
        wrapper = f"""
import sys

# Windows: resource limits not available
# Rely on subprocess timeout instead

{codigo}
"""
    return wrapper


def executar_codigo(codigo: str, timeout: int = 30, max_output: int = 50000) -> CodeResult:
    """
    Execute Python code in a sandboxed subprocess with resource limits.
    """
    # Static analysis
    error = _validate_code(codigo)
    if error:
        return CodeResult("", f"Security error: {error}", -1)

    # Write code to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        wrapper = _build_wrapper_code(codigo, timeout)
        f.write(wrapper)
        temp_path = f.name

    try:
        # Build command - use restricted environment on Unix, minimal on Windows
        cmd = [sys.executable, "-I", "-B", temp_path]

        env = _sandbox_env()
        preexec_fn = _limit_resources if hasattr(os, 'fork') else None

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5,  # Extra buffer for process overhead
            env=env,
            cwd=tempfile.gettempdir(),
            preexec_fn=preexec_fn,
        )
        stdout = result.stdout[:max_output]
        stderr = result.stderr[:max_output]
        return CodeResult(stdout, stderr, result.returncode)
    except subprocess.TimeoutExpired:
        return CodeResult("", "Timeout: código excedeu tempo limite.", -1, timed_out=True)
    except Exception as e:
        return CodeResult("", str(e), -1)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def _limit_resources():
    """Set resource limits in child process (Unix only)."""
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    # Drop privileges if possible
    try:
        import os
        os.setgid(65534)  # nogroup
        os.setuid(65534)  # nobody
    except (PermissionError, OSError):
        pass


def _sandbox_env():
    env = os.environ.copy()
    # Remove sensitive keys
    for key in ["AWS_SECRET_ACCESS_KEY", "OPENAI_API_API_KEY", "ANTHROPIC_API_KEY"]:
        env.pop(key, None)
    # Restrict environment
    env["PYTHONPATH"] = ""
    env["PYTHONHOME"] = ""
    if hasattr(os, 'fork'):  # Unix
        env["PATH"] = "/usr/bin:/bin"
    return env
