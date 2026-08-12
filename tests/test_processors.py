import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from processors import PROCESSADORES, processar_arquivo
from processors.base import SecurityError
from processors.pdf import (
    EXTRACTION_FAILURE_MARKER,
    ProcessadorPDF,
    _representative_page_indices,
)


class TestFileProcessors:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_txt_file(self, temp_dir):
        test_file = temp_dir / "test.txt"
        test_file.write_text("Hello world\nThis is a test")

        result = processar_arquivo(str(test_file), base_dir=temp_dir)
        assert "Hello world" in result
        assert "This is a test" in result

    def test_python_file(self, temp_dir):
        test_file = temp_dir / "test.py"
        test_file.write_text("print('hello')\n# comment")

        result = processar_arquivo(str(test_file), base_dir=temp_dir)
        assert "print('hello')" in result

    def test_json_file(self, temp_dir):
        test_file = temp_dir / "test.json"
        test_file.write_text('{"key": "value", "num": 42}')

        result = processar_arquivo(str(test_file), base_dir=temp_dir)
        assert "key" in result
        assert "value" in result

    def test_unsupported_format(self, temp_dir):
        test_file = temp_dir / "test.xyz"
        test_file.write_text("content")

        result = processar_arquivo(str(test_file), base_dir=temp_dir)
        assert "nao suportado" in result.lower()

    def test_path_traversal_blocked(self, temp_dir):
        test_file = temp_dir / "test.txt"
        test_file.write_text("secret")

        # Try to access via path traversal
        result = processar_arquivo(str(test_file) + "/../../etc/passwd", base_dir=temp_dir)
        assert (
            "Path traversal" in result
            or "nao suportado" in result.lower()
            or "erro" in result.lower()
        )

    def test_processor_registry(self):
        assert ".pdf" in PROCESSADORES
        assert ".docx" in PROCESSADORES
        assert ".png" in PROCESSADORES
        assert ".mp3" in PROCESSADORES
        assert ".txt" in PROCESSADORES  # now handled by ProcessadorTexto
        assert ".py" in PROCESSADORES
        assert ".json" in PROCESSADORES

    def test_large_pdf_is_processed_as_safe_sample(self, temp_dir, monkeypatch):
        class FakePage:
            def __init__(self, text):
                self.text = text

            def extract_text(self):
                return self.text

        class FakeReader:
            metadata = None
            pages = [
                FakePage("pagina um " * 20),
                FakePage("pagina dois " * 20),
                FakePage("pagina tres " * 20),
            ]

        fake_pypdf = SimpleNamespace(PdfReader=lambda _path: FakeReader())
        monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)
        fake_settings = SimpleNamespace(
            max_file_size_mb=50,
            doc_text_limit=12000,
            file=SimpleNamespace(max_pdf_size_mb=300, large_pdf_page_limit=2),
        )
        monkeypatch.setattr("processors.pdf.get_settings", lambda: fake_settings)

        large_pdf = temp_dir / "large.pdf"
        with large_pdf.open("wb") as file:
            file.seek((51 * 1024 * 1024) - 1)
            file.write(b"\0")

        result = ProcessadorPDF.processar(str(large_pdf), base_dir=temp_dir)

        assert "Aviso: PDF acima do limite normal de 50 MB" in result
        assert "Pagina 1/3" in result
        assert "Pagina 2/3" not in result
        assert "Pagina 3/3" in result
        assert "pagina um" in result
        assert "inicio, meio e fim" in result

    def test_representative_pages_include_start_middle_and_end(self):
        indices = _representative_page_indices(total_pages=101, max_pages=5)

        assert indices == [0, 25, 50, 75, 100]

    def test_pdf_uses_pdfplumber_fallback(self, temp_dir, monkeypatch):
        class EmptyPage:
            def extract_text(self):
                return ""

        class FakeReader:
            metadata = None
            pages = [EmptyPage(), EmptyPage()]

        class PlumberPage:
            def __init__(self, text):
                self.text = text

            def extract_text(self, layout=False):
                assert layout is True
                return self.text

        class FakePlumberDocument:
            pages = [
                PlumberPage("conteudo recuperado da primeira pagina " * 5),
                PlumberPage("conteudo recuperado da segunda pagina " * 5),
            ]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        monkeypatch.setitem(
            sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda _path: FakeReader())
        )
        monkeypatch.setitem(
            sys.modules,
            "pdfplumber",
            SimpleNamespace(open=lambda _path: FakePlumberDocument()),
        )
        monkeypatch.setattr(
            "processors.pdf.get_settings",
            lambda: SimpleNamespace(
                max_file_size_mb=50,
                doc_text_limit=24000,
                file=SimpleNamespace(max_pdf_size_mb=300, large_pdf_page_limit=24),
            ),
        )
        pdf_file = temp_dir / "difficult.pdf"
        pdf_file.write_bytes(b"%PDF")

        result = ProcessadorPDF.processar(str(pdf_file), base_dir=temp_dir)

        assert "Metodo de extracao local: pdfplumber" in result
        assert "conteudo recuperado da primeira pagina" in result
        assert EXTRACTION_FAILURE_MARKER not in result

    def test_pdf_reuses_cached_extraction_until_file_changes(self, temp_dir, monkeypatch):
        reader_calls = 0

        class FakePage:
            def extract_text(self):
                return "conteudo confiavel para o relatorio " * 10

        class FakeReader:
            metadata = None
            pages = [FakePage()]

        def create_reader(_path):
            nonlocal reader_calls
            reader_calls += 1
            return FakeReader()

        monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=create_reader))
        monkeypatch.setattr(
            "processors.pdf.get_settings",
            lambda: SimpleNamespace(
                data_dir=temp_dir / "data",
                max_file_size_mb=50,
                doc_text_limit=12000,
                file=SimpleNamespace(max_pdf_size_mb=300, large_pdf_page_limit=24),
            ),
        )
        pdf_file = temp_dir / "cached.pdf"
        pdf_file.write_bytes(b"%PDF")

        first_result = ProcessadorPDF.processar(str(pdf_file), base_dir=temp_dir)
        second_result = ProcessadorPDF.processar(str(pdf_file), base_dir=temp_dir)

        assert second_result == first_result
        assert reader_calls == 1

        pdf_file.write_bytes(b"%PDF changed")
        ProcessadorPDF.processar(str(pdf_file), base_dir=temp_dir)

        assert reader_calls == 2

    def test_scanned_pdf_reports_need_for_ocr(self, temp_dir, monkeypatch):
        class EmptyPage:
            def extract_text(self, layout=False):
                return ""

        class FakeReader:
            metadata = None
            pages = [EmptyPage() for _ in range(40)]

        class FakePlumberDocument:
            pages = [EmptyPage() for _ in range(40)]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        monkeypatch.setitem(
            sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda _path: FakeReader())
        )
        monkeypatch.setitem(
            sys.modules,
            "pdfplumber",
            SimpleNamespace(open=lambda _path: FakePlumberDocument()),
        )
        monkeypatch.setitem(sys.modules, "rapidocr", None)
        monkeypatch.setitem(sys.modules, "pypdfium2", None)
        monkeypatch.setattr(
            "processors.pdf.get_settings",
            lambda: SimpleNamespace(
                max_file_size_mb=50,
                doc_text_limit=24000,
                file=SimpleNamespace(max_pdf_size_mb=300, large_pdf_page_limit=24),
            ),
        )
        pdf_file = temp_dir / "scanned.pdf"
        pdf_file.write_bytes(b"%PDF")

        result = ProcessadorPDF.processar(str(pdf_file), base_dir=temp_dir)

        assert EXTRACTION_FAILURE_MARKER in result
        assert "OCR local" in result
        assert "Nao use memorias do usuario" in result

    def test_scanned_pdf_uses_local_rapidocr(self, temp_dir, monkeypatch):
        class EmptyPage:
            def extract_text(self, layout=False):
                return ""

        class FakeReader:
            metadata = None
            pages = [EmptyPage() for _ in range(40)]

        class FakePlumberDocument:
            pages = [EmptyPage() for _ in range(40)]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class FakeBitmap:
            def to_numpy(self):
                return object()

            def close(self):
                pass

        class FakePdfiumPage:
            def render(self, scale):
                assert scale == 1.5
                return FakeBitmap()

            def close(self):
                pass

        class FakePdfiumDocument:
            def __init__(self, _path):
                self.pages = [FakePdfiumPage() for _ in range(40)]

            def __len__(self):
                return len(self.pages)

            def __getitem__(self, index):
                return self.pages[index]

            def close(self):
                pass

        class FakeRapidOCR:
            def __call__(self, _image):
                return SimpleNamespace(
                    txts=("texto recuperado localmente " * 8,),
                    scores=(0.98,),
                )

        monkeypatch.setitem(
            sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda _path: FakeReader())
        )
        monkeypatch.setitem(
            sys.modules,
            "pdfplumber",
            SimpleNamespace(open=lambda _path: FakePlumberDocument()),
        )
        monkeypatch.setitem(
            sys.modules,
            "pypdfium2",
            SimpleNamespace(PdfDocument=FakePdfiumDocument),
        )
        monkeypatch.setitem(
            sys.modules,
            "rapidocr",
            SimpleNamespace(RapidOCR=lambda **_kwargs: FakeRapidOCR()),
        )
        monkeypatch.setattr("processors.pdf._RAPID_OCR_ENGINE", None)
        monkeypatch.setattr(
            "processors.pdf.get_settings",
            lambda: SimpleNamespace(
                max_file_size_mb=50,
                doc_text_limit=12000,
                file=SimpleNamespace(max_pdf_size_mb=300, large_pdf_page_limit=24),
            ),
        )
        pdf_file = temp_dir / "scanned-with-ocr.pdf"
        pdf_file.write_bytes(b"%PDF")

        result = ProcessadorPDF.processar(str(pdf_file), base_dir=temp_dir)

        assert "Metodo de extracao local: RapidOCR" in result
        assert "texto recuperado localmente" in result
        assert "Pagina 1/40" in result
        assert "Pagina 40/40" in result
        assert "amostra representativa de 6 das 40 paginas" in result
        assert EXTRACTION_FAILURE_MARKER not in result

    def test_pdf_above_safe_limit_is_blocked(self, temp_dir):
        huge_pdf = temp_dir / "huge.pdf"
        with huge_pdf.open("wb") as file:
            file.seek((301 * 1024 * 1024) - 1)
            file.write(b"\0")

        with pytest.raises(SecurityError, match="PDF muito grande"):
            ProcessadorPDF.processar(str(huge_pdf), base_dir=temp_dir)
