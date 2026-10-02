"""Deterministic inspection and filling of existing DOCX and PDF forms.

The document is treated only as data.  Filling always creates a new file and
never executes macros, follows links, or evaluates instructions found inside
the document.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from core.file_security import restrict_private_file
from core.file_validation import validate_file_content

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]{1,120}?)\s*\}\}|\[\[\s*([^\[\]]{1,120}?)\s*\]\]")
_SPACE = re.compile(r"\s+")
# Word renders checkbox options as "( )" or "(X)"; captions follow each marker.
_MARKER = re.compile(r"\(\s*(x|X)?\s*\)")
_OPTION = re.compile(r"\(\s*(x|X)?\s*\)\s*([^\(\)]{1,90}?)(?=\(\s*(?:x|X)?\s*\)|$)")


@dataclass(frozen=True)
class FormField:
    key: str
    label: str
    current_value: str
    location: str
    kind: str = "text"
    options: tuple[str, ...] = ()
    checked: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = asdict(self)
        data["options"] = list(self.options)
        data["checked"] = list(self.checked)
        return data


def _clean(value: Any) -> str:
    return _SPACE.sub(" ", str(value or "").replace("\xa0", " ")).strip()


def _normalized(value: str) -> str:
    ascii_value = "".join(
        char
        for char in unicodedata.normalize("NFKD", _clean(value))
        if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def _key(label: str) -> str:
    return _normalized(label).replace(" ", "_")[:80] or "campo"


def _split_label_value(text: str) -> tuple[str, str] | None:
    text = _clean(text)
    if not text:
        return None
    question = text.find("?")
    colon = text.find(":")
    separators = [index for index in (question, colon) if 1 <= index <= 160]
    if not separators:
        return None
    split_at = min(separators) + 1
    label = text[:split_at].strip()
    value = text[split_at:].strip(" _\t")
    if len(label) < 3:
        return None
    return label, value


def _is_neighbour_label(text: str, next_text: str) -> bool:
    """Recognise compact label/value rows without treating table data as fields.

    School forms sometimes omit the colon in labels such as ``Professor do AEE``.
    A broad "first column is a label" rule is unsafe, however: the PAEE also has
    two-column objective/strategy tables.  This deliberately accepts only short,
    heading-like text and rejects prose and column headers.
    """

    clean = _clean(text)
    if not clean or len(clean) > 40 or clean.endswith((".", ";", "!")):
        return False
    if _normalized(clean) in {"objetivo", "objetivos", "estrategia", "estrategias"}:
        return False
    next_key = _normalized(next_text)
    if next_key.startswith(("estrategia", "recurso")):
        return False
    return True


def _unique_cells(row: Any) -> list[Any]:
    cells: list[Any] = []
    seen: set[int] = set()
    for cell in row.cells:
        identity = id(cell._tc)
        if identity not in seen:
            seen.add(identity)
            cells.append(cell)
    return cells


def _docx_containers(document: Any) -> list[Any]:
    containers = [document]
    seen: set[str] = set()
    for section in document.sections:
        for name in ("header", "footer", "first_page_header", "first_page_footer",
                     "even_page_header", "even_page_footer"):
            container = getattr(section, name)
            if container.is_linked_to_previous:
                continue
            part = str(container.part.partname)
            if part not in seen:
                seen.add(part)
                containers.append(container)
    return containers


def _all_docx_tables(document: Any) -> list[Any]:
    tables: list[Any] = []
    seen: set[int] = set()

    def visit(table: Any) -> None:
        if id(table._tbl) in seen:
            return
        seen.add(id(table._tbl))
        tables.append(table)
        for row in table.rows:
            for cell in _unique_cells(row):
                for nested in cell.tables:
                    visit(nested)

    for container in _docx_containers(document):
        for table in container.tables:
            visit(table)
    return tables


def _docx_controls(document: Any) -> list[tuple[str, Any, str, bool]]:
    """Named content controls, retaining their original OOXML container."""
    controls = []
    for container in _docx_containers(document):
        for index, control in enumerate(container.part._element.xpath(".//w:sdt")):
            labels = _control_xpath(control, "./w:sdtPr/w:alias/@w:val | ./w:sdtPr/w:tag/@w:val")
            if not labels:
                continue
            checkbox = control.find(".//{http://schemas.microsoft.com/office/word/2010/wordml}checkbox")
            controls.append((str(labels[0]), control, f"control:{container.part.partname}/{index}",
                             checkbox is not None))
    return controls


def _control_xpath(control: Any, expression: str) -> list[Any]:
    from lxml import etree

    return etree.XPath(expression, namespaces={
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    })(control)


def _section_fields(table: Any, table_index: int) -> list[FormField]:
    """Address numbered entries and answer rows beneath single-cell headings."""
    rows = [_unique_cells(row) for row in table.rows]
    if not rows or any(len(cells) != 1 for cells in rows):
        return []
    fields = []
    owned: set[int] = set()
    for index, cells in enumerate(rows):
        if index in owned:
            continue
        split = _split_label_value(cells[0].text)
        if not split or split[1] or not split[0].endswith(":"):
            continue
        label = split[0].rstrip(": ")
        items = []
        for ri in range(index + 1, len(rows)):
            text = _clean(rows[ri][0].text)
            numbered = re.match(r"^(\d{1,3})(?:\s*[-.)]\s*.*|\s*)$", text)
            if not numbered:
                break
            item_label = f"{label} / item {numbered.group(1)}"
            items.append(FormField(_key(item_label), item_label, text,
                                   f"table:{table_index}/row:{ri}/cell:0", "section_item"))
            owned.add(ri)
        if items:
            fields.extend(items)
            continue
        following = index + 1
        following_split = (_split_label_value(rows[following][0].text)
                           if following < len(rows) else None)
        narrative_colon = (following_split is not None and bool(re.search(r"\d", following_split[0]))
                           and not following_split[0].isupper())
        if following < len(rows) and (following_split is None or narrative_colon):
            fields.append(FormField(_key(label), label, _clean(rows[following][0].text),
                                    f"table:{table_index}/row:{following}/cell:0", "section_text"))
            owned.add(following)
        elif index > 0 or len(rows) == 1:
            fields.append(FormField(_key(label), label, "",
                                    f"table:{table_index}/row:{index}/cell:0", "section_inline"))
    return fields


def _docx_fields(path: Path) -> list[FormField]:
    from docx import Document

    document = Document(str(path))
    found: list[FormField] = []
    seen: set[tuple[str, str]] = set()

    def add(label: str, value: str, location: str, kind: str = "text") -> None:
        label = _clean(label).strip(" _")
        value = _clean(value).strip(" _")
        signature = (_normalized(label), location)
        if not signature[0] or signature in seen:
            return
        seen.add(signature)
        found.append(FormField(_key(label), label, value, location, kind))

    paragraphs = [paragraph for container in _docx_containers(document)
                  for paragraph in container.paragraphs]
    for index, paragraph in enumerate(paragraphs):
        for match in _PLACEHOLDER.finditer(paragraph.text):
            label = match.group(1) or match.group(2) or ""
            add(label, "", f"paragraph:{index}", "placeholder")
        if not _PLACEHOLDER.search(paragraph.text):
            split = _split_label_value(paragraph.text)
            if split:
                following = paragraph._p.getnext()
                if (not split[1] and split[0].isupper() and following is not None
                        and following.tag.endswith("}tbl")):
                    continue
                add(split[0], split[1], f"paragraph:{index}")

    for table_index, table in enumerate(_all_docx_tables(document)):
        for field in _section_fields(table, table_index):
            add(field.label, field.current_value, field.location, field.kind)
        for row_index, row in enumerate(table.rows):
            cells = _unique_cells(row)
            for cell_index, cell in enumerate(cells):
                location = f"table:{table_index}/row:{row_index}/cell:{cell_index}"
                text = _clean(cell.text)
                for match in _PLACEHOLDER.finditer(text):
                    label = match.group(1) or match.group(2) or ""
                    add(label, "", location, "placeholder")

                options = _checkbox_options(text)
                if options:
                    # A checkbox group owns its whole cell. Its label is either the
                    # text before the first marker or the neighbouring label cell.
                    own_label = _clean(_MARKER.split(text)[0]).strip(" _:")
                    if not own_label and cell_index > 0:
                        own_label = _clean(cells[cell_index - 1].text)
                    own_label = own_label.strip(" _:")
                    if own_label:
                        found.append(
                            FormField(
                                _key(own_label),
                                own_label,
                                ", ".join(cap for cap, on in options if on),
                                location,
                                "checkbox",
                                tuple(cap for cap, _ in options),
                                tuple(cap for cap, on in options if on),
                            )
                        )
                    continue

                split = _split_label_value(text)
                if split:
                    # A merged, blank cell ending in ':' is normally a section
                    # heading (e.g. "Competencias Cognitivas:"), not an answer
                    # box. Questions ending in '?' remain valid blank fields.
                    if len(cells) == 1 and not split[1] and split[0].endswith(":"):
                        continue
                    value = split[1]
                    location_cell = cell_index
                    if not value and cell_index + 1 < len(cells):
                        neighbour = _split_label_value(cells[cell_index + 1].text)
                        if neighbour is None:
                            value = _clean(cells[cell_index + 1].text)
                            location_cell = cell_index + 1
                        # The next cell is a checkbox group, so this label names
                        # that group and must not also become a text field.
                        if _checkbox_options(value):
                            continue
                    add(
                        split[0],
                        value,
                        f"table:{table_index}/row:{row_index}/cell:{location_cell}",
                    )
                    continue
                if not text or len(text) > 160 or cell_index + 1 >= len(cells):
                    continue
                next_text = _clean(cells[cell_index + 1].text)
                # A label cell naming a checkbox group is that group's label; the
                # group itself was already reported from the marker cell.
                if _checkbox_options(next_text):
                    continue
                # Most Word forms use one short label cell followed by a merged
                # answer cell. Section titles generally occupy the whole row.
                # A blank template has an empty answer cell, so an empty neighbour
                # is still a field waiting to be filled.
                if text.endswith((":", "?")) or (
                    cell_index == 0
                    and (not next_text or _is_neighbour_label(text, next_text))
                ):
                    add(
                        text,
                        next_text,
                        f"table:{table_index}/row:{row_index}/cell:{cell_index + 1}",
                    )
    for label, control, location, checkbox in _docx_controls(document):
        current = "".join(node.text or "" for node in _control_xpath(control, "./w:sdtContent//w:t"))
        add(label, current, location, "content_checkbox" if checkbox else "content_control")
    return found


def _pdf_fields(path: Path) -> list[FormField]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError("PDF protegido por senha; desbloqueie uma copia antes de preencher.")
    fields = reader.get_fields() or {}
    result: list[FormField] = []
    for name, metadata in fields.items():
        label = str(metadata.get("/TU") or metadata.get("/T") or name)
        value = str(metadata.get("/V") or "")
        field_type = str(metadata.get("/FT") or "/Tx").removeprefix("/")
        result.append(FormField(str(name), label, value, f"pdf:{name}", field_type))
    return result


def inspect_document_form(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    validate_file_content(source.name, source.read_bytes())
    suffix = source.suffix.lower()
    if suffix == ".odt":
        from core.office_conversion import docx_template

        with docx_template(source) as converted:
            result = inspect_document_form(converted)
        return {**result, "source": str(source), "format": "odt", "output_format": "docx",
                "note": "Modelo ODT convertido localmente para DOCX; confira a paginacao da copia."}
    if suffix == ".docx":
        fields = _docx_fields(source)
        form_type = "word_table_or_template"
    elif suffix == ".pdf":
        fields = _pdf_fields(source)
        form_type = "pdf_acroform" if fields else "pdf_static"
    else:
        raise ValueError("Use um documento DOCX ou PDF.")
    return {
        "source": str(source),
        "format": suffix.removeprefix("."),
        "form_type": form_type,
        "field_count": len(fields),
        "fields": [field.as_dict() for field in fields],
        "fillable": bool(fields),
        "note": (
            "PDF estatico ou digitalizado: converta/preencha o Word de origem ou crie um mapa "
            "de coordenadas revisado antes de escrever sobre as paginas."
            if suffix == ".pdf" and not fields
            else ""
        ),
    }


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace, keeping a map from normalized index to raw index."""

    out: list[str] = []
    positions: list[int] = []
    previous_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if previous_space:
                continue
            out.append(" ")
            positions.append(index)
            previous_space = True
        else:
            out.append(char)
            positions.append(index)
            previous_space = False
    return "".join(out), positions


