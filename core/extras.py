"""Probe helpers for the optional feature extras declared in pyproject.toml.

The base ``pip install celsius`` keeps the runtime lean. Features such as
document parsing, OCR, voice, web/mobile access and the Docker sandbox backend
live behind ``[project.optional-dependencies]`` groups and import their heavy
dependencies lazily. These helpers let the UI expose clear install hints when a
feature is selected but its extra is not installed.
"""

from __future__ import annotations

from importlib.util import find_spec

#: Representative import modules for each extra group. A group is considered
#: available when every probe module resolves (packages are imported lazily,
#: so resolving the module is enough to confirm the extra is installed).
EXTRA_PROBES: dict[str, tuple[str, ...]] = {
    "docker": ("docker",),
    "documents": ("pypdf", "pdfplumber", "pypdfium2", "rapidocr", "docx", "PIL", "odf", "fpdf"),
    "voice": ("whisper", "faster_whisper", "speech_recognition", "sounddevice", "pygame", "pydub"),
    "web": (
        "playwright",
        "duckduckgo_search",
        "feedparser",
        "qrcode",
        "cryptography",
        "fastapi",
        "uvicorn",
        "jwt",
        "passlib",
    ),
}

INSTALL_HINTS: dict[str, str] = {
    "docker": "pip install celsius[docker]",
    "documents": "pip install celsius[documents]",
    "voice": "pip install celsius[voice]",
    "web": "pip install celsius[web]",
    "all": "pip install celsius[all]",
}


def missing_modules(extra: str) -> tuple[str, ...]:
    """Return the probe modules of ``extra`` that cannot be imported."""
    probes = EXTRA_PROBES.get(extra)
    if probes is None:
        return ()
    missing = []
    for module in probes:
        try:
            if find_spec(module) is None:
                missing.append(module)
        except (ValueError, ImportError):
            missing.append(module)
    return tuple(missing)


def is_extra_available(extra: str) -> bool:
    """True when ``extra`` is installed (all probe modules resolve)."""
    return extra in EXTRA_PROBES and not missing_modules(extra)


def install_hint(extra: str) -> str:
    """Human-readable command to install ``extra`` when it is missing."""
    return INSTALL_HINTS.get(extra, f"pip install celsius[{extra}]")
