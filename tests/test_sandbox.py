"""Tests for core.sandbox (AST validation, SafeNamespace, SandboxedExecutor)."""

import sys

import pytest

from core.sandbox import (
    BLOCKED_ATTRIBUTES,
    BLOCKED_FUNCTION_NAMES,
    BLOCKED_IMPORTS,
    BLOCKED_METHOD_NAMES,
    SAFE_MODULES,
    ExecutionResult,
    SandboxedExecutor,
    _build_safe_builtins,
    validate_code,
)

# On Windows, _run_in_subprocess uses preexec_fn which is unsupported.
# Use execute_in_process instead for runtime executor tests.
_USE_IN_PROCESS = sys.platform == "win32"


@pytest.fixture(autouse=True)
def _patch_metric_names():
    """sandbox.py references MetricNames.WORKER_* which only exists in
    core.telemetry.MetricNames, not core.metrics.MetricNames. Patch them."""
    from core.metrics import MetricNames

    missing = {
        "WORKER_ERRORS_TOTAL": "celsius.worker.errors.total",
        "WORKER_JOBS_TOTAL": "celsius.worker.jobs.total",
        "WORKER_JOB_DURATION_SECONDS": "celsius.worker.job.duration",
    }
    patched = {}
    for attr, val in missing.items():
        if not hasattr(MetricNames, attr):
            setattr(MetricNames, attr, val)
            patched[attr] = attr
    yield
    for attr in patched:
        delattr(MetricNames, attr)


# ---------------------------------------------------------------------------
# validate_code (AST static analysis)
# ---------------------------------------------------------------------------


class TestValidateCodeSyntaxErrors:
    def test_syntax_error(self):
        err = validate_code("def (")
        assert err is not None
        assert "Syntax error" in err

    def test_valid_code(self):
        assert validate_code("print(1 + 2)") is None

    def test_empty_code(self):
        assert validate_code("") is None

    def test_comment_only(self):
        assert validate_code("# just a comment") is None


class TestValidateCodeBlockedImports:
    @pytest.mark.parametrize(
        "module",
        [
            "os",
            "sys",
            "subprocess",
            "shutil",
            "pathlib",
            "socket",
            "http",
            "ctypes",
            "multiprocessing",
            "threading",
            "asyncio",
            "pickle",
            "sqlite3",
            "webbrowser",
            "importlib",
            "runpy",
        ],
    )
    def test_direct_import_blocked(self, module):
        err = validate_code(f"import {module}")
        assert err is not None
        assert "Blocked import" in err

    @pytest.mark.parametrize(
        "code",
        [
            "from os import system",
            "from subprocess import run",
            "from pathlib import Path",
            "from ctypes import CDLL",
            "from importlib import import_module",
            "from multiprocessing import Process",
            "from threading import Thread",
            "import urllib.request",
            "import http.client",
        ],
    )
    def test_from_import_blocked(self, code):
        err = validate_code(code)
        assert err is not None
        assert "Blocked import" in err

    def test_dotted_import_blocked(self):
        err = validate_code("import os.path")
        assert err is not None
        assert "Blocked import" in err

    def test_import_os_environ(self):
        err = validate_code("import os; x = os.environ")
        assert err is not None


class TestValidateCodeSafeImports:
    @pytest.mark.parametrize(
        "module",
        [
            "math",
            "random",
            "re",
            "json",
            "datetime",
            "collections",
            "itertools",
            "statistics",
            "decimal",
            "fractions",
        ],
    )
    def test_safe_imports_allowed(self, module):
        err = validate_code(f"import {module}")
        assert err is None

    def test_from_math_import(self):
        assert validate_code("from math import sqrt") is None

    def test_from_collections_import(self):
        assert validate_code("from collections import Counter") is None