def _replace_across_runs(paragraph: Any, old: str, new: str, *, after_label: bool = False) -> bool:
    """Replace `old` with `new`, matching on whitespace-normalized text.

    Word splits a value across runs and paragraphs, so the literal text rarely
    appears in any single run. Matching is done on the normalized concatenation
    and the resulting span is mapped back onto the original runs, which keeps
    the existing run formatting instead of appending a fresh run.
    """

    if not old:
        return False
    # Mutate only w:t text nodes. Run.text would delete drawings, hyperlinks,
    # bookmarks or other OOXML elements living in the same run.
    runs = paragraph._p.xpath(".//w:t")
    if paragraph._p.xpath(".//w:fldChar | .//w:instrText"):
        return False
    if not runs:
        return False
    full = "".join(run.text or "" for run in runs)
    normalized, positions = _norm_with_map(full)
    needle, _ = _norm_with_map(old)
    needle = needle.strip()
    if not needle:
        return False
    start_at = 0
    if after_label:
        separators = [index for index in (normalized.find(":"), normalized.find("?")) if index >= 0]
        if separators:
            start_at = min(separators) + 1
    found = normalized.find(needle, start_at)
    if found < 0:
        return False
    start = positions[found]
    last = found + len(needle) - 1
    if last >= len(positions):
        return False
    end = positions[last] + 1

    cursor = 0
    inserted = False
    for run in runs:
        text = run.text or ""
        run_start, run_end = cursor, cursor + len(text)
        cursor = run_end
        if run_end <= start or run_start >= end:
            continue
        local_start = max(0, start - run_start)
        local_end = min(len(text), end - run_start)
        prefix = text[:local_start]
        suffix = text[local_end:]
        run.text = prefix + (new if not inserted else "") + suffix
        run.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        inserted = True
    return inserted


