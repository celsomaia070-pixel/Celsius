"""Deterministic extraction of labelled values from source documents.

The target form is scanned by :mod:`core.document_forms`; this module answers the
other half of the problem: turning a source document (report, laudo, spreadsheet,
previous form) into a flat ``label -> value`` map that can be matched against the
target fields.  Extraction never guesses: a value is only produced when a label
and its value are adjacent, and every ambiguous hit is reported.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.document_forms import (
    _PLACEHOLDER,
    _checkbox_options,
    _clean,
    _control_xpath,
    _docx_controls,
    _docx_fields,
    _normalized,
    _unique_cells,
)
from core.file_validation import validate_file_content

# "Nome da criança: Maria" in running text. The label must stay reasonably short
# and must not swallow a sentence, otherwise every line looks like a field.
_INLINE = re.compile(r"^[\s\-–—*•]*([^:：\n]{2,80}?)\s*[:：]\s*(.+)$")
_MAX_LABEL = 80
_MAX_VALUE = 20_000


def _docx_evidence(path: Path) -> tuple[dict[str, str], dict[str, list[str]], list[dict[str, str]]]:
    """Extract labelled facts with physical locations, including nested tables."""
    from docx import Document

    document = Document(str(path))
    store: dict[str, str] = {}
    origins: dict[str, list[str]] = {}
    evidence: list[dict[str, str]] = []

    def add(label: str, value: str, location: str) -> None:
        options = _checkbox_options(value)
        if options:
            for caption, checked in options:
                if checked:
                    add(label, caption, location)
            return
        if _PLACEHOLDER.search(value) or not value.strip(" _\t\n"):
            return
        before = len(origins.get(_normalized(label), []))
        _add(store, origins, label, value)
        key = _normalized(label)
        if len(origins.get(key, [])) > before:
            evidence.append({"key": key, "label": _clean(label), "value": _clean(value),
                             "source": str(path), "location": location})

    def paragraphs(items: Any, prefix: str) -> None:
        for index, paragraph in enumerate(items):
            for line in paragraph.text.splitlines():
                match = _INLINE.match(_clean(line))
                if match:
                    add(match.group(1), match.group(2), f"{prefix}/paragraph:{index}")

    def tables(items: Any, prefix: str) -> None:
        for ti, table in enumerate(items):
            for ri, row in enumerate(table.rows):
                cells = _unique_cells(row)
                for ci, cell in enumerate(cells):
                    location = f"{prefix}/table:{ti}/row:{ri}/cell:{ci}"
                    previous_count = len(evidence)
                    paragraphs(cell.paragraphs, location)
                    label = _clean(cell.text)
                    inline = _INLINE.match(label)
                    if inline and len(evidence) == previous_count:
                        add(inline.group(1), inline.group(2), location)
                    # Read label/value pairs, not arbitrary overlapping cell pairs.
                    if ci % 2 == 0 and ci + 1 < len(cells) and not inline:
                        value = _clean(cells[ci + 1].text)
                        if not _looks_like_value(label):
                            add(label, value, f"{prefix}/table:{ti}/row:{ri}/cell:{ci + 1}")
                    tables(cell.tables, location)

    paragraphs(document.paragraphs, "body")
    tables(document.tables, "body")
    seen: set[str] = set()
    for si, section in enumerate(document.sections):
        for name in ("header", "footer", "first_page_header", "first_page_footer",
                     "even_page_header", "even_page_footer"):
            container = getattr(section, name)
            if container.is_linked_to_previous:
                continue
            part = str(container.part.partname)
            if part in seen:
                continue
            seen.add(part)
            prefix = f"section:{si}/{name}"
            paragraphs(container.paragraphs, prefix)
            tables(container.tables, prefix)
    for label, control, location, checkbox in _docx_controls(document):
        if _control_xpath(control, "./w:sdtPr/w:showingPlcHdr"):
            continue
        if checkbox:
            checked = control.find(".//{http://schemas.microsoft.com/office/word/2010/wordml}checked")
            if checked is None:
                continue
            value = "Sim" if checked.get(
                "{http://schemas.microsoft.com/office/word/2010/wordml}val"
            ) in {"1", "true", "on"} else "Não"
        else:
            value = "".join(node.text or "" for node in _control_xpath(control, "./w:sdtContent//w:t"))
        add(label, value, location)
    for field in _docx_fields(path):
        if field.kind in {"section_item", "section_text"}:
            if field.kind == "section_item" and re.fullmatch(r"\d+\s*[-.)]?", field.current_value):
                continue
            add(field.label, field.current_value, field.location)
    return store, origins, evidence


def _add(store: dict[str, str], origins: dict[str, list[str]], label: str, value: str) -> None:
    label = _clean(label).strip(" *_-\t")
    value = _clean(value)
    if not label or not value or len(label) > _MAX_LABEL or len(value) > _MAX_VALUE:
        return
    key = _normalized(label)
    if not key:
        return
    existing = store.get(key)
    if existing is not None and _normalized(existing) != _normalized(value):
        # Two different values for one label is a real ambiguity, not a merge.
        origins.setdefault(key, []).append(value)
        return
    store[key] = value
    origins.setdefault(key, []).append(value)


def _from_tables(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    from docx import Document

    store: dict[str, str] = {}
    origins: dict[str, list[str]] = {}
    document = Document(str(path))
    for table in document.tables:
        for row in table.rows:
            cells = _unique_cells(row)
            texts = [_clean(cell.text) for cell in cells]
            # "Label | Value" in adjacent cells is the common Word layout.
            for index in range(len(texts) - 1):
                label, value = texts[index], texts[index + 1]
                if not label or not value or len(label) > _MAX_LABEL:
                    continue
                # A cell that already carries "Label: value" owns its own answer,
                # so it must not be read as the label of the next cell.
                if _INLINE.match(label):
                    continue
                if _looks_like_value(label) and not _looks_like_value(value):
                    continue
                _add(store, origins, label, value)
            # "Label: value" inside a single merged cell.
            for text in texts:
                match = _INLINE.match(text)
                if match:
                    _add(store, origins, match.group(1), match.group(2))
    return store, origins


def _from_paragraphs(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    from docx import Document

    store: dict[str, str] = {}
    origins: dict[str, list[str]] = {}
    document = Document(str(path))
    blocks = [paragraph.text for paragraph in document.paragraphs]
    for section in document.sections:
        blocks.extend(paragraph.text for paragraph in section.header.paragraphs)
        blocks.extend(paragraph.text for paragraph in section.footer.paragraphs)
    for raw in blocks:
        match = _INLINE.match(_clean(raw))
        if match:
            _add(store, origins, match.group(1), match.group(2))
    return store, origins


def _looks_like_value(text: str) -> bool:
    """A cell holding a date, number or long sentence is a value, not a label."""

    if len(text) > _MAX_LABEL:
        return True
    if re.match(r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", text):
        return True
    if re.match(r"^[\d.,]+$", text):
        return True
    return text.endswith((".", ";")) and len(text) > 40


def _from_pdf(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    from pypdf import PdfReader

    store: dict[str, str] = {}
    origins: dict[str, list[str]] = {}
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError("PDF protegido por senha; desbloqueie uma copia antes de ler.")
    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            match = _INLINE.match(_clean(line))
            if match:
                _add(store, origins, match.group(1), match.group(2))
    return store, origins


def _from_xlsx(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    from openpyxl import load_workbook

    store: dict[str, str] = {}
    origins: dict[str, list[str]] = {}
    workbook = load_workbook(str(path), data_only=True, read_only=True)
    try:
        for sheet in workbook.worksheets:
            rows = [list(row) for row in sheet.iter_rows(values_only=True)]
            for index, row in enumerate(rows):
                cells = [_clean(cell) for cell in row]
                # A two-column sheet is a plain label/value table.
                if len(cells) == 2 and cells[0] and cells[1]:
                    _add(store, origins, cells[0], cells[1])
                    continue
                # Otherwise treat a header row plus the row beneath it as a record.
                for column, header in enumerate(cells):
                    if not header or column >= len(row):
                        continue
                    value = row[column]
                    if value is None or column >= len(cells):
                        continue
                    following = cells[column + 1] if column + 1 < len(cells) else ""
                    if following:
                        continue
                    _add(store, origins, header, _clean(value))
                del index
    finally:
        workbook.close()
    return store, origins


def _from_text(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    store: dict[str, str] = {}
    origins: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _INLINE.match(_clean(line))
        if match:
            _add(store, origins, match.group(1), match.group(2))
    return store, origins


def extract_source_values(path: str | Path) -> dict[str, Any]:
    """Read a source document and return its labelled values.

    The result is data only.  Nothing inside the document is ever treated as an
    instruction, and no value is invented: a label with two conflicting values is
    reported under ``conflicts`` so the caller can ask the user.
    """

    source = Path(path).resolve()
    validate_file_content(source.name, source.read_bytes())
    suffix = source.suffix.lower()
    evidence: list[dict[str, str]] = []
    if suffix == ".docx":
        store, origins, evidence = _docx_evidence(source)
    elif suffix == ".pdf":
        store, origins = _from_pdf(source)
    elif suffix == ".xlsx":
        store, origins = _from_xlsx(source)
    elif suffix in {".txt", ".md", ".csv", ".json"}:
        store, origins = _from_text(source)
    else:
        raise ValueError("Use um documento DOCX, PDF, XLSX ou texto como fonte.")

    conflicts = {
        key: sorted({_clean(item) for item in values})
        for key, values in origins.items()
        if len({_normalized(item) for item in values}) > 1
    }
    return {
        "source": str(source),
        "field_count": len(store),
        "values": {key: value for key, value in store.items() if key not in conflicts},
        "conflicts": conflicts,
        "evidence": evidence,
    }
