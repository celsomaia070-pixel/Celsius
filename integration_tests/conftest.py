"""Opt-in native smoke suite, intentionally separate from tests/conftest.py."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def pytest_addoption(parser):
    group = parser.getgroup("native smoke")
    group.addoption("--run-native-smoke", action="store_true", default=False)
    group.addoption("--run-local-model", action="store_true", default=False)
    group.addoption(
        "--local-model-path", default=None, help="Existing text-only GGUF; never downloaded"
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        if Path(__file__).parent not in Path(item.path).parents:
            continue
        if not config.getoption("--run-native-smoke"):
            item.add_marker(pytest.mark.skip(reason="opt in with --run-native-smoke"))
        elif item.name == "test_local_model_generation" and not config.getoption(
            "--run-local-model"
        ):
            item.add_marker(
                pytest.mark.skip(reason="also requires --run-local-model and --local-model-path")
            )


@pytest.fixture
def run_native(tmp_path):
    def run(case, *, model_path=None, timeout=60):
        # Do not inherit application credentials, data locations, proxies or Qt overrides.
        keep = {"SYSTEMROOT", "WINDIR", "PATH", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS"}
        env = {key: value for key, value in os.environ.items() if key.upper() in keep}
        env.update(
            {
                "TEMP": str(tmp_path),
                "TMP": str(tmp_path),
                "TMPDIR": str(tmp_path),
                "HOME": str(tmp_path),
                "USERPROFILE": str(tmp_path),
                "APPDATA": str(tmp_path),
                "LOCALAPPDATA": str(tmp_path),
                "QT_QPA_PLATFORM": "offscreen",
                "SDL_AUDIODRIVER": "dummy",
                "SDL_VIDEODRIVER": "dummy",
                "PYGAME_HIDE_SUPPORT_PROMPT": "1",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HOME": str(tmp_path / "hf"),
                "NO_PROXY": "*",
                "CELSIUS_ENVIRONMENT": "test",
                "CELSIUS_BASE_DIR": str(tmp_path),
                "CELSIUS_DATA_DIR": str(tmp_path / "data"),
                "CELSIUS_LOGS_DIR": str(tmp_path / "logs"),
                "CELSIUS_RESOURCES_DIR": str(tmp_path / "resources"),
                "CELSIUS_TELEMETRY_ENABLED": "false",
                "CELSIUS_MOBILE_ENABLED": "false",
                "CELSIUS_MOBILE_PAIRING_TOKEN": "native-smoke-token-not-a-real-secret",
            }
        )
        for field, filename in {
            "MEMORIAS_FILE": "memorias.json",
            "CHATS_FILE": "chats.json",
            "INVENTORY_FILE": "inventory.json",
            "AUDIO_TEMP_FILE": "voice.mp3",
            "AUDIO_MIC_FILE": "unused-mic.wav",
        }.items():
            env[f"CELSIUS_{field}"] = str(tmp_path / filename)
        command = [sys.executable, "-I", "-B", str(Path(__file__).with_name("_runner.py")), case]
        if model_path:
            command.append(str(Path(model_path).resolve()))
        try:
            result = subprocess.run(
                command,
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            pytest.fail(f"Native case {case} exceeded {timeout}s: {exc.stdout!r}\n{exc.stderr!r}")
        assert result.returncode == 0, (
            f"Native case {case} exited {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert f"PASS {case}" in result.stdout, result.stdout
        print(result.stdout.strip())
        return result

    return run
