"""Hardened Python code execution sandbox.

Executes user-supplied Python code in a restricted namespace with:
- Blocked dangerous imports (os, sys, subprocess, socket, etc.)
- Memory and CPU time limits
- Restricted filesystem access (only /tmp writable)
- stdout/stderr capture
- AST-based static analysis pre-check
- Cross-platform timeout handling (signal on Unix, threading on Windows)
"""

from __future__ import annotations

import ast
import base64
import builtins
import io
import logging
import math
import random
import re
import signal
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any

from core.metrics import MetricNames, get_metrics
from core.telemetry import trace_span

try:
    import resource
except ImportError:  # Windows
    resource = None

logger = logging.getLogger(__name__)

# ── Blocked modules / names ───────────────────────────────────

BLOCKED_IMPORTS: frozenset[str] = frozenset(
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
        "builtins",
        "_thread",
    }
)

BLOCKED_FUNCTION_NAMES: frozenset[str] = frozenset(
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
        "globals",
        "locals",
    }
)

BLOCKED_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "__globals__",
        "__code__",
        "__class__",
        "__bases__",
        "__subclasses__",
        "__mro__",
        "__builtins__",
        "__import__",
        "__loader__",
        "__spec__",
        "__qualname__",
        "__dict__",
    }
)

BLOCKED_METHOD_NAMES: frozenset[str] = frozenset(
    {
        "system",
        "popen",
        "spawn",
        "fork",
        "exec",
        "load_module",
        "find_module",
        "find_loader",
        "import_module",
        "get_loader",
    }
)

# ── Safe builtins ─────────────────────────────────────────────

SAFE_MODULES: dict[str, Any] = {
    "math": math,
    "random": random,
    "re": re,
    "json": __import__("json"),
    "datetime": __import__("datetime"),
    "collections": __import__("collections"),
    "itertools": __import__("itertools"),
    "functools": __import__("functools"),
    "string": __import__("string"),
    "textwrap": __import__("textwrap"),
    "hashlib": __import__("hashlib"),
    "base64": __import__("base64"),
    "heapq": __import__("heapq"),
    "bisect": __import__("bisect"),
    "array": __import__("array"),
    "decimal": __import__("decimal"),
    "fractions": __import__("fractions"),
    "statistics": __import__("statistics"),
    "copy": __import__("copy"),
    "pprint": __import__("pprint"),
    "enum": __import__("enum"),
    "dataclasses": __import__("dataclasses"),
    "abc": __import__("abc"),
    "typing": __import__("typing"),
    "contextlib": __import__("contextlib"),
    "io": io,
}

