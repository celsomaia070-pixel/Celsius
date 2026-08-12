import logging
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from core.json_persistence import atomic_write_json, locked_path, read_json
from core.settings import get_settings

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


class StockStatus(str, Enum):
    """Stock health derived from quantity thresholds, never persisted."""

    SEM_ESTOQUE = "sem_estoque"
    CRITICO = "critico"
    NORMAL = "normal"
    EXCESSO = "excesso"

    @property
    def label(self) -> str:
        return {
            StockStatus.SEM_ESTOQUE: "Sem Estoque",
            StockStatus.CRITICO: "Critico",
            StockStatus.NORMAL: "Normal",
            StockStatus.EXCESSO: "Excesso",
        }[self]


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
    def stock_status(self) -> StockStatus:
        if self.quantidade <= 0:
            return StockStatus.SEM_ESTOQUE
        if self.quantidade <= self.estoque_min:
            return StockStatus.CRITICO
        if self.estoque_max > 0 and self.quantidade > self.estoque_max:
            return StockStatus.EXCESSO
        return StockStatus.NORMAL

    @property
    def estoque_normal(self) -> bool:
        return self.stock_status == StockStatus.NORMAL

    @property
    def excedeu_max(self) -> bool:
        return self.stock_status == StockStatus.EXCESSO

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
    def __init__(self, settings=None, data_file: Path | None = None):
        self.settings = settings or get_settings()
        self.data_file = Path(data_file) if data_file else self.settings.inventory_file
        self._items: dict[str, ItemEstoque] = {}
        self._movimentacoes: list[Movimentacao] = []
        self._lock = threading.RLock()
        self._listeners: list = []
        self._file_signature: tuple[int, int] | None = None
        self._load_error: Exception | None = None
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
        with self._lock, locked_path(self.data_file):
            self._load_unlocked()

    def _load_unlocked(self):
        self._items = {}
        self._movimentacoes = []
        self._load_error = None
        try:
            raw = read_json(self.data_file, {"items": [], "movimentacoes": []})
            for item_data in raw.get("items", []):
                item = ItemEstoque.from_dict(item_data)
                self._items[item.id] = item
            for mov_data in raw.get("movimentacoes", []):
                self._movimentacoes.append(Movimentacao.from_dict(mov_data))
            self._file_signature = self._signature()
        except Exception as error:
            self._load_error = error
            logger.error("Erro ao ler estoque: %s", error)

    def _signature(self) -> tuple[int, int] | None:
        try:
            stat = self.data_file.stat()
            return stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return None

    def _refresh_if_changed(self):
        if self._signature() == self._file_signature:
            return
        with locked_path(self.data_file):
            if self._signature() != self._file_signature:
                self._load_unlocked()

    def _save_unlocked(self):
        if self._load_error is not None:
            raise RuntimeError(
                "O estoque nao foi salvo porque o arquivo existente esta invalido."
            ) from self._load_error
        data = {
            "items": [item.to_dict() for item in self._items.values()],
            "movimentacoes": [m.to_dict() for m in self._movimentacoes[-200:]],
        }
        atomic_write_json(self.data_file, data)
        self._file_signature = self._signature()

    def get_all_items(self) -> list[ItemEstoque]:
        with self._lock:
            self._refresh_if_changed()
            return list(self._items.values())

    def get_item(self, item_id: str) -> ItemEstoque | None:
        with self._lock:
            self._refresh_if_changed()
            return self._items.get(item_id)

    def get_items_por_coluna(self, coluna: ColunaKanban) -> list[ItemEstoque]:
        with self._lock:
            self._refresh_if_changed()
            return [i for i in self._items.values() if i.coluna == coluna]

    def get_movimentacoes(self, item_id: str = None) -> list[Movimentacao]:
        with self._lock:
            self._refresh_if_changed()
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
        with self._lock, locked_path(self.data_file):
            self._load_unlocked()
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
            self._save_unlocked()
            self._notify("item_adicionado", item)
            return item

    def remover_item(self, item_id: str) -> bool:
        with self._lock, locked_path(self.data_file):
            self._load_unlocked()
            if item_id in self._items:
                del self._items[item_id]
                self._save_unlocked()
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
    ) -> ItemEstoque | None:
        with self._lock, locked_path(self.data_file):
            self._load_unlocked()
            item = self._items.get(item_id)
            if not item:
                return None
            if nome is not None:
                item.nome = nome
            if categoria is not None:
                item.categoria = categoria
            if estoque_min is not None and estoque_min != item.estoque_min:
                item.estoque_min = estoque_min
            if estoque_max is not None and estoque_max != item.estoque_max:
                item.estoque_max = estoque_max
            item.updated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
            item.atualizar_coluna_automaticamente()
            self._save_unlocked()
            self._notify("item_editado", item)
            return item

    def entrada(self, item_id: str, quantidade: int) -> Movimentacao | None:
        with self._lock, locked_path(self.data_file):
            self._load_unlocked()
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
            self._save_unlocked()
            self._notify("entrada", mov)
            return mov

    def saida(self, item_id: str, quantidade: int) -> Movimentacao | None:
        with self._lock, locked_path(self.data_file):
            self._load_unlocked()
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
            self._save_unlocked()
            self._notify("saida", mov)
            if item.precisa_repor:
                self._notify("alerta_estoque_minimo", item)
            return mov

    def mover_item(self, item_id: str, nova_coluna: ColunaKanban) -> bool:
        with self._lock, locked_path(self.data_file):
            self._load_unlocked()
            item = self._items.get(item_id)
            if not item:
                return False
            item.coluna = nova_coluna
            item.updated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
            self._save_unlocked()
            self._notify("item_movido", item)
            return True

    def itens_estoque_baixo(self) -> list[ItemEstoque]:
        with self._lock:
            self._refresh_if_changed()
            return [i for i in self._items.values() if i.precisa_repor]

    def buscar(self, query: str) -> list[ItemEstoque]:
        q = query.lower().strip()
        with self._lock:
            self._refresh_if_changed()
            return [
                i for i in self._items.values() if q in i.nome.lower() or q in i.categoria.lower()
            ]


_inventory_service: InventoryService | None = None


def get_inventory_service() -> InventoryService:
    global _inventory_service
    if _inventory_service is None:
        _inventory_service = InventoryService()
    return _inventory_service
