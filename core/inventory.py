import json
import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from core.config import get_settings

logger = logging.getLogger(__name__)


class ColunaKanban(str, Enum):
    A_COMPRAR = "a_comprar"
    EM_ESTOQUE = "em_estoque"
    EM_USO = "em_uso"
    CRITICO = "critico"

    @property
    def label(self) -> str:
        labels = {
            ColunaKanban.A_COMPRAR: "A Comprar",
            ColunaKanban.EM_ESTOQUE: "Em Estoque",
            ColunaKanban.EM_USO: "Em Uso",
            ColunaKanban.CRITICO: "Estoque Minimo",
        }
        return labels[self]


@dataclass
class ItemEstoque:
    id: str
    nome: str
    categoria: str
    quantidade: int
    estoque_min: int
    estoque_max: int
    localizacao: str = ColunaKanban.EM_ESTOQUE.value
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    @property
    def coluna(self) -> ColunaKanban:
        return ColunaKanban(self.localizacao)

    @coluna.setter
    def coluna(self, value: ColunaKanban):
        self.localizacao = value.value

    def atualizar_coluna_automaticamente(self):
        if self.quantidade <= 0:
            self.coluna = ColunaKanban.A_COMPRAR
        elif self.quantidade <= self.estoque_min:
            self.coluna = ColunaKanban.CRITICO
        else:
            if self.coluna in (ColunaKanban.A_COMPRAR, ColunaKanban.CRITICO):
                self.coluna = ColunaKanban.EM_ESTOQUE

    @property
    def precisa_repor(self) -> bool:
        return self.quantidade <= self.estoque_min

    @property
    def estoque_normal(self) -> bool:
        return self.estoque_min < self.quantidade <= self.estoque_max

    @property
    def excedeu_max(self) -> bool:
        return self.quantidade > self.estoque_max

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ItemEstoque":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Movimentacao:
    id: str
    item_id: str
    item_nome: str
    tipo: str  # "entrada" ou "saida"
    quantidade: int
    quantidade_anterior: int
    quantidade_nova: int
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Movimentacao":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class InventoryService:
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._items: dict[str, ItemEstoque] = {}
        self._movimentacoes: list[Movimentacao] = []
        self._lock = threading.RLock()
        self._listeners: list = []
        self._load()

    def add_listener(self, callback):
        self._listeners.append(callback)

    def _notify(self, event: str, data=None):
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception as e:
                logger.warning("Listener error: %s", e)

    def _load(self):
        with self._lock:
            path = self.settings.inventory_file
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        raw = json.load(f)
                    items_raw = raw.get("items", [])
                    for item_data in items_raw:
                        item = ItemEstoque.from_dict(item_data)
                        self._items[item.id] = item
                    movs_raw = raw.get("movimentacoes", [])
                    for mov_data in movs_raw:
                        self._movimentacoes.append(Movimentacao.from_dict(mov_data))
                except Exception as e:
                    logger.error("Erro ao ler estoque: %s", e)
            else:
                self._items = {}
                self._movimentacoes = []

    def _save(self):
        try:
            path = self.settings.inventory_file
            data = {
                "items": [item.to_dict() for item in self._items.values()],
                "movimentacoes": [m.to_dict() for m in self._movimentacoes[-200:]],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Erro ao salvar estoque: %s", e)

    def get_all_items(self) -> list[ItemEstoque]:
        with self._lock:
            return list(self._items.values())

    def get_item(self, item_id: str) -> Optional[ItemEstoque]:
        with self._lock:
            return self._items.get(item_id)

    def get_items_por_coluna(self, coluna: ColunaKanban) -> list[ItemEstoque]:
        with self._lock:
            return [i for i in self._items.values() if i.coluna == coluna]

    def get_movimentacoes(self, item_id: str = None) -> list[Movimentacao]:
        with self._lock:
            if item_id:
                return [m for m in self._movimentacoes if m.item_id == item_id]
            return list(self._movimentacoes)

    def adicionar_item(
        self,
        nome: str,
        categoria: str,
        quantidade: int,
        estoque_min: int,
        estoque_max: int,
    ) -> ItemEstoque:
        with self._lock:
            item_id = str(uuid.uuid4())[:8]
            item = ItemEstoque(
                id=item_id,
                nome=nome,
                categoria=categoria,
                quantidade=quantidade,
                estoque_min=estoque_min,
                estoque_max=estoque_max,
            )
            item.atualizar_coluna_automaticamente()
            self._items[item_id] = item
            self._save()
            self._notify("item_adicionado", item)
            return item

    def remover_item(self, item_id: str) -> bool:
        with self._lock:
            if item_id in self._items:
                del self._items[item_id]
                self._save()
                self._notify("item_removido", item_id)
                return True
            return False

    def editar_item(
        self,
        item_id: str,
        nome: str = None,
        categoria: str = None,
        estoque_min: int = None,
        estoque_max: int = None,
    ) -> Optional[ItemEstoque]:
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                return None
            if nome is not None:
                item.nome = nome
            if categoria is not None:
                item.categoria = categoria
            if estoque_min is not item.estoque_min and estoque_min is not None:
                item.estoque_min = estoque_min
            if estoque_max is not item.estoque_max and estoque_max is not None:
                item.estoque_max = estoque_max
            item.updated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
            item.atualizar_coluna_automaticamente()
            self._save()
            self._notify("item_editado", item)
            return item

    def entrada(self, item_id: str, quantidade: int) -> Optional[Movimentacao]:
        with self._lock:
            item = self._items.get(item_id)
            if not item or quantidade <= 0:
                return None
            antiga = item.quantidade
            item.quantidade += quantidade
            item.updated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
            item.atualizar_coluna_automaticamente()
            mov = Movimentacao(
                id=str(uuid.uuid4())[:8],
                item_id=item_id,
                item_nome=item.nome,
                tipo="entrada",
                quantidade=quantidade,
                quantidade_anterior=antiga,
                quantidade_nova=item.quantidade,
            )
            self._movimentacoes.append(mov)
            self._save()
            self._notify("entrada", mov)
            return mov

    def saida(self, item_id: str, quantidade: int) -> Optional[Movimentacao]:
        with self._lock:
            item = self._items.get(item_id)
            if not item or quantidade <= 0 or quantidade > item.quantidade:
                return None
            antiga = item.quantidade
            item.quantidade -= quantidade
            item.updated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
            item.atualizar_coluna_automaticamente()
            mov = Movimentacao(
                id=str(uuid.uuid4())[:8],
                item_id=item_id,
                item_nome=item.nome,
                tipo="saida",
                quantidade=quantidade,
                quantidade_anterior=antiga,
                quantidade_nova=item.quantidade,
            )
            self._movimentacoes.append(mov)
            self._save()
            self._notify("saida", mov)
            if item.precisa_repor:
                self._notify("alerta_estoque_minimo", item)
            return mov

    def mover_item(self, item_id: str, nova_coluna: ColunaKanban) -> bool:
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                return False
            item.coluna = nova_coluna
            item.updated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
            self._save()
            self._notify("item_movido", item)
            return True

    def itens_estoque_baixo(self) -> list[ItemEstoque]:
        with self._lock:
            return [i for i in self._items.values() if i.precisa_repor]

    def buscar(self, query: str) -> list[ItemEstoque]:
        q = query.lower().strip()
        with self._lock:
            return [
                i
                for i in self._items.values()
                if q in i.nome.lower() or q in i.categoria.lower()
            ]


_inventory_service: Optional[InventoryService] = None


def get_inventory_service() -> InventoryService:
    global _inventory_service
    if _inventory_service is None:
        _inventory_service = InventoryService()
    return _inventory_service