class TestValidateCodeBlockedFunctions:
    @pytest.mark.parametrize(
        "code",
        [
            "eval('1+1')",
            "exec('print(1)')",
            "compile('1+1', '<string>', 'eval')",
            "__import__('os')",
            "open('/etc/passwd')",
            "input('password')",
            "breakpoint()",
            "exit()",
            "quit()",
        ],
    )
    def test_dangerous_function_blocked(self, code):
        err = validate_code(code)
        assert err is not None
        assert "Blocked" in err

    def test_blocks_reported_getattr_builtins_bypass(self):
        code = "getattr(__builtins__, 'pr' + 'int')('SANDBOX_BYPASS_OK')"
        err = validate_code(code)
        assert err is not None
        assert "Blocked" in err


class TestValidateCodeBlockedMethods:
    @pytest.mark.parametrize(
        "code",
        [
            "import os; os.system('ls')",
            "import os; os.popen('ls')",
            "import subprocess; subprocess.system('ls')",
        ],
    )
    def test_blocked_method(self, code):
        err = validate_code(code)
        assert err is not None
        assert "Blocked" in err


class TestValidateCodeBlockedAttributes:
    @pytest.mark.parametrize(
        "attr",
        [
            "__globals__",
            "__code__",
            "__class__",
            "__bases__",
            "__subclasses__",
            "__mro__",
            "__builtins__",
        ],
    )
    def test_blocked_attribute(self, attr):
        err = validate_code(f"x = (1).{attr}")
        assert err is not None
        assert "Blocked" in err


class TestValidateCodeEdgeCases:
    def test_importlib_import_module(self):
        err = validate_code("import importlib; importlib.import_module('os')")
        assert err is not None

    def test_lambda_with_import(self):
        err = validate_code("f = lambda: __import__('os')")
        assert err is not None

    def test_list_comp_import(self):
        err = validate_code("[__import__('os') for _ in range(1)]")
        assert err is not None

    def test_walrus_eval(self):
        err = validate_code("x := eval('1+1')")
        assert err is not None

    def test_star_import(self):
        err = validate_code("from os import *")
        assert err is not None

    def test_blocked_string_constant(self):
        err = validate_code("x = '__import__'")
        assert err is not None

    def test_blocked_string_builtins(self):
        err = validate_code("x = 'builtins'")
        assert err is not None


# ---------------------------------------------------------------------------
# _build_safe_builtins (SafeNamespace)
# ---------------------------------------------------------------------------


class TestSafeNamespace:
    def test_safe_builtins_contain_core_types(self):
        ns = _build_safe_builtins()
        assert "int" in ns
        assert "str" in ns
        assert "list" in ns
        assert "dict" in ns
        assert "float" in ns
        assert "bool" in ns
        assert "len" in ns
        assert "range" in ns
        assert "print" in ns

    def test_safe_builtins_contain_modules(self):
        ns = _build_safe_builtins()
        assert "math" in ns
        assert "random" in ns
        assert "re" in ns
        assert "json" in ns
        assert "datetime" in ns
        assert "collections" in ns

    def test_safe_builtins_no_dangerous_modules(self):
        ns = _build_safe_builtins()
        assert "os" not in ns
        assert "sys" not in ns
        assert "subprocess" not in ns
        assert "socket" not in ns

    def test_safe_builtins_contain_constants(self):
        ns = _build_safe_builtins()
        assert ns["True"] is True
        assert ns["False"] is False
        assert ns["None"] is None

    def test_safe_builtins_namespace_works_in_exec(self):
        ns = _build_safe_builtins()
        ns["__name__"] = "__sandbox__"
        exec("result = math.sqrt(16)", ns)
        assert ns["result"] == 4.0

    def test_safe_builtins_json_roundtrip(self):
        ns = _build_safe_builtins()
        ns["__name__"] = "__sandbox__"
        exec("result = json.dumps({'a': 1})", ns)
        assert '"a": 1' in ns["result"]


# ---------------------------------------------------------------------------
# SandboxedExecutor
# ---------------------------------------------------------------------------