def _replace_in_cell(cell: Any, old: str, new: str, *, label: str = "") -> bool:
    for paragraph in cell.paragraphs:
        split = _split_label_value(paragraph.text) if label else None
        labelled = bool(split and _normalized(split[0]) == _normalized(label))
        if labelled and not split[1]:
            continue
        if _replace_across_runs(paragraph, old, new, after_label=labelled):
            return True
    return False


def _copy_run_format(source_run: Any, target_run: Any) -> None:
    """Carry the surrounding character formatting over to a new run."""

    source, target = source_run._element, target_run._element
    properties = source.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr"
    )
    if properties is None:
        return
    existing = target.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr"
    )
    if existing is not None:
        target.remove(existing)
    import copy as _copy

    target.insert(0, _copy.deepcopy(properties))


def _set_cell(cell: Any, current: str, value: str) -> bool:
    if current and _replace_in_cell(cell, current, value):
        return True
    if current:
        # Appending beside an unreplaceable existing answer corrupts the form.
        return False
    # An empty box has nothing to replace, so write into the existing run to
    # inherit its formatting instead of creating an unformatted paragraph.
    paragraphs = cell.paragraphs
    preferred = [p for p in paragraphs if not _clean(p.text)]
    for paragraph in preferred or paragraphs[-1:]:
        if paragraph.runs:
            if paragraph.text and not paragraph.text.endswith((" ", "\n")):
                paragraph.add_run(" ")
            new_run = paragraph.add_run(value)
            _copy_run_format(paragraph.runs[0], new_run)
            return True
    paragraph = cell.paragraphs[-1] if cell.paragraphs else cell.add_paragraph()
    paragraph.add_run(value)
    return True


