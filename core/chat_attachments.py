"""Shared attachment preparation for desktop and web chat requests."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

StatusCallback = Callable[[str], None]


def prepare_prompt_attachments(
    prompt_dict: dict,
    *,
    settings,
    fn_status: StatusCallback | None = None,
) -> None:
    attachments = prompt_dict.pop("anexos", []) or []
    if not attachments:
        return

    from processors import processar_arquivo

    doc_parts = []
    existing_doc = str(prompt_dict.get("documento", "")).strip()
    if existing_doc:
        doc_parts.append(existing_doc)

    doc_names = []
    document_paths = []
    first_image = ""
    for file_path, file_name in attachments:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix in settings.image_extensions and not first_image:
            if fn_status:
                fn_status(f"Preparando imagem anexada: {file_name}...")
            first_image = str(path)
            continue

        try:
            if fn_status:
                fn_status(f"Extraindo conteudo do arquivo: {file_name}...")
            processed = processar_arquivo(str(path), base_dir=path.parent)
        except Exception as exc:
            processed = f"Erro ao processar anexo '{file_name}': {exc}"
        doc_names.append(file_name)
        document_paths.append(str(path))
        doc_parts.append(f"### Anexo: {file_name}\n{processed}")

    if first_image:
        prompt_dict["caminho_imagem"] = first_image

    if doc_parts:
        if fn_status:
            fn_status("Organizando conteudo extraido...")
        prompt_dict["documento"] = "\n\n".join(doc_parts)
        if doc_names:
            prompt_dict["nome_documento"] = ", ".join(doc_names)
            prompt_dict["caminho_documento"] = "; ".join(document_paths)


class AttachmentError(ValueError):
    """Raised when a web attachment violates local upload rules."""


@dataclass(frozen=True)
class StoredAttachment:
    id: str
    name: str
    path: Path
    size: int

    def public_dict(self) -> dict[str, str | int]:
        return {"id": self.id, "name": self.name, "size": self.size}


class AttachmentStore:
    """Keep paired uploads inside a dedicated local temporary directory."""

    _VALID_ID = re.compile(r"^[a-f0-9]{32}$")

    def __init__(self, root: Path, *, allowed_extensions, max_size_mb: int):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.allowed_extensions = {str(ext).lower() for ext in allowed_extensions}
        self.max_bytes = max(1, int(max_size_mb)) * 1024 * 1024
        self._items: dict[str, StoredAttachment] = {}
        self._lock = RLock()

    def save(self, filename: str, content: bytes) -> StoredAttachment:
        clean_name = Path(filename or "").name.strip()
        if not clean_name or clean_name in {".", ".."}:
            raise AttachmentError("Nome de arquivo invalido.")
        suffix = Path(clean_name).suffix.lower()
        if suffix not in self.allowed_extensions:
            raise AttachmentError(f"Formato '{suffix or 'sem extensao'}' nao suportado.")
        if not content:
            raise AttachmentError("O arquivo enviado esta vazio.")
        if len(content) > self.max_bytes:
            raise AttachmentError(
                f"O arquivo excede o limite local de {self.max_bytes // (1024 * 1024)} MB."
            )

        attachment_id = uuid.uuid4().hex
        path = (self.root / f"{attachment_id}{suffix}").resolve()
        if path.parent != self.root:
            raise AttachmentError("Destino de arquivo invalido.")
        path.write_bytes(content)
        stored = StoredAttachment(attachment_id, clean_name, path, len(content))
        with self._lock:
            self._items[attachment_id] = stored
        return stored

    def resolve(self, attachment_ids: list[str]) -> list[StoredAttachment]:
        resolved = []
        with self._lock:
            for attachment_id in attachment_ids:
                if not self._VALID_ID.fullmatch(attachment_id or ""):
                    raise AttachmentError("Identificador de anexo invalido.")
                stored = self._items.get(attachment_id)
                if stored is None or not stored.path.is_file():
                    raise AttachmentError("Anexo nao encontrado ou expirado.")
                resolved.append(stored)
        return resolved

    def discard(self, attachment_ids: list[str]) -> None:
        with self._lock:
            items = [self._items.pop(attachment_id, None) for attachment_id in attachment_ids]
        for stored in items:
            if stored is not None:
                stored.path.unlink(missing_ok=True)
