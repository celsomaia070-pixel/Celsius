import os
import tempfile

from processors.report import GeradorRelatorio


class TestGeradorRelatorio:
    def test_gerar_markdown_simple(self):
        result = GeradorRelatorio.gerar_markdown("Test Title", "Hello world")
        assert "# Test Title" in result
        assert "Hello world" in result

    def test_gerar_markdown_with_metadata(self):
        result = GeradorRelatorio.gerar_markdown("Title", "Content", {"Author": "Test"})
        assert "**Author**" in result
        assert "Test" in result

    def test_exportar_pdf(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            output = f.name
        try:
            GeradorRelatorio.exportar_pdf("Test", "Hello", output)
            assert os.path.exists(output)
            assert os.path.getsize(output) > 0
        finally:
            if os.path.exists(output):
                os.unlink(output)

    def test_exportar_docx(self):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            output = f.name
        try:
            GeradorRelatorio.exportar_docx("Test", "Hello", output)
            assert os.path.exists(output)
            assert os.path.getsize(output) > 0
        finally:
            if os.path.exists(output):
                os.unlink(output)

    def test_exportar_pdf_with_metadata(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            output = f.name
        try:
            GeradorRelatorio.exportar_pdf("Title", "Content", output, {"Author": "Test"})
            assert os.path.exists(output)
        finally:
            if os.path.exists(output):
                os.unlink(output)

    def test_exportar_pdf_with_unicode(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            output = f.name
        try:
            GeradorRelatorio.exportar_pdf("Título", "Conteúdo com acentuação e emoji 😊", output)
            assert os.path.exists(output)
        finally:
            if os.path.exists(output):
                os.unlink(output)
