"""Tests for inventory context visibility in AI responses."""

import sys
from enum import Enum
from types import SimpleNamespace

import pytest


class FakeColunaKanban(str, Enum):
    A_COMPRAR = "a_comprar"
    EM_ESTOQUE = "em_estoque"
    EM_USO = "em_uso"
    CRITICO = "critico"

    @property
    def label(self) -> str:
        return {
            FakeColunaKanban.A_COMPRAR: "A Comprar",
            FakeColunaKanban.EM_ESTOQUE: "Em Estoque",
            FakeColunaKanban.EM_USO: "Em Uso",
            FakeColunaKanban.CRITICO: "Estoque Minimo",
        }[self]


class FakeInventoryService:
    def __init__(self, items):
        self._items = items

    def get_all_items(self):
        return list(self._items)


def _item(
    nome: str,
    categoria: str,
    quantidade: int,
    *,
    item_id: str,
    localizacao: str = "em_estoque",
    estoque_min: int = 2,
    estoque_max: int = 20,
):
    return SimpleNamespace(
        id=item_id,
        nome=nome,
        categoria=categoria,
        quantidade=quantidade,
        estoque_min=estoque_min,
        estoque_max=estoque_max,
        localizacao=localizacao,
        precisa_repor=quantidade <= estoque_min,
    )


@pytest.fixture
def fake_inventory(monkeypatch):
    items = [
        _item("Parafuso M8", "Produtos", 50, item_id="p1"),
        _item("Martelo", "Ferramentas", 3, item_id="m1"),
        _item("Oleo 20W50", "Insumos", 1, item_id="o1", localizacao="critico"),
    ]
    module = SimpleNamespace(
        ColunaKanban=FakeColunaKanban,
        get_inventory_service=lambda: FakeInventoryService(items),
    )
    monkeypatch.setitem(sys.modules, "core.inventory", module)
    return items


class TestInventoryContext:
    def test_general_product_question_keeps_full_inventory(self, fake_inventory):
        from ai.engine import _obter_contexto_estoque

        context = _obter_contexto_estoque("quais produtos tenho no meu estoque?")

        assert "Dados do estoque do usuario (3 itens" in context
        assert "Parafuso M8" in context
        assert "Martelo" in context
        assert "Oleo 20W50" in context
        assert "itens encontrados" not in context

    def test_direct_inventory_list_response_includes_all_items(self, fake_inventory):
        from ai.engine import _responder_lista_estoque_direta

        response = _responder_lista_estoque_direta("listar meu estoque completo")

        assert "Estoque completo: 3 item" in response
        assert "Parafuso M8" in response
        assert "Martelo" in response
        assert "Oleo 20W50" in response

    def test_specific_inventory_question_still_filters_by_item_name(self, fake_inventory):
        from ai.engine import _obter_contexto_estoque

        context = _obter_contexto_estoque("quanto de parafuso tenho?")

        assert "Dados do estoque (itens encontrados)" in context
        assert "Parafuso M8" in context
        assert "Martelo" not in context
