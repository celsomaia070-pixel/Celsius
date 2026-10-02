"""Local office-format conversion for Celsius document tools."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from core.file_validation import validate_file_content


def _office_executable() -> Path:
    candidates = [shutil.which("soffice")]
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = os.environ.get(variable)
        if root:
            candidates.append(str(Path(root) / "LibreOffice/program/soffice.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise ValueError(
        "O modelo esta em ODT. Para gerar DOCX com sua estrutura, instale o LibreOffice "
        "ou envie uma copia do modelo salva como DOCX. Nenhum documento foi preenchido."
    )


@contextmanager
def docx_template(source: str | Path):
    """Yield an existing DOCX or an isolated converted copy; preserve the source."""
    original = Path(source).resolve()
    if original.suffix.lower() != ".odt":
        yield original
        return
    validate_file_content(original.name, original.read_bytes())
    executable = _office_executable()
    with tempfile.TemporaryDirectory(prefix="celsius-odt-") as temporary:
        root = Path(temporary)
        incoming = root / "modelo.odt"
        shutil.copyfile(original, incoming)
        output_dir = root / "converted"
        output_dir.mkdir()
        profile = (root / "profile").as_uri()
        try:
            result = subprocess.run(
                [
                    str(executable),
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--nologo",
                    "--nodefault",
                    "--nofirststartwizard",
                    "--norestore",
                    "--convert-to",
                    "docx:Office Open XML Text",
                    "--outdir",
                    str(output_dir),
                    str(incoming),
                ],
                capture_output=True,
                timeout=60,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                "A conversao do ODT excedeu o tempo limite; envie o modelo em DOCX."
            ) from exc
        converted = output_dir / "modelo.docx"
        if result.returncode != 0 or not converted.is_file():
            raise ValueError(
                "Nao foi possivel converter o modelo ODT para DOCX. Nenhum original foi alterado."
            )
        validate_file_content(converted.name, converted.read_bytes())
        yield converted
