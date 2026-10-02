"""Runner for golden-set tests in a fresh process to avoid conftest.py mocks."""

import subprocess
import sys


def run_golden_set_tests() -> int:
    """Run golden-set tests in a fresh subprocess."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_golden_set.py",
            "-q",
            "--tb=short",
        ],
        cwd="E:/PythonProjectCELSIUS",
        capture_output=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(run_golden_set_tests())