class TestExecutionResult:
    def test_default(self):
        r = ExecutionResult()
        assert r.output == ""
        assert r.error == ""
        assert r.success is False
        assert r.execution_time == 0.0

    def test_to_dict(self):
        r = ExecutionResult(output="hi", error="", success=True, execution_time=0.1)
        d = r.to_dict()
        assert d["output"] == "hi"
        assert d["error"] == ""
        assert d["success"] is True
        assert d["execution_time"] == 0.1


class TestSandboxedExecutorSafeCode:
    def _run(self, code, cpu_time=5):
        ex = SandboxedExecutor(cpu_time=cpu_time)
        if _USE_IN_PROCESS:
            return ex.execute_in_process(code)
        return ex.execute(code)

    def test_simple_print(self):
        r = self._run("print('hello world')")
        assert r.success
        assert "hello world" in r.output

    def test_math_computation(self):
        r = self._run("print(sum(range(100)))")
        assert r.success
        assert "4950" in r.output

    def test_import_json(self):
        r = self._run('import json; print(json.dumps({"key": "value"}))')
        assert r.success
        assert '"key": "value"' in r.output

    def test_import_math(self):
        r = self._run("import math; print(math.pi)")
        assert r.success
        assert "3.14" in r.output

    def test_import_datetime(self):
        r = self._run("from datetime import datetime; print(datetime.now().year)")
        assert r.success

    def test_import_collections(self):
        r = self._run("from collections import Counter; print(Counter([1,1,2]))")
        assert r.success
        assert "2" in r.output

    def test_import_statistics(self):
        r = self._run("import statistics; print(statistics.mean([1,2,3,4,5]))")
        assert r.success
        assert "3" in r.output

    def test_import_regex(self):
        r = self._run("import re; print(len(re.findall(r'\\w+', 'hello world foo bar')))")
        assert r.success
        assert "4" in r.output

    def test_import_itertools(self):
        r = self._run("import itertools; print(list(itertools.chain([1,2],[3,4])))")
        assert r.success
        assert "[1, 2, 3, 4]" in r.output

    def test_execution_time_populated(self):
        r = self._run("print(42)")
        assert r.execution_time > 0


class TestSandboxedExecutorBlockedCode:
    def _run(self, code, cpu_time=5):
        ex = SandboxedExecutor(cpu_time=cpu_time)
        if _USE_IN_PROCESS:
            return ex.execute_in_process(code)
        return ex.execute(code)

    def test_import_os(self):
        r = self._run("import os; os.system('echo pwned')")
        assert not r.success
        assert "Blocked import" in r.error

    def test_import_subprocess(self):
        r = self._run("import subprocess; subprocess.run(['ls'])")
        assert not r.success
        assert "Blocked" in r.error

    def test_import_socket(self):
        r = self._run("import socket; socket.socket()")
        assert not r.success

    def test_eval_call(self):
        r = self._run("eval('1+1')")
        assert not r.success
        assert "Blocked" in r.error

    def test_exec_call(self):
        r = self._run("exec('print(1)')")
        assert not r.success

    def test_open_call(self):
        r = self._run("open('/etc/passwd')")
        assert not r.success

    def test_breakpoint_call(self):
        r = self._run("breakpoint()")
        assert not r.success

    def test_dunder_globals(self):
        r = self._run("x = (1).__globals__")
        assert not r.success

    @pytest.mark.parametrize(
        "code",
        [
            "import io; io.open('sandbox_escape.txt', 'w')",
            "import contextlib; contextlib.os.getcwd()",
            "import random; random._os.listdir('.')",
        ],
    )
    def test_safe_module_facades_do_not_expose_system_access(self, code):
        r = self._run(code)
        assert not r.success

    def test_dunder_subclasses(self):
        r = self._run("x = (1).__class__.__bases__")
        assert not r.success

    def test_syntax_error(self):
        r = self._run("def (")
        assert not r.success
        assert "Syntax error" in r.error


