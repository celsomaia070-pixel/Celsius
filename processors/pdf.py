import hashlib
import json
import logging
import os
import re
import threading
import time
from contextlib import suppress
from pathlib import Path

from core.settings import get_settings
from processors.base import ProcessadorArquivo, SecurityError

logger = logging.getLogger(__name__)

MAX_REPRESENTATIVE_PAGES = 24
MAX_OCR_PAGES = 6
OCR_RENDER_SCALE = 1.5
OCR_TARGET_CHARS = 7000
OCR_MIN_CONFIDENCE = 0.45
EXTRACTION_FAILURE_MARKER = "EXTRACAO_INSUFICIENTE"
PDF_CACHE_VERSION = 1
MAX_PDF_CACHE_ENTRIES = 32
_RAPID_OCR_ENGINE = None
_RAPID_OCR_LOCK = threading.Lock()
_PDF_CACHE_LOCK = threading.Lock()


def _pdf_cache_file(path: Path, settings) -> Path:
    stat = path.stat()
    signature = {
        "version": PDF_CACHE_VERSION,
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "doc_text_limit": int(settings.doc_text_limit),
        "page_limit": int(settings.file.large_pdf_page_limit),
        "representative_pages": MAX_REPRESENTATIVE_PAGES,
        "ocr_pages": MAX_OCR_PAGES,
        "ocr_scale": OCR_RENDER_SCALE,
        "ocr_target_chars": OCR_TARGET_CHARS,
        "ocr_min_confidence": OCR_MIN_CONFIDENCE,
    }
    digest = hashlib.sha256(json.dumps(signature, sort_keys=True).encode("utf-8")).hexdigest()
    data_dir = Path(getattr(settings, "data_dir", path.parent / ".celsius-cache"))
    return data_dir / "cache" / "pdf" / f"{digest}.json"


def _load_pdf_cache(cache_file: Path) -> str | None:
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if payload.get("version") != PDF_CACHE_VERSION:
        return None
    result = payload.get("result")
    return result if isinstance(result, str) and result.strip() else None


def _prune_pdf_cache(cache_dir: Path) -> None:
    try:
        cache_files = sorted(
            cache_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime_ns,
            reverse=True,
        )
        for stale_file in cache_files[MAX_PDF_CACHE_ENTRIES:]:
            stale_file.unlink(missing_ok=True)
    except OSError as exc:
        logger.debug("Falha ao limitar cache de PDF: %s", exc)


