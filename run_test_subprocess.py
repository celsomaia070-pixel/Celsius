import subprocess
import sys

result = subprocess.run(
    [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_golden_set.py::test_semantic_layer_is_not_silently_inert",
        "-v",
        "-s",
    ],
    capture_output=True,
    text=True,
    timeout=300,
)

print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print("Return code:", result.returncode)
