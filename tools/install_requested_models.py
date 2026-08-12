"""Install the larger local GGUF models requested for Celsius.

Run from the project root:
    python tools/install_requested_models.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUESTED_MODEL_IDS = [
    "qwen2.5-vl-7b-q6k",
    "qwen2.5-omni-7b-q4km",
    "deepseek-r1-distill-qwen-7b-q4km",
]


def _status(message: str) -> None:
    print(message, flush=True)


def _local_path(model_id: str) -> Path:
    from core.config import get_model_by_id
    from core.settings import get_settings

    settings = get_settings()
    model = get_model_by_id(model_id)
    if model is None:
        raise ValueError(f"Modelo nao encontrado no catalogo: {model_id}")
    return settings.get_resources_dir() / model.filename


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Baixa modelos GGUF registrados no catalogo do Celsius."
    )
    parser.add_argument(
        "model_ids",
        nargs="*",
        help="IDs dos modelos. Sem argumentos, instala a lista recomendada.",
    )
    return parser.parse_args()


def main() -> int:
    from core.config import get_model_by_id
    from core.model_downloader import download_mmproj, download_model
    from core.settings import get_settings

    args = _parse_args()
    requested_model_ids = args.model_ids or REQUESTED_MODEL_IDS
    settings = get_settings()
    settings.get_resources_dir().mkdir(parents=True, exist_ok=True)

    _status(f"Pasta de modelos: {settings.get_resources_dir()}")
    _status("Modelos solicitados:")
    for model_id in requested_model_ids:
        model = get_model_by_id(model_id)
        if model is None:
            _status(f"- {model_id}: nao encontrado no catalogo")
            return 1
        exists = "ja instalado" if _local_path(model_id).exists() else "pendente"
        _status(f"- {model.name} {model.quant} ({model.size_gb} GB): {exists}")

    _status("")
    for model_id in requested_model_ids:
        model = get_model_by_id(model_id)
        assert model is not None
        local_file = _local_path(model_id)
        if local_file.exists():
            _status(f"Pulando {local_file.name}: arquivo ja existe.")
        else:
            _status(f"Baixando {model.name} {model.quant}...")
            downloaded = download_model(model_id, fn_status=_status)
            if downloaded is None:
                _status(f"Falha ao baixar {model.name}.")
                return 1

        if model.has_mmproj:
            mmproj = settings.get_resources_dir() / model.mmproj_file
            if mmproj.exists():
                _status(f"Pulando {mmproj.name}: mmproj ja existe.")
            else:
                downloaded_mmproj = download_mmproj(model_id, fn_status=_status)
                if downloaded_mmproj is None:
                    _status(f"Aviso: nao foi possivel baixar o mmproj de {model.name}.")

    _status("")
    _status("Instalacao concluida. Reinicie o Celsius para atualizar o seletor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
