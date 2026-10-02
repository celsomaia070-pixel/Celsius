"""Helpers para respostas interrompidas pelo usuario."""

from __future__ import annotations

INTERRUPTED_MARKER = "_(resposta interrompida pelo usuario)_"


def marcar_interrompida(texto: str, *, marca: str = INTERRUPTED_MARKER) -> str:
    """Devolve o trecho parcial com a marca de interrupcao, sem duplicar."""
    limpo = (texto or "").strip()
    if not limpo:
        return marca
    if limpo.endswith(marca):
        return limpo
    return f"{limpo}\n\n{marca}"