def _checkbox_options(text: str) -> list[tuple[str, bool]]:
    return [
        (_clean(match.group(2)), match.group(1) is not None)
        for match in _OPTION.finditer(text)
        if _clean(match.group(2))
    ]


def _fold(value: str) -> str:
    """Lowercase and strip accents so caption matching ignores case and diacritics."""

    return re.sub(r"\s+", " ", _normalized(value)).strip()


def _find_folded(haystack: str, needle: str) -> int:
    """Locate `needle` inside `haystack` through accent/case folding.

    Offsets are returned against the original string because the caller maps them
    back onto the raw runs to preserve formatting.
    """

    if not needle:
        return -1
    # Folding is per character, so the folded string keeps the same length as the
    # source and the match offset is directly usable against the raw runs.
    folded_hay = "".join(_strip_accents(char).lower() for char in haystack)
    folded_needle = "".join(_strip_accents(char).lower() for char in needle)
    return folded_hay.find(folded_needle)


def _strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def _toggle_option(cell: Any, option: str, checked: bool) -> bool:
    """Set one checkbox marker by matching its caption across paragraphs."""

    needle = _fold(option)
    if not needle:
        return False
    for paragraph in cell.paragraphs:
        runs = paragraph._p.xpath(".//w:t")
        if not runs:
            continue
        full = "".join(run.text or "" for run in runs)
        collapsed, positions = _norm_with_map(full)
        position = _find_folded(collapsed, needle)
        if position < 0:
            continue
        # The marker for an option sits immediately before its caption.
        prefix = collapsed[:position]
        matches = list(_MARKER.finditer(prefix))
        if not matches:
            continue
        marker = matches[-1]
        start = positions[marker.start()]
        end = positions[marker.end() - 1] + 1
        replacement = "(X)" if checked else "( )"
        cursor = 0
        written = False
        for run in runs:
            text = run.text or ""
            run_start, run_end = cursor, cursor + len(text)
            cursor = run_end
            if run_end <= start or run_start >= end:
                continue
            local_start = max(0, start - run_start)
            local_end = min(len(text), end - run_start)
            run.text = (
                text[:local_start] + (replacement if not written else "") + text[local_end:]
            )
            run.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            written = True
        if written:
            return True
    return False