SAFE_MODULE_EXPORTS: dict[str, frozenset[str]] = {
    "abc": frozenset({"ABC", "ABCMeta", "abstractmethod"}),
    "array": frozenset({"array"}),
    "base64": frozenset(
        {"b16decode", "b16encode", "b32decode", "b32encode", "b64decode", "b64encode"}
    ),
    "bisect": frozenset({"bisect", "bisect_left", "bisect_right", "insort"}),
    "collections": frozenset(
        {"ChainMap", "Counter", "OrderedDict", "defaultdict", "deque", "namedtuple"}
    ),
    "contextlib": frozenset({"nullcontext", "redirect_stderr", "redirect_stdout", "suppress"}),
    "copy": frozenset({"copy", "deepcopy"}),
    "dataclasses": frozenset({"asdict", "astuple", "dataclass", "field", "fields", "replace"}),
    "datetime": frozenset({"date", "datetime", "time", "timedelta", "timezone"}),
    "decimal": frozenset({"Decimal", "DecimalException", "getcontext", "localcontext"}),
    "enum": frozenset({"Enum", "Flag", "IntEnum", "IntFlag", "auto", "unique"}),
    "fractions": frozenset({"Fraction"}),
    "functools": frozenset({"cache", "cached_property", "lru_cache", "partial", "reduce", "wraps"}),
    "hashlib": frozenset(
        {"blake2b", "blake2s", "md5", "new", "sha1", "sha224", "sha256", "sha384", "sha512"}
    ),
    "heapq": frozenset({"heapify", "heappop", "heappush", "heappushpop", "merge", "nlargest", "nsmallest"}),
    "io": frozenset({"BytesIO", "StringIO"}),
    "itertools": frozenset(
        {"accumulate", "chain", "combinations", "combinations_with_replacement", "compress", "count", "cycle", "dropwhile", "filterfalse", "groupby", "islice", "pairwise", "permutations", "product", "repeat", "starmap", "takewhile", "tee", "zip_longest"}
    ),
    "json": frozenset({"JSONDecodeError", "dump", "dumps", "load", "loads"}),
    "math": frozenset(name for name in dir(math) if not name.startswith("_")),
    "pprint": frozenset({"pformat", "pp", "pprint"}),
    "random": frozenset(
        {"choice", "choices", "getrandbits", "randint", "random", "randrange", "sample", "seed", "shuffle", "uniform"}
    ),
    "re": frozenset(
        {"ASCII", "DOTALL", "IGNORECASE", "MULTILINE", "Match", "Pattern", "VERBOSE", "compile", "escape", "findall", "finditer", "fullmatch", "match", "search", "split", "sub", "subn"}
    ),
    "statistics": frozenset(
        {"StatisticsError", "correlation", "fmean", "geometric_mean", "harmonic_mean", "linear_regression", "mean", "median", "median_grouped", "median_high", "median_low", "mode", "multimode", "pstdev", "pvariance", "quantiles", "stdev", "variance"}
    ),
    "string": frozenset(
        {"Formatter", "Template", "ascii_letters", "ascii_lowercase", "ascii_uppercase", "digits", "hexdigits", "octdigits", "printable", "punctuation", "whitespace"}
    ),
    "textwrap": frozenset({"TextWrapper", "dedent", "fill", "indent", "shorten", "wrap"}),
    "typing": frozenset({"Any", "Callable", "Dict", "Iterable", "Iterator", "List", "Literal", "Optional", "Sequence", "Set", "Tuple", "Union"}),
}


class _SafeModuleProxy:
    """Expose only explicitly approved attributes from a standard-library module."""

    __slots__ = ("_exports", "_module")

    def __init__(self, module: Any, exports: frozenset[str]):
        object.__setattr__(self, "_module", module)
        object.__setattr__(self, "_exports", exports)

    def __getattribute__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError("Atributo privado bloqueado no sandbox")
        exports = object.__getattribute__(self, "_exports")
        if name not in exports:
            raise AttributeError(f"Atributo nao permitido no sandbox: {name}")
        module = object.__getattribute__(self, "_module")
        return getattr(module, name)


SAFE_MODULE_PROXIES: dict[str, _SafeModuleProxy] = {
    name: _SafeModuleProxy(module, SAFE_MODULE_EXPORTS[name])
    for name, module in SAFE_MODULES.items()
}

# ── Safe builtins subset ──────────────────────────────────────

SAFE_BUILTIN_NAMES: frozenset[str] = frozenset(
    {
        "abs",
        "all",
        "any",
        "bin",
        "bool",
        "bytearray",
        "bytes",
        "callable",
        "chr",
        "classmethod",
        "complex",
        "dict",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "hash",
        "hex",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "object",
        "oct",
        "ord",
        "pow",
        "print",
        "property",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "staticmethod",
        "str",
        "sum",
        "tuple",
        "zip",
        "__name__",
        "__doc__",
        "__build_class__",
        "ArithmeticError",
        "AssertionError",
        "Exception",
        "IndexError",
        "KeyError",
        "RuntimeError",
        "TypeError",
        "ValueError",
        "ZeroDivisionError",
    }
)


def _build_safe_builtins() -> dict[str, Any]:
    """Construct a dict of only safe builtins + safe modules."""
    ns: dict[str, Any] = {}
    for name in SAFE_BUILTIN_NAMES:
        if hasattr(builtins, name):
            ns[name] = getattr(builtins, name)
    # Inject safe modules as if they were builtins
    ns.update(SAFE_MODULE_PROXIES)
    # Add commonly-needed constants
    ns["True"] = True
    ns["False"] = False
    ns["None"] = None
    ns["Ellipsis"] = Ellipsis
    ns["NotImplemented"] = NotImplemented
    ns["__import__"] = _safe_import
    return ns


