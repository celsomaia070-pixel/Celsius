#!/usr/bin/env python3
"""Run the local security checks used before a Celsius release."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Transitive dependency of llama-cpp-python. No fixed diskcache release exists.
# It is not used with untrusted cache paths in Celsius; remove when a patch ships.
TEMPORARY_AUDIT_EXCEPTIONS = (
    "PYSEC-2026-2447",
    # The affected Chroma HTTP server is never started or exposed by Celsius.
    "PYSEC-2026-311",
)


def run_pip_audit() -> bool:
    print("=" * 60)
    print("1. VULNERABILITY SCAN (pip-audit)")
    print("=" * 60)
    command = [
        sys.executable,
        "-m",
        "pip_audit",
        str(ROOT),
        "--locked",
        "--strict",
        "--desc",
    ]
    for vulnerability in TEMPORARY_AUDIT_EXCEPTIONS:
        command.extend(("--ignore-vuln", vulnerability))
    try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return result.returncode == 0
    except FileNotFoundError:
        print("[SKIP] pip-audit not installed. Run: pip install pip-audit")
        return True
    except subprocess.TimeoutExpired:
        print("[WARN] pip-audit timed out")
        return False


def run_ruff_check() -> bool:
    print("\n" + "=" * 60)
    print("2. LINTING (ruff)")
    print("=" * 60)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", ".", "--output-format=json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        findings = json.loads(result.stdout or "[]")
        errors = [item for item in findings if item.get("code", "").startswith("S")]
        if errors:
            print(f"  Found {len(errors)} security-related issues:")
            for error in errors[:10]:
                location = error["location"]
                print(
                    f"    {error['filename']}:{location['row']}: {error['code']} {error['message']}"
                )
            return False
        print("  No security-related lint issues found.")
        return True
    except (FileNotFoundError, json.JSONDecodeError) as error:
        print(f"[ERROR] {error}")
        return False


def check_sandbox_validation() -> bool:
    print("\n" + "=" * 60)
    print("3. SANDBOX AST VALIDATION TEST")
    print("=" * 60)
    try:
        from core.sandbox import validate_code

        test_cases = [
            ("import os", True),
            ("import subprocess", True),
            ("from os import system", True),
            ("eval('1+1')", True),
            ("exec('print(1)')", True),
            ("__import__('os')", True),
            ("getattr(__builtins__, 'pr' + 'int')('BYPASS')", True),
            ("import importlib; importlib.import_module('os')", True),
            ("print('hello')", False),
            ("import math; print(math.pi)", False),
            ("x = 2 + 2", False),
        ]
        failed = 0
        for code, should_block in test_cases:
            was_blocked = validate_code(code) is not None
            passed = was_blocked == should_block
            failed += int(not passed)
            expected = "BLOCKED" if should_block else "ALLOWED"
            print(f"  [{'PASS' if passed else 'FAIL'}] {expected}: {code[:50]}")
        print(f"\n  Results: {len(test_cases) - failed}/{len(test_cases)} passed")
        return failed == 0
    except Exception as error:
        print(f"  [ERROR] {error}")
        return False


def check_circuit_breakers() -> bool:
    print("\n" + "=" * 60)
    print("4. CIRCUIT BREAKER STATUS")
    print("=" * 60)
    try:
        from core.circuit_breaker import get_all_breakers

        breakers = get_all_breakers()
        if not breakers:
            print("  No circuit breakers registered yet (normal on fresh start).")
        for breaker in breakers:
            print(
                f"  [{breaker.get('state', 'unknown').upper()}] {breaker['name']} - "
                f"failures: {breaker.get('failure_count', 0)}"
            )
        return True
    except Exception as error:
        print(f"  [ERROR] {error}")
        return False


def check_metrics() -> bool:
    print("\n" + "=" * 60)
    print("5. METRICS HEALTH CHECK")
    print("=" * 60)
    try:
        from core.metrics import get_metrics

        snapshot = get_metrics().snapshot()
        print(f"  Uptime: {snapshot['uptime_seconds']:.1f}s")
        print(f"  Counters: {len(snapshot['counters'])}")
        print(f"  Gauges: {len(snapshot['gauges'])}")
        print(f"  Timers: {len(snapshot['timers'])}")
        return True
    except Exception as error:
        print(f"  [ERROR] {error}")
        return False


def main() -> int:
    print("Celsius Security Scan")
    print("=" * 60)
    results = {
        "pip_audit": run_pip_audit(),
        "ruff": run_ruff_check(),
        "ast_validation": check_sandbox_validation(),
        "circuit_breakers": check_circuit_breakers(),
        "metrics": check_metrics(),
    }
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    if all(results.values()):
        print("\nAll checks passed!")
        return 0
    print("\nSome checks failed. Review output above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