class TestSandboxedExecutorTimeout:
    @pytest.mark.skipif(
        _USE_IN_PROCESS,
        reason="In-process timeout is cooperative on Windows, cannot interrupt exec()",
    )
    def test_timeout(self):
        ex = SandboxedExecutor(cpu_time=2)
        r = ex.execute("while True:\n    pass")
        assert not r.success
        assert (
            "Timeout" in r.error or "timeout" in r.error.lower() or "timed out" in r.error.lower()
        )


class TestSandboxedExecutorEdgeCases:
    def _run(self, code, cpu_time=5):
        ex = SandboxedExecutor(cpu_time=cpu_time)
        if _USE_IN_PROCESS:
            return ex.execute_in_process(code)
        return ex.execute(code)

    def test_empty_code(self):
        r = self._run("")
        assert r.success

    def test_multiline_code(self):
        code = """
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
print(fib(10))
"""
        r = self._run(code)
        assert r.success
        assert "55" in r.output

    def test_class_definition(self):
        code = """
class Counter:
    def __init__(self):
        self.value = 0
    def increment(self):
        self.value += 1
        return self.value

c = Counter()
print(c.increment())
print(c.increment())
"""
        r = self._run(code)
        assert r.success
        assert "1" in r.output
        assert "2" in r.output

    def test_exception_in_code(self):
        r = self._run("raise ValueError('test error')")
        assert not r.success
        assert "ValueError" in r.error

    def test_division_by_zero(self):
        r = self._run("print(1/0)")
        assert not r.success
        assert "ZeroDivisionError" in r.error

    def test_list_comprehension(self):
        r = self._run("print([x**2 for x in range(10)])")
        assert r.success
        assert "[0, 1, 4, 9, 16, 25, 36, 49, 64, 81]" in r.output

    def test_string_operations(self):
        r = self._run("print('hello'.upper(), 'WORLD'.lower())")
        assert r.success
        assert "HELLO" in r.output
        assert "world" in r.output

    def test_lambda_function(self):
        r = self._run("f = lambda x: x * 2; print(f(21))")
        assert r.success
        assert "42" in r.output

    def test_nested_loops(self):
        code = """
result = []
for i in range(3):
    for j in range(3):
        result.append(i * 3 + j)
print(sum(result))
"""
        r = self._run(code)
        assert r.success
        assert "36" in r.output

    def test_dict_comprehension(self):
        r = self._run("print({k: k**2 for k in range(5)})")
        assert r.success
        assert "16" in r.output

    def test_try_except(self):
        code = """
try:
    x = int("not_a_number")
except ValueError:
    print("caught")
"""
        r = self._run(code)
        assert r.success
        assert "caught" in r.output


class TestBlockedModulesSet:
    def test_core_modules_in_blocked(self):
        for mod in [
            "os",
            "sys",
            "subprocess",
            "shutil",
            "pathlib",
            "socket",
            "ctypes",
            "multiprocessing",
            "threading",
            "asyncio",
            "pickle",
            "sqlite3",
            "importlib",
        ]:
            assert mod in BLOCKED_IMPORTS

    def test_blocked_functions(self):
        for fn in [
            "eval",
            "exec",
            "compile",
            "__import__",
            "open",
            "input",
            "breakpoint",
            "exit",
            "quit",
        ]:
            assert fn in BLOCKED_FUNCTION_NAMES

    def test_blocked_attributes(self):
        for attr in [
            "__globals__",
            "__code__",
            "__class__",
            "__bases__",
            "__subclasses__",
            "__mro__",
            "__builtins__",
        ]:
            assert attr in BLOCKED_ATTRIBUTES

    def test_blocked_methods(self):
        for method in ["system", "popen", "spawn", "fork", "exec"]:
            assert method in BLOCKED_METHOD_NAMES

    def test_safe_modules_exist(self):
        for mod in [
            "math",
            "random",
            "re",
            "json",
            "datetime",
            "collections",
            "itertools",
            "statistics",
            "decimal",
            "fractions",
        ]:
            assert mod in SAFE_MODULES