def _apply_checkbox_value(cell: Any, value: str) -> tuple[bool, list[str]]:
    """Apply a checkbox-group value such as "Psicologia" or "TEA; TDHA"."""

    options = _checkbox_options(_clean(cell.text))
    if not options:
        return False, []
    # The whole value may name a single option whose caption contains a slash or
    # separator, so match the full value first and only then split it.
    candidates = [value.strip()]
    if len(options) > 1:
        candidates.extend(
            part.strip() for part in re.split(r"\s*[;,]\s*|\s+ e \s+", value, flags=re.I)
        )
    captions = [caption for caption, _ in options]
    resolved: list[str] = []
    for want in candidates:
        want_key = _fold(want)
        if not want_key:
            continue
        for caption in captions:
            caption_key = _fold(caption)
            if not caption_key:
                continue
            if caption_key == want_key or caption_key.startswith(want_key) or want_key.startswith(
                caption_key
            ):
                if _toggle_option(cell, caption, True) and caption not in resolved:
                    resolved.append(caption)
                break
    if not resolved:
        return False, []
    # An exclusive group must not keep its previous selection alongside the new one.
    if len(resolved) == 1 and len(captions) <= 4:
        for caption in captions:
            if _fold(caption) != _fold(resolved[0]):
                _toggle_option(cell, caption, False)
    return True, resolved


def _lookup(values: dict[str, str], label: str, key: str) -> str | None:
    aliases = {_normalized(label), _normalized(key)}
    for supplied_key, value in values.items():
        if _normalized(supplied_key) in aliases:
            return value
    return None