def _save_pdf_cache(cache_file: Path, result: str) -> None:
    temporary_file = cache_file.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with _PDF_CACHE_LOCK:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            temporary_file.write_text(
                json.dumps(
                    {"version": PDF_CACHE_VERSION, "result": result},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.replace(temporary_file, cache_file)
            _prune_pdf_cache(cache_file.parent)
    except OSError as exc:
        logger.debug("Falha ao salvar cache de PDF: %s", exc)
    finally:
        with suppress(OSError):
            temporary_file.unlink(missing_ok=True)


def _representative_page_indices(total_pages: int, max_pages: int) -> list[int]:
    """Return evenly distributed zero-based pages, always including both ends."""
    if total_pages <= 0 or max_pages <= 0:
        return []
    if total_pages <= max_pages:
        return list(range(total_pages))
    if max_pages == 1:
        return [0]

    last = total_pages - 1
    return sorted({round(position * last / (max_pages - 1)) for position in range(max_pages)})


def _useful_text_length(page_texts: dict[int, str]) -> int:
    return len(re.sub(r"\s+", "", "\n".join(page_texts.values())))


def _minimum_useful_chars(total_pages: int) -> int:
    # A long book needs more than a title or copyright page to support a report.
    return min(500, max(80, total_pages * 5))


def _prioritize_ocr_page_indices(page_indices: list[int]) -> list[int]:
    """Read start, end and middle first so early stopping keeps broad coverage."""
    if len(page_indices) <= 2:
        return page_indices.copy()

    priority_positions = (0, len(page_indices) - 1, len(page_indices) // 2)
    prioritized = [page_indices[position] for position in priority_positions]
    prioritized.extend(index for index in page_indices if index not in prioritized)
    return prioritized


def _extract_with_pypdf(reader, page_indices: list[int]) -> dict[int, str]:
    extracted: dict[int, str] = {}
    for index in page_indices:
        try:
            extracted[index] = reader.pages[index].extract_text() or ""
        except Exception as exc:
            logger.warning("Falha ao extrair pagina %s com pypdf: %s", index + 1, exc)
            extracted[index] = ""
    return extracted


def _extract_with_pdfplumber(path: Path, page_indices: list[int]) -> dict[int, str]:
    """Use the MIT-licensed pdfplumber as a local fallback for difficult PDFs."""
    try:
        import pdfplumber
    except ImportError:
        logger.info("pdfplumber nao instalado; fallback de PDF indisponivel")
        return {}

    extracted: dict[int, str] = {}
    try:
        with pdfplumber.open(str(path)) as pdf:
            for index in page_indices:
                if index >= len(pdf.pages):
                    continue
                try:
                    extracted[index] = pdf.pages[index].extract_text(layout=True) or ""
                except Exception as exc:
                    logger.warning(
                        "Falha ao extrair pagina %s com pdfplumber: %s",
                        index + 1,
                        exc,
                    )
                    extracted[index] = ""
    except Exception as exc:
        logger.warning("Falha ao abrir PDF com pdfplumber: %s", exc)
        return {}
    return extracted


def _get_rapidocr_engine():
    global _RAPID_OCR_ENGINE

    if _RAPID_OCR_ENGINE is not None:
        return _RAPID_OCR_ENGINE

    with _RAPID_OCR_LOCK:
        if _RAPID_OCR_ENGINE is None:
            from rapidocr import RapidOCR

            ocr_threads = max(1, min(4, (os.cpu_count() or 4) // 2))
            _RAPID_OCR_ENGINE = RapidOCR(
                params={
                    "Global.log_level": "warning",
                    "Det.intra_op_num_threads": ocr_threads,
                    "Cls.intra_op_num_threads": ocr_threads,
                    "Rec.intra_op_num_threads": ocr_threads,
                }
            )
    return _RAPID_OCR_ENGINE


def _close_pdfium_object(obj) -> None:
    close = getattr(obj, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception as exc:
        logger.debug("Falha ao liberar recurso temporario de PDF: %s", exc)


def _ocr_result_text(result) -> str:
    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if texts is not None:
        if scores is None:
            return "\n".join(str(text) for text in texts if str(text).strip())
        return "\n".join(
            str(text)
            for text, score in zip(texts, scores, strict=False)
            if str(text).strip() and float(score) >= OCR_MIN_CONFIDENCE
        )

    # Compatibility with the legacy RapidOCR tuple result.
    rows = result[0] if isinstance(result, tuple) and result else result
    if not isinstance(rows, (list, tuple)):
        return ""

    extracted_lines = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        payload = row[1]
        if isinstance(payload, (list, tuple)) and payload:
            text = str(payload[0])
            score = float(payload[1]) if len(payload) > 1 else 1.0
            if text.strip() and score >= OCR_MIN_CONFIDENCE:
                extracted_lines.append(text)
    return "\n".join(extracted_lines)


def _extract_with_rapidocr(path: Path, page_indices: list[int]) -> dict[int, str]:
    """Render selected pages and recognize their text with a fully local OCR engine."""
    try:
        import pypdfium2 as pdfium
        from rapidocr import RapidOCR  # noqa: F401 - verifies the optional dependency
    except ImportError:
        logger.info("RapidOCR/PDFium nao instalados; OCR local indisponivel")
        return {}

    try:
        engine = _get_rapidocr_engine()
        pdf = pdfium.PdfDocument(str(path))
    except Exception as exc:
        logger.warning("Falha ao iniciar OCR local do PDF: %s", exc)
        return {}

    extracted: dict[int, str] = {}
    try:
        for processed_count, index in enumerate(
            _prioritize_ocr_page_indices(page_indices),
            start=1,
        ):
            if index >= len(pdf):
                continue
            page = None
            bitmap = None
            try:
                page = pdf[index]
                bitmap = page.render(scale=OCR_RENDER_SCALE)
                image = bitmap.to_numpy()
                if getattr(image, "ndim", 0) == 3 and image.shape[2] > 3:
                    image = image[:, :, :3]
                result = engine(image)
                extracted[index] = _ocr_result_text(result)
            except Exception as exc:
                logger.warning("Falha no OCR local da pagina %s: %s", index + 1, exc)
                extracted[index] = ""
            finally:
                _close_pdfium_object(bitmap)
                _close_pdfium_object(page)
            if processed_count >= 3 and _useful_text_length(extracted) >= OCR_TARGET_CHARS:
                break
    finally:
        _close_pdfium_object(pdf)
    return extracted


def _format_page_sample(
    page_texts: dict[int, str],
    *,
    total_pages: int,
    char_limit: int,
) -> str:
    nonempty_pages = [
        (index, text.strip()) for index, text in sorted(page_texts.items()) if text.strip()
    ]
    if not nonempty_pages:
        return ""

    marker_budget = sum(len(f"Pagina {index + 1}/{total_pages}\n\n") for index, _ in nonempty_pages)
    text_budget = max(1, char_limit - marker_budget)
    per_page_budget = max(200, text_budget // len(nonempty_pages))
    sections = []

    for index, text in nonempty_pages:
        snippet = text[:per_page_budget].strip()
        if len(text) > per_page_budget:
            snippet += "\n... [Trecho da pagina truncado] ..."
        sections.append(f"Pagina {index + 1}/{total_pages}\n{snippet}")

    result = "\n\n".join(sections)
    if len(result) > char_limit:
        result = result[:char_limit].rstrip() + "\n... [Amostra truncada] ..."
    return result


class ProcessadorPDF(ProcessadorArquivo):
    extensoes_suportadas = [".pdf"]

    @classmethod
    def processar(cls, caminho: str, base_dir: Path | None = None) -> str:
        from pypdf import PdfReader

        started_at = time.perf_counter()
        settings = get_settings()
        path = cls._validar_caminho(caminho, base_dir, enforce_size_limit=False)
        tamanho_mb = path.stat().st_size / (1024 * 1024)
        limite_normal_mb = settings.max_file_size_mb
        limite_pdf_mb = settings.file.max_pdf_size_mb
        pdf_grande = tamanho_mb > limite_normal_mb

        if tamanho_mb > limite_pdf_mb:
            raise SecurityError(
                "PDF muito grande para processamento local seguro: "
                f"{tamanho_mb:.1f} MB. Limite atual para PDFs: {limite_pdf_mb} MB."
            )

        cache_file = _pdf_cache_file(path, settings)
        cached_result = _load_pdf_cache(cache_file)
        if cached_result is not None:
            logger.info(
                "PDF reutilizado do cache: arquivo=%s tempo=%.2fs",
                path.name,
                time.perf_counter() - started_at,
            )
            return cached_result

        leitor = PdfReader(str(path))
        total_paginas = len(leitor.pages)
        configured_page_limit = max(1, int(settings.file.large_pdf_page_limit))
        sample_page_limit = min(configured_page_limit, MAX_REPRESENTATIVE_PAGES)
        page_indices = _representative_page_indices(total_paginas, sample_page_limit)

        metadados = leitor.metadata
        metadata_fields = []
        if metadados:
            for label, attribute in (
                ("Titulo", "title"),
                ("Autor", "author"),
                ("Assunto", "subject"),
                ("Criador", "creator"),
            ):
                value = getattr(metadados, attribute, None)
                if value:
                    metadata_fields.append(f"{label}: {value}")

        page_texts = _extract_with_pypdf(leitor, page_indices)
        extraction_method = "pypdf"
        minimum_chars = _minimum_useful_chars(total_paginas)

        if _useful_text_length(page_texts) < minimum_chars:
            fallback_texts = _extract_with_pdfplumber(path, page_indices)
            if _useful_text_length(fallback_texts) > _useful_text_length(page_texts):
                page_texts = fallback_texts
                extraction_method = "pdfplumber"

        if _useful_text_length(page_texts) < minimum_chars:
            ocr_page_limit = min(configured_page_limit, MAX_OCR_PAGES)
            ocr_page_indices = _representative_page_indices(total_paginas, ocr_page_limit)
            ocr_texts = _extract_with_rapidocr(path, ocr_page_indices)
            if _useful_text_length(ocr_texts) > _useful_text_length(page_texts):
                page_texts = ocr_texts
                page_indices = sorted(ocr_texts)
                extraction_method = "RapidOCR"

        useful_chars = _useful_text_length(page_texts)
        text_sample = _format_page_sample(
            page_texts,
            total_pages=total_paginas,
            char_limit=settings.doc_text_limit,
        )
        page_numbers = ", ".join(str(index + 1) for index in page_indices)

        result_lines = [
            f"PDF: {total_paginas} paginas | Tamanho: {tamanho_mb:.1f} MB",
            f"Metodo de extracao local: {extraction_method}",
        ]
        if metadata_fields:
            result_lines.append(" | ".join(metadata_fields))
        if page_numbers:
            result_lines.append(f"Paginas amostradas: {page_numbers}")
        if extraction_method == "RapidOCR" and len(page_indices) < total_paginas:
            result_lines.append(
                "Escopo: o OCR local analisou uma amostra representativa de "
                f"{len(page_indices)} das {total_paginas} paginas. O relatorio deve deixar "
                "claro que suas conclusoes se baseiam nessa amostra."
            )
        if pdf_grande:
            result_lines.append(
                "Aviso: PDF acima do limite normal de "
                f"{limite_normal_mb} MB. Foi feita uma amostra local segura e "
                "representativa do inicio, meio e fim do documento."
            )

        if useful_chars < minimum_chars:
            result_lines.extend(
                [
                    "",
                    f"{EXTRACTION_FAILURE_MARKER}: o PDF nao possui texto pesquisavel "
                    "suficiente para produzir um relatorio confiavel.",
                    "O arquivo pode ser digitalizado, composto por imagens ou ter uma "
                    "camada de texto danificada. O OCR local tambem nao recuperou conteudo "
                    "suficiente. Tente uma versao mais nitida ou pesquisavel do PDF.",
                    "Nao use memorias do usuario nem outras fontes como substituto do "
                    "conteudo deste documento.",
                ]
            )
            if text_sample:
                result_lines.extend(["", "Conteudo parcial detectado:", text_sample])
        else:
            result_lines.extend(["", text_sample])

        result = "\n".join(result_lines).strip()
        if useful_chars >= minimum_chars:
            _save_pdf_cache(cache_file, result)
        logger.info(
            "PDF processado: arquivo=%s metodo=%s paginas=%s caracteres=%s tempo=%.2fs",
            path.name,
            extraction_method,
            len(page_indices),
            useful_chars,
            time.perf_counter() - started_at,
        )
        return result