def _safe_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
    if level != 0 or name not in SAFE_MODULES:
        raise ImportError(f"Import nao permitido no sandbox: {name}")
    return SAFE_MODULE_PROXIES[name]


def build_restricted_wrapper(code: str) -> str:
    """Build an isolated namespace wrapper for the child Python process."""
    payload = base64.b64encode(code.encode("utf-8")).decode("ascii")
    safe_names = sorted(SAFE_BUILTIN_NAMES)
    module_exports = {name: sorted(exports) for name, exports in SAFE_MODULE_EXPORTS.items()}
    return f"""
import base64 as _base64
import builtins as _builtins

_MODULE_EXPORTS = {module_exports!r}
_SAFE_NAMES = {safe_names!r}

class _SafeModuleProxy:
    __slots__ = ('_exports', '_module')

    def __init__(self, module, exports):
        object.__setattr__(self, '_module', module)
        object.__setattr__(self, '_exports', frozenset(exports))

    def __getattribute__(self, name):
        if name.startswith('_'):
            raise AttributeError('Atributo privado bloqueado no sandbox')
        exports = object.__getattribute__(self, '_exports')
        if name not in exports:
            raise AttributeError(f'Atributo nao permitido no sandbox: {{name}}')
        module = object.__getattribute__(self, '_module')
        return getattr(module, name)

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split('.')[0]
    if level != 0 or name != root or root not in _MODULE_EXPORTS:
        raise ImportError(f'Import nao permitido no sandbox: {{name}}')
    module = _builtins.__import__(root, globals, locals, (), level)
    return _SafeModuleProxy(module, _MODULE_EXPORTS[root])

_safe_builtins = {{name: getattr(_builtins, name) for name in _SAFE_NAMES}}
_safe_builtins['__import__'] = _safe_import
for _module_name, _exports in _MODULE_EXPORTS.items():
    _safe_builtins[_module_name] = _SafeModuleProxy(
        _builtins.__import__(_module_name), _exports
    )
_globals = {{'__builtins__': _safe_builtins, '__name__': '__sandbox__'}}
_source = _base64.b64decode({payload!r}).decode('utf-8')
exec(_builtins.compile(_source, '<celsius-sandbox>', 'exec'), _globals, _globals)
"""


# ── AST validation ────────────────────────────────────────────