def _fill_docx(
    source: Path, target: Path, values: dict[str, str]
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    from docx import Document

    document = Document(str(source))
    editable_parts = [container.part for container in _docx_containers(document)]
    before = {str(part.partname): part.blob for part in editable_parts}
    applied: list[str] = []
    # Deterministic filling must never claim success it did not achieve, so every
    # skipped or unresolvable field is reported back for human review.
    unresolved: list[str] = []

    def replace_placeholders(paragraph: Any) -> None:
        for match in list(_PLACEHOLDER.finditer(paragraph.text)):
            label = match.group(1) or match.group(2) or ""
            value = _lookup(values, label, _key(label))
            if value is not None and _replace_across_runs(paragraph, match.group(0), value):
                applied.append(label)

    for container in _docx_containers(document):
        for paragraph in container.paragraphs:
            replace_placeholders(paragraph)
            if _PLACEHOLDER.search(paragraph.text):
                continue
            split = _split_label_value(paragraph.text)
            if split:
                label, current = split
                value = _lookup(values, label, _key(label))
                if value is not None:
                    if current:
                        if _replace_across_runs(paragraph, current, value, after_label=True):
                            applied.append(label)
                        else:
                            unresolved.append(label)
                    else:
                        run = paragraph.add_run(" " + value)
                        if len(paragraph.runs) > 1:
                            _copy_run_format(paragraph.runs[0], run)
                        applied.append(label)

    for table_index, table in enumerate(_all_docx_tables(document)):
        section_fields = _section_fields(table, table_index)
        section_locations = {field.location for field in section_fields}
        for field in section_fields:
            value = _lookup(values, field.label, field.key)
            if value is None:
                continue
            row_index = int(field.location.split("/row:")[1].split("/")[0])
            cell = _unique_cells(table.rows[row_index])[0]
            if _set_cell(cell, field.current_value, value):
                applied.append(field.label)
            else:
                unresolved.append(field.label)
        for row_index, row in enumerate(table.rows):
            cells = _unique_cells(row)
            for cell_index, cell in enumerate(cells):
                if f"table:{table_index}/row:{row_index}/cell:{cell_index}" in section_locations:
                    continue
                for paragraph in cell.paragraphs:
                    replace_placeholders(paragraph)
                text = _clean(cell.text)
                options = _checkbox_options(text)
                if options:
                    # Checkbox groups are filled by caption, never by rewriting the
                    # cell text, so the surrounding layout and markers survive.
                    own_label = _clean(_MARKER.split(text)[0]).strip(" _:")
                    candidates = [own_label]
                    if cell_index > 0:
                        candidates.append(_clean(cells[cell_index - 1].text))
                    for candidate in candidates:
                        candidate = candidate.strip(" _:")
                        if not candidate:
                            continue
                        value = _lookup(values, candidate, _key(candidate))
                        if value is None:
                            continue
                        ok, resolved = _apply_checkbox_value(cell, value)
                        if ok:
                            applied.append(candidate)
                        else:
                            unresolved.append(
                                f"{candidate}: nenhuma opcao corresponde a {value!r}"
                            )
                        break
                    continue

                # A label cell whose neighbour holds checkboxes is already handled
                # by the checkbox branch on that neighbour, so skip it silently.
                if cell_index + 1 < len(cells) and _checkbox_options(
                    _clean(cells[cell_index + 1].text)
                ):
                    continue

                split = _split_label_value(text)
                if split:
                    if len(cells) == 1 and not split[1] and split[0].endswith(":"):
                        continue
                    label, current = split
                    value = _lookup(values, label, _key(label))
                    if value is not None:
                        ok = False
                        if current:
                            ok = _replace_in_cell(cell, current, value, label=label)
                        elif cell_index + 1 < len(cells):
                            next_cell = cells[cell_index + 1]
                            if _split_label_value(next_cell.text) is not None:
                                ok = _set_cell(cell, "", value)
                            else:
                                ok = _set_cell(next_cell, _clean(next_cell.text), value)
                        else:
                            ok = _set_cell(cell, "", value)
                        if ok:
                            applied.append(label)
                        else:
                            unresolved.append(label)
                    continue
                if not text or len(text) > 160 or cell_index + 1 >= len(cells):
                    continue
                next_cell = cells[cell_index + 1]
                next_text = _clean(next_cell.text)
                # Mirrors the inspect pass: a blank template has an empty answer
                # cell, so an empty neighbour is still a field to fill.
                if text.endswith((":", "?")) or (
                    cell_index == 0
                    and (not next_text or _is_neighbour_label(text, next_text))
                ):
                    value = _lookup(values, text, _key(text))
                    if value is not None:
                        if _set_cell(next_cell, next_text, value):
                            applied.append(text)
                        else:
                            unresolved.append(text)

    for label, control, _location, checkbox in _docx_controls(document):
        value = _lookup(values, label, _key(label))
        if value is None:
            continue
        if _control_xpath(control,
                          "./w:sdtPr/w:lock | ./w:sdtPr/w:dataBinding | ./w:sdtPr/w:picture | "
                          "./w:sdtPr/w:dropDownList | ./w:sdtPr/w:comboBox | ./w:sdtPr/w:date | "
                          "./w:sdtContent//w:tbl | ./w:sdtContent//w:drawing | ./w:sdtContent//w:fldChar"):
            unresolved.append(label)
            continue
        nodes = _control_xpath(control, "./w:sdtContent//w:t")
        if not nodes:
            unresolved.append(label)
            continue
        if checkbox:
            normalized = _normalized(value)
            if normalized not in {"sim", "nao", "true", "false", "1", "0"}:
                unresolved.append(label)
                continue
            checked = normalized in {"sim", "true", "1"}
            checked_node = control.find(".//{http://schemas.microsoft.com/office/word/2010/wordml}checked")
            if checked_node is None:
                unresolved.append(label)
                continue
            checked_node.set("{http://schemas.microsoft.com/office/word/2010/wordml}val", "1" if checked else "0")
            value = "☒" if checked else "☐"
        nodes[0].text = value
        nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        for node in nodes[1:]:
            node.text = ""
        for placeholder_flag in _control_xpath(control, "./w:sdtPr/w:showingPlcHdr"):
            placeholder_flag.getparent().remove(placeholder_flag)
        applied.append(label)

    # Preserve every package entry except XML parts actually modified. python-docx
    # supplies the OOXML objects but does not rebuild styles, media or metadata.
    replacements = {
        str(part.partname).lstrip("/"): part.blob for part in editable_parts
        if part.blob != before[str(part.partname)]
    }
    with ZipFile(source) as original, ZipFile(target, "x") as output:
        for info in original.infolist():
            output.writestr(info, replacements.get(info.filename, original.read(info.filename)))
    applied_normalized = {_normalized(item) for item in applied}
    unmatched = [key for key in values if _normalized(key) not in applied_normalized]
    return (
        list(dict.fromkeys(applied)),
        unmatched,
        {"unresolved": unresolved},
    )


def _fill_pdf(source: Path, target: Path, values: dict[str, str]) -> tuple[list[str], list[str]]:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    if reader.is_encrypted:
        raise ValueError("PDF protegido por senha; desbloqueie uma copia antes de preencher.")
    available = reader.get_fields() or {}
    if not available:
        raise ValueError(
            "Este PDF nao possui campos editaveis. Preencha o DOCX de origem ou use um modelo "
            "PDF previamente mapeado."
        )
    resolved: dict[str, str] = {}
    matched_supplied: set[str] = set()
    for supplied_key, value in values.items():
        match = next(
            (
                name
                for name, metadata in available.items()
                if _normalized(supplied_key)
                in {
                    _normalized(str(name)),
                    _normalized(str(metadata.get("/TU") or metadata.get("/T") or name)),
                }
            ),
            None,
        )
        if match is not None:
            resolved[match] = value
            matched_supplied.add(supplied_key)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    for page in writer.pages:
        writer.update_page_form_field_values(page, resolved, auto_regenerate=False)
    with target.open("xb") as output:
        writer.write(output)
    unmatched = [key for key in values if key not in matched_supplied]
    return list(resolved), unmatched


def _default_target(source: Path) -> Path:
    base = source.with_name(f"{source.stem} - preenchido{source.suffix}")
    if not base.exists():
        return base
    for index in range(2, 1000):
        candidate = source.with_name(f"{source.stem} - preenchido {index}{source.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError("Ha copias preenchidas demais nesta pasta; escolha outro nome de saida.")


def fill_document_form(
    source_path: str | Path,
    values: dict[str, Any],
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    source = Path(source_path).resolve()
    if source.suffix.lower() == ".odt":
        from core.office_conversion import docx_template

        target = Path(output_path).resolve() if output_path else _default_target(source.with_suffix(".docx"))
        if target.suffix.lower() != ".docx":
            raise ValueError("O preenchimento de um modelo ODT gera uma nova copia DOCX.")
        with docx_template(source) as converted:
            result = fill_document_form(converted, values, target)
        return {**result, "source": str(source), "converted_from": "odt",
                "conversion_note": "Conversao para DOCX; confira a paginacao. O ODT original foi preservado."}
    validate_file_content(source.name, source.read_bytes())
    clean_values = {str(key): _clean(value) for key, value in values.items() if _clean(value)}
    if not clean_values:
        raise ValueError("Informe pelo menos um campo com valor.")
    if len(clean_values) > 200 or any(len(value) > 20_000 for value in clean_values.values()):
        raise ValueError("Quantidade ou tamanho dos campos excede o limite seguro.")
    target = Path(output_path).resolve() if output_path else _default_target(source)
    if target == source:
        raise ValueError("O arquivo original nunca e sobrescrito; escolha outro nome de saida.")
    if target.exists():
        raise FileExistsError(f"O arquivo de saida ja existe: {target}")
    if target.suffix.lower() != source.suffix.lower():
        raise ValueError("A extensao do arquivo de saida deve ser igual a do modelo.")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Validate in an isolated staging folder, then exclusively create the output.
    # If another task wins the filename race, its file must never be removed.
    with tempfile.TemporaryDirectory(prefix=".celsius-fill-", dir=target.parent) as staging:
        staged = Path(staging) / target.name
        notes: dict[str, list[str]] = {}
        if source.suffix.lower() == ".docx":
            applied, unmatched, notes = _fill_docx(source, staged, clean_values)
        elif source.suffix.lower() == ".pdf":
            applied, unmatched = _fill_pdf(source, staged, clean_values)
        else:
            raise ValueError("Use um documento DOCX ou PDF.")
        validate_file_content(staged.name, staged.read_bytes())
        restrict_private_file(staged)
        if not applied:
            return {
                "source": str(source), "output": "", "written": False,
                "applied_count": 0, "applied": [], "unmatched": unmatched,
                "needs_review": notes.get("unresolved", []), "original_preserved": True,
                "size_bytes": 0,
            }
        owned_output = False
        try:
            with target.open("xb") as output:
                owned_output = True
                restrict_private_file(target)
                with staged.open("rb") as input_file:
                    shutil.copyfileobj(input_file, output)
        except Exception:
            if owned_output:
                target.unlink(missing_ok=True)
            raise
    return {
        "source": str(source),
        "output": str(target),
        "written": True,
        "applied_count": len(applied),
        "applied": applied,
        "unmatched": unmatched,
        "needs_review": notes.get("unresolved", []),
        "original_preserved": True,
        "size_bytes": target.stat().st_size,
    }


def duplicate_template(source_path: str | Path, output_path: str | Path) -> Path:
    """Small tested helper retained for future reviewed template onboarding."""
    source, target = Path(source_path).resolve(), Path(output_path).resolve()
    shutil.copy2(source, target)
    restrict_private_file(target)
    return target
