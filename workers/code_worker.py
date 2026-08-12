import contextlib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from core.sandbox import build_restricted_wrapper, validate_code


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
        self.status.emit("Executando codigo...")
        resultado = executar_codigo(self.codigo, self.timeout)
        self.resultado.emit(resultado)


BLOCKED_IMPORTS = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "shutil",
        "pathlib",
        "glob",
        "socket",
        "http",
        "urllib",
        "requests",
        "ftplib",
        "telnetlib",
        "importlib",
        "pkgutil",
        "runpy",
        "compileall",
        "py_compile",
        "ctypes",
        "multiprocessing",
        "threading",
        "asyncio",
        "pickle",
        "shelve",
        "marshal",
        "dbm",
        "sqlite3",
        "webbrowser",
        "tkinter",
        "PySide6",
        "PyQt6",
        "code",
        "codeop",
        "compile",
    }
)

BLOCKED_FUNCTION_NAMES = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "open",
        "input",
        "breakpoint",
        "exit",
        "quit",
    }
)

BLOCKED_ATTRIBUTES = frozenset(
    {
        "__globals__",
        "__code__",
        "__class__",
        "__bases__",
        "__subclasses__",
        "__mro__",
        "__builtins__",
    }
)

BLOCKED_METHOD_NAMES = frozenset(
    {
        "system",
        "popen",
        "spawn",
        "fork",
        "exec",
        "system_calls",
        "load_module",
        "find_module",
        "find_loader",
        "import_module",
        "get_loader",
    }
)

BLOCKED_STRING_PATTERNS = (
    "__import__",
    "builtins",
    "breakpoint",
)


def _validate_code(code: str) -> str | None:
    """AST-based static analysis to catch dangerous patterns.

    Checks for:
    - Blocked module imports (os, subprocess, ctypes, etc.)
    - Dangerous function calls (eval, exec, open, etc.)
    - Dangerous attribute access (__globals__, __subclasses__, etc.)
    - Dangerous method calls (system, popen, spawn, etc.)
    - String-based import attempts (__import__('os'))
    - Importlib-based evasion (importlib.import_module)
    """
    return validate_code(code)


def _build_wrapper_code(codigo: str, timeout: int) -> str:
    """Build wrapper code with platform-appropriate resource limits."""
    if hasattr(os, "fork"):  # Unix
        wrapper = f"""
import sys
import resource

# Set resource limits
resource.setrlimit(resource.RLIMIT_CPU, ({timeout}, {timeout}))
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))  # 256MB
resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))  # 10MB
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))

{build_restricted_wrapper(codigo)}
"""
    else:  # Windows
        wrapper = build_restricted_wrapper(codigo)
    return wrapper


def _limit_resources() -> None:
    """Set resource limits in child process (Unix only, called via preexec_fn)."""
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    try:
        os.setgid(65534)  # nogroup
        os.setuid(65534)  # nobody
    except (PermissionError, OSError):
        pass


def _sandbox_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in [
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "HUGGING_FACE_HUB_TOKEN",
        "HF_TOKEN",
        "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY",
    ]:
        env.pop(key, None)
    env["PYTHONPATH"] = ""
    env["PYTHONHOME"] = ""
    if hasattr(os, "fork"):
        env["PATH"] = "/usr/bin:/bin"
    return env


def executar_codigo(codigo: str, timeout: int = 30, max_output: int = 50000) -> CodeResult:
    """Execute Python code in a sandboxed subprocess with resource limits.

    On Windows: uses Job Objects for CPU time + memory limits.
    On Unix: uses resource.setrlimit + privilege drop.
    """
    # Static analysis
    error = _validate_code(codigo)
    if error:
        return CodeResult("", f"Security error: {error}", -1)

    # Windows path: use Job Objects sandbox
    if sys.platform == "win32":
        from workers.windows_sandbox import (
            WindowsSandboxConfig,
            executar_codigo_windows,
        )

        config = WindowsSandboxConfig(cpu_time_limit_seconds=timeout)
        result = executar_codigo_windows(
            codigo, timeout=timeout, max_output=max_output, config=config
        )
        return CodeResult(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            timed_out=result.timed_out,
        )

    # Unix path: use preexec_fn + resource limits
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        wrapper = _build_wrapper_code(codigo, timeout)
        f.write(wrapper)
        temp_path = f.name

    try:
        cmd = [sys.executable, "-I", "-B", temp_path]
        env = _sandbox_env()

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
            env=env,
            cwd=tempfile.gettempdir(),
            preexec_fn=_limit_resources,
        )
        stdout = result.stdout[:max_output]
        stderr = result.stderr[:max_output]
        return CodeResult(stdout, stderr, result.returncode)
    except subprocess.TimeoutExpired:
        return CodeResult("", "Timeout: codigo excedeu tempo limite.", -1, timed_out=True)
    except Exception as e:
        return CodeResult("", str(e), -1)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(temp_path)
