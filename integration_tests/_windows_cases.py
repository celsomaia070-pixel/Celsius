"""Real Win32 sandbox and bundled DLL loading, without unbounded allocations."""

import ctypes
import os
import struct
import time
from pathlib import Path
from unittest.mock import patch


def dlls():
    import llama_cpp

    root = Path(llama_cpp.__file__).parent / "lib"
    # Architecture-specialized CPU plugins are deliberately not executed.
    names = ("ggml-base.dll", "ggml-cpu.dll", "llama.dll", "mtmd.dll")
    with os.add_dll_directory(str(root)):
        libraries = [ctypes.CDLL(str(root / name)) for name in names]
        assert all(library._handle for library in libraries)
        assert libraries[2].llama_model_default_params
        assert libraries[3].mtmd_context_params_default
    print(f"Loaded bundled native DLLs: {', '.join(names)}")


def worker():
    from PySide6.QtCore import QCoreApplication, Qt

    from workers.code_worker import CodeWorker, executar_codigo

    app = QCoreApplication.instance() or QCoreApplication([])
    results, statuses = [], []
    task = CodeWorker("import math\nprint(math.sqrt(81))", timeout=3)
    task.resultado.connect(results.append, Qt.ConnectionType.DirectConnection)
    task.status.connect(statuses.append, Qt.ConnectionType.DirectConnection)
    task.start()
    assert task.wait(15000), "CodeWorker did not finish its sandbox child"
    app.processEvents()
    assert len(results) == 1 and statuses
    assert results[0].success, results[0]
    assert results[0].stdout.strip() == "9.0"
    for code in ("import socket", "open('must-not-exist', 'w')", "import subprocess"):
        result = executar_codigo(code, timeout=2)
        assert not result.success and "Security error" in result.stderr, result
    assert not Path("must-not-exist").exists()
    result = executar_codigo("print('x' * 2000)", max_output=64)
    assert result.success and len(result.stdout) == 64, result
    result = executar_codigo("print(1 / 0)")
    assert not result.success and "ZeroDivisionError" in result.stderr, result


def timeout():
    from workers.code_worker import executar_codigo

    before = time.monotonic()
    result = executar_codigo("while True:\n    pass", timeout=1)
    assert not result.success, result
    assert result.timed_out or result.returncode != 0
    assert time.monotonic() - before < 12, "Sandbox did not bound infinite-loop execution"
    assert not list(Path.cwd().glob("tmp*.py")), "Sandbox wrapper leaked"


def memory():
    from workers.windows_sandbox import WindowsSandboxConfig, executar_codigo_windows

    result = executar_codigo_windows(
        "print('started', flush=True)\nx = 'x' * (96 * 1024 * 1024)\nprint('allocation survived')",
        timeout=3,
        config=WindowsSandboxConfig(process_memory_limit_mb=48, job_memory_limit_mb=64),
    )
    assert "started" in result.stdout, result
    assert not result.success and not result.timed_out, result
    assert "allocation survived" not in result.stdout, result
    assert "MemoryError" in result.stderr or result.memory_exceeded, result


def job_limits():
    from workers import windows_sandbox as sandbox

    config = sandbox.WindowsSandboxConfig(
        cpu_time_limit_seconds=2, process_memory_limit_mb=48, job_memory_limit_mb=64
    )
    job = sandbox._create_job_object()
    try:
        sandbox._configure_job_limits(job, config)
        query = sandbox.kernel32.QueryInformationJobObject
        query.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        query.restype = ctypes.c_int
        data = ctypes.create_string_buffer(144)
        size = ctypes.c_ulong()
        assert query(job, 9, data, len(data), ctypes.byref(size)), ctypes.WinError()
        flags = struct.unpack_from("<I", data.raw, 16)[0]
        assert flags & sandbox.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        assert flags & sandbox.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        assert struct.unpack_from("<I", data.raw, 40)[0] == 1
        assert struct.unpack_from("<Q", data.raw, 112)[0] == 48 * 1024 * 1024
        assert struct.unpack_from("<Q", data.raw, 120)[0] == 64 * 1024 * 1024
        assert flags & sandbox.JOB_OBJECT_LIMIT_JOB_TIME, "Configured CPU time limit is not enabled"
        assert struct.unpack_from("<q", data.raw, 8)[0] == 2 * 10_000_000
    finally:
        sandbox.kernel32.CloseHandle(job)


def assignment_failure():
    import subprocess

    from workers import windows_sandbox as sandbox

    processes = []
    real_popen = subprocess.Popen

    def track_process(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    with (
        patch.object(sandbox.kernel32, "AssignProcessToJobObject", return_value=0),
        patch.object(sandbox.subprocess, "Popen", side_effect=track_process),
    ):
        result = sandbox.executar_codigo_windows("print('USER CODE REACHED')", timeout=2)
    assert len(processes) == 1
    assert not result.success and "Security error" in result.stderr, result
    process = processes[0]
    assert process.poll() is not None, "Uncontained child survived failed job assignment"
    assert process.stdout.read() == "", "User code ran before successful job assignment"
    process.stdin.close()
    process.stdout.close()
    process.stderr.close()
    assert not list(Path.cwd().glob("tmp*.py"))
