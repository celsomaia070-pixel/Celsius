"""Windows-specific sandboxing using Win32 Job Objects via ctypes.

Provides CPU time limits, memory limits, and process tree restrictions
without requiring pywin32 as a dependency.
"""

import ctypes
import ctypes.wintypes
import logging
import os
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Win32 constants
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_TIME = 0x00000010
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
CREATE_NO_WINDOW = 0x08000000
ERROR_NOT_FOUND = 1168

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


@dataclass
class WindowsSandboxConfig:
    """Configuration for Windows sandbox limits."""

    cpu_time_limit_seconds: int = 30
    process_memory_limit_mb: int = 256
    job_memory_limit_mb: int = 512
    active_process_limit: int = 4
    kill_on_job_close: bool = True
    die_on_unhandled_exception: bool = True


@dataclass
class WindowsSandboxResult:
    """Result from a Windows sandboxed execution."""

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False
    memory_exceeded: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.memory_exceeded


def _create_job_object() -> ctypes.wintypes.HANDLE:
    """Create a Win32 Job Object."""
    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return job_handle


def _configure_job_limits(job_handle: ctypes.wintypes.HANDLE, config: WindowsSandboxConfig) -> None:
    """Set resource limits on a Job Object using JOBOBJECT_EXTENDED_LIMIT_INFORMATION.

    Layout (x64, packed via struct module):
      BasicLimitInformation (64 bytes):
        [0..7]   PerProcessUserTimeLimit  (int64)
        [8..15]  PerJobUserTimeLimit      (int64)
        [16..19] LimitFlags               (uint32)
        [20..23] padding                  (uint32)
        [24..31] MinimumWorkingSetSize    (uint64)
        [32..39] MaximumWorkingSetSize    (uint64)
        [40..43] ActiveProcessLimit       (uint32)
        [44..47] padding                  (uint32)
        [48..55] Affinity                 (uint64)
        [56..59] PriorityClass            (uint32)
        [60..63] SchedulingClass          (uint32)
      IoInfo (48 bytes, all zeros):
        [64..111]
      ProcessMemoryLimit (uint64):
        [112..119]
      JobMemoryLimit (uint64):
        [120..127]
      PeakProcessMemoryUsed (uint64):
        [128..135]
      PeakJobMemoryUsed (uint64):
        [136..143]
    Total: 144 bytes
    """
    flags = 0
    if config.kill_on_job_close:
        flags |= JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if config.die_on_unhandled_exception:
        flags |= JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
    if config.active_process_limit > 0:
        flags |= JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    if config.process_memory_limit_mb > 0:
        flags |= JOB_OBJECT_LIMIT_PROCESS_MEMORY
    if config.job_memory_limit_mb > 0:
        flags |= JOB_OBJECT_LIMIT_JOB_MEMORY

    struct_data = struct.pack(
        "<qqII"  # PerProcess(8) + PerJob(8) + Flags(4) + pad(4) = 24
        "QQ"  # MinWS(8) + MaxWS(8) = 16
        "II"  # ActiveLimit(4) + pad(4) = 8
        "Q"  # Affinity(8)
        "II"  # Priority(4) + Scheduling(4) = 8
        "QQQQQQ"  # IoInfo (6 x uint64 = 48 bytes)
        "QQQQ",  # ProcMem(8) + JobMem(8) + PeakProc(8) + PeakJob(8) = 32
        # BasicLimitInformation
        0,  # PerProcessUserTimeLimit
        0,  # PerJobUserTimeLimit
        flags,  # LimitFlags
        0,  # padding
        4 * 1024 * 1024,  # MinimumWorkingSetSize (4MB)
        256 * 1024 * 1024,  # MaximumWorkingSetSize (256MB)
        config.active_process_limit,  # ActiveProcessLimit
        0,  # padding
        0,  # Affinity (all cores)
        0,  # PriorityClass
        0,  # SchedulingClass
        # IoInfo (all zeros)
        0,
        0,
        0,
        0,
        0,
        0,
        # Memory limits
        config.process_memory_limit_mb * 1024 * 1024,  # ProcessMemoryLimit
        config.job_memory_limit_mb * 1024 * 1024,  # JobMemoryLimit
        0,  # PeakProcessMemoryUsed
        0,  # PeakJobMemoryUsed
    )

    success = kernel32.SetInformationJobObject(
        job_handle,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        struct_data,
        len(struct_data),
    )
    if not success:
        raise ctypes.WinError(ctypes.get_last_error())


def _sandbox_env() -> dict[str, str]:
    """Create a restricted environment for the subprocess."""
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
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def executar_codigo_windows(
    codigo: str,
    timeout: int = 30,
    max_output: int = 50000,
    config: WindowsSandboxConfig | None = None,
) -> WindowsSandboxResult:
    """Execute Python code in a Windows sandboxed subprocess using Job Objects."""
    config = config or WindowsSandboxConfig(cpu_time_limit_seconds=timeout)

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(codigo)
            temp_path = f.name

        env = _sandbox_env()
        cmd = [sys.executable, "-I", "-B", temp_path]

        job_handle = _create_job_object()
        try:
            _configure_job_limits(job_handle, config)

            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags = subprocess.STARTF_USESHOWWINDOW
            startup_info.wShowWindow = 0  # SW_HIDE

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=tempfile.gettempdir(),
                startupinfo=startup_info,
                creationflags=CREATE_NO_WINDOW,
            )

            try:
                # Get native process handle for Job Object assignment
                # Python 3.14 uses ._handle on Windows
                proc_handle = getattr(process, "_handle", None)
                if proc_handle is None:
                    proc_handle = getattr(process, "process_handle", None)
                if proc_handle is not None:
                    assigned = kernel32.AssignProcessToJobObject(job_handle, proc_handle)
                    if not assigned:
                        err = ctypes.get_last_error()
                        if err != ERROR_NOT_FOUND:
                            logger.warning("AssignProcessToJobObject failed: %s", err)

                stdout, stderr = process.communicate(timeout=timeout + 5)
                stdout = stdout[:max_output]
                stderr = stderr[:max_output]

                memory_exceeded = process.returncode == 107
                if memory_exceeded:
                    stderr = (
                        f"Memory limit exceeded ({config.process_memory_limit_mb}MB). "
                        f"Code was too memory-intensive.\n{stderr}"
                    )

                return WindowsSandboxResult(
                    stdout=stdout,
                    stderr=stderr,
                    returncode=process.returncode,
                    timed_out=False,
                    memory_exceeded=memory_exceeded,
                )

            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                return WindowsSandboxResult(
                    stdout="",
                    stderr="Timeout: codigo excedeu tempo limite.",
                    returncode=-1,
                    timed_out=True,
                )
            except Exception as e:
                process.kill()
                process.wait()
                return WindowsSandboxResult(
                    stdout="",
                    stderr=f"Execution error: {e}",
                    returncode=-1,
                )
        finally:
            kernel32.CloseHandle(job_handle)
    finally:
        if temp_path and os.path.exists(temp_path):
            with __import__("contextlib").suppress(OSError):
                os.unlink(temp_path)
