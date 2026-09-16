"""Each case executes real production imports in a clean, bounded subprocess."""

import sys

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "case",
    [
        "llama.imports",
        "llama.lifecycle",
        "llama.stream_close",
        "llama.stream_error",
        "llama.missing_model",
        "llama.integrity",
        "server.lifecycle",
        "server.restart",
        "tts.playback",
        "tts.streaming",
        "tts.provider_error",
        "tts.disabled",
        "tts.cancel",
    ],
)
def test_native_case(run_native, case):
    run_native(case)


@pytest.mark.skipif(sys.platform != "win32", reason="requires actual Win32 Job Objects/DLLs")
@pytest.mark.parametrize(
    "case",
    [
        "windows.dlls",
        "windows.worker",
        "windows.timeout",
        "windows.memory",
        "windows.job_limits",
        "windows.assignment_failure",
    ],
)
def test_windows_native_case(run_native, case):
    run_native(case)


def test_local_model_generation(run_native, pytestconfig):
    path = pytestconfig.getoption("--local-model-path")
    if not path:
        pytest.fail(
            "--run-local-model requires --local-model-path pointing to an existing text GGUF"
        )
    run_native("llama.generation", model_path=path, timeout=300)
