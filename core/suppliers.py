import json
import logging
import os
import tempfile
import threading
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from core.settings import get_settings

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


@dataclass
class Supplier:
    id: str
    nome: str
    contato: str = ""
    telefone: str = ""
    email: str = ""
    categoria: str = ""
    observacoes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = _now()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Supplier":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class SupplierService:
    def __init__(self, data_file: Path | None = None, settings=None):
        self.settings = settings or get_settings()
        self.data_file = Path(data_file) if data_file else self.settings.data_dir / "suppliers.json"
        self._suppliers: dict[str, Supplier] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        with self._lock:
            self._suppliers = {}
            if not self.data_file.exists():
                return

            try:
                raw = json.loads(self.data_file.read_text(encoding="utf-8"))
                suppliers_raw = raw.get("suppliers", []) if isinstance(raw, dict) else []
                for supplier_data in suppliers_raw:
                    supplier = Supplier.from_dict(supplier_data)
                    self._suppliers[supplier.id] = supplier
            except Exception as exc:
                logger.error("Erro ao ler fornecedores: %s", exc)

    def _save(self):
        with self._lock:
            data = {"suppliers": [supplier.to_dict() for supplier in self._suppliers.values()]}
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{self.data_file.name}.",
                suffix=".tmp",
                dir=self.data_file.parent,
                text=True,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as file:
                    json.dump(data, file, ensure_ascii=False, indent=2)
                os.replace(tmp_name, self.data_file)
            except Exception as exc:
                logger.error("Erro ao salvar fornecedores: %s", exc)
                with suppress(OSError):
                    os.unlink(tmp_name)

    def list_all(self) -> list[Supplier]:
        with self._lock:
            return sorted(self._suppliers.values(), key=lambda supplier: supplier.nome.lower())

    def get(self, supplier_id: str) -> Supplier | None:
        with self._lock:
            return self._suppliers.get(supplier_id)

    def add(
        self,
        nome: str,
        contato: str = "",
        telefone: str = "",
        email: str = "",
        categoria: str = "",
        observacoes: str = "",
    ) -> Supplier:
        nome = nome.strip()
        if not nome:
            raise ValueError("Nome do fornecedor e obrigatorio.")

        with self._lock:
            supplier = Supplier(
                id=str(uuid.uuid4())[:8],
                nome=nome,
                contato=contato.strip(),
                telefone=telefone.strip(),
                email=email.strip(),
                categoria=categoria.strip(),
                observacoes=observacoes.strip(),
            )
            self._suppliers[supplier.id] = supplier
            self._save()
            return supplier

    def update(
        self,
        supplier_id: str,
        nome: str,
        contato: str = "",
        telefone: str = "",
        email: str = "",
        categoria: str = "",
        observacoes: str = "",
    ) -> Supplier | None:
        nome = nome.strip()
        if not nome:
            raise ValueError("Nome do fornecedor e obrigatorio.")

        with self._lock:
            supplier = self._suppliers.get(supplier_id)
            if supplier is None:
                return None

            supplier.nome = nome
            supplier.contato = contato.strip()
            supplier.telefone = telefone.strip()
            supplier.email = email.strip()
            supplier.categoria = categoria.strip()
            supplier.observacoes = observacoes.strip()
            supplier.updated_at = _now()
            self._save()
            return supplier

    def delete(self, supplier_id: str) -> bool:
        with self._lock:
            if supplier_id not in self._suppliers:
                return False
            del self._suppliers[supplier_id]
            self._save()
            return True

    def search(self, term: str) -> list[Supplier]:
        query = term.strip().lower()
        if not query:
            return self.list_all()

        with self._lock:
            return [
                supplier
                for supplier in self.list_all()
                if query in supplier.nome.lower()
                or query in supplier.contato.lower()
                or query in supplier.email.lower()
                or query in supplier.categoria.lower()
            ]


_supplier_service: SupplierService | None = None


def get_supplier_service() -> SupplierService:
    global _supplier_service
    if _supplier_service is None:
        _supplier_service = SupplierService()
    return _supplier_service


def reset_supplier_service():
    global _supplier_service
    _supplier_service = None
