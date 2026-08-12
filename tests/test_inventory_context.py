"""Tests for inventory service and tools."""

from __future__ import annotations

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


class FakeItem:
    def __init__(
        self,
        nome,
        categoria,
        quantidade,
        item_id,
        localizacao="em_estoque",
        estoque_min=2,
        estoque_max=20,
    ):
        self.id = item_id
        self.nome = nome
        self.categoria = categoria
        self.quantidade = quantidade
        self.estoque_min = estoque_min
        self.estoque_max = estoque_max
        self.localizacao = localizacao

    @property
    def precisa_repor(self):
        return self.quantidade <= self.estoque_min


class FakeMovimentacao:
    def __init__(self, item_nome, quantidade, quantidade_anterior, quantidade_nova):
        self.item_nome = item_nome
        self.quantidade = quantidade
        self.quantidade_anterior = quantidade_anterior
        self.quantidade_nova = quantidade_nova


class FakeInventoryService:
    def __init__(self, items):
        self._items = {item.id: item for item in items}

    def get_all_items(self):
        return list(self._items.values())

    def get_item(self, item_id):
        return self._items.get(item_id)

    def buscar(self, query):
        q = query.lower().strip()
        return [i for i in self._items.values() if q in i.nome.lower() or q in i.categoria.lower()]

    def itens_estoque_baixo(self):
        return [i for i in self._items.values() if i.precisa_repor]

    def entrada(self, item_id, quantidade):
        item = self._items.get(item_id)
        if not item or quantidade <= 0:
            return None
        antiga = item.quantidade
        item.quantidade += quantidade
        return FakeMovimentacao(item.nome, quantidade, antiga, item.quantidade)

    def saida(self, item_id, quantidade):
        item = self._items.get(item_id)
        if not item or quantidade <= 0 or quantidade > item.quantidade:
            return None
        antiga = item.quantidade
        item.quantidade -= quantidade
        return FakeMovimentacao(item.nome, quantidade, antiga, item.quantidade)

    def adicionar_item(self, nome, categoria, quantidade, estoque_min, estoque_max):
        new_id = f"new_{len(self._items)}"
        item = FakeItem(
            nome, categoria, quantidade, new_id, estoque_min=estoque_min, estoque_max=estoque_max
        )
        self._items[item.id] = item
        return item


@pytest.fixture
def fake_inventory(monkeypatch):
    items = [
        FakeItem("Parafuso M8", "Produtos", 50, item_id="p1"),
        FakeItem("Martelo", "Ferramentas", 3, item_id="m1"),
        FakeItem("Oleo 20W50", "Insumos", 1, item_id="o1", localizacao="critico"),
    ]
    service = FakeInventoryService(items)
    module = SimpleNamespace(
        ColunaKanban=FakeColunaKanban,
        get_inventory_service=lambda: service,
    )
    monkeypatch.setitem(sys.modules, "core.inventory", module)
    return service


class TestInventoryTools:
    def test_listar_estoque_returns_all_items(self, fake_inventory):
        from ai.tools import _tool_listar_estoque

        result = _tool_listar_estoque()
        assert "Parafuso M8" in result
        assert "Martelo" in result
        assert "Oleo 20W50" in result

    def test_buscar_item_estoque_by_name(self, fake_inventory):
        from ai.tools import _tool_buscar_item_estoque

        result = _tool_buscar_item_estoque("parafuso")
        assert "Parafuso M8" in result
        assert "Martelo" not in result

    def test_entrada_estoque_increases_quantity(self, fake_inventory):
        from ai.tools import _tool_entrada_estoque

        result = _tool_entrada_estoque("p1", 10)
        assert "60" in result  # 50 + 10
        assert fake_inventory.get_item("p1").quantidade == 60

    def test_saida_estoque_decreases_quantity(self, fake_inventory):
        from ai.tools import _tool_saida_estoque

        result = _tool_saida_estoque("p1", 5)
        assert "45" in result  # 50 - 5
        assert fake_inventory.get_item("p1").quantidade == 45

    def test_itens_estoque_baixo_returns_critical(self, fake_inventory):
        from ai.tools import _tool_itens_estoque_baixo

        result = _tool_itens_estoque_baixo()
        assert "Oleo 20W50" in result
        assert "Parafuso M8" not in result
