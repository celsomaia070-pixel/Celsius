#!/usr/bin/env python3
"""Release readiness checks that do not load an LLM."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_IMPORTS = (
    "PySide6",
    "cryptography",
    "edge_tts",
    "huggingface_hub",
    "llama_cpp",
    "matplotlib",
    "onnxruntime",
    "pydantic",
    "pydantic_settings",
    "pypdf",
    "rapidocr",
    "sentence_transformers",
)

REQUIRED_PROJECT_FILES = (
    "main.py",
    "celsius.spec",
    "installer/celsius.iss",
    "installer/runtime_llama_cpp.py",
    "logo/logo.ico",
    "logo/celsius-logo.svg",
    "core/settings.py",
    "core/config.py",
)


def _check(condition: bool, message: str, errors: list[str]) -> None:
    marker = "OK" if condition else "ERRO"
    print(f"[{marker}] {message}")
    if not condition:
        errors.append(message)


def run(flavor: str) -> int:
    errors: list[str] = []

    for relative in REQUIRED_PROJECT_FILES:
        path = ROOT / relative
        _check(path.is_file(), f"Arquivo obrigatorio: {relative}", errors)

    for module_name in REQUIRED_IMPORTS:
        _check(
            importlib.util.find_spec(module_name) is not None,
            f"Dependencia importavel: {module_name}",
            errors,
        )

    llama_spec = importlib.util.find_spec("llama_cpp")
    llama_lib_dir = (
        Path(next(iter(llama_spec.submodule_search_locations))) / "lib"
        if llama_spec is not None and llama_spec.submodule_search_locations
        else None
    )
    for library_name in ("llama.dll", "mtmd.dll"):
        _check(
            llama_lib_dir is not None and (llama_lib_dir / library_name).is_file(),
            f"Biblioteca nativa do llama_cpp: {library_name}",
            errors,
        )

    from core.config import get_model_by_id
    from core.settings import get_settings

    settings = get_settings()
    model = get_model_by_id(settings.model.llm_model)
    _check(model is not None, f"Modelo registrado: {settings.model.llm_model}", errors)

    if flavor == "offline" and model is not None:
        _check(
            (ROOT / "resources" / model.filename).is_file(),
            f"Modelo offline presente: {model.filename}",
            errors,
        )
        if model.has_mmproj:
            _check(
                (ROOT / "resources" / model.mmproj_file).is_file(),
                f"Projetor visual presente: {model.mmproj_file}",
                errors,
            )

    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=settings.data_dir, delete=True):
            pass
        writable = True
    except OSError:
        writable = False
    _check(writable, f"Diretorio de dados gravavel: {settings.data_dir}", errors)

    spec_text = (ROOT / "celsius.spec").read_text(encoding="utf-8")
    _check(
        '"llama_cpp/lib"' in spec_text,
        "Spec preserva as bibliotecas nativas em llama_cpp/lib",
        errors,
    )
    _check(
        "runtime_llama_cpp.py" in spec_text,
        "Spec configura o caminho nativo do llama_cpp no executavel",
        errors,
    )
    forbidden_data = ("inventory.json", "memorias.json", "chroma_db")
    for forbidden in forbidden_data:
        _check(
            forbidden not in spec_text,
            f"Dados pessoais nao incluidos no spec: {forbidden}",
            errors,
        )

    license_text = (ROOT / "core" / "license.py").read_text(encoding="utf-8")
    _check(
        "_EMBEDDED_PRIVATE_KEY_PEM" not in license_text,
        "Nenhuma chave privada incorporada ao aplicativo",
        errors,
    )

    result = {
        "ok": not errors,
        "flavor": flavor,
        "errors": errors,
        "data_dir": str(settings.data_dir),
        "model": settings.model.llm_model,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--flavor", choices=("thin", "offline"), default="thin")
    args = parser.parse_args()
    return run(args.flavor)


if __name__ == "__main__":
    raise SystemExit(main())
