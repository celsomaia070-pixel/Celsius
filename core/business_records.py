import json
import logging
import os
import tempfile
import threading
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from core.modules import get_module_definition
from core.settings import get_settings

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


@dataclass
class BusinessRecord:
    id: str
    module_id: str
    title: str
    fields: dict[str, str] = field(default_factory=dict)
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
    def from_dict(cls, data: dict) -> "BusinessRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class BusinessRecordService:
    """Simple local registry for modular business records."""

    def __init__(self, data_file: Path | None = None, settings=None):
        self.settings = settings or get_settings()
        self.data_file = (
            Path(data_file) if data_file else self.settings.data_dir / "business_records.json"
        )
        self._records: dict[str, BusinessRecord] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        with self._lock:
            self._records = {}
            if not self.data_file.exists():
                return
            try:
                raw = json.loads(self.data_file.read_text(encoding="utf-8"))
                records_raw = raw.get("records", []) if isinstance(raw, dict) else []
                for record_data in records_raw:
                    record = BusinessRecord.from_dict(record_data)
                    if get_module_definition(record.module_id):
                        self._records[record.id] = record
            except Exception as exc:
                logger.error("Erro ao ler registros modulares: %s", exc)

    def _save(self):
        with self._lock:
            data = {"records": [record.to_dict() for record in self._records.values()]}
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
                logger.error("Erro ao salvar registros modulares: %s", exc)
                with suppress(OSError):
                    os.unlink(tmp_name)

    def list_by_module(self, module_id: str) -> list[BusinessRecord]:
        with self._lock:
            records = [record for record in self._records.values() if record.module_id == module_id]
            return sorted(records, key=lambda record: record.updated_at, reverse=True)

    def get(self, record_id: str) -> BusinessRecord | None:
        with self._lock:
            return self._records.get(record_id)

    def save_record(self, module_id: str, title: str, fields: dict[str, str], record_id: str = ""):
        title = title.strip()
        if not title:
            raise ValueError("Titulo do registro e obrigatorio.")
        if get_module_definition(module_id) is None:
            raise ValueError("Modulo desconhecido.")

        with self._lock:
            if record_id and record_id in self._records:
                record = self._records[record_id]
                record.title = title
                record.fields = {key: value.strip() for key, value in fields.items()}
                record.updated_at = _now()
            else:
                record = BusinessRecord(
                    id=str(uuid.uuid4())[:8],
                    module_id=module_id,
                    title=title,
                    fields={key: value.strip() for key, value in fields.items()},
                )
                self._records[record.id] = record
            self._save()
            return record

    def delete(self, record_id: str) -> bool:
        with self._lock:
            if record_id not in self._records:
                return False
            del self._records[record_id]
            self._save()
            return True

    def search(self, module_id: str, term: str) -> list[BusinessRecord]:
        query = term.strip().lower()
        records = self.list_by_module(module_id)
        if not query:
            return records
        return [
            record
            for record in records
            if query in record.title.lower()
            or any(query in value.lower() for value in record.fields.values())
        ]


_business_record_service: BusinessRecordService | None = None


def get_business_record_service() -> BusinessRecordService:
    global _business_record_service
    if _business_record_service is None:
        _business_record_service = BusinessRecordService()
    return _business_record_service


def reset_business_record_service():
    global _business_record_service
    _business_record_service = None
