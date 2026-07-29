import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path

import pytest

from processors import PROCESSADORES, processar_arquivo
from processors.base import SecurityError
from processors.pdf import ProcessadorPDF


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
            pages = [FakePage("pagina um"), FakePage("pagina dois"), FakePage("pagina tres")]

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
        assert "Pagina 2/3" in result
        assert "Pagina 3/3" not in result
        assert "pagina um" in result

    def test_pdf_above_safe_limit_is_blocked(self, temp_dir):
        huge_pdf = temp_dir / "huge.pdf"
        with huge_pdf.open("wb") as file:
            file.seek((301 * 1024 * 1024) - 1)
            file.write(b"\0")

        with pytest.raises(SecurityError, match="PDF muito grande"):
            ProcessadorPDF.processar(str(huge_pdf), base_dir=temp_dir)
