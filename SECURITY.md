# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it responsibly by emailing
celso@example.com or opening a GitHub issue with the `security` label.

## Sandbox Security

Celsius executes user-provided Python code in a sandboxed subprocess:

| Layer | Unix | Windows |
|-------|------|---------|
| **Import blocking** | AST analysis blocks `os`, `subprocess`, `ctypes`, etc. | Same |
| **Function blocking** | `eval`, `exec`, `__import__`, `open`, `input` | Same |
| **Attribute blocking** | `__globals__`, `__subclasses__`, `__code__`, etc. | Same |
| **CPU limit** | `resource.RLIMIT_CPU` | Win32 Job Object |
| **Memory limit** | `resource.RLIMIT_AS` (256MB) | Job Object (256MB) |
| **File size limit** | `resource.RLIMIT_FSIZE` (10MB) | Subprocess timeout |
| **Process limit** | `resource.RLIMIT_NOFILE` (64) | Job Object (4 procs) |
| **Privilege drop** | `setuid(nobody)` | Restricted env |
| **Network** | Minimal `PATH`, no API keys | Same |

## Known Limitations

- **Static analysis only**: AST validation cannot catch all runtime-only attacks
- **No seccomp**: Unix sandbox uses `resource` limits, not kernel-level syscall filtering
- **Windows**: Job Objects provide CPU/memory limits but no filesystem isolation
- **Importlib**: `importlib.import_module` is blocked, but creative string manipulation may bypass

## Supply Chain

- Dependencies pinned in `requirements.txt` (loose) and `requirements.in` (compiled)
- `pip-audit` runs weekly in CI (`.github/workflows/ci.yml`)
- `ruff` checks for security-related lint issues (S-rule subset)
- Security scan script: `python scripts/security_scan.py`
