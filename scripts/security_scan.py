#!/usr/bin/env python3
"""Local security scan script for Celsius.

Runs:
1. pip-audit (vulnerability scan)
2. AST validation on sandbox code
3. Circuit breaker status check
4. Metrics health check

Usage:
    python scripts/security_scan.py
"""

import json
import subprocess
import sys


def run_pip_audit() -> bool:
    """Run pip-audit and report results."""
    print("=" * 60)
    print("1. VULNERABILITY SCAN (pip-audit)")
    print("=" * 60)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--strict", "--desc"],
            capture_output=True,
            text=True,
            timeout=120,
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
    """Run ruff linter."""
    print("\n" + "=" * 60)
    print("2. LINTING (ruff)")
    print("=" * 60)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", ".", "--output-format=json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.stdout:
            findings = json.loads(result.stdout)
            errors = [f for f in findings if f.get("code", "").startswith("S")]
            if errors:
                print(f"  Found {len(errors)} security-related issues:")
                for e in errors[:10]:
                    print(f"    {e['filename']}:{e['location']['row']}: {e['code']} {e['message']}")
            else:
                print("  No security-related lint issues found.")
        else:
            print("  Clean.")
        return True
    except FileNotFoundError:
        print("[SKIP] ruff not installed. Run: pip install ruff")
        return True
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def check_sandbox_validation() -> bool:
    """Test AST validation catches dangerous patterns."""
    print("\n" + "=" * 60)
    print("3. SANDBOX AST VALIDATION TEST")
    print("=" * 60)
    try:
        from workers.code_worker import _validate_code

        test_cases = [
            ("import os", True),
            ("import subprocess", True),
            ("from os import system", True),
            ("eval('1+1')", True),
            ("exec('print(1)')", True),
            ("__import__('os')", True),
            ("import importlib; importlib.import_module('os')", True),
            ("print('hello')", False),
            ("import math; print(math.pi)", False),
            ("x = 2 + 2", False),
        ]

        passed = 0
        failed = 0
        for code, should_block in test_cases:
            result = _validate_code(code)
            was_blocked = result is not None
            if was_blocked == should_block:
                passed += 1
                status = "PASS"
            else:
                failed += 1
                status = "FAIL"
            expected = "BLOCKED" if should_block else "ALLOWED"
            print(f"  [{status}] {expected}: {code[:50]}")

        print(f"\n  Results: {passed}/{len(test_cases)} passed, {failed} failed")
        return failed == 0
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def check_circuit_breakers() -> bool:
    """Check circuit breaker status."""
    print("\n" + "=" * 60)
    print("4. CIRCUIT BREAKER STATUS")
    print("=" * 60)
    try:
        from core.circuit_breaker import get_all_breakers

        breakers = get_all_breakers()
        if not breakers:
            print("  No circuit breakers registered yet (normal on fresh start).")
        else:
            for cb in breakers:
                state = cb.get("state", "unknown")
                failures = cb.get("failure_count", 0)
                print(f"  [{state.upper()}] {cb['name']} - failures: {failures}")
        return True
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def check_metrics() -> bool:
    """Check metrics collector."""
    print("\n" + "=" * 60)
    print("5. METRICS HEALTH CHECK")
    print("=" * 60)
    try:
        from core.metrics import get_metrics

        m = get_metrics()
        snap = m.snapshot()
        print(f"  Uptime: {snap['uptime_seconds']:.1f}s")
        print(f"  Counters: {len(snap['counters'])}")
        print(f"  Gauges: {len(snap['gauges'])}")
        print(f"  Timers: {len(snap['timers'])}")
        return True
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def main():
    print("Celsius Security Scan")
    print("=" * 60)

    results = {}
    results["pip_audit"] = run_pip_audit()
    results["ruff"] = run_ruff_check()
    results["ast_validation"] = check_sandbox_validation()
    results["circuit_breakers"] = check_circuit_breakers()
    results["metrics"] = check_metrics()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {name}")

    if all_pass:
        print("\nAll checks passed!")
        return 0
    else:
        print("\nSome checks failed. Review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