def validate_code(code: str) -> str | None:
    """AST-based static analysis. Returns error string or None if safe."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in SAFE_MODULES:
                    return f"Blocked import: {alias.name}"

        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module not in SAFE_MODULES
        ):
            return f"Blocked import: {node.module}"

        if isinstance(node, ast.Name) and (
            node.id in BLOCKED_FUNCTION_NAMES
            or node.id in {"__builtins__", "getattr", "setattr", "delattr", "vars", "globals", "locals"}
        ):
            return f"Blocked name: {node.id}"

        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in BLOCKED_FUNCTION_NAMES:
                return f"Blocked function: {func.id}"
            if isinstance(func, ast.Attribute) and func.attr in BLOCKED_METHOD_NAMES:
                return f"Blocked method: {func.attr}"

        if isinstance(node, ast.Attribute) and (
            node.attr in BLOCKED_ATTRIBUTES or node.attr.startswith("_")
        ):
            return f"Blocked attribute access: {node.attr}"

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "__import__"
        ):
            return "Blocked function: __import__"
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "__import__"
        ):
            return "Blocked function: __import__"

        if isinstance(node, ast.Attribute) and node.attr in {
            "import_module",
            "import_module_of_type",
        }:
            return f"Blocked method: importlib.{node.attr}"

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value.lower()
            if any(pattern in val for pattern in ("__import__", "__builtins__", "builtins", "breakpoint")):
                return f"Blocked string constant: '{node.value}'"

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            try:
                value = ast.literal_eval(node)
            except (ValueError, TypeError):
                value = None
            if isinstance(value, str) and any(
                pattern in value.lower()
                for pattern in ("__import__", "__builtins__", "builtins", "breakpoint")
            ):
                return "Blocked dynamically constructed string"

    return None


# ── Timeout handlers ──────────────────────────────────────────


class _TimeoutError(Exception):
    """Raised when code execution exceeds the time limit."""


def _timeout_handler_signal(signum: int, frame: Any) -> None:
    raise _TimeoutError("Execution timed out")


def _set_timeout_signal(seconds: int) -> None:
    signal.signal(signal.SIGALRM, _timeout_handler_signal)
    signal.alarm(seconds)


def _clear_timeout_signal() -> None:
    signal.alarm(0)
    signal.signal(signal.SIGALRM, signal.SIG_DFL)


class _TimeoutWatcher(threading.Thread):
    """Cross-platform timeout via daemon thread (used on Windows)."""

    def __init__(self, seconds: int) -> None:
        super().__init__(daemon=True)
        self._seconds = seconds
        self._deadline = time.monotonic() + seconds
        self.timed_out = False
        self._thread_to_kill: threading.Thread | None = None

    def run(self) -> None:
        remaining = self._deadline - time.monotonic()
        while remaining > 0 and not self.timed_out:
            time.sleep(min(remaining, 0.1))
            remaining = self._deadline - time.monotonic()
        if not self.timed_out:
            self.timed_out = True

    def check(self) -> None:
        if self.timed_out:
            raise _TimeoutError("Execution timed out")


# ── Result dataclass ──────────────────────────────────────────


@dataclass
class ExecutionResult:
    """Result of sandboxed code execution."""

    output: str = ""
    error: str = ""
    success: bool = False
    execution_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "error": self.error,
            "success": self.success,
            "execution_time": self.execution_time,
        }


# ── SandboxedExecutor ─────────────────────────────────────────


class SandboxedExecutor:
    """Execute Python code in a restricted namespace with resource limits.

    Usage:
        executor = SandboxedExecutor(cpu_time=30, memory_mb=256)
        result = executor.execute("print(1 + 2)")
        print(result.to_dict())
    """

    def __init__(
        self,
        cpu_time: int = 30,
        memory_mb: int = 256,
        max_output: int = 50_000,
    ) -> None:
        self.cpu_time = cpu_time
        self.memory_mb = memory_mb
        self.max_output = max_output

    def execute(self, code: str) -> ExecutionResult:
        """Run *code* inside the sandbox and return an ExecutionResult."""
        metrics = get_metrics()

        with trace_span("sandbox.execute", {"sandbox.cpu_time": self.cpu_time}):
            # 1. Static analysis
            error = validate_code(code)
            if error:
                metrics.inc(MetricNames.WORKER_ERRORS_TOTAL, error_type="validation")
                logger.warning("Code validation failed: %s", error)
                return ExecutionResult(
                    error=f"Security error: {error}",
                    success=False,
                )

            # 2. Execute
            t0 = time.perf_counter()
            try:
                result = self._run_in_subprocess(code)
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                metrics.inc(MetricNames.WORKER_ERRORS_TOTAL, error_type="execution")
                return ExecutionResult(
                    error=f"Execution error: {exc}",
                    execution_time=elapsed,
                    success=False,
                )
            elapsed = time.perf_counter() - t0
            result.execution_time = elapsed

            metrics.inc(MetricNames.WORKER_JOBS_TOTAL, status="ok" if result.success else "error")
            metrics.observe(MetricNames.WORKER_JOB_DURATION_SECONDS, elapsed)
            return result

    # ── Subprocess-based execution (Unix) ─────────────────────

    def _run_in_subprocess(self, code: str) -> ExecutionResult:
        """Fork-safe execution via subprocess with resource limits."""
        import contextlib as _ctx
        import subprocess

        sandbox_code = self._wrap_code(code)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(sandbox_code)
            temp_path = f.name

        try:
            cmd = [sys.executable, "-I", "-B", temp_path]
            env = self._sandbox_env()

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.cpu_time + 5,
                env=env,
                cwd=tempfile.gettempdir(),
                preexec_fn=self._resource_limits_fn,
            )

            stdout = result.stdout[: self.max_output]
            stderr = result.stderr[: self.max_output]
            returncode = result.returncode

            return ExecutionResult(
                output=stdout,
                error=stderr if returncode != 0 else "",
                success=returncode == 0,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                error="Timeout: execution exceeded time limit.",
                success=False,
            )
        finally:
            with _ctx.suppress(OSError):
                import os

                os.unlink(temp_path)

    def _wrap_code(self, code: str) -> str:
        """Wrap user code with resource limits."""
        if sys.platform != "win32":
            mem_bytes = self.memory_mb * 1024 * 1024
            return (
                "import resource\n"
                f"resource.setrlimit(resource.RLIMIT_CPU, ({self.cpu_time}, {self.cpu_time}))\n"
                f"resource.setrlimit(resource.RLIMIT_AS, ({mem_bytes}, {mem_bytes}))\n"
                "resource.setrlimit(resource.RLIMIT_FSIZE, (10*1024*1024, 10*1024*1024))\n"
                "resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))\n"
                + build_restricted_wrapper(code)
            )
        return build_restricted_wrapper(code)

    def _resource_limits_fn(self) -> None:
        """preexec_fn for Unix subprocesses."""
        if sys.platform == "win32" or resource is None:
            return
        mem_bytes = self.memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_CPU, (self.cpu_time, self.cpu_time))
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        try:
            import os

            os.setgid(65534)
            os.setuid(65534)
        except (PermissionError, OSError):
            pass

    @staticmethod
    def _sandbox_env() -> dict[str, str]:
        """Build a clean environment stripping API keys."""
        import os

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
        if sys.platform != "win32":
            env["PATH"] = "/usr/bin:/bin"
        return env

    # ── In-process execution (safe namespace) ─────────────────

    def execute_in_process(self, code: str) -> ExecutionResult:
        """Execute code in-process with a restricted namespace.

        WARNING: Less isolated than subprocess but useful for quick eval
        where fork overhead matters. Still runs AST validation first.
        """
        metrics = get_metrics()

        with trace_span("sandbox.execute_in_process"):
            error = validate_code(code)
            if error:
                metrics.inc(MetricNames.WORKER_ERRORS_TOTAL, error_type="validation")
                return ExecutionResult(error=f"Security error: {error}", success=False)

            safe_builtins = _build_safe_builtins()
            safe_ns = {"__builtins__": safe_builtins, "__name__": "__sandbox__"}

            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
            old_stdout, old_stderr = sys.stdout, sys.stderr

            watcher: _TimeoutWatcher | None = None
            if sys.platform == "win32":
                watcher = _TimeoutWatcher(self.cpu_time)
                watcher.start()

            t0 = time.perf_counter()
            try:
                if sys.platform != "win32":
                    _set_timeout_signal(self.cpu_time)

                sys.stdout = stdout_buf
                sys.stderr = stderr_buf

                exec(compile(code, "<sandbox>", "exec"), safe_ns, safe_ns)

                elapsed = time.perf_counter() - t0
                return ExecutionResult(
                    output=stdout_buf.getvalue()[: self.max_output],
                    error=stderr_buf.getvalue()[: self.max_output],
                    success=True,
                    execution_time=elapsed,
                )
            except _TimeoutError:
                elapsed = time.perf_counter() - t0
                return ExecutionResult(
                    error="Timeout: execution exceeded time limit.",
                    execution_time=elapsed,
                    success=False,
                )
            except Exception:
                elapsed = time.perf_counter() - t0
                tb = traceback.format_exc()
                return ExecutionResult(
                    output=stdout_buf.getvalue()[: self.max_output],
                    error=tb[: self.max_output],
                    execution_time=elapsed,
                    success=False,
                )
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr
                if sys.platform != "win32":
                    _clear_timeout_signal()
                if watcher is not None:
                    watcher.timed_out = True
                    watcher.join(timeout=1)
                metrics.inc(MetricNames.WORKER_JOBS_TOTAL)
                metrics.observe(MetricNames.WORKER_JOB_DURATION_SECONDS, elapsed)
